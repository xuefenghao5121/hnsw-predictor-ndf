#!/usr/bin/env bash
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB="${CGROUP_MB:-256}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
RESULTS=poc/block-size-tuning/results
mkdir -p "$RESULTS"

EF=65
FVC=64

run_strict() {
    local TAG=$1 GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
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
        cg_create; cg_set_limit $CGROUP_MB; cg_drop_caches; cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf
        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ
        export REFINE_EF=$EF FLAT_VEC_MB=$FVC NUM_THREADS=$T ADAPTIVE_EF=0
        $PREFIX
        ./build/benchmark_sustained \
            $GRAPH $BFS $BLOCKS $ROUTE \
            data/sift_base.fvecs $POOL $GT 10 $EF \
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

# Graph + BFS are shared across all BS (same M=16 graph)
G=output/sift1m_m16_bs32k/sift1m_m16_bs32k_graph.bin
B=output/sift1m_m16_bs32k/sift1m_m16_bs32k_bfs.bin
# Actually graph/bfs are in output/ flat, and they're the same for all BS (M=16)
G=output/sift1m_m16_bs32k_graph.bin
B=output/sift1m_m16_bs32k_bfs.bin

# PQ: use the one matching each BS (they differ by BFS order)
PQ=output/pqco_sift1m_M32_correct.bin

PART="${1:-all}"

# === R0: Block size scan (1T, BASE) ===
if [ "$PART" = "all" ] || [ "$PART" = "r0" ]; then
echo "============================================"
echo "  R0: Block size scan (M=16 EF=65, 1T, BASE, ${CGROUP_MB}MB)"
echo "============================================"

# bs16k
run_strict "m16_ef65_bs16k_1t" $G $B \
    output/sift1m_m16_bs16k_blocks_16k.bin \
    output/sift1m_m16_bs16k_route_16k.bin \
    output/sift1m_m16_bs16k_vecblocks_16k.bin 1
# bs32k
run_strict "m16_ef65_bs32k_1t" $G $B \
    output/sift1m_m16_bs32k_blocks_32k.bin \
    output/sift1m_m16_bs32k_route_32k.bin \
    output/sift1m_m16_bs32k_vecblocks_32k.bin 1
# bs48k
run_strict "m16_ef65_bs48k_1t" $G $B \
    output/sift1m_m16_bs48k_blocks_48k.bin \
    output/sift1m_m16_bs48k_route_48k.bin \
    output/sift1m_m16_bs48k_vecblocks_48k.bin 1
# bs64k (Trunk default, in subdir)
run_strict "m16_ef65_bs64k_1t" \
    output/sift1m_m16/sift1m_m16_graph.bin \
    output/sift1m_m16/sift1m_m16_bfs.bin \
    output/sift1m_m16/sift1m_m16_blocks_64k.bin \
    output/sift1m_m16/sift1m_m16_route_64k.bin \
    output/sift1m_m16/sift1m_m16_vecblocks_64k.bin 1
# bs128k
run_strict "m16_ef65_bs128k_1t" $G $B \
    output/sift1m_m16_bs128k_blocks_128k.bin \
    output/sift1m_m16_bs128k_route_128k.bin \
    output/sift1m_m16_bs128k_vecblocks_128k.bin 1
fi

# === R2: Multi-thread (bs32k, best candidate) ===
if [ "$PART" = "all" ] || [ "$PART" = "r2" ]; then
echo ""
echo "============================================"
echo "  R2: Multi-thread (bs32k, M=16 EF=65)"
echo "============================================"
for T in 4 16; do
    run_strict "m16_ef65_bs32k_${T}t" $G $B \
        output/sift1m_m16_bs32k_blocks_32k.bin \
        output/sift1m_m16_bs32k_route_32k.bin \
        output/sift1m_m16_bs32k_vecblocks_32k.bin $T
done
fi

# === R3: ADAPTIVE (bs32k) ===
if [ "$PART" = "all" ] || [ "$PART" = "r3" ]; then
echo ""
echo "============================================"
echo "  R3: ADAPTIVE (bs32k, M=16 EF=65)"
echo "============================================"
run_strict "m16_ef65_bs32k_adapt_1t" $G $B \
    output/sift1m_m16_bs32k_blocks_32k.bin \
    output/sift1m_m16_bs32k_route_32k.bin \
    output/sift1m_m16_bs32k_vecblocks_32k.bin 1 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40"
run_strict "m16_ef65_bs32k_adapt_16t" $G $B \
    output/sift1m_m16_bs32k_blocks_32k.bin \
    output/sift1m_m16_bs32k_route_32k.bin \
    output/sift1m_m16_bs32k_vecblocks_32k.bin 16 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40"
fi

# === Summary ===
echo ""
echo "============================================"
echo "  SUMMARY (block-size-tuning, ${CGROUP_MB}MB)"
echo "============================================"
printf "%-28s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
echo "----------------------------------------------------"
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
    printf "%-28s %-10s %-10s %-8s %-6s\n" "$tag" "${AGG:-FAIL}" "${STEADY:-?}" "${RECALL:-?}" "${RSS:-?}"
done
echo "DONE."
