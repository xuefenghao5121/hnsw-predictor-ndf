#!/bin/bash
# run_r5.sh - L4 POC R5: WILLNEED + Selective DONTNEED
# 基线: 256MB cgroup + flat_vec_cache=64MB (R4 promoted state)
# 使用 systemd-run --scope (MemoryLimit) 替代 sudo cgroup
# 使用 posix_fadvise helper 替代 sudo drop_caches
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt
BIN=build/benchmark_l4
DROP_CACHE=./drop_file_cache

GRAPH=../../output/sift1m_graph.bin
BFS=../../output/sift1m_bfs.bin
BLOCKS=../../output/sift1m_blocks_64k.bin
ROUTE=../../output/sift1m_route_64k.bin
DATA=../../data/sift_base.fvecs
QUERY=../../data/sift1m_query200.fvecs
GT=../../data/sift1m_gt200.bin
VECBLOCKS=../../output/sift1m_vecblocks_64k.bin
PQCODES=../../output/pqco_sift1m_M32_correct.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=${CGROUP_MB:-256}

# Files to evict before each run
EVICT_FILES="$GRAPH $BFS $BLOCKS $ROUTE $VECBLOCKS $PQCODES $DATA"

run_round() {
    local name=$1; shift
    local extra_env="$@"
    echo ""; echo "============================================"
    echo "  $name  (cgroup=${CGROUP_MB}MB)"
    echo "============================================"
    
    # Evict page cache for data files (no sudo needed)
    $DROP_CACHE $EVICT_FILES 2>/dev/null || true
    sync
    
    # Run benchmark in cgroup, capture cgroup path for stats
    local unit_name="hnsw_r5_$(echo "$name" | tr -cd 'a-zA-Z0-9_')"
    
    # Run benchmark and capture output; read cgroup stats from within the scope
    systemd-run --scope --property=MemoryLimit=${CGROUP_MB}M \
        --unit="$unit_name" \
        --collect \
        bash -c "
            CG=/sys/fs/cgroup/system.slice/$unit_name.scope
            
            # Export env
            export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
            export VEC_BLOCKS_PATH=$VECBLOCKS
            export PQ_CODES_PATH=$PQCODES
            export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
            export EVICT_PAGE_CACHE=0 NUM_THREADS=0 PROFILE_TS=1
            export $extra_env
            
            # Run benchmark
            $BIN '$GRAPH' '$BFS' '$BLOCKS' '$ROUTE' '$DATA' '$QUERY' '$GT' $K $EF $NUMQ 2>&1
            
            # Read cgroup stats while still in scope
            echo ''
            echo '--- cgroup ---'
            echo \"peak: \$(cat \$CG/memory.peak 2>/dev/null)\"
            echo 'events:'
            cat \$CG/memory.events 2>/dev/null
            grep -E '^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)' \$CG/memory.stat 2>/dev/null
        " 2>&1 || true
}

# R5-base: Promoted baseline (256MB, flat_vec=64MB, no L4 mgmt)
run_round "R5-base" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0"

# R5a: + WILLNEED (prefetch hint before pread)
run_round "R5a-WILLNEED" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=0"

# R5b: + Selective DONTNEED (evict only cold pages)
run_round "R5b-SelDontNeed" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=1"

# R5d: Best combination
run_round "R5d-Both" "FINE_FADVISE=0 L4_EVICT_META=1 L4_WILLNEED=1 L4_SELECTIVE_DONTNEED=1"

# R1-blanket: Reference (blanket FADVISE, known -17x)
run_round "R1-blanket-ref" "FINE_FADVISE=1 L4_EVICT_META=1 L4_WILLNEED=0 L4_SELECTIVE_DONTNEED=0"
