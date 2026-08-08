#!/usr/bin/env bash
# R6.1: GBDT profiling - 生成训练数据 (CON-SLA-020 金标配置)
#
# 用 benchmark_llsp + PROFILE_LLSP=1 在 256MB cgroup 下对官方 10K query 池做 profiling
# 输出: /tmp/llsp_r6_{m16_ef65,m24_ef60}.txt
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
LLSP_BIN=poc/gbdt-learned-pruning/benchmark_llsp

run_profiling() {
    local TAG=$1
    local GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
    local EF=$7
    local OUT="/tmp/llsp_r6_${TAG}.txt"

    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init prof_${TAG} 256
        cg_create
        cg_set_limit 256
        cg_drop_caches
        cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf

        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ32
        export REFINE_EF=$EF FLAT_VEC_MB=64
        export NUM_THREADS=1 ADAPTIVE_EF=0
        export PROFILE_LLSP=1

        $LLSP_BIN \
            $GRAPH $BFS $BLOCKS $ROUTE \
            data/sift_base.fvecs $POOL $GT \
            10 $EF 10000 \
            > /dev/null 2> $OUT

        cg_cleanup
    " 2>/dev/null

    LINES=$(wc -l < "$OUT" 2>/dev/null || echo 0)
    echo "profiling done, $LINES LLSP lines"
}

M16=output/sift1m_m16
M24=output/sift1m_m24

echo "============================================"
echo "  R6.1: GBDT Profiling (256MB, CON-SLA-020)"
echo "============================================"

# M=16 EF=65
run_profiling "m16_ef65" \
    $M16/sift1m_m16_graph.bin $M16/sift1m_m16_bfs.bin \
    $M16/sift1m_m16_blocks_64k.bin $M16/sift1m_m16_route_64k.bin \
    $M16/sift1m_m16_vecblocks_64k.bin 65

# M=24 EF=60
run_profiling "m24_ef60" \
    $M24/sift1m_m24_graph.bin $M24/sift1m_m24_bfs.bin \
    $M24/sift1m_m24_blocks_64k.bin $M24/sift1m_m24_route_64k.bin \
    $M24/sift1m_m24_vecblocks_64k.bin 60

echo ""
echo "=== Profiling Summary ==="
for TAG in m16_ef65 m24_ef60; do
    OUT="/tmp/llsp_r6_${TAG}.txt"
    if [ -f "$OUT" ]; then
        LINES=$(wc -l < "$OUT")
        FIRST=$(head -1 "$OUT" | cut -c1-80)
        echo "$TAG: $LINES lines, first: $FIRST..."
    else
        echo "$TAG: MISSING"
    fi
done
