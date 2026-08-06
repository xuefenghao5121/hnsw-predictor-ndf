#!/usr/bin/env bash
# R2: cache saturation curve — poc/sustained-query-benchmark
# Clauses: BEH-035, API-019 | Isolation: CON-SLA-014 protocol via API-016
set -uo pipefail

REPO=/home/huawei/hnsw-predictor-ndf
cd "$REPO"

CGROUP_MB="${CGROUP_MB:-512}"
THREADS="${THREADS:-1}"
POOL="${POOL:-data/sift_query_official10k.fvecs}"
GT="${GT:-data/sift_groundtruth_official.ivecs}"
ROUNDS="${ROUNDS:-50}"
PER_ROUND="${PER_ROUND:-200}"
SEED="${SEED:-42}"
TAG="${TAG:-r2}"
EXTRA="${EXTRA:-}"

OUT="poc/sustained-query-benchmark/results/${TAG}_${CGROUP_MB}mb_${THREADS}t_n${PER_ROUND}_r${ROUNDS}.log"
mkdir -p "$(dirname "$OUT")"

FVC=160
[ "$CGROUP_MB" -le 256 ] && FVC=64

echo "huawei" | sudo -S bash -c "
source $REPO/scripts/cgroup_utils.sh
cg_init sqb_${TAG}_${CGROUP_MB}_${THREADS}_${PER_ROUND} $CGROUP_MB
cg_create
cg_set_limit $CGROUP_MB
cg_drop_caches
cg_add_proc \$\$
cd $REPO
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 EVICT_PAGE_CACHE=0 NUM_THREADS=$THREADS
export FLAT_VEC_MB=$FVC PAGE_MERGE_BG=1 L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
$EXTRA
./poc/sustained-query-benchmark/benchmark_sustained \
  output/sift1m_graph.bin output/sift1m_bfs.bin \
  output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
  data/sift_base.fvecs $POOL $GT \
  10 100 --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED --verbose
" > "$OUT" 2>&1

echo "=== $TAG | ${CGROUP_MB}MB | ${THREADS}T | N=$PER_ROUND | R=$ROUNDS ==="
grep -E "^Round|^QPS:|^Recall@|^Cumulative|^Decay:|^Round 1 QPS|^Round .* QPS:" "$OUT" | tail -8
echo "--- log: $OUT"
