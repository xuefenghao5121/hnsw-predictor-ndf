#!/usr/bin/env bash
# Block size tuning - sustained benchmark (CON-SLA-020 金标)
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB="${CGROUP_MB:-256}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/block-size-tuning/results
mkdir -p "$RESULTS"

EF=65  # M=16 最优 (DEC-087)
FVC=64  # 256MB cgroup

run_strict() {
    local TAG=$1
    local GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
    local T=${7:-1}
    local EXTRA="${8:-}"

    local OUT="${RESULTS}/${TAG}.log"
    local PREFIX=""
    [ -n "$EXTRA" ] && PREFIX="export $EXTRA;"

    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init bs_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches
        cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf

        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ32
        export REFINE_EF=$EF FLAT_VEC_MB=$FVC
        export NUM_THREADS=$T ADAPTIVE_EF=0
        $PREFIX

        ./build/benchmark_sustained \
            $GRAPH $BFS $BLOCKS $ROUTE \
            data/sift_base.fvecs $POOL $GT \
            10 $EF \
            --rounds 15 --per-round 1000 --seed 42 \
            > $OUT 2>&1 || true

        cg_stats_summary >> $OUT 2>&1 || true
        cg_cleanup
    " 2>/dev/null

    LINE=$(grep "CSV_AGG" "$OUT" | tail -1)
    AGG=$(echo "$LINE" | cut -d, -f5)
    RECALL=$(echo "$LINE" | cut -d, -f6)
    STEADY=$(echo "$LINE" | cut -d, -f8)
    RSS=$(grep "RSS:" "$OUT" | tail -1 | awk '{print $2}')
    echo "agg=${AGG} steady=${STEADY} recall=${RECALL} rss=${RSS}"
}

M16=output/sift1m_m16
PART="${1:-all}"

# Block size path helper
bs_paths() {
    local BS_NAME=$1
    local DIR="output/sift1m_m16_bs${BS_NAME}k"
    echo "${M16}/sift1m_m16_graph.bin ${M16}/sift1m_m16_bfs.bin"
    echo "${DIR}/sift1m_m16_bs${BS_NAME}k_blocks.bin"
    echo "${DIR}/sift1m_m16_bs${BS_NAME}k_route.bin"
    echo "${DIR}/sift1m_m16_bs${BS_NAME}k_vecblocks.bin"
}

# === R0: Block size scan (1T, BASE) ===
if [ "$PART" = "all" ] || [ "$PART" = "r0" ]; then
echo "============================================"
echo "  R0: Block size scan (M=16 EF=65, 1T, BASE, ${CGROUP_MB}MB)"
echo "============================================"

for BS in 16 32 48 64 128; do
    DIR="output/sift1m_m16_bs${BS}k"
    if [ ! -f "${DIR}/sift1m_m16_bs${BS}k_vecblocks.bin" ]; then
        echo "bs${BS}k: SKIP (data not built)"
        continue
    fi
    run_strict "m16_ef65_bs${BS}k_1t" \
        ${M16}/sift1m_m16_graph.bin ${M16}/sift1m_m16_bfs.bin \
        ${DIR}/sift1m_m16_bs${BS}k_blocks.bin \
        ${DIR}/sift1m_m16_bs${BS}k_route.bin \
        ${DIR}/sift1m_m16_bs${BS}k_vecblocks.bin 1
done
fi

# === R2: Multi-thread (最优 BS × T={4,16}) ===
if [ "$PART" = "all" ] || [ "$PART" = "r2" ]; then
echo ""
echo "============================================"
echo "  R2: Multi-thread (最优 BS, M=16 EF=65)"
echo "============================================"

# 先用 32K 测多线程（R4' 最优）
for T in 4 16; do
    run_strict "m16_ef65_bs32k_${T}t" \
        ${M16}/sift1m_m16_graph.bin ${M16}/sift1m_m16_bfs.bin \
        output/sift1m_m16_bs32k/sift1m_m16_bs32k_blocks.bin \
        output/sift1m_m16_bs32k/sift1m_m16_bs32k_route.bin \
        output/sift1m_m16_bs32k/sift1m_m16_bs32k_vecblocks.bin $T
done
fi

# === R3: ADAPTIVE (最优 BS + ADAPTIVE) ===
if [ "$PART" = "all" ] || [ "$PART" = "r3" ]; then
echo ""
echo "============================================"
echo "  R3: ADAPTIVE (bs32k, M=16 EF=65)"
echo "============================================"

run_strict "m16_ef65_bs32k_adapt_1t" \
    ${M16}/sift1m_m16_graph.bin ${M16}/sift1m_m16_bfs.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_blocks.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_route.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_vecblocks.bin 1 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40"

run_strict "m16_ef65_bs32k_adapt_16t" \
    ${M16}/sift1m_m16_graph.bin ${M16}/sift1m_m16_bfs.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_blocks.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_route.bin \
    output/sift1m_m16_bs32k/sift1m_m16_bs32k_vecblocks.bin 16 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40"
fi

# === Summary ===
echo ""
echo "============================================"
echo "  SUMMARY (block-size-tuning, ${CGROUP_MB}MB)"
echo "============================================"
printf "%-24s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
echo "------------------------------------------------"
for tag in m16_ef65_bs16k_1t m16_ef65_bs32k_1t m16_ef65_bs48k_1t m16_ef65_bs64k_1t m16_ef65_bs128k_1t \
           m16_ef65_bs32k_4t m16_ef65_bs32k_16t \
           m16_ef65_bs32k_adapt_1t m16_ef65_bs32k_adapt_16t; do
    FILE="${RESULTS}/${tag}.log"
    [ -f "$FILE" ] || continue
    LINE=$(grep "CSV_AGG" "$FILE" | tail -1)
    AGG=$(echo "$LINE" | cut -d, -f5)
    RECALL=$(echo "$LINE" | cut -d, -f6)
    STEADY=$(echo "$LINE" | cut -d, -f8)
    RSS=$(grep "RSS:" "$FILE" | tail -1 | awk '{print $2}')
    printf "%-24s %-10s %-10s %-8s %-6s\n" "$tag" "${AGG:-FAIL}" "${STEADY:-?}" "${RECALL:-?}" "${RSS:-?}"
done
echo "DONE."
