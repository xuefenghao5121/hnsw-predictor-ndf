#!/usr/bin/env bash
# 严格 cgroup 隔离 sustained benchmark for pipeline-param-retuning POC
#
# 协议: CON-SLA-014 (cgroup 隔离) + CON-SLA-019 (禁预热) + CON-SLA-020 (sustained 基线)
#
# Usage: CGROUP_MB=256 bash poc/pipeline-param-retuning/run_strict.sh
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

CGROUP_MB="${CGROUP_MB:-256}"
THREADS="${THREADS:-1}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
EXTRA_ENV="${EXTRA_ENV:-}"
PASS="${PASS:-huawei}"

POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/pipeline-param-retuning/results
mkdir -p "$RESULTS"

# FVC by cgroup size
FVC=160
[ "$CGROUP_MB" -le 256 ] && FVC=64

run_strict() {
    local TAG=$1
    local GRAPH=$2
    local BFS=$3
    local BLOCKS=$4
    local ROUTE=$5
    local VECBLOCKS=$6
    local EF=$7

    local OUT="${RESULTS}/${TAG}.log"
    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init pp_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches
        cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf

        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ
        export REFINE_EF=$EF
        export FLAT_VEC_MB=$FVC
        export NUM_THREADS=$THREADS
        export WILLNEED_BG=1 VL_POOL_THREADS=14
        export ADAPTIVE_EF=0
        $EXTRA_ENV

        ./build/benchmark_sustained \
            $GRAPH $BFS $BLOCKS $ROUTE \
            data/sift_base.fvecs $POOL $GT \
            10 $EF \
            --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED \
            > $OUT 2>&1

        cg_stats >> $OUT 2>&1
        cg_cleanup
    " 2>/dev/null

    LINE=$(grep "CSV_AGG" "$OUT" | tail -1)
    RECALL=$(echo "$LINE" | cut -d, -f6)
    AGG=$(echo "$LINE" | cut -d, -f5)
    STEADY=$(echo "$LINE" | cut -d, -f8)
    RSS=$(grep "RSS:" "$OUT" | tail -1 | awk '{print $2}')
    PEAK=$(grep "peak" "$OUT" | tail -1 | awk '{print $NF}' 2>/dev/null || echo "?")
    FAIL=$(grep -i "failcnt\|violation\|OOM" "$OUT" | tail -1 || echo "0")
    echo "agg=${AGG} steady=${STEADY} recall=${RECALL} rss=${RSS} peak=${PEAK} ${FAIL}"
}

M16=output/sift1m_m16
M24=output/sift1m_m24

echo "=== Strict cgroup ${CGROUP_MB}MB, ${THREADS}T, EF=60 ==="
echo ""

# M=16 baseline
run_strict "m16_ef60" \
    $M16/sift1m_m16_graph.bin $M16/sift1m_m16_bfs.bin \
    $M16/sift1m_m16_blocks_64k.bin $M16/sift1m_m16_route_64k.bin \
    $M16/sift1m_m16_vecblocks_64k.bin 60

run_strict "m16_ef80" \
    $M16/sift1m_m16_graph.bin $M16/sift1m_m16_bfs.bin \
    $M16/sift1m_m16_blocks_64k.bin $M16/sift1m_m16_route_64k.bin \
    $M16/sift1m_m16_vecblocks_64k.bin 80

run_strict "m16_ef100" \
    $M16/sift1m_m16_graph.bin $M16/sift1m_m16_bfs.bin \
    $M16/sift1m_m16_blocks_64k.bin $M16/sift1m_m16_route_64k.bin \
    $M16/sift1m_m16_vecblocks_64k.bin 100

# M=24
run_strict "m24_ef60" \
    $M24/sift1m_m24_graph.bin $M24/sift1m_m24_bfs.bin \
    $M24/sift1m_m24_blocks_64k.bin $M24/sift1m_m24_route_64k.bin \
    $M24/sift1m_m24_vecblocks_64k.bin 60

run_strict "m24_ef80" \
    $M24/sift1m_m24_graph.bin $M24/sift1m_m24_bfs.bin \
    $M24/sift1m_m24_blocks_64k.bin $M24/sift1m_m24_route_64k.bin \
    $M24/sift1m_m24_vecblocks_64k.bin 80

echo ""
echo "=== Summary (${CGROUP_MB}MB cgroup, ${THREADS}T, strict) ==="
printf "%-12s %-4s %-10s %-10s %-8s %-6s\n" "Config" "EF" "Agg_QPS" "Steady" "Recall" "RSS"
echo "------------------------------------------------"
for TAG in m16_ef60 m16_ef80 m16_ef100 m24_ef60 m24_ef80; do
    FILE="${RESULTS}/${TAG}.log"
    if [ -f "$FILE" ]; then
        LINE=$(grep "CSV_AGG" "$FILE" | tail -1)
        AGG=$(echo "$LINE" | cut -d, -f5)
        RECALL=$(echo "$LINE" | cut -d, -f6)
        STEADY=$(echo "$LINE" | cut -d, -f8)
        RSS=$(grep "RSS:" "$FILE" | tail -1 | awk '{print $2}')
        printf "%-12s %-4s %-10s %-10s %-8s %-6s\n" "$TAG" "" "$AGG" "$STEADY" "$RECALL" "$RSS"
    fi
done
