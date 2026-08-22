#!/bin/bash
# R5c mincore diagnostic - 512MB cgroup comparison
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt

export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 FINE_PREAD=1 FINE_BUFFERED=1
export EVICT_PAGE_CACHE=0 NUM_THREADS=0
export L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14
export PAGE_MERGE_BG=1 FLAT_VEC_MB=160
export MINCORE_DIAG=1

CGROUP_PATH=/sys/fs/cgroup/hnsw_l4_r5c

sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
echo "$((512 * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null

echo "============================================"
echo "  R5c: mincore diagnostic (512MB cgroup)"
echo "============================================"

# Move self into cgroup then run benchmark
exec bash -c "echo \$\$ > $CGROUP_PATH/cgroup.procs && exec build/benchmark_l4 \
  ../../output/sift1m_graph.bin ../../output/sift1m_bfs.bin \
  ../../output/sift1m_blocks_64k.bin ../../output/sift1m_route_64k.bin \
  ../../data/sift_base.fvecs ../../data/sift1m_query200.fvecs \
  ../../data/sift1m_gt200.bin 10 100 200"
