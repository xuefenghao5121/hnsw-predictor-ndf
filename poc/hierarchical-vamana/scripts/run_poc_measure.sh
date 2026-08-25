#!/usr/bin/env bash
# run_poc_measure.sh — hierarchical-vamana POC sustained measurement
#
# Mirrors scripts/run_sustained.sh inner command (VER-001 sustained + VER-003 cgroup v2,
# cfg-sla-ef100 protocol: SIFT1M official 10K pool, 15 rounds × 1000, seed=42,
# REFINE_EF=100, cgroup memory.max=512MB, THREADS=16), but binds DATA_PREFIX /
# VEC_BLOCKS_PATH to the POC index under poc/hierarchical-vamana/output/.
#
# Why not `run_sustained.sh --config cfg-sla-ef100`? That path hard-overrides
# VEC_BLOCKS_PATH to output/sift1m_vecblocks_64k.bin (Trunk BFS order), which would
# mismatch the POC BFS order and corrupt fine-rerank distances. The POC must use its
# own vecblocks file (same vectors, POC BFS order).
#
# Usage: CGROUP_MB=512 THREADS=16 bash poc/hierarchical-vamana/scripts/run_poc_measure.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"

CGROUP_MB="${CGROUP_MB:-512}"
THREADS="${THREADS:-16}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
EF="${EF:-100}"
TAG="${TAG:-hv_vamana}"

DATA_PREFIX="poc/hierarchical-vamana/output/sift1m"
VEC_BLOCKS_PATH="${DATA_PREFIX}_vecblocks_64k.bin"
PQ_CODES_PATH="output/pqco_sift1m_M32_correct.bin"
POOL="${POOL:-data/sift_query_official10k.fvecs}"
GT="${GT:-data/sift_groundtruth_official.ivecs}"
BIN="${BIN:-build/benchmark_sustained}"
OUTDIR="${OUTDIR:-results/sustained}"

[ "$CGROUP_MB" -le 256 ] && FVC=64 || FVC=160

OUT="${OUTDIR}/${TAG}_${CGROUP_MB}mb_${THREADS}t_n${PER_ROUND}_r${ROUNDS}.log"
mkdir -p "$(dirname "$OUT")"

if [ ! -x "$BIN" ]; then echo "ERROR: $BIN not found" >&2; exit 1; fi

sudo -n true 2>/dev/null || echo "(sudo may be needed)" >&2

sudo bash -c "
set -uo pipefail
source $REPO/scripts/cgroup_utils.sh
cg_init sqb_${TAG}_${CGROUP_MB}_${THREADS}_${PER_ROUND} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches
cg_add_proc \$\$
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=$VEC_BLOCKS_PATH
export PQ_CODES_PATH=$PQ_CODES_PATH
export REFINE_EF=$EF EVICT_PAGE_CACHE=0 NUM_THREADS=$THREADS
export FLAT_VEC_MB=$FVC PAGE_MERGE_BG=1 L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
$BIN \
  ${DATA_PREFIX}_graph.bin ${DATA_PREFIX}_bfs.bin \
  ${DATA_PREFIX}_blocks_64k.bin ${DATA_PREFIX}_route_64k.bin \
  data/sift_base.fvecs $POOL $GT \
  10 $EF --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED --verbose
echo '--- cgroup accounting (CON-SLA-014) ---'
cg_stats_summary 2>/dev/null || true
cg_check_violations 2>/dev/null || true
" > "$OUT" 2>&1
RC=$?

echo "=== $TAG | 512MB | ${THREADS}T | N=$PER_ROUND | R=$ROUNDS | seed=$SEED ==="
grep -E "^QPS:|^Recall@|^Round 1 QPS|^Ramp-up:|^CSV_AGG|^Hit%|^RSS" "$OUT" || {
  echo "(no result lines; rc=$RC) tail:"; tail -20 "$OUT"
}
echo "--- log: $OUT"
exit $RC
