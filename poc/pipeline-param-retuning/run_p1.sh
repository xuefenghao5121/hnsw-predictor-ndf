#!/bin/bash
# P1: M_graph scanning with sustained benchmark
# Fixed: M_pq=32, BS=64K, 256MB cgroup
# Scan: M_graph={16,24,32,48} × EF={60,80,100,120}
# Mode: BASE (TWO_STAGE=1, FINE_RERANK=1, no GBDT, no ADAPTIVE)

set -e
cd /home/huawei/hnsw-predictor-ndf

QUERY_POOL=data/sift_query_official10k.fvecs
GT=data/sift_gt_official10k_k10.bin
PQ_CODES=output/pqco_sift1m_M32_correct.bin
RESULTS_DIR=poc/pipeline-param-retuning/results
mkdir -p "$RESULTS_DIR"

echo "PQ: $PQ_CODES ($(du -sh $PQ_CODES | cut -f1))"
echo ""

run_bench() {
    local M=$1
    local EF=$2
    local PREFIX="sift1m_m${M}"
    local O="output/${PREFIX}"
    local TAG="m${M}_ef${EF}_256mb"
    
    local GRAPH="${O}/${PREFIX}_graph.bin"
    local BFS="${O}/${PREFIX}_bfs.bin"
    local BLOCKS="${O}/${PREFIX}_blocks_64k.bin"
    local ROUTE="${O}/${PREFIX}_route_64k.bin"
    local VECBLOCKS="${O}/${PREFIX}_vecblocks_64k.bin"
    
    echo "--- M=${M} EF=${EF} ---"
    
    sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
    
    CACHE_MB=64 FLAT_VEC_MB=64 \
    TWO_STAGE=1 \
    FINE_RERANK=1 PAGE_SIZE=4096 FINE_PREAD=1 FINE_BUFFERED=1 \
    VEC_BLOCKS_PATH="$VECBLOCKS" \
    PQ_CODES_PATH="$PQ_CODES" \
    REFINE_EF=$EF \
    ADAPTIVE_EF=0 \
    WILLNEED_BG=1 \
    ./build/benchmark_sustained \
        "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" \
        data/sift_base.fvecs "$QUERY_POOL" "$GT" \
        10 $EF \
        --rounds 15 --per-round 1000 --seed 42 --warmup 2 \
        > "${RESULTS_DIR}/${TAG}.txt" 2>&1
    
    if grep -q "Aggregate QPS" "${RESULTS_DIR}/${TAG}.txt"; then
        local AGG=$(grep "Aggregate QPS" "${RESULTS_DIR}/${TAG}.txt" | tail -1 | awk '{print $NF}')
        local STEADY=$(grep "Steady State QPS" "${RESULTS_DIR}/${TAG}.txt" | tail -1 | awk '{print $NF}')
        local RECALL=$(grep "Recall" "${RESULTS_DIR}/${TAG}.txt" | tail -1 | awk '{print $NF}')
        local RSS=$(grep "Peak RSS" "${RESULTS_DIR}/${TAG}.txt" | tail -1 | awk '{print $NF}')
        echo "  agg=${AGG} steady=${STEADY} recall=${RECALL} rss=${RSS}"
    else
        echo "  RESULT (CSV parse):"
        grep "CSV_AGG" "${RESULTS_DIR}/${TAG}.txt" | tail -1
    fi
}

for M in 16 24 32 48; do
    for EF in 60 80 100 120; do
        run_bench $M $EF
    done
done

echo ""
echo "=== P1 Summary (256MB, TWO_STAGE + FINE_RERANK, BASE mode) ==="
printf "%-4s %-4s %-12s %-12s %-8s %-8s\n" "M" "EF" "Agg_QPS" "Steady_QPS" "Recall" "RSS"
echo "--------------------------------------------------------"
for M in 16 24 32 48; do
    for EF in 60 80 100 120; do
        TAG="m${M}_ef${EF}_256mb"
        FILE="${RESULTS_DIR}/${TAG}.txt"
        if [ -f "$FILE" ]; then
            LINE=$(grep "CSV_AGG" "$FILE" | tail -1)
            if [ -n "$LINE" ]; then
                # CSV_AGG,rounds,queries,time,agg_qps,recall,cum_unique,steady_qps
                AGG=$(echo "$LINE" | cut -d, -f5)
                RECALL=$(echo "$LINE" | cut -d, -f6)
                STEADY=$(echo "$LINE" | cut -d, -f8)
                RSS=$(grep "RSS:" "$FILE" | tail -1 | awk '{print $2}')
                printf "%-4s %-4s %-12s %-12s %-8s %-8s\n" "$M" "$EF" "$AGG" "$STEADY" "$RECALL" "$RSS"
            else
                printf "%-4s %-4s %-12s\n" "$M" "$EF" "NO CSV"
            fi
        else
            printf "%-4s %-4s %-12s\n" "$M" "$EF" "MISSING"
        fi
    done
done
