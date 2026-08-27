#!/usr/bin/env bash
# run_gbdt_probe.sh — CAT GBDT probe pipeline (per-artifact search-side calibration).
#
# Promoted from poc/constraint-aware-tuning → tools/constraint-aware-tuner/.
# Per-artifact GBDT calibration ([[BEH-028]] P4 / [[BEH-010]] optional axis): NO graph
# rebuild, NOT counted in CAT_BUDGET_REBUILDS. MUST NOT overwrite Trunk
# include/gbdt_model.h — the model is exported per-artifact to
# tools/constraint-aware-tuner/harness/gbdt_model_<id>.h and MUST NOT be reused on
# another graph ([[API-013]] / DESIGN §2 P4).
#
# Pipeline (DESIGN §2 P4 + skip gates #2/#3, R6+R8 calibrated):
#   PROFILE official SIFT 10K + official GT  → analyze (P75 min_n list headroom)
#   → skip gate #2 (P75 stuck at list cap ≈ floor_ef → skip)
#   → LightGBM 100 trees / depth=4 → model header $CAT_GBDT_MODEL
#   → skip gate #3 (sim margin sweep; only sim >=95% advances)
#   → sustained on/off via scripts/run_sustained.sh (Trunk benchmark_sustained)
#
# NOTE ([[BEH-028]]): the PROFILE step requires a PROFILE_LLSP-capable binary. Trunk
# `benchmark_sustained` does NOT emit `[LLSP]` feature dumps; set PROFILE_LLSP_BIN to a
# profiling-capable binary to run the full profile→analyze→train path. If unset, the
# probe records "skip: no profile binary" and exits 0 (skip is a valid outcome — the
# winner operating point skips the probe at gate #1 anyway, leftover +0.57pp).
#
# Inputs (env):
#   CAT_ARTIFACT_ID   (required)  per-artifact model key (e.g. r0_40_beam_64_...)
#   REFINE_EF         (required)  measured >=95% ef floor (operating point)
#   CAT_GBDT_MODEL    (required)  model export path (tools/constraint-aware-tuner/
#                                 harness/gbdt_model_<id>.h)
#   CAT_BLOCK_SIZE    block size (default 262144)
#   CAT_R0/CAT_BEAM/CAT_ALPHA/CAT_PQ_M  (knob description, default to high-recall leg)
#   CGROUP_MB         cgroup budget (default 512)
#   CAT_GBDT_MARGINS  comma sim sweep (default 0.8,1.0,1.1,1.3)
#   CAT_GBDT_SKIP_LIST_HEADROOM  list-cap gate on/off (default 1)
#   PROFILE_LLSP_BIN  optional PROFILE_LLSP-capable binary (empty → skip profile)
#   PROBE_RESULT      JSON result path (default tools/.../results/gbdt_probe_<id>.json)
#
# Skip is a VALID outcome (not an error): the script exits 0 with a JSON result
# recording the skip reason. The probe result is consumed by traverse.py probe_gbdt().
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"

ARTIFACT_ID="${CAT_ARTIFACT_ID:-}"
REFINE_EF="${REFINE_EF:-}"
CAT_GBDT_MODEL="${CAT_GBDT_MODEL:-}"
if [ -z "$ARTIFACT_ID" ] || [ -z "$REFINE_EF" ] || [ -z "$CAT_GBDT_MODEL" ]; then
    echo "ERROR: CAT_ARTIFACT_ID, REFINE_EF and CAT_GBDT_MODEL are required" >&2
    exit 2
fi

CGROUP_MB="${CGROUP_MB:-512}"
BS="${CAT_BLOCK_SIZE:-262144}"
R0="${CAT_R0:-40}"
BEAM="${CAT_BEAM:-64}"
ALPHA="${CAT_ALPHA:-1.2}"
PQ_M="${CAT_PQ_M:-32}"
MARGINS="${CAT_GBDT_MARGINS:-0.8,1.0,1.1,1.3}"
SKIP_LIST_HEADROOM="${CAT_GBDT_SKIP_LIST_HEADROOM:-1}"
PROFILE_LLSP_BIN="${PROFILE_LLSP_BIN:-}"
PROBE_RESULT="${PROBE_RESULT:-tools/constraint-aware-tuner/results/gbdt_probe_${ARTIFACT_ID}.json}"

case "$BS" in
  32768|65536|131072|262144) ;;
  *) echo "ERROR: CAT_BLOCK_SIZE=$BS invalid (closed ladder {32768,65536,131072,262144})" >&2; exit 2 ;;
esac
BS_K=$(( BS / 1024 ))
BLKSUF="${BS_K}k"

KNOBS_DESC="R0=${R0} / beam=${BEAM} / alpha=${ALPHA} / block=${BS} / pq_M=${PQ_M} / ef=${REFINE_EF} / pool=official10k"

DATA_PREFIX="output/sift1m"
POOL="data/sift_query_official10k.fvecs"
GT="data/sift_groundtruth_official.ivecs"
SUSTAINED_BIN="build/benchmark_sustained"
MEASURE_SH="scripts/run_sustained.sh"
LLSP_OUT="/tmp/cat_${ARTIFACT_ID}_llsp.txt"
FEAT_CSV="/tmp/cat_${ARTIFACT_ID}_features.csv"
LAB_CSV="/tmp/cat_${ARTIFACT_ID}_labels.csv"
ANALYZE_REPORT="/tmp/cat_${ARTIFACT_ID}_analyze.json"
TRAIN_REPORT="/tmp/cat_${ARTIFACT_ID}_train.json"

[ "$CGROUP_MB" -le 256 ] && FVC=64 || FVC=160

mkdir -p "$(dirname "$PROBE_RESULT")"

write_result() {
    # $1 = JSON string (single line)
    echo "$1" > "$PROBE_RESULT"
    echo "=== GBDT probe result -> $PROBE_RESULT ==="
    echo "$1"
}

# ---------------------------------------------------------------------------
# Step 1: PROFILE (official 10K pool, NUM_THREADS=1, PROFILE_LLSP=1, floor ef).
# ---------------------------------------------------------------------------
echo "=== [1/4] PROFILE ${ARTIFACT_ID} @ ef=${REFINE_EF} (official 10K, 1T, ${CGROUP_MB}MB) ==="
for f in "$DATA_PREFIX"_graph.bin "$DATA_PREFIX"_bfs.bin \
         "$DATA_PREFIX"_blocks_${BLKSUF}.bin "$DATA_PREFIX"_route_${BLKSUF}.bin \
         "$DATA_PREFIX"_vecblocks_${BLKSUF}.bin \
         output/pqco_sift1m_M32_correct.bin; do
    [ -e "$f" ] || { echo "ERROR: missing artifact file $f (run build_pipeline.sh first)" >&2; exit 2; }
done

if [ -z "$PROFILE_LLSP_BIN" ] || [ ! -x "$PROFILE_LLSP_BIN" ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"no_profile_binary\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

sudo bash -c "
set -uo pipefail
source $REPO/scripts/cgroup_utils.sh
cg_init cat_probe_${ARTIFACT_ID} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches
cg_add_proc \$\$
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
export VEC_BLOCKS_PATH=$DATA_PREFIX\_vecblocks_${BLKSUF}.bin
export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=$REFINE_EF FLAT_VEC_MB=$FVC
export NUM_THREADS=1 ADAPTIVE_EF=0 LEARNED_EF=0
export PROFILE_LLSP=1
$PROFILE_LLSP_BIN \
    $DATA_PREFIX\_graph.bin $DATA_PREFIX\_bfs.bin \
    $DATA_PREFIX\_blocks_${BLKSUF}.bin $DATA_PREFIX\_route_${BLKSUF}.bin \
    data/sift_base.fvecs $POOL $GT \
    10 $REFINE_EF 10000 \
    > /tmp/cat_${ARTIFACT_ID}_stdout.txt 2> /tmp/cat_${ARTIFACT_ID}_llsp_all.txt
rc=\$?
cg_cleanup 2>/dev/null || true
exit \$rc
"
PROFILE_RC=$?
if [ "$PROFILE_RC" -ne 0 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"profile rc=$PROFILE_RC\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi
grep '^\[LLSP\]' /tmp/cat_${ARTIFACT_ID}_llsp_all.txt | tail -10000 > "$LLSP_OUT"
LLSP_LINES=$(wc -l < "$LLSP_OUT" 2>/dev/null || echo 0)
echo "profile: $LLSP_LINES timed-pass [LLSP] lines -> $LLSP_OUT"

# ---------------------------------------------------------------------------
# Step 2: analyze (features + labels + min_n P75).
# ---------------------------------------------------------------------------
echo "=== [2/4] ANALYZE ${ARTIFACT_ID} (official-GT min_n labels) ==="
python3 tools/constraint-aware-tuner/gbdt/analyze.py \
    --llsp "$LLSP_OUT" --gt "$GT" \
    --features "$FEAT_CSV" --labels "$LAB_CSV" \
    --tag "$ARTIFACT_ID" --knobs "$KNOBS_DESC" \
    --report "$ANALYZE_REPORT"
ANALYZE_RC=$?
if [ "$ANALYZE_RC" -ne 0 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"analyze rc=$ANALYZE_RC\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

# skip gate #2: list headroom — P75 min_n stuck at list cap (~= floor_ef) -> skip.
P75_MIN_N=$(python3 -c "import json;print(int(round(json.load(open('$ANALYZE_REPORT'))['min_n']['p75'])))" 2>/dev/null || echo -1)
if [ "$SKIP_LIST_HEADROOM" = "1" ] && [ "$P75_MIN_N" -ge "$REFINE_EF" ] 2>/dev/null; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"list_headroom\",\"p75_min_n\":$P75_MIN_N,\"list_cap\":$REFINE_EF,\"refine_ef\":$REFINE_EF}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: train (LightGBM 100t/d4 -> $CAT_GBDT_MODEL + sim margin sweep).
# ---------------------------------------------------------------------------
echo "=== [3/4] TRAIN ${ARTIFACT_ID} (LightGBM 100t/d4 -> $CAT_GBDT_MODEL) ==="
python3 tools/constraint-aware-tuner/gbdt/train.py \
    --features "$FEAT_CSV" --labels "$LAB_CSV" --llsp "$LLSP_OUT" --gt "$GT" \
    --model-export "$CAT_GBDT_MODEL" --artifact-id "$ARTIFACT_ID" \
    --knobs "$KNOBS_DESC" --r0 "$R0" --beam "$BEAM" --alpha "$ALPHA" \
    --block "$BS" --pq-m "$PQ_M" --floor-ef "$REFINE_EF" --pool official10k \
    --margins "$MARGINS" \
    --report "$TRAIN_REPORT"
TRAIN_RC=$?
if [ "$TRAIN_RC" -ne 0 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"train rc=$TRAIN_RC\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

# skip gate #3: sim margin sweep — only sim >=95% advances to sustained.
ADVANCING=$(python3 -c "import json;print(','.join(str(m) for m in json.load(open('$TRAIN_REPORT'))['advancing_margins']))" 2>/dev/null || echo "")
if [ -z "$ADVANCING" ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"sim_margin_none_ge_95\",\"refine_ef\":$REFINE_EF,\"model\":\"$CAT_GBDT_MODEL\"}"
    exit 0
fi
echo "advancing margins (sim >=95%): $ADVANCING"

# ---------------------------------------------------------------------------
# Step 4: sustained on/off (16T primary / 1T supplementary) for advancing margins.
# ---------------------------------------------------------------------------
echo "=== [4/4] SUSTAINED on/off ${ARTIFACT_ID} (16T + 1T) ==="
# NOTE: LEARNED_EF=1 with a per-artifact model requires benchmark_sustained built with
# the per-artifact header (MUST NOT overwrite Trunk include/gbdt_model.h). The off-leg
# (LEARNED_EF=0) is the search default and measures against Trunk as-is.
run_leg() {
  local threads="$1" learned="$2" margin="$3" tag="$4"
  echo "----- $tag | ${threads}T | LEARNED_EF=$learned margin=$margin -----"
  CGROUP_MB=$CGROUP_MB THREADS=$threads \
    EF=$REFINE_EF REFINE_EF=$REFINE_EF CAT_BLOCK_SIZE=$BS BS=$BS \
    LEARNED_EF=$learned GBDT_MARGIN="$margin" \
    TAG="$tag" \
    bash "$MEASURE_SH" || true
  echo ""
}

run_leg 16 0 off "${ARTIFACT_ID}_off"
for margin in $(echo "$ADVANCING" | tr ',' ' '); do
  run_leg 16 1 "$margin" "${ARTIFACT_ID}_on_m${margin}"
done
run_leg 1 0 off "${ARTIFACT_ID}_off"
for margin in $(echo "$ADVANCING" | tr ',' ' '); do
  run_leg 1 1 "$margin" "${ARTIFACT_ID}_on_m${margin}"
done

write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"measured\",\"refine_ef\":$REFINE_EF,\"model\":\"$CAT_GBDT_MODEL\",\"advancing_margins\":\"$ADVANCING\"}"
exit 0
