#!/bin/bash
# R0-R4 I/O Pipelining Benchmark
# SIFT1M, 512MB cgroup, REFINE_EF=100, 4T, 10000 queries
set -e

cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_pipe
COMMON_ARGS="output/sift1m_graph.bin output/sift1m_bfs.bin output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin 10 100 10000"

export CACHE_MB=64
export TWO_STAGE=1
export FINE_RERANK=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODE_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100
export BATCH_QUERIES=4

run_round() {
    local name=$1
    shift
    echo "============================================"
    echo "  $name"
    echo "============================================"
    
    # 设置 cgroup
    CGROUP=/sys/fs/cgroup/hnsw_pipe_$$
    sudo mkdir -p $CGROUP 2>/dev/null || true
    echo "536870912" | sudo tee $CGROUP/memory.max > /dev/null  # 512MB
    echo $$ | sudo tee $CGROUP/cgroup.procs > /dev/null
    
    env "$@" $BIN $COMMON_ARGS 2>&1 | grep -E "Recall|QPS|RSS|Results|PipeFine|Mode:"
    
    # 清理 cgroup
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir $CGROUP 2>/dev/null || true
    echo ""
}

# R0: Baseline (no pipelining)
run_round "R0: Baseline (PIPE_FINE=0)" \
    FINE_PREAD=1

# R1: L5 only (O_DIRECT)
run_round "R1: L5 pipe_ring_ (O_DIRECT)" \
    FINE_DIRECT=1 PIPE_FINE=1

# R2: L5 + L1 (O_DIRECT)
run_round "R2: L5 + L1 CPU cache (O_DIRECT)" \
    FINE_DIRECT=1 PIPE_FINE=1 PIPE_L1=1

# R3: L5 + L4 (Buffered)
run_round "R3: L5 + L4 page cache (Buffered)" \
    FINE_PREAD=1 PIPE_FINE=1 PIPE_L4=1

# R4: All layers (Buffered)
run_round "R4: L5 + L4 + L1 (Buffered)" \
    FINE_PREAD=1 PIPE_FINE=1 PIPE_L4=1 PIPE_L1=1

echo "============================================"
echo "  Benchmark complete"
echo "============================================"
