#!/usr/bin/env bash
# Strict cgroup 256MB benchmark — one config per invocation
# Usage: bash run_one.sh <tag> <M_graph> <EF> <threads> [extra_exports]
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

TAG=$1; M=$2; EF=$3; T=$4; EXTRA="${5:-}"
P="sift1m_m${M}"; O="output/${P}"
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ=output/pqco_sift1m_M32_correct.bin
OUT="poc/pipeline-param-retuning/results-strict/${TAG}.log"
mkdir -p "$(dirname "$OUT")"

echo "$PASS" | sudo -S bash -c "
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
export ${EXTRA}
./build/benchmark_sustained \
    ${O}/${P}_graph.bin ${O}/${P}_bfs.bin \
    ${O}/${P}_blocks_64k.bin ${O}/${P}_route_64k.bin \
    data/sift_base.fvecs ${POOL} ${GT} \
    10 ${EF} \
    --rounds 15 --per-round 1000 --seed 42 \
    > ${OUT} 2>&1
cg_stats >> ${OUT} 2>&1
cg_cleanup
" 2>/dev/null

LINE=$(grep "CSV_AGG" "$OUT" | tail -1)
AGG=$(echo "$LINE" | cut -d, -f5)
RECALL=$(echo "$LINE" | cut -d, -f6)
STEADY=$(echo "$LINE" | cut -d, -f8)
RSS=$(grep "RSS:" "$OUT" | tail -1 | awk '{print $2}')
echo "${TAG}: agg=${AGG:-FAIL} steady=${STEADY:-?} recall=${RECALL:-?} rss=${RSS:-?}"
