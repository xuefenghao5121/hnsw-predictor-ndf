#!/usr/bin/env bash
# 严格 cgroup 256MB sustained benchmark - pipeline-param-retuning POC (redo)
#
# 协议: CON-SLA-014 (cgroup 隔离) + CON-SLA-019 (禁预热) + CON-SLA-020 (sustained 金标)
# 配置: 对齐 CON-SLA-020 标准 env (L4_WILLNEED=1 + PAGE_MERGE_BG=1)
#
# Usage: bash poc/pipeline-param-retuning/run_strict_redo.sh [PART]
#   PART=all|base|adaptive|mt|pq|bs
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB="${CGROUP_MB:-256}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/pipeline-param-retuning/results-redo
mkdir -p "$RESULTS"

FVC=64  # 256MB cgroup -> FVC=64

# === 通用运行函数 ===
run_strict() {
    local TAG=$1
    local GRAPH=$2 BFS=$3 BLOCKS=$4 ROUTE=$5 VECBLOCKS=$6
    local EF=$7
    local T=${8:-1}
    local EXTRA="${9:-}"

    local OUT="${RESULTS}/${TAG}.log"
    local PREFIX=""
    [ -n "$EXTRA" ] && PREFIX="export $EXTRA;"

    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init redo_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches
        cg_add_proc $$
        cd /home/huawei/hnsw-predictor-ndf

        # CON-SLA-020 标准配置 (含 L4_WILLNEED + PAGE_MERGE_BG)
        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ32
        export REFINE_EF=$EF FLAT_VEC_MB=$FVC
        export NUM_THREADS=$T
        export ADAPTIVE_EF=0
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
    OOM=$(grep -c "oom" "$OUT" 2>/dev/null || echo "0")
    echo "agg=${AGG} steady=${STEADY} recall=${RECALL} rss=${RSS} oom=${OOM}"
}

# === 路径定义 ===
M16G=output/sift1m_m16/sift1m_m16_graph.bin
M16B=output/sift1m_m16/sift1m_m16_bfs.bin
M16BK=output/sift1m_m16/sift1m_m16_blocks_64k.bin
M16R=output/sift1m_m16/sift1m_m16_route_64k.bin
M16V=output/sift1m_m16/sift1m_m16_vecblocks_64k.bin

M24G=output/sift1m_m24/sift1m_m24_graph.bin
M24B=output/sift1m_m24/sift1m_m24_bfs.bin
M24BK=output/sift1m_m24/sift1m_m24_blocks_64k.bin
M24R=output/sift1m_m24/sift1m_m24_route_64k.bin
M24V=output/sift1m_m24/sift1m_m24_vecblocks_64k.bin

M32G=output/sift1m_m32/sift1m_m32_graph.bin
M32B=output/sift1m_m32/sift1m_m32_bfs.bin
M32BK=output/sift1m_m32/sift1m_m32_blocks_64k.bin
M32R=output/sift1m_m32/sift1m_m32_route_64k.bin
M32V=output/sift1m_m32/sift1m_m32_vecblocks_64k.bin

M48G=output/sift1m_m48/sift1m_m48_graph.bin
M48B=output/sift1m_m48/sift1m_m48_bfs.bin
M48BK=output/sift1m_m48/sift1m_m48_blocks_64k.bin
M48R=output/sift1m_m48/sift1m_m48_route_64k.bin
M48V=output/sift1m_m48/sift1m_m48_vecblocks_64k.bin

PART="${1:-all}"

# === R0': M_graph × EF 扫描 (1T, BASE 模式) ===
if [ "$PART" = "all" ] || [ "$PART" = "base" ]; then
echo "============================================"
echo "  R0': M_graph × EF (1T, BASE, ${CGROUP_MB}MB)"
echo "  CON-SLA-020 金标配置 (L4_WILLNEED=1 + PAGE_MERGE_BG=1)"
echo "============================================"

for EF in 60 80 100 120; do
    run_strict "m16_ef${EF}_1t" $M16G $M16B $M16BK $M16R $M16V $EF 1
    run_strict "m24_ef${EF}_1t" $M24G $M24B $M24BK $M24R $M24V $EF 1
    run_strict "m32_ef${EF}_1t" $M32G $M32B $M32BK $M32R $M32V $EF 1
    run_strict "m48_ef${EF}_1t" $M48G $M48B $M48BK $M48R $M48V $EF 1
done
fi

# === R1': GBDT/ADAPTIVE (M=24 EF=60, 1T) ===
if [ "$PART" = "all" ] || [ "$PART" = "adaptive" ]; then
echo ""
echo "============================================"
echo "  R1': GBDT/ADAPTIVE (M=24 EF=60, 1T)"
echo "============================================"

# ADAPTIVE (对齐 DEC-086 最优: eef=40)
run_strict "m24_ef60_adapt_1t" $M24G $M24B $M24BK $M24R $M24V 60 1 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_HARD_EF=200"

# GBDT
run_strict "m24_ef60_gbdt_1t" $M24G $M24B $M24BK $M24R $M24V 60 1 \
    "LEARNED_EF=1 GBDT_MARGIN=0.8"

# ADAPTIVE 基线 (M=16 EF=90, 对齐 DEC-086)
run_strict "m16_ef90_adapt_1t" $M16G $M16B $M16BK $M16R $M16V 90 1 \
    "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_HARD_EF=200"
fi

# === R2': PQ M scan (M=24 EF=60, 1T) ===
if [ "$PART" = "all" ] || [ "$PART" = "pq" ]; then
echo ""
echo "============================================"
echo "  R2': PQ M scan (M=24 EF=60, 1T)"
echo "============================================"

# PQ M=16
echo "$PASS" | sudo -S bash -c "
    source scripts/cgroup_utils.sh
    cg_init redo_m24_ef60_pqm16_1t 256; cg_create; cg_set_limit 256
    cg_drop_caches; cg_add_proc $$
    cd /home/huawei/hnsw-predictor-ndf
    export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
    export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
    export VEC_BLOCKS_PATH=$M24V PQ_CODES_PATH=output/pqco_sift1m_M16.bin
    export REFINE_EF=60 FLAT_VEC_MB=64 NUM_THREADS=1 ADAPTIVE_EF=0
    ./build/benchmark_sustained $M24G $M24B $M24BK $M24R data/sift_base.fvecs $POOL $GT 10 60 --rounds 15 --per-round 1000 --seed 42 > $RESULTS/m24_ef60_pqm16_1t.log 2>&1 || true
    cg_stats_summary >> $RESULTS/m24_ef60_pqm16_1t.log 2>&1; cg_cleanup
" 2>/dev/null
echo -n "m24_ef60_pqm16_1t: "; grep "CSV_AGG" "$RESULTS/m24_ef60_pqm16_1t.log" | tail -1

# PQ M=64
echo "$PASS" | sudo -S bash -c "
    source scripts/cgroup_utils.sh
    cg_init redo_m24_ef60_pqm64_1t 256; cg_create; cg_set_limit 256
    cg_drop_caches; cg_add_proc $$
    cd /home/huawei/hnsw-predictor-ndf
    export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
    export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
    export VEC_BLOCKS_PATH=$M24V PQ_CODES_PATH=output/pqco_sift1m_M64.bin
    export REFINE_EF=60 FLAT_VEC_MB=64 NUM_THREADS=1 ADAPTIVE_EF=0
    ./build/benchmark_sustained $M24G $M24B $M24BK $M24R data/sift_base.fvecs $POOL $GT 10 60 --rounds 15 --per-round 1000 --seed 42 > $RESULTS/m24_ef60_pqm64_1t.log 2>&1 || true
    cg_stats_summary >> $RESULTS/m24_ef60_pqm64_1t.log 2>&1; cg_cleanup
" 2>/dev/null
echo -n "m24_ef60_pqm64_1t: "; grep "CSV_AGG" "$RESULTS/m24_ef60_pqm64_1t.log" | tail -1
fi

# === R3': 多线程 (M={16,24} × EF={60,80} × T={4,8,16}) ===
if [ "$PART" = "all" ] || [ "$PART" = "mt" ]; then
echo ""
echo "============================================"
echo "  R3': Multi-thread (BASE, ${CGROUP_MB}MB)"
echo "============================================"

for EF in 60 80; do
    for T in 4 8 16; do
        run_strict "m16_ef${EF}_${T}t" $M16G $M16B $M16BK $M16R $M16V $EF $T
        run_strict "m24_ef${EF}_${T}t" $M24G $M24B $M24BK $M24R $M24V $EF $T
    done
done
fi

# === R4': Block size scan (M=24 EF=60, 1T) ===
if [ "$PART" = "all" ] || [ "$PART" = "bs" ]; then
echo ""
echo "============================================"
echo "  R4': Block size scan (M=24 EF=60, 1T)"
echo "============================================"

for BK in 32k 64k 128k; do
    O=output/sift1m_m24_bs${BK}
    run_strict "m24_ef60_bs${BK}_1t" $M24G $M24B \
        $O/sift1m_m24_bs${BK}_blocks.bin \
        $O/sift1m_m24_bs${BK}_route.bin \
        $O/sift1m_m24_bs${BK}_vecblocks.bin 60 1
done
fi

# === Summary ===
echo ""
echo "============================================"
echo "  SUMMARY (redo, ${CGROUP_MB}MB cgroup, CON-SLA-020 金标)"
echo "============================================"
echo ""
echo "--- R0': M_graph × EF (1T, BASE) ---"
printf "%-20s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
echo "------------------------------------------------------------"
for M in 16 24 32 48; do
    for EF in 60 80 100 120; do
        FILE="${RESULTS}/m${M}_ef${EF}_1t.log"
        [ -f "$FILE" ] || continue
        LINE=$(grep "CSV_AGG" "$FILE" | tail -1)
        AGG=$(echo "$LINE" | cut -d, -f5)
        RECALL=$(echo "$LINE" | cut -d, -f6)
        STEADY=$(echo "$LINE" | cut -d, -f8)
        RSS=$(grep "RSS:" "$FILE" | tail -1 | awk '{print $2}')
        printf "M=%-2s EF=%-3s         %-10s %-10s %-8s %-6s\n" "$M" "$EF" "${AGG}:-FAIL}" "${STEADY}:-?}" "${RECALL}:-?}" "${RSS}:-?}"
    done
done

echo ""
echo "--- R3': Multi-thread ---"
printf "%-20s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
echo "------------------------------------------------------------"
for M in 16 24; do
    for EF in 60 80; do
        for T in 4 8 16; do
            FILE="${RESULTS}/m${M}_ef${EF}_${T}t.log"
            [ -f "$FILE" ] || continue
            LINE=$(grep "CSV_AGG" "$FILE" | tail -1)
            AGG=$(echo "$LINE" | cut -d, -f5)
            RECALL=$(echo "$LINE" | cut -d, -f6)
            STEADY=$(echo "$LINE" | cut -d, -f8)
            RSS=$(grep "RSS:" "$FILE" | tail -1 | awk '{print $2}')
            printf "M=%-2s EF=%-3s T=%-2s      %-10s %-10s %-8s %-6s\n" "$M" "$EF" "$T" "${AGG}:-FAIL}" "${STEADY}:-?}" "${RECALL}:-?}" "${RSS}:-?}"
        done
    done
done

echo ""
echo "DONE."
