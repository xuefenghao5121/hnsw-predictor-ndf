#!/usr/bin/env bash
# run_gbdt_probe.sh — rp-optuna-tuner GBDT probe pipeline (per-artifact search-side
# calibration, [[BEH-RPT-002]]). Copy-then-edit of
# tools/constraint-aware-tuner/scripts/run_gbdt_probe.sh ([[BEH-018]]).
#
# Per-artifact GBDT calibration (DESIGN §2 S0): NO graph rebuild, NOT counted in
# RPT_BUDGET_REBUILDS. MUST NOT overwrite Trunk include/gbdt_model.h — the model is
# exported per-artifact to tools/rp-optuna-tuner/harness/gbdt_model_<id>.h and MUST NOT be
# reused on another graph ([[API-013]] / [[BEH-RPT-002]]). The sustained "on" leg runs
# tools/rp-optuna-tuner/harness-bin/benchmark_sustained_poc, which is (re)built against the
# retrained harness/gbdt_model_active.h — this is what "frozen include/gbdt_model.h
# on/off is forbidden" means in practice: every artifact gets its own model.
#
# Pipeline (DESIGN §2 P4 + skip gates #2/#3):
#   PROFILE official SIFT 10K + official GT  → analyze (P75 min_n list headroom)
#   → skip gate #2 (P75 stuck at list cap ≈ floor_ef → skip)
#   → LightGBM 100 trees / depth=4 → model header $RPT_GBDT_MODEL
#   → skip gate #3 (sim margin sweep; only sim >=95% advances)
#   → sustained on/off via scripts/run_sustained.sh + benchmark_sustained_poc
#
# Inputs (env):
#   RPT_ARTIFACT_ID   (required)  per-artifact model key
#   REFINE_EF         (required)  measured >=95% ef floor (operating point)
#   RPT_GBDT_MODEL    (required)  model export path (harness/gbdt_model_<id>.h)
#   RPT_BLOCK_SIZE / RPT_R0 / RPT_BEAM / RPT_ALPHA / RPT_PQ_M  (knob description)
#   CGROUP_MB / THREADS / RPT_GBDT_MARGINS / RPT_GBDT_SKIP_LIST_HEADROOM
#   RPT_PROFILE_LLSP_BIN  (default harness-bin/benchmark_llsp)
#
# Skip is a VALID outcome (exit 0 with a JSON result recording the skip reason).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"

ARTIFACT_ID="${RPT_ARTIFACT_ID:-}"
REFINE_EF="${REFINE_EF:-}"
RPT_GBDT_MODEL="${RPT_GBDT_MODEL:-}"
if [ -z "$ARTIFACT_ID" ] || [ -z "$REFINE_EF" ] || [ -z "$RPT_GBDT_MODEL" ]; then
    echo "ERROR: RPT_ARTIFACT_ID, REFINE_EF and RPT_GBDT_MODEL are required" >&2
    exit 2
fi

CGROUP_MB="${CGROUP_MB:-512}"
BS="${RPT_BLOCK_SIZE:-262144}"
R0="${RPT_R0:-40}"
BEAM="${RPT_BEAM:-48}"
ALPHA="${RPT_ALPHA:-1.07}"
PQ_M="${RPT_PQ_M:-32}"
MARGINS="${RPT_GBDT_MARGINS:-0.8,1.0,1.1,1.3}"
SKIP_LIST_HEADROOM="${RPT_GBDT_SKIP_LIST_HEADROOM:-1}"
PROFILE_LLSP_BIN="${RPT_PROFILE_LLSP_BIN:-tools/rp-optuna-tuner/harness-bin/benchmark_llsp}"
SUSTAINED_POC_BIN="tools/rp-optuna-tuner/harness-bin/benchmark_sustained_poc"
PROBE_RESULT="${PROBE_RESULT:-tools/rp-optuna-tuner/evidence/gbdt_probe_${ARTIFACT_ID}.json}"

case "$BS" in
  32768|65536|131072|262144) ;;
  *) echo "ERROR: RPT_BLOCK_SIZE=$BS invalid (closed ladder {32768,65536,131072,262144})" >&2; exit 2 ;;
esac
BS_K=$(( BS / 1024 ))
BLKSUF="${BS_K}k"

KNOBS_DESC="R0=${R0} / beam=${BEAM} / alpha=${ALPHA} / block=${BS} / pq_M=${PQ_M} / ef=${REFINE_EF} / pool=official10k"

DATA_PREFIX="${RPT_DATA_PREFIX:-output/sift1m}"
VEC_BLOCKS_PATH="${RPT_VEC_BLOCKS_PATH:-${DATA_PREFIX}_vecblocks_${BLKSUF}.bin}"
PQ_CODES_PATH="${RPT_PQ_CODES_PATH:-output/pqco_sift1m_M32_correct.bin}"
POOL="data/sift_query_official10k.fvecs"
GT="data/sift_groundtruth_official.ivecs"
MEASURE_SH="tools/rp-optuna-tuner/scripts/run_rp_sustained.sh"
LLSP_OUT="/tmp/rpt_${ARTIFACT_ID}_llsp.txt"
FEAT_CSV="/tmp/rpt_${ARTIFACT_ID}_features.csv"
LAB_CSV="/tmp/rpt_${ARTIFACT_ID}_labels.csv"
ANALYZE_REPORT="/tmp/rpt_${ARTIFACT_ID}_analyze.json"
TRAIN_REPORT="/tmp/rpt_${ARTIFACT_ID}_train.json"

[ "$CGROUP_MB" -le 256 ] && FVC=64 || FVC=160

mkdir -p "$(dirname "$PROBE_RESULT")"

write_result() {
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
         "$VEC_BLOCKS_PATH" "$PQ_CODES_PATH"; do
    [ -e "$f" ] || { echo "ERROR: missing artifact file $f (run build_pipeline.sh first)" >&2; exit 2; }
done

if [ -z "$PROFILE_LLSP_BIN" ] || [ ! -x "$PROFILE_LLSP_BIN" ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"no_profile_binary\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

sudo bash -c "
set -uo pipefail
source $REPO/scripts/cgroup_utils.sh
cg_init rpt_probe_${ARTIFACT_ID} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches
cg_add_proc \$\$
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
export VEC_BLOCKS_PATH='$VEC_BLOCKS_PATH'
export PQ_CODES_PATH='$PQ_CODES_PATH'
export REFINE_EF=$REFINE_EF FLAT_VEC_MB=$FVC
export NUM_THREADS=1 ADAPTIVE_EF=0 LEARNED_EF=0
export PROFILE_LLSP=1
$PROFILE_LLSP_BIN \
    $DATA_PREFIX\_graph.bin $DATA_PREFIX\_bfs.bin \
    $DATA_PREFIX\_blocks_${BLKSUF}.bin $DATA_PREFIX\_route_${BLKSUF}.bin \
    data/sift_base.fvecs $POOL $GT \
    10 $REFINE_EF 10000 \
    > /tmp/rpt_${ARTIFACT_ID}_stdout.txt 2> /tmp/rpt_${ARTIFACT_ID}_llsp_all.txt
rc=\$?
cg_cleanup 2>/dev/null || true
exit \$rc
"
PROFILE_RC=$?
# The profile binary dumps [LLSP] to stderr for BOTH passes (warm + timed) and then may
# crash at exit-time thread teardown (known DiskHNSW io_uring/GraphPrefetcher cleanup
# issue: "terminate called without an active exception"). The dump is complete before the
# crash, so we tolerate a non-zero rc IF the timed-pass [LLSP] dump is complete.
grep '^\[LLSP\]' /tmp/rpt_${ARTIFACT_ID}_llsp_all.txt | tail -10000 > "$LLSP_OUT"
LLSP_LINES=$(wc -l < "$LLSP_OUT" 2>/dev/null || echo 0)
if [ "$LLSP_LINES" -lt 10000 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"profile rc=$PROFILE_RC llsp_lines=$LLSP_LINES\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi
if [ "$PROFILE_RC" -ne 0 ]; then
    echo "WARNING: profile exit rc=$PROFILE_RC (exit-time teardown crash); [LLSP] dump complete ($LLSP_LINES lines), proceeding"
fi
echo "profile: $LLSP_LINES timed-pass [LLSP] lines -> $LLSP_OUT"

# ---------------------------------------------------------------------------
# Step 2: analyze (features + labels + min_n P75).
# ---------------------------------------------------------------------------
echo "=== [2/4] ANALYZE ${ARTIFACT_ID} (official-GT min_n labels) ==="
python3 tools/rp-optuna-tuner/gbdt/analyze.py \
    --llsp "$LLSP_OUT" --gt "$GT" \
    --features "$FEAT_CSV" --labels "$LAB_CSV" \
    --tag "$ARTIFACT_ID" --knobs "$KNOBS_DESC" \
    --report "$ANALYZE_REPORT"
ANALYZE_RC=$?
if [ "$ANALYZE_RC" -ne 0 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"analyze rc=$ANALYZE_RC\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

P75_MIN_N=$(python3 -c "import json;print(int(round(json.load(open('$ANALYZE_REPORT'))['min_n']['p75'])))" 2>/dev/null || echo -1)
if [ "$SKIP_LIST_HEADROOM" = "1" ] && [ "$P75_MIN_N" -ge "$REFINE_EF" ] 2>/dev/null; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"list_headroom\",\"p75_min_n\":$P75_MIN_N,\"list_cap\":$REFINE_EF,\"refine_ef\":$REFINE_EF}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: train (LightGBM 100t/d4 -> $RPT_GBDT_MODEL + sim margin sweep).
# ---------------------------------------------------------------------------
echo "=== [3/4] TRAIN ${ARTIFACT_ID} (LightGBM 100t/d4 -> $RPT_GBDT_MODEL) ==="
python3 tools/rp-optuna-tuner/gbdt/train.py \
    --features "$FEAT_CSV" --labels "$LAB_CSV" --llsp "$LLSP_OUT" --gt "$GT" \
    --model-export "$RPT_GBDT_MODEL" --artifact-id "$ARTIFACT_ID" \
    --knobs "$KNOBS_DESC" --r0 "$R0" --beam "$BEAM" --alpha "$ALPHA" \
    --block "$BS" --pq-m "$PQ_M" --floor-ef "$REFINE_EF" --pool official10k \
    --margins "$MARGINS" \
    --report "$TRAIN_REPORT"
TRAIN_RC=$?
if [ "$TRAIN_RC" -ne 0 ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"train rc=$TRAIN_RC\",\"refine_ef\":$REFINE_EF}"
    exit 0
fi

ADVANCING=$(python3 -c "import json;print(','.join(str(m) for m in json.load(open('$TRAIN_REPORT'))['advancing_margins']))" 2>/dev/null || echo "")
if [ -z "$ADVANCING" ]; then
    write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"skip\",\"reason\":\"sim_margin_none_ge_95\",\"refine_ef\":$REFINE_EF,\"model\":\"$RPT_GBDT_MODEL\"}"
    exit 0
fi
echo "advancing margins (sim >=95%): $ADVANCING"

# ---- (re)build benchmark_sustained_poc against the freshly retrained model ----
echo "=== [3.5/4] rebuild benchmark_sustained_poc against retrained model ==="
ln -sf "$(basename "$RPT_GBDT_MODEL")" tools/rp-optuna-tuner/harness/gbdt_model_active.h
# gbdt_model_active.h is a prerequisite of benchmark_sustained_poc in the harness Makefile;
# the fresh symlink mtime forces a rebuild.
make -C tools/rp-optuna-tuner/harness ../harness-bin/benchmark_sustained_poc
[ -x "$SUSTAINED_POC_BIN" ] || { write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"error\",\"reason\":\"sustained_poc build failed\",\"refine_ef\":$REFINE_EF}"; exit 0; }

# ---------------------------------------------------------------------------
# Step 4: sustained on/off (16T primary / 1T supplementary) for advancing margins.
# ---------------------------------------------------------------------------
echo "=== [4/4] SUSTAINED on/off ${ARTIFACT_ID} (16T + 1T) ==="
run_leg() {
  local threads="$1" learned="$2" margin="$3" tag="$4"
  echo "----- $tag | ${threads}T | LEARNED_EF=$learned margin=$margin -----"
  local extra="export LEARNED_EF=$learned"
  [ "$learned" = "1" ] && extra="$extra GBDT_MARGIN=$margin"
  CGROUP_MB=$CGROUP_MB THREADS=$threads \
    EF=$REFINE_EF BS=$BS EXTRA="$extra" \
    TAG="$tag" OUTDIR="tools/rp-optuna-tuner/evidence" \
    BIN="$SUSTAINED_POC_BIN" \
    DATA_PREFIX="$DATA_PREFIX" VEC_BLOCKS_PATH="$VEC_BLOCKS_PATH" PQ_CODES_PATH="$PQ_CODES_PATH" \
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

write_result "{\"schema\":\"ndf-poc-gbdt-probe/v1\",\"artifact_id\":\"$ARTIFACT_ID\",\"decision\":\"measured\",\"refine_ef\":$REFINE_EF,\"model\":\"$RPT_GBDT_MODEL\",\"advancing_margins\":\"$ADVANCING\"}"
exit 0
