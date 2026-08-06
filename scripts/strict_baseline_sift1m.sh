#!/bin/bash
# strict_baseline_sift1m.sh - SIFT1M 严格 cgroup 隔离基线测试
# 遵循 CON-SLA-014 协议, 支持 cgroup v1/v2
# 用法: bash scripts/strict_baseline_sift1m.sh [cgroup_mb]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

# 引入 cgroup 兼容层
source scripts/cgroup_utils.sh

BIN=build/benchmark_diskhnsw
GRAPH=output/sift1m_graph.bin
BFS=output/sift1m_bfs.bin
BLOCKS=output/sift1m_blocks_64k.bin
ROUTE=output/sift1m_route_64k.bin
DATA=data/sift_base.fvecs
QUERY=data/sift1m_query200.fvecs
GT=data/sift1m_gt200.bin
K=10; EF=100; NUMQ=200

CGROUP_MB="${1:-512}"
CGROUP_NAME="hnsw_strict_baseline"

echo "============================================"
echo "  SIFT1M 严格 cgroup 隔离基线测试"
echo "  协议: CON-SLA-014"
echo "============================================"

# 确保 sudo 缓存 (避免后续 sudo prompt 导致挂起)
sudo -v 2>/dev/null || true

# ============================================================
# Step 1: 检测 cgroup 版本 + 初始化
# ============================================================
echo ""
echo "=== Step 1: cgroup 环境初始化 ==="
cg_init "$CGROUP_NAME" "$CGROUP_MB"

# ============================================================
# Step 2: drop_caches 清场 (严格隔离第一步)
# ============================================================
echo ""
echo "=== Step 2: drop_caches 清场 ==="
cg_drop_caches

# ============================================================
# Step 3: 创建 cgroup + 设置限制
# ============================================================
echo ""
echo "=== Step 3: 创建 cgroup (${CGROUP_MB}MB) ==="
cg_create
cg_set_limit "$CGROUP_MB"

echo "  初始内存状态:"
cg_stats_summary

# ============================================================
# Step 4: 启动后台内存监控
# ============================================================
MONITOR_LOG="/tmp/cgroup_monitor_sift1m_baseline.log"
cg_start_monitor "$MONITOR_LOG"
MONITOR_PID="$CG_MONITOR_PID"
echo "  监控已启动: PID=$MONITOR_PID, log=$MONITOR_LOG"

# ============================================================
# Step 5: 将当前 shell 加入 cgroup (严格隔离: 之后所有内存都被追踪)
# ============================================================
echo ""
echo "=== Step 5: 加入 cgroup ==="
cg_add_proc "$$"
echo "  PID $$ 已加入 $CG_PATH"

# ============================================================
# Step 6: 环境变量 (推荐配置)
# ============================================================
export CACHE_MB=64 TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1
export VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin
export PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin
export REFINE_EF=100 EVICT_PAGE_CACHE=0 NUM_THREADS=0
export L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14

if [ "$CGROUP_MB" = "256" ]; then
    export FLAT_VEC_MB=64 PAGE_MERGE_BG=1
else
    export FLAT_VEC_MB=160 PAGE_MERGE_BG=0
fi

# ============================================================
# Step 7: 运行 benchmark (1T)
# ============================================================
echo ""
echo "=== Step 7: Buffered 1T (${CG_VERSION}) ==="
$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 || true

# ============================================================
# Step 8: 收集统计 + 严格验证
# ============================================================
echo ""
echo "=== Step 8: cgroup 统计 + 严格验证 (1T) ==="
cg_stats_summary

echo ""
echo "=== 严格验证 ==="
if cg_verify; then
    echo "  ✅ SLA 通过"
else
    echo "  ❌ SLA 违规!"
fi

# 监控峰值
echo ""
echo "  监控峰值:"
echo "    Peak anon (MB):  $(awk '{if($3>m) m=$3} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"
echo "    Peak file (MB):  $(awk '{if($4>m) m=$4} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"
echo "    Peak total (MB): $(awk '{if($2>m) m=$2} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG")"

cg_stop_monitor "$MONITOR_PID"

# ============================================================
# Step 9: 多线程测试 (4T)
# ============================================================
echo ""
echo "=== Step 9: 重新清场 + 4T ==="
cg_drop_caches

MONITOR_LOG4="/tmp/cgroup_monitor_sift1m_baseline_4t.log"
cg_start_monitor "$MONITOR_LOG4"
MONITOR_PID="$CG_MONITOR_PID"

export NUM_THREADS=4
$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 || true

echo ""
echo "=== cgroup 统计 + 严格验证 (4T) ==="
cg_stats_summary

echo ""
echo "=== 严格验证 (4T) ==="
if cg_verify; then
    echo "  ✅ SLA 通过"
else
    echo "  ❌ SLA 违规!"
fi

echo ""
echo "  监控峰值 (4T):"
echo "    Peak anon (MB):  $(awk '{if($3>m) m=$3} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"
echo "    Peak file (MB):  $(awk '{if($4>m) m=$4} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"
echo "    Peak total (MB): $(awk '{if($2>m) m=$2} END{if(m>0) print m/1024/1024; else print 0}' "$MONITOR_LOG4")"

cg_stop_monitor "$MONITOR_PID"

# ============================================================
# Step 10: 清理
# ============================================================
echo ""
echo "=== Step 10: 清理 ==="
# 移出 cgroup (回到 root)
case "$CG_VERSION" in
    v2) echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true ;;
    v1) echo $$ | sudo tee /sys/fs/cgroup/memory/cgroup.procs > /dev/null 2>/dev/null || true ;;
esac
cg_destroy

echo ""
echo "============================================"
echo "  测试完成"
echo "  cgroup 版本: $CG_VERSION"
echo "  日志:"
echo "    /tmp/cgroup_monitor_sift1m_baseline.log"
echo "    /tmp/cgroup_monitor_sift1m_baseline_4t.log"
echo "============================================"
