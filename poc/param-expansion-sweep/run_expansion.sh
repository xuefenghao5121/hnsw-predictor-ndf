#!/usr/bin/env bash
# param-expansion-sweep: DEC-088 全参数展开扫描
# R0: FLAT_VEC_MB | R1: CACHE_MB | R2: ADAPTIVE | R3: Block size | R4: 组合
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB=256
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/param-expansion-sweep/results
mkdir -p "$RESULTS"

run_bench() {
    local TAG=$1 GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
    local EF=$7 T=${8:-1} EXTRA="${9:-}"
    local OUT="${RESULTS}/${TAG}.log"
    
    echo -n "${TAG}: "
    
    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init pes_${TAG} ${CGROUP_MB}
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
        cg_cleanup
    " 2>/dev/null
    
    local LINE=$(grep "^CSV_AGG" "$OUT" | tail -1)
    local AGG=$(echo "$LINE" | awk -F, '{print $5}')
    local STEADY=$(echo "$LINE" | awk -F, '{print $8}')
    local RECALL=$(echo "$LINE" | awk -F, '{print $6}')
    local RSS=$(grep "^RSS:" "$OUT" | tail -1 | awk '{print $2}')
    
    echo "agg=${AGG:-FAIL} steady=${STEADY:-?} recall=${RECALL:-?}% rss=${RSS:-?}MB"
}

# Data paths
M16_O=output/sift1m_m16
M16_G=${M16_O}/sift1m_m16_graph.bin
M16_BFS=${M16_O}/sift1m_m16_bfs.bin
M16_BLK=${M16_O}/sift1m_m16_blocks_64k.bin
M16_RTE=${M16_O}/sift1m_m16_route_64k.bin
M16_VEC=${M16_O}/sift1m_m16_vecblocks_64k.bin

M24_O=output/sift1m_m24
M24_G=${M24_O}/sift1m_m24_graph.bin
M24_BFS=${M24_O}/sift1m_m24_bfs.bin
M24_BLK=${M24_O}/sift1m_m24_blocks_64k.bin
M24_RTE=${M24_O}/sift1m_m24_route_64k.bin
M24_VEC=${M24_O}/sift1m_m24_vecblocks_64k.bin

# ========== R0: FLAT_VEC_MB scan ==========
echo "========================================="
echo "R0: FLAT_VEC_MB scan (M=16 EF=65)"
echo "========================================="
for FVC in 32 64 96 128 160; do
    run_bench "r0_fvc${FVC}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 65 1 \
        "FLAT_VEC_MB=${FVC}"
done

# ========== R1: CACHE_MB scan ==========
echo ""
echo "========================================="
echo "R1: CACHE_MB scan (M=16 EF=65)"
echo "========================================="
for CMB in 32 64 96 128; do
    run_bench "r1_cmb${CMB}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 65 1 \
        "CACHE_MB=${CMB}"
done

# ========== R2a: ADAPTIVE_EASY_EF scan ==========
echo ""
echo "========================================="
echo "R2a: ADAPTIVE_EASY_EF scan"
echo "========================================="
echo "--- M=16 EF=65 (budget=0.52pp) ---"
for EEF in 35 40 45; do
    run_bench "r2a_m16_ef65_eef${EEF}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 65 1 \
        "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=${EEF}"
done

echo "--- M=16 EF=80 (budget=1.79pp) ---"
for EEF in 35 40 45 50; do
    run_bench "r2a_m16_ef80_eef${EEF}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 80 1 \
        "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=${EEF}"
done

echo "--- M=24 EF=60 (budget=1.60pp) ---"
for EEF in 35 40 45 50; do
    run_bench "r2a_m24_ef60_eef${EEF}" "$M24_G" "$M24_BFS" "$M24_BLK" "$M24_RTE" "$M24_VEC" 60 1 \
        "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=${EEF}"
done

# ========== R2b: ADAPTIVE_EASY_GAP scan ==========
echo ""
echo "========================================="
echo "R2b: ADAPTIVE_EASY_GAP scan (M=16 EF=80)"
echo "========================================="
for GAP in 1.003 1.006 1.010 1.015 1.020; do
    run_bench "r2b_gap${GAP}" "$M16_G" "$M16_BFS" "$M16_BLK" "$M16_RTE" "$M16_VEC" 80 1 \
        "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_EASY_GAP=${GAP}"
done

# ========== R3: M=24 block size (32K) ==========
# Note: need to build M=24 32K vecblocks first
echo ""
echo "========================================="
echo "R3: M=24 block size comparison"
echo "========================================="
echo "--- M=24 EF=60 64K (baseline) ---"
run_bench "r3_m24_ef60_bs64k" "$M24_G" "$M24_BFS" "$M24_BLK" "$M24_RTE" "$M24_VEC" 60 1

# Check if 32K data exists
M24_VEC_32K=${M24_O}/sift1m_m24_vecblocks_32k.bin
M24_RTE_32K=${M24_O}/sift1m_m24_route_32k.bin
if [ -f "$M24_VEC_32K" ]; then
    echo "--- M=24 EF=60 32K ---"
    run_bench "r3_m24_ef60_bs32k" "$M24_G" "$M24_BFS" "$M24_BLK" "$M24_RTE" "$M24_VEC_32K" 60 1
else
    echo "--- M=24 32K vecblocks NOT FOUND, skipping (need build_pipeline.sh) ---"
fi

# ========== R4: Best combination ==========
echo ""
echo "========================================="
echo "R4: Best combination validation"
echo "========================================="
# Will be filled based on R0-R3 results
echo "(filled after R0-R3 analysis)"

echo ""
echo "========================================="
echo "All scans complete."
echo "========================================="
