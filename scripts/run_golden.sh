#!/bin/bash
# run_golden.sh — 跑性能金标测试 (4 配置 × 3 轮)
# 用法: sudo bash scripts/run_golden.sh
# 输出: /tmp/golden/*.log + 汇总到 stdout

set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/cgroup_utils.sh

BINDIR=${1:-build}
MINDIR=/tmp/golden
mkdir -p $MINDIR

run_one() {
    local CG=$1; local NT=$2; local TAG=$3; local RUN=$4
    cg_init gold_${TAG}_r${RUN} $CG; cg_create; cg_set_limit $CG; cg_drop_caches; cg_add_proc $$
    cd /home/huawei/hnsw-predictor-ndf
    export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
    export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
    export VEC_BLOCKS_PATH=output/sift1m_m16/sift1m_m16_vecblocks_64k.bin
    export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
    export REFINE_EF=100 FLAT_VEC_MB=64 NUM_THREADS=$NT ADAPTIVE_EF=0
    $BINDIR/benchmark_sustained \
        output/sift1m_m16/sift1m_m16_graph.bin output/sift1m_m16/sift1m_m16_bfs.bin \
        output/sift1m_m16/sift1m_m16_blocks_64k.bin output/sift1m_m16/sift1m_m16_route_64k.bin \
        data/sift_base.fvecs data/sift_query_official10k.fvecs data/sift_groundtruth_official.ivecs \
        10 100 --rounds 15 --per-round 1000 --seed 42 \
        > $MINDIR/${TAG}_r${RUN}.log 2>&1
    cg_cleanup
    echo -n "$TAG R$RUN: "
    grep "CSV_AGG" $MINDIR/${TAG}_r${RUN}.log | tail -1 | awk -F, '{printf "agg=%-8s steady=%-8s recall=%s%%\n",$5,$8,$6}'
}

echo "=== Golden Baseline — Trunk $(git rev-parse --short HEAD) ==="
for RUN in 1 2 3; do
    run_one 256 1  256_1t  $RUN
    run_one 256 16 256_16t $RUN
    run_one 512 1  512_1t  $RUN
    run_one 512 16 512_16t $RUN
done
echo "=== DONE ==="
