#!/usr/bin/env bash
# R0 A/B comparison: vector PQ (A) vs mmap PQ (B)
# Protocol: CON-SLA-020 sustained, CON-SLA-019 no preheating, CON-SLA-014 strict cgroup
# Config: C (DEC-087: M=24, EF=60), 256MB cgroup, 1T
# 15 rounds x 1000q, seed=42
#
# Uses cgroup_utils.sh: cg_init, cg_start_monitor, cg_stats_summary, cg_verify
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

CGROUP_MB="${CGROUP_MB:-256}"
THREADS="${THREADS:-1}"
ROUNDS="${ROUNDS:-15}"
PER_ROUND="${PER_ROUND:-1000}"
SEED="${SEED:-42}"
PASS="${PASS:-huawei}"

source scripts/cgroup_utils.sh

DATA=output/sift1m_m24
POOL=data/sift_query_official10k.fvecs
GT=data/sift_groundtruth_official.ivecs
BASE=data/sift_base.fvecs
PQ=output/pqco_sift1m_M32_correct.bin
PQ_MMAP=$DATA/sift1m_m24_pq_bfs.bin
BIN_A=build/benchmark_sustained
BIN_B=$POC/build/benchmark_mmap
RESULTS=$POC/results
mkdir -p "$RESULTS"

run_strict() {
    local TAG=$1
    local BINARY=$2
    local EXTRA_ENV=$3
    local OUT="$RESULTS/${TAG}.log"

    echo "=========================================="
    echo "  $TAG"
    echo "=========================================="

    echo "$PASS" | sudo -S bash -c "
        set -uo pipefail
        source $REPO/scripts/cgroup_utils.sh
        cg_init r0_${TAG} $CGROUP_MB
        cg_create
        cg_set_limit $CGROUP_MB
        cg_drop_caches                      # CON-SLA-014 step 1
        cg_add_proc \$\$                     # CON-SLA-014 step 2

        # Background memory monitor (peak tracking)
        MONITOR_LOG=/tmp/r0_${TAG}_monitor.log
        cg_start_monitor \$MONITOR_LOG
        MONITOR_PID=\$CG_MONITOR_PID

        cd $REPO
        export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
        export VEC_BLOCKS_PATH=$DATA/sift1m_m24_vecblocks_64k.bin
        export PQ_CODES_PATH=$PQ
        export REFINE_EF=60 ADAPTIVE_EF=0
        export FLAT_VEC_MB=64 NUM_THREADS=$THREADS
        export L4_WILLNEED=1 PAGE_MERGE_BG=1 WILLNEED_BG=1 VL_POOL_THREADS=14
        $EXTRA_ENV

        # CON-SLA-019: no --warmup => no preheating of measured queries
        $BINARY \\
            $DATA/sift1m_m24_graph.bin $DATA/sift1m_m24_bfs.bin \\
            $DATA/sift1m_m24_blocks_64k.bin $DATA/sift1m_m24_route_64k.bin \\
            $BASE $POOL $GT \\
            10 60 --rounds $ROUNDS --per-round $PER_ROUND --seed $SEED --verbose

        # CON-SLA-014 steps 4-5: cgroup accounting evidence
        echo ''
        echo '--- cgroup accounting (CON-SLA-014) ---'
        cg_stats_summary
        echo ''
        echo '--- cgroup verify ---'
        if cg_verify; then
            echo '  ✅ SLA 通过 (无违规)'
        else
            echo '  ❌ SLA 违规!'
        fi

        # Peak from monitor
        cg_stop_monitor \$MONITOR_PID
        echo ''
        echo '--- monitor peak ---'
        echo \"  Peak anon (MB):  \$(awk '{if(\$3>m) m=\$3} END{if(m>0) print m/1024/1024; else print 0}' \$MONITOR_LOG)\"
        echo \"  Peak file (MB):  \$(awk '{if(\$4>m) m=\$4} END{if(m>0) print m/1024/1024; else print 0}' \$MONITOR_LOG)\"
        echo \"  Peak total (MB): \$(awk '{if(\$2>m) m=\$2} END{if(m>0) print m/1024/1024; else print 0}' \$MONITOR_LOG)\"

        cg_cleanup
    " > "$OUT" 2>&1

    # Print summary
    echo "--- $TAG results ---"
    grep -E "^CSV_AGG|^QPS:|^Recall@|anon_bytes:|file_bytes:|peak_bytes:|violations:|Peak anon|Peak file|Peak total|SLA" "$OUT" || {
        echo "(no result lines) tail:"
        tail -10 "$OUT"
    }
    echo ""
}

echo "=== R0 A/B Comparison ==="
echo "Config: C (M=24 EF=60), ${CGROUP_MB}MB cgroup, ${THREADS}T"
echo "Protocol: CON-SLA-020 sustained, ${ROUNDS} rounds x ${PER_ROUND}q, seed=${SEED}"
echo "Binary A: $BIN_A (Trunk, vector PQ)"
echo "Binary B: $BIN_B (POC, mmap PQ)"
echo ""

# A: Baseline (vector PQ, Trunk benchmark)
run_strict "A_vector" "$BIN_A" ""

sleep 3

# B: mmap PQ (POC benchmark)
run_strict "B_mmap" "$BIN_B" "export PQ_MMAP_PATH=$PQ_MMAP"

echo "=== Done ==="
echo "Logs: $RESULTS/A_vector.log, $RESULTS/B_mmap.log"
