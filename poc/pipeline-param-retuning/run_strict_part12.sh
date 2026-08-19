#!/usr/bin/env bash
# Strict cgroup 256MB — Part 1: M_graph × EF main matrix (1T)
# CON-SLA-014 gold standard
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

PASS="huawei"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ=output/pqco_sift1m_M32_correct.bin
R=poc/pipeline-param-retuning/results-strict
mkdir -p "$R"

run() {
    local TAG=$1 M=$2 EF=$3 T=${4:-1}
    local P="sift1m_m${M}"
    local O="output/${P}"
    local OUT="${R}/${TAG}.log"
    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash << ENDOFSCRIPT 2>/dev/null
set -uo pipefail
source scripts/cgroup_utils.sh
cg_init strict_${TAG} 256
cg_create
cg_set_limit 256
cg_drop_caches
cg_add_proc \$\$
cd /home/huawei/hnsw-predictor-ndf
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=${O}/${P}_vecblocks_64k.bin
export PQ_CODES_PATH=${PQ}
export REFINE_EF=${EF} FLAT_VEC_MB=64
export NUM_THREADS=${T}
export WILLNEED_BG=1 VL_POOL_THREADS=14
export ADAPTIVE_EF=0
./build/benchmark_sustained \
    ${O}/${P}_graph.bin ${O}/${P}_bfs.bin \
    ${O}/${P}_blocks_64k.bin ${O}/${P}_route_64k.bin \
    data/sift_base.fvecs ${POOL} ${GT} \
    10 ${EF} \
    --rounds 15 --per-round 1000 --seed 42 \
    > ${OUT} 2>&1
cg_stats >> ${OUT} 2>&1
cg_cleanup
ENDOFSCRIPT

    local LINE=$(grep "CSV_AGG" "$OUT" | tail -1)
    local AGG=$(echo "$LINE" | cut -d, -f5)
    local RECALL=$(echo "$LINE" | cut -d, -f6)
    local STEADY=$(echo "$LINE" | cut -d, -f8)
    local RSS=$(grep "RSS:" "$OUT" | tail -1 | awk '{print $2}')
    echo "agg=${AGG:-FAIL} steady=${STEADY:-?} recall=${RECALL:-?} rss=${RSS:-?}"
}

echo "=== Part 1: M_graph × EF (1T, 256MB strict) ==="
for EF in 60 80 100 120; do
    for M in 16 24 32 48; do
        run "m${M}_ef${EF}_1t" $M $EF 1
    done
done

echo ""
echo "=== Part 2: M_graph × EF (16T, 256MB strict) ==="
for EF in 60 80; do
    for M in 16 24 32 48; do
        run "m${M}_ef${EF}_16t" $M $EF 16
    done
done

echo ""
echo "=== Summary ==="
echo "--- 1T ---"
printf "%-4s %-4s %-10s %-10s %-8s %-6s\n" "M" "EF" "Agg" "Steady" "Recall" "RSS"
for EF in 60 80 100 120; do
    for M in 16 24 32 48; do
        F="${R}/m${M}_ef${EF}_1t.log"
        if [ -f "$F" ]; then
            L=$(grep "CSV_AGG" "$F" | tail -1)
            A=$(echo "$L"|cut -d, -f5); RC=$(echo "$L"|cut -d, -f6); ST=$(echo "$L"|cut -d, -f8)
            RS=$(grep "RSS:" "$F"|tail -1|awk '{print $2}')
            printf "%-4s %-4s %-10s %-10s %-8s %-6s\n" "$M" "$EF" "${A:-?}" "${ST:-?}" "${RC:-?}" "${RS:-?}"
        fi
    done
done
echo ""
echo "--- 16T ---"
printf "%-4s %-4s %-10s %-10s %-8s %-6s\n" "M" "EF" "Agg" "Steady" "Recall" "RSS"
for EF in 60 80; do
    for M in 16 24 32 48; do
        F="${R}/m${M}_ef${EF}_16t.log"
        if [ -f "$F" ]; then
            L=$(grep "CSV_AGG" "$F" | tail -1)
            A=$(echo "$L"|cut -d, -f5); RC=$(echo "$L"|cut -d, -f6); ST=$(echo "$L"|cut -d, -f8)
            RS=$(grep "RSS:" "$F"|tail -1|awk '{print $2}')
            printf "%-4s %-4s %-10s %-10s %-8s %-6s\n" "$M" "$EF" "${A:-?}" "${ST:-?}" "${RC:-?}" "${RS:-?}"
        fi
    done
done
echo ""
echo "Part 1+2 DONE."
