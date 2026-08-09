#!/usr/bin/env bash
# framework-driven-optimization: 决策树系统性扫描脚本
# 按 DEC-088 决策树顺序执行，自动校验 cgroup 有效性
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB=256
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/framework-driven-optimization/results
mkdir -p "$RESULTS"

# cgroup 有效性校验
check_cgroup() {
    local FILE=$1
    local MAJFAULT=$(grep "pgmajfault:" "$FILE" | tail -1 | awk '{print $2}')
    local FILEBYTES=$(grep "file_bytes:" "$FILE" | tail -1 | awk '{print $2}')
    local VIOLATIONS=$(grep "violations:" "$FILE" | tail -1 | awk '{print $2}')
    
    if [ "$MAJFAULT" = "0" ] || [ -z "$MAJFAULT" ]; then
        echo "  ⚠️ INVALID: pgmajfault=0 (cgroup leakage!)"
        return 1
    fi
    echo "  ✅ cgroup valid: pgmajfault=$MAJFAULT file=${FILEBYTES}"
    return 0
}

# 核心运行函数
run_bench() {
    local TAG=$1 GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
    local EF=$7 T=${8:-1} EXTRA="${9:-}"
    local OUT="${RESULTS}/${TAG}.log"
    
    echo -n "${TAG}: "
    
    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init fdo_${TAG} ${CGROUP_MB}
        cg_create; cg_set_limit ${CGROUP_MB}; cg_drop_caches; cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf
        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        export VEC_BLOCKS_PATH=${VECBLOCKS}
        export PQ_CODES_PATH=${PQ32}
        export REFINE_EF=${EF} FLAT_VEC_MB=64 NUM_THREADS=${T} ADAPTIVE_EF=0
        export ${EXTRA}
        ./build/benchmark_sustained \
            ${GRAPH} ${BFS} ${BLOCKS} ${ROUTE} \
            data/sift_base.fvecs ${POOL} ${GT} \
            10 ${EF} \
            --rounds 15 --per-round 1000 --seed 42 \
            > ${OUT} 2>&1
        cg_stats >> ${OUT} 2>&1
        cg_cleanup
    " 2>/dev/null
    
    # Extract results
    local LINE=$(grep "^CSV_AGG" "$OUT" | tail -1)
    local AGG=$(echo "$LINE" | awk -F, '{print $4}')
    local STEADY=$(echo "$LINE" | awk -F, '{print $8}')
    local RECALL=$(echo "$LINE" | awk -F, '{print $5}')
    local RSS=$(grep "^RSS:" "$OUT" | tail -1 | awk '{print $2}')
    
    echo "agg=${AGG:-FAIL} steady=${STEADY:-?} recall=${RECALL:-?}% rss=${RSS:-?}MB"
    check_cgroup "$OUT"
}

# ========== Data paths ==========
M16_O=output/sift1m_m16
M16_G=${M16_O}/sift1m_m16_graph.bin
M16_BFS=${M16_O}/sift1m_m16_bfs.bin
M16_BLK=${M16_O}/sift1m_m16_blocks_64k.bin
M16_RTE=${M16_O}/sift1m_m16_route_64k.bin
M16_VEC=${M16_O}/sift1m_m16_vecblocks_64k.bin

M24_O=output/sift1m_m24
M24_G=${M24_O}/sift1m_m24_graph.bin 2>/dev/null
M24_BFS=${M24_O}/sift1m_m24_bfs.bin 2>/dev/null
M24_BLK=${M24_O}/sift1m_m24_blocks_64k.bin 2>/dev/null
M24_RTE=${M24_O}/sift1m_m24_route_64k.bin 2>/dev/null
M24_VEC=${M24_O}/sift1m_m24_vecblocks_64k.bin 2>/dev/null

# Check M=24 data exists
if [ ! -f "$M24_G" ]; then
    echo "M=24 data not found, using M=16 only"
    HAS_M24=0
else
    HAS_M24=1
fi

# ========== R0: Baseline ==========
echo "========================================="
echo "R0: Baseline (M=16 EF=100, strict cgroup)"
echo "========================================="
run_bench "r0_m16_ef100" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 100 1

# ========== R1: M_graph scan ==========
echo ""
echo "========================================="
echo "R1: M_graph × EF scan (decision tree step 2)"
echo "========================================="
for EF in 60 80 100; do
    run_bench "r1_m16_ef${EF}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" $EF 1
done
if [ "$HAS_M24" = "1" ]; then
    for EF in 60 80 100; do
        run_bench "r1_m24_ef${EF}" "$M24_G" "$M24_BFS" "$M24_BLK" "$M24_RTE" "$M24_VEC" $EF 1
    done
fi

# ========== R2: EF fine scan ==========
echo ""
echo "========================================="
echo "R2: EF fine scan (decision tree step 3) on M=16"
echo "========================================="
for EF in 50 55 60 65 70 75 90; do
    run_bench "r2_m16_ef${EF}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" $EF 1
done

# ========== R3: ADAPTIVE evaluation ==========
echo ""
echo "========================================="
echo "R3: ADAPTIVE evaluation (decision tree step 4)"
echo "========================================="
# Test ADAPTIVE at the best EF found in R2
for EF in 65 80 90; do
    run_bench "r3_m16_ef${EF}_adapt" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" $EF 1 \
        "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40"
done

echo ""
echo "========================================="
echo "All scans complete. Check results/ for details."
echo "========================================="
