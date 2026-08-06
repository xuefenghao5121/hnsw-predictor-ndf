#!/usr/bin/env bash
# Sustained query benchmark runner
#
# Clauses: BEH-035 (multi-round sampling), API-019 (CLI),
#          CON-SLA-019 (no warmup of measured queries), CON-SLA-020 (baseline)
# Reference semantics: MODEL-SUSTAINED-001 (spec/models/sustained-query-measurement.md)
# Isolation: CON-SLA-014 protocol via API-016 (scripts/cgroup_utils.sh)
# Verification: VER-043
#
# Usage:
#   CGROUP_MB=512 THREADS=4 PER_ROUND=1000 ROUNDS=15 bash scripts/run_sustained.sh
#
# Env knobs:
#   CGROUP_MB   cgroup memory.max in MB          (default 512)
#   THREADS     NUM_THREADS                      (default 1)
#   PER_ROUND   queries sampled per round        (default 1000)
#   ROUNDS      number of statistics rounds      (default 15)
#   SEED        seed base (round i uses SEED+i)  (default 42)
#   POOL        query pool (standard set only)   (default official 10K)
#   GT          groundtruth (.ivecs or .bin)     (default official)
#   TAG         output log prefix                (default ver043)
#   OUTDIR      results directory                (default results/sustained)
#   EXTRA       extra `export ...` line(s), e.g. ADAPTIVE_EF=1
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CGROUP_MB="${CGROUP_MB:-512}"
THREADS="${THREADS:-1}"
POOL="${POOL:-data/sift_query_official10k.fvecs}"
GT="${GT:-data/sift_groundtruth_official.ivecs}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
TAG="${TAG:-ver043}"
OUTDIR="${OUTDIR:-results/sustained}"
EXTRA="${EXTRA:-}"

BIN=build/benchmark_sustained
if [ ! -x "$BIN" ]; then
  echo "ERROR: $BIN not found. Run: make $BIN" >&2
  exit 1
fi

# BEH-035: sampling pool MUST be a standard query set, MUST NOT be sampled from base.
case "$POOL" in
  *base*) echo "ERROR: pool looks base-derived ($POOL) — violates BEH-035" >&2; exit 1 ;;
esac

OUT="${OUTDIR}/${TAG}_${CGROUP_MB}mb_${THREADS}t_n${PER_ROUND}_r${ROUNDS}.log"
mkdir -p "$(dirname "$OUT")"

# CON-SLA-016/017/018 measurement convention for flat-vec cache sizing.
FVC=160
[ "$CGROUP_MB" -le 256 ] && FVC=64

sudo -n true 2>/dev/null || echo "(sudo password may be required for cgroup + drop_caches)" >&2

SUDO=(sudo)
if [ -n "${SUDO_STDIN_PASS:-}" ]; then
  SUDO=(sudo -S)
fi

"${SUDO[@]}" bash -c "
set -uo pipefail
source $REPO/scripts/cgroup_utils.sh
cg_init sqb_${TAG}_${CGROUP_MB}_${THREADS}_${PER_ROUND} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches                      # CON-SLA-014 step 1
cg_add_proc \$\$                     # CON-SLA-014 step 2
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 EVICT_PAGE_CACHE=0 NUM_THREADS=$THREADS
export FLAT_VEC_MB=$FVC PAGE_MERGE_BG=1 L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
$EXTRA
# CON-SLA-019: --warmup omitted => 0 => no warmup over measured queries.
./$BIN \
  output/sift1m_graph.bin output/sift1m_bfs.bin \
  output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
  data/sift_base.fvecs $POOL $GT \
  10 100 --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED --verbose
# CON-SLA-014 steps 4-5: cgroup accounting evidence
echo '--- cgroup accounting (CON-SLA-014) ---'
cg_stats_summary 2>/dev/null || true
cg_check_violations 2>/dev/null || true
" > "$OUT" 2>&1 < <(printf '%s\n' "${SUDO_STDIN_PASS:-}")
RC=$?

echo "=== $TAG | ${CGROUP_MB}MB | ${THREADS}T | N=$PER_ROUND | R=$ROUNDS | seed=$SEED ==="
grep -E "^QPS:|^Recall@|^Round 1 QPS|^Round .* QPS:|^Ramp-up:|^Cumulative|^CSV_AGG" "$OUT" || {
  echo "(no result lines; rc=$RC) tail:"; tail -15 "$OUT"
}
echo "--- log: $OUT"
exit $RC
