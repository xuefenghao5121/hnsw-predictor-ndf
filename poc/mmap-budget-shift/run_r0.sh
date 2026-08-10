#!/usr/bin/env bash
# R0 A/B comparison: vector PQ (A) vs mmap PQ (B)
# Protocol: CON-SLA-020 sustained, CON-SLA-019 no preheating
# Config: C (DEC-087: M=24, EF=60), 256MB cgroup, 1T
# 15 rounds x 1000q, seed=42
set -uo pipefail
cd /home/huawei/hnsw-predictor-ndf

CGROUP_MB="${CGROUP_MB:-256}"
THREADS="${THREADS:-1}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
PASS="${PASS:-huawei}"

POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
PQ=output/pqco_sift1m_M32_correct.bin
PQ_MMAP=output/sift1m_m24/sift1m_m24_pq_bfs.bin
DATA=output/sift1m_m24
BIN_A=build/benchmark_sustained
BIN_B=poc/mmap-budget-shift/build/benchmark_mmap
RESULTS=poc/mmap-budget-shift/results
mkdir -p "$RESULTS"

FVC=64  # 256MB cgroup -> FVC=64

run_strict() {
    local TAG=$1
    local BINARY=$2
    local EXTRA_ENV=$3

    local OUT="${RESULTS}/${TAG}.log"
    echo -n "${TAG}: "

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source scripts/cgroup_utils.sh
        cg_init r0_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches
        cg_add_proc \$\$
        cd /home/huawei/hnsw-predictor-ndf

        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export VEC_BLOCKS_PATH=$DATA/sift1m_m24_vecblocks_64k.bin
        export PQ_CODES_PATH=$PQ
        export REFINE_EF=60
        export FLAT_VEC_MB=$FVC
        export NUM_THREADS=$THREADS
        export WILLNEED_BG=1 VL_POOL_THREADS=14
        export L4_WILLNEED=1 PAGE_MERGE_BG=1
        export ADAPTIVE_EF=0
        $EXTRA_ENV

        $BINARY \
            $DATA/sift1m_m24_graph.bin $DATA/sift1m_m24_bfs.bin \
            $DATA/sift1m_m24_blocks_64k.bin $DATA/sift1m_m24_route_64k.bin \
            data/sift_base.fvecs $POOL $GT \
            10 60 --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED \
            > $OUT 2>&1

        # Memory stats
        echo '--- memory.stat ---' >> $OUT
        cat \$CG_PATH/memory.stat | grep -E '^(anon|file|slab)' >> $OUT 2>/dev/null
        echo '--- memory.peak ---' >> $OUT
        cat \$CG_PATH/memory.peak >> $OUT 2>/dev/null

        cg_cleanup
    " 2>&1

    # Print summary
    if grep -q "CSV_AGG" "$OUT"; then
        grep "CSV_AGG" "$OUT" | tail -1 | awk -F, '{printf "agg=%-8s steady=%-8s recall=%s%%\n",$5,$8,$6}'
    else
        echo "FAILED (check $OUT)"
        tail -5 "$OUT"
    fi
}

echo "=== R0 A/B Comparison ==="
echo "Config: C (M=24 EF=60), ${CGROUP_MB}MB cgroup, ${THREADS}T"
echo "Protocol: CON-SLA-020 sustained, ${ROUNDS} rounds x ${PER_ROUND}q, seed=${SEED}"
echo ""

# A: Baseline (vector PQ, Trunk benchmark)
run_strict "A_vector" "$BIN_A" ""

echo ""
sleep 3
echo ""

# B: mmap PQ (POC benchmark)
run_strict "B_mmap" "$BIN_B" "export PQ_MMAP_PATH=$PQ_MMAP"

echo ""
echo "=== Memory Stats ==="
echo "--- A (vector) ---"
grep -E "^(anon|file|slab)" "${RESULTS}/A_vector.log" 2>/dev/null | head -5
echo "--- B (mmap) ---"
grep -E "^(anon|file|slab)" "${RESULTS}/B_mmap.log" 2>/dev/null | head -5
echo ""
echo "=== Done ==="
