#!/bin/bash
# strict_baseline_sift1m.sh - SIFT1M 严格 cgroup 隔离基线测试
# 遵循 CON-SLA-014 协议
# 用法: bash scripts/strict_baseline_sift1m.sh
set -euo pipefail

cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_diskhnsw

# 数据文件
GRAPH=output/sift1m_graph.bin
BFS=output/sift1m_bfs.bin
BLOCKS=output/sift1m_blocks_64k.bin
ROUTE=output/sift1m_route_64k.bin
DATA=data/sift_base.fvecs
QUERY=data/sift1m_query200.fvecs
GT=data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

CGROUP_MB=512
CGROUP_PATH=/sys/fs/cgroup/hnsw_strict_baseline

echo "============================================"
echo "  SIFT1M 严格 cgroup 隔离基线测试"
echo "  协议: CON-SLA-014"
echo "  cgroup: ${CGROUP_MB}MB"
echo "============================================"

# ============================================================
# Step 1: drop_caches 清场 (CON-SLA-014 协议第1步)
# ============================================================
echo ""
echo "=== Step 1: drop_caches 清场 ==="
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
echo "  drop_caches done"

# ============================================================
# Step 2: 创建 cgroup (CON-SLA-014 协议第2步)
# ============================================================
echo ""
echo "=== Step 2: 创建 cgroup (${CGROUP_MB}MB) ==="
sudo mkdir -p "$CGROUP_PATH"
echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null
echo "  memory.current (before): $(cat $CGROUP_PATH/memory.current) bytes"
echo "  memory.peak (before): $(cat $CGROUP_PATH/memory.peak) bytes"

# ============================================================
# Step 3: 后台 cgroup 监控 (CON-SLA-014 协议第4步)
# ============================================================
MONITOR_LOG="/tmp/cgroup_monitor_sift1m_baseline.log"
echo "" > "$MONITOR_LOG"
(
    while true; do
        ts=$(date +%s%N)
        cur=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
        anon=$(grep "^anon " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$MONITOR_LOG"
        sleep 0.1
    done
) &
MONITOR_PID=$!

# ============================================================
# Step 4: 将当前 shell 加入 cgroup (CON-SLA-014 协议第2步)
# ============================================================
echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null

# ============================================================
# Step 5: 环境变量
# ============================================================
export CACHE_MB=64
export TWO_STAGE=1
export FINE_RERANK=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODE_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100
export FINE_PREAD=1
export EVICT_PAGE_CACHE=0
export NUM_THREADS=0  # 1T

# ============================================================
# Step 6: 运行 Buffered benchmark (CON-SLA-014 协议第3步)
# ============================================================
echo ""
echo "=== Step 6a: Buffered 1T ==="
$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 | tee /tmp/bench_strict_sift1m_buffered_1t.log

# ============================================================
# Step 7: 收集 cgroup 统计
# ============================================================
echo ""
echo "=== Step 7: cgroup 统计 (Buffered 1T) ==="
echo "  memory.current: $(cat $CGROUP_PATH/memory.current) bytes"
echo "  memory.peak:    $(cat $CGROUP_PATH/memory.peak) bytes"
echo "  memory.events:"
cat "$CGROUP_PATH/memory.events"
echo ""
echo "  memory.stat (key fields):"
grep -E "^(anon|file|slab|file_mapped|file_dirty|active_anon|inactive_anon|active_file|inactive_file|workingset_refault|pgmajfault|pgfault)" "$CGROUP_PATH/memory.stat"
echo ""
echo "  Monitor peaks:"
echo "    Peak anon (MB): $(awk '{if($3>m) m=$3} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"
echo "    Peak file (MB): $(awk '{if($4>m) m=$4} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"
echo "    Peak total (MB): $(awk '{if($2>m) m=$2} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"

# Stop monitor
kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

# ============================================================
# Step 8: 4T Buffered (需要重新 drop_caches)
# ============================================================
echo ""
echo "=== Step 8: 重新清场 + 4T Buffered ==="
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

# Reset monitor
MONITOR_LOG4="/tmp/cgroup_monitor_sift1m_baseline_4t.log"
echo "" > "$MONITOR_LOG4"
(
    while true; do
        ts=$(date +%s%N)
        cur=$(cat "$CGROUP_PATH/memory.current" 2>/dev/null)
        anon=$(grep "^anon " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        file=$(grep "^file " "$CGROUP_PATH/memory.stat" 2>/dev/null | awk '{print $2}')
        echo "$ts $cur $anon $file" >> "$MONITOR_LOG4"
        sleep 0.1
    done
) &
MONITOR_PID=$!

export NUM_THREADS=4
$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 | tee /tmp/bench_strict_sift1m_buffered_4t.log

echo ""
echo "=== cgroup 统计 (Buffered 4T) ==="
echo "  memory.peak: $(cat $CGROUP_PATH/memory.peak) bytes"
echo "  memory.events:"
cat "$CGROUP_PATH/memory.events"
echo ""
echo "  memory.stat (key fields):"
grep -E "^(anon|file|active_file|inactive_file|workingset_refault|pgmajfault)" "$CGROUP_PATH/memory.stat"
echo ""
echo "  Monitor peaks:"
echo "    Peak anon (MB): $(awk '{if($3>m) m=$3} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"
echo "    Peak file (MB): $(awk '{if($4>m) m=$4} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"
echo "    Peak total (MB): $(awk '{if($2>m) m=$2} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"

kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

# ============================================================
# Step 9: O_DIRECT 1T (重新 drop_caches)
# ============================================================
echo ""
echo "=== Step 9: 重新清场 + O_DIRECT 1T ==="
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

export FINE_DIRECT=1
export FINE_PREAD=0  # O_DIRECT 模式不用 pread
export NUM_THREADS=0

$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 | tee /tmp/bench_strict_sift1m_odirect_1t.log

echo ""
echo "=== cgroup 统计 (O_DIRECT 1T) ==="
echo "  memory.peak: $(cat $CGROUP_PATH/memory.peak) bytes"
echo "  memory.events:"
cat "$CGROUP_PATH/memory.events"
grep -E "^(anon|file|workingset_refault|pgmajfault)" "$CGROUP_PATH/memory.stat"

# ============================================================
# Step 10: O_DIRECT 4T (重新 drop_caches)
# ============================================================
echo ""
echo "=== Step 10: 重新清场 + O_DIRECT 4T ==="
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

export NUM_THREADS=4

$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 | tee /tmp/bench_strict_sift1m_odirect_4t.log

echo ""
echo "=== cgroup 统计 (O_DIRECT 4T) ==="
echo "  memory.peak: $(cat $CGROUP_PATH/memory.peak) bytes"
echo "  memory.events:"
cat "$CGROUP_PATH/memory.events"
grep -E "^(anon|file|workingset_refault|pgmajfault)" "$CGROUP_PATH/memory.stat"

# ============================================================
# Step 11: 清理
# ============================================================
echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
sudo rmdir "$CGROUP_PATH" 2>/dev/null || true

echo ""
echo "============================================"
echo "  测试完成。结果日志:"
echo "  /tmp/bench_strict_sift1m_buffered_1t.log"
echo "  /tmp/bench_strict_sift1m_buffered_4t.log"
echo "  /tmp/bench_strict_sift1m_odirect_1t.log"
echo "  /tmp/bench_strict_sift1m_odirect_4t.log"
echo "  cgroup 监控:"
echo "  /tmp/cgroup_monitor_sift1m_baseline.log"
echo "  /tmp/cgroup_monitor_sift1m_baseline_4t.log"
echo "============================================"
