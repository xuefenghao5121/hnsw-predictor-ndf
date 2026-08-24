#!/bin/bash
# run_l4_poc.sh - L4 Page Cache 主动管理 POC 测试
# 遵循 CON-SLA-014 严格隔离协议
set -euo pipefail

cd /home/huawei/hnsw-predictor-ndf/poc/l4-cache-mgmt
BIN=build/benchmark_l4

GRAPH=../../output/sift1m_graph.bin
BFS=../../output/sift1m_bfs.bin
BLOCKS=../../output/sift1m_blocks_64k.bin
ROUTE=../../output/sift1m_route_64k.bin
DATA=../../data/sift_base.fvecs
QUERY=../../data/sift1m_query200.fvecs
GT=../../data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=512
CGROUP_PATH=/sys/fs/cgroup/hnsw_l4_poc

export CACHE_MB=64
export TWO_STAGE=1
export FINE_RERANK=1
export VEC_BLOCKS_PATH=../../output/sift1m_vecblocks_64k.bin
export PQ_CODE_PATH=../../output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100
export FINE_PREAD=1
export EVICT_PAGE_CACHE=0
export NUM_THREADS=0  # 1T

run_round() {
    local name=$1
    shift
    
    echo ""
    echo "============================================"
    echo "  $name"
    echo "============================================"
    
    # drop_caches 清场 (CON-SLA-014)
    sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
    
    # 创建 cgroup
    sudo mkdir -p "$CGROUP_PATH"
    echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null
    
    # 后台监控
    local monitor_log="/tmp/l4_poc_${name// /_}.log"
    echo "" > "$monitor_log"
    (
        while true; do
            ts=$(date +%s%N)
            cur=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
            anon=$(grep "^anon " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            file=$(grep "^file " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
            echo "$ts $cur $anon $file" >> "$monitor_log"
            sleep 0.1
        done
    ) &
    local monitor_pid=$!
    
    # 加入 cgroup
    echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null
    
    # 运行 benchmark
    env "$@" $BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1
    
    # 收集统计
    echo ""
    echo "--- cgroup stats ---"
    echo "  memory.peak: $(cat $CGROUP_PATH/memory.peak) bytes"
    echo "  memory.events:"
    cat "$CGROUP_PATH/memory.events"
    echo "  memory.stat (key):"
    grep -E "^(anon|file|active_file|inactive_file|workingset_refault_file|pgmajfault)" "$CGROUP_PATH/memory.stat"
    echo "  Monitor peaks:"
    echo "    Peak anon (MB): $(awk '{if($3>m) m=$3} END{if(m>0) print m/1024/1024; else print 0}' "$monitor_log")"
    echo "    Peak file (MB): $(awk '{if($4>m) m=$4} END{if(m>0) print m/1024/1024; else print 0}' "$monitor_log")"
    echo "    Peak total (MB): $(awk '{if($2>m) m=$2} END{if(m>0) print m/1024/1024; else print 0}' "$monitor_log")"
    
    kill $monitor_pid 2>/dev/null || true
    wait $monitor_pid 2>/dev/null || true
    
    # 清理 cgroup
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
    sudo rmdir "$CGROUP_PATH" 2>/dev/null || true
}

# R0: True Buffered (FINE_BUFFERED=1, no fadvise, no evict)
run_round "R0 Buffered 1T" \
    FINE_BUFFERED=1 FINE_FADVISE=0 L4_EVICT_META=0

# R1: Buffered + FINE_FADVISE (evict vecblocks after read)
run_round "R1 Buffered+FADVISE 1T" \
    FINE_BUFFERED=1 FINE_FADVISE=1 L4_EVICT_META=0

# R2: Buffered + L4_EVICT_META (evict graph+BFS page cache after init)
run_round "R2 Buffered+EvictMeta 1T" \
    FINE_BUFFERED=1 FINE_FADVISE=0 L4_EVICT_META=1

# R3: Buffered + L4_EVICT_META + FINE_FADVISE (evict meta + evict vecblocks)
run_round "R3 Buffered+EvictMeta+FADVISE 1T" \
    FINE_BUFFERED=1 FINE_FADVISE=1 L4_EVICT_META=1

echo ""
echo "============================================"
echo "  R0-R3 完成"
echo "============================================"
