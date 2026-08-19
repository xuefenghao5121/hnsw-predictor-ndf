#!/usr/bin/env bash
# 严格 cgroup 256MB 隔离 sustained benchmark — CON-SLA-014 金标
# 覆盖: M_graph={16,24,32,48} × EF={60,80,100,120} × {1T,16T}
#        GBDT / ADAPTIVE 三模式对比
#        PQ M={16,32,64} 扫描
#        Block size={32K,64K,128K} 扫描
#
# 协议: CON-SLA-014 (drop_caches + cgroup) + CON-SLA-019 (禁预热) + CON-SLA-020 (sustained)
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="${PASS:-huawei}"
CGROUP_MB="${CGROUP_MB:-256}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ32=output/pqco_sift1m_M32_correct.bin
RESULTS=poc/pipeline-param-retuning/results-strict
mkdir -p "$RESULTS"

FVC=64  # 256MB cgroup → FVC=64

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
        cg_init strict_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches
        cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf

        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export VEC_BLOCKS_PATH=$VECBLOCKS
        export PQ_CODES_PATH=$PQ32
        export REFINE_EF=$EF FLAT_VEC_MB=$FVC
        export NUM_THREADS=$T
        export WILLNEED_BG=1 VL_POOL_THREADS=14
        export ADAPTIVE_EF=0
        $PREFIX

        ./build/benchmark_sustained \
            $GRAPH $BFS $BLOCKS $ROUTE \
            data/sift_base.fvecs $POOL $GT \
            10 $EF \
            --rounds 15 --per-round 1000 --seed 42 \
            > $OUT 2>&1

        cg_stats >> $OUT 2>&1
        cg_cleanup
    " 2>/dev/null

    LINE=\$(grep "CSV_AGG" "\$OUT" | tail -1)
    # CSV_AGG,rounds,queries,time,agg_qps,recall,cum_unique,steady_qps
    AGG=\$(echo "\$LINE" | cut -d, -f5)
    RECALL=\$(echo "\$LINE" | cut -d, -f6)
    STEADY=\$(echo "\$LINE" | cut -d, -f8)
    RSS=\$(grep "RSS:" "\$OUT" | tail -1 | awk '{print \$2}')
    PEAK=\$(grep "peak" "\$OUT" | tail -1 | awk '{print \$NF}' 2>/dev/null || echo "?")
    OOM=\$(grep -c "oom" "\$OUT" 2>/dev/null || echo "0")
    echo "agg=\${AGG} steady=\${STEADY} recall=\${RECALL} rss=\${RSS} oom=\${OOM}"
}

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

echo "============================================"
echo "  STRICT 256MB cgroup — CON-SLA-014"
echo "============================================"

# === Part 1: M_graph scan (main matrix) ===
echo ""
echo "=== Part 1: M_graph × EF (1T) ==="

for EF in 60 80 100 120; do
    run_strict "m16_ef${EF}_1t" $M16G $M16B $M16BK $M16R $M16V $EF 1
    run_strict "m24_ef${EF}_1t" $M24G $M24B $M24BK $M24R $M24V $EF 1
    run_strict "m32_ef${EF}_1t" $M32G $M32B $M32BK $M32R $M32V $EF 1
    run_strict "m48_ef${EF}_1t" $M48G $M48B $M48BK $M48R $M48V $EF 1
done

# === Part 2: 16T (key configs only) ===
echo ""
echo "=== Part 2: M_graph × EF (16T) ==="

for EF in 60 80; do
    run_strict "m16_ef${EF}_16t" $M16G $M16B $M16BK $M16R $M16V $EF 16
    run_strict "m24_ef${EF}_16t" $M24G $M24B $M24BK $M24R $M24V $EF 16
    run_strict "m32_ef${EF}_16t" $M32G $M32B $M32BK $M32R $M32V $EF 16
    run_strict "m48_ef${EF}_16t" $M48G $M48B $M48BK $M48R $M48V $EF 16
done

# === Part 3: GBDT / ADAPTIVE on M=24 EF=60 ===
echo ""
echo "=== Part 3: GBDT / ADAPTIVE (M=24, 1T) ==="

# GBDT (need M=24 model in include/gbdt_model.h)
run_strict "m24_ef60_gbdt_1t" $M24G $M24B $M24BK $M24R $M24V 60 1 "LEARNED_EF=1 GBDT_MARGIN=1.0"

# ADAPTIVE
run_strict "m24_ef60_adapt_1t" $M24G $M24B $M24BK $M24R $M24V 60 1 "ADAPTIVE_EF=1 ADAPTIVE_EASY_EF=40 ADAPTIVE_HARD_EF=100"

# === Part 4: PQ M scan on M=24 EF=60 ===
echo ""
echo "=== Part 4: PQ M scan (M=24, 1T) ==="

run_strict "m24_ef60_pqm16_1t" $M24G $M24B $M24BK $M24R $M24V 60 1
# override PQ path for M=16
TAG="m24_ef60_pqm16_1t"
OUT="${RESULTS}/${TAG}.log"
echo "$PASS" | sudo -S bash -c "
    source scripts/cgroup_utils.sh
    cg_init strict_${TAG} 256; cg_create; cg_set_limit 256
    cg_drop_caches; cg_add_proc \$\$
    cd /home/huawei/hnsw-predictor-ndf
    export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
    export VEC_BLOCKS_PATH=$M24V PQ_CODES_PATH=output/pqco_sift1m_M16.bin
    export REFINE_EF=60 FLAT_VEC_MB=64 NUM_THREADS=1 WILLNEED_BG=1 VL_POOL_THREADS=14 ADAPTIVE_EF=0
    ./build/benchmark_sustained $M24G $M24B $M24BK $M24R data/sift_base.fvecs $POOL $GT 10 60 --rounds 15 --per-round 1000 --seed 42 > $OUT 2>&1
    cg_stats >> $OUT 2>&1; cg_cleanup
" 2>/dev/null
echo -n "m24_ef60_pqm16_1t: "; grep "CSV_AGG" "$OUT" | tail -1

# === Part 5: Block size scan on M=24 EF=60 ===
echo ""
echo "=== Part 5: Block size scan (M=24, 1T) ==="

for BK in 32k 64k 128k; do
    BS_NUM=$([ "$BK" = "32k" ] && echo 32768 || ([ "$BK" = "64k" ] && echo 65536 || echo 131072))
    O=output/sift1m_m24_bs${BK}
    run_strict "m24_ef60_bs${BK}_1t" $M24G $M24B \
        $O/sift1m_m24_bs${BK}_blocks.bin \
        $O/sift1m_m24_bs${BK}_route.bin \
        $O/sift1m_m24_bs${BK}_vecblocks.bin 60 1
done

# === Summary ===
echo ""
echo "============================================"
echo "  SUMMARY (256MB cgroup, CON-SLA-014)"
echo "============================================"
echo ""
echo "--- Part 1: M_graph × EF (1T) ---"
printf "%-16s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
for M in 16 24 32 48; do
    for EF in 60 80 100 120; do
        FILE="${RESULTS}/m${M}_ef${EF}_1t.log"
        [ -f "$FILE" ] || continue
        LINE=\$(grep "CSV_AGG" "\$FILE" | tail -1)
        AGG=\$(echo "\$LINE" | cut -d, -f5)
        RECALL=\$(echo "\$LINE" | cut -d, -f6)
        STEADY=\$(echo "\$LINE" | cut -d, -f8)
        RSS=\$(grep "RSS:" "\$FILE" | tail -1 | awk '{print \$2}')
        printf "M=%-2s EF=%-3s   %-10s %-10s %-8s %-6s\n" "$M" "$EF" "\${AGG:-FAIL}" "\${STEADY:-?}" "\${RECALL:-?}" "\${RSS:-?}"
    done
done

echo ""
echo "--- Part 2: M_graph × EF (16T) ---"
printf "%-16s %-10s %-10s %-8s %-6s\n" "Config" "Agg_QPS" "Steady" "Recall" "RSS"
for M in 16 24 32 48; do
    for EF in 60 80; do
        FILE="${RESULTS}/m${M}_ef${EF}_16t.log"
        [ -f "$FILE" ] || continue
        LINE=\$(grep "CSV_AGG" "\$FILE" | tail -1)
        AGG=\$(echo "\$LINE" | cut -d, -f5)
        RECALL=\$(echo "\$LINE" | cut -d, -f6)
        STEADY=\$(echo "\$LINE" | cut -d, -f8)
        RSS=\$(grep "RSS:" "\$FILE" | tail -1 | awk '{print \$2}')
        printf "M=%-2s EF=%-3s   %-10s %-10s %-8s %-6s\n" "$M" "$EF" "\${AGG:-FAIL}" "\${STEADY:-?}" "\${RECALL:-?}" "\${RSS:-?}"
    done
done
echo ""
echo "DONE."
