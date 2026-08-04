# 无白嫖 Page Cache 测试方案

> 目标：在 cgroup 限制下，确保 benchmark **不能**使用超出 cgroup 限制的任何内存（包括 page cache）。
> 模拟真实物理机场景：机器只有 N MB RAM，进程 + OS cache 必须全部装在 N MB 内。

---

## 1. 记账陷阱根因分析

### 1.1 为什么会有 root cgroup 和 benchmark cgroup？

cgroup v2 是**树形结构**：

```
/sys/fs/cgroup/          <- root cgroup (系统默认)
├── cgroup.procs         <- 所有未被显式分配的进程
├── hnsw_bench/          <- benchmark cgroup (我们创建的)
│   ├── memory.max       <- 512MB / 2GB
│   └── cgroup.procs     <- benchmark 进程
└── ...
```

**根因**：数据准备阶段（build_index, write_blocks, bfs_reorder 等 pipeline 工具）在**用户 shell 的默认 cgroup（root）**中运行。这些工具读写了 vecblocks、graph、PQ codes 等文件，OS 把文件页缓存到 page cache，**记账归属 root cgroup**。

当 benchmark 进程随后被放入 `hnsw_bench/` cgroup 并读取同一文件时：

```
cgroup v2 page cache 记账规则：谁先读，谁付钱

1. build_index (root cgroup) 写了 vecblocks.bin
   -> 文件页在 page cache 中，记账: root cgroup

2. benchmark (hnsw_bench cgroup, 512MB) 读 vecblocks.bin
   -> 页面已在 cache -> 直接命中
   -> 不重新记账! 仍归属 root cgroup
   -> benchmark 的 memory.file 不增长
```

### 1.2 三个统计陷阱

| 陷阱 | 描述 | 影响 |
|------|------|------|
| **陷阱1：首次读取归属** | page cache 记账归属"首次读取者"，不是"当前使用者" | benchmark 白嫖 root 的 cache |
| **陷阱2：RSS 不含 page cache** | `/proc/self/status` VmRSS 只含匿名页 + mmap 映射页，不含 `read()` 产生的 page cache | RSS 看着小，实际可用内存远超 cgroup 限制 |
| **陷阱3：memory.current 漏计** | cgroup `memory.current = anon + file`，但 `file` 只算本 cgroup 首次读取的页 | 别人读过的页对你是"免费"的 |

### 1.3 当前代码中的相关机制

项目已有部分工具，但不完整：

| 机制 | 状态 | 局限 |
|------|------|------|
| `EVICT_PAGE_CACHE=1` | 每次查询后 `posix_fadvise(DONTNEED)` 驱逐 vecblocks | 只驱逐 vecblocks，不驱逐 graph/PQ/route |
| `FINE_DIRECT=1` | O_DIRECT 读 vecblocks（绕过 page cache） | 只对 fine rerank 路径，不覆盖 BlockCache |
| `O_DIRECT` in BlockCache | BlockCache 可选 O_DIRECT | 需 `use_odirect=true` 传入 |
| `drop_caches` | 未使用 | 需要 root，全局影响 |

**核心缺口**：graph（587MB）、PQ codes（31MB SIFT1M / 305MB DEEP10M）、route（3.9MB）、BFS（7.7MB）这些文件全部是 `ifstream` buffered 读，走的 page cache，且在 benchmark 启动前已被 root cgroup 预热。

---

## 2. 测试方案设计

### 2.1 方案选择

| 方案 | 描述 | 严格度 | 可行性 |
|------|------|--------|--------|
| A. 全量 drop_caches | benchmark 前 `echo 3 > /proc/sys/vm/drop_caches` | ⭐⭐⭐ | 需要 root，全局影响 |
| B. posix_fadvise 逐文件驱逐 | 对每个数据文件调用 DONTNEED | ⭐⭐⭐ | 不需要全局 root（只需文件 fd） |
| C. 全程 O_DIRECT | 所有文件 I/O 都用 O_DIRECT | ⭐⭐⭐ | 改动大，graph/PQ 需重写 I/O |
| D. 全程在 cgroup 内运行 | 数据准备也在 cgroup 内完成 | ⭐⭐ | 数据准备可能需要更多内存 |
| **E. 混合方案（推荐）** | drop_caches + cgroup 内启动 + 分层监控 | ⭐⭐⭐ | 最实用 |

**推荐方案 E**：`drop_caches` 清场 → benchmark 在 cgroup 内启动 → 所有 I/O 重新在 cgroup 内记账 → 分层监控验证。

### 2.2 测试脚本设计

```bash
#!/bin/bash
# strict_cgroup_bench.sh - 无白嫖 page cache 严格测试
# 用法: ./strict_cgroup_bench.sh <dataset> <cgroup_mb> [extra env...]
set -euo pipefail

DATASET="${1:?Usage: $0 <sift1m|deep10m> <cgroup_mb> [ENV=val ...]}"
CGROUP_MB="${2:?}"
shift 2

cd /home/huawei/hnsw-predictor-ndf
BIN=build/benchmark_diskhnsw

# ============================================================
# 数据文件路径
# ============================================================
if [ "$DATASET" = "sift1m" ]; then
    GRAPH=output/sift1m_graph.bin
    BFS=output/sift1m_bfs.bin
    BLOCKS=output/sift1m_blocks_64k.bin
    ROUTE=output/sift1m_route_64k.bin
    VECBLOCKS=output/sift1m_vecblocks_64k.bin
    PQCODES=output/pqco_sift1m_M32_correct.bin
    DATA=data/sift_base.fvecs
    QUERY=data/sift1m_query200.fvecs
    GT=output/sift1m_gt200.bin
    K=10; EF=100; NUMQ=10000
elif [ "$DATASET" = "deep10m" ]; then
    GRAPH=output/deep10m_graph.bin
    BFS=output/deep10m_bfs.bin
    BLOCKS=output/deep10m_blocks_64k.bin
    ROUTE=output/deep10m_vecblocks_64k_route.bin
    VECBLOCKS=output/deep10m_vecblocks_64k.bin
    PQCODES=output/pqco_deep10m_M32.bin
    DATA=data/deep10m_base.fvecs
    QUERY=data/deep10m_query.fvecs
    GT=output/deep10m_gt.bin
    K=10; EF=300; NUMQ=10000
else
    echo "Unknown dataset: $DATASET"; exit 1
fi

CGROUP_PATH=/sys/fs/cgroup/hnsw_strict_$$

# ============================================================
# Step 1: 清场 - 驱逐所有 page cache
# ============================================================
echo "=== Step 1: Evicting ALL page cache ==="
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
echo "  drop_caches done"

# 验证: 检查目标文件是否还在 cache 中
# 用 fincore (linux-tools) 或 mincore 程序
if command -v fincore &>/dev/null; then
    echo "  fincore check (before benchmark):"
    fincore "$VECBLOCKS" "$GRAPH" "$PQCODES" 2>/dev/null || true
fi

# ============================================================
# Step 2: 创建 cgroup
# ============================================================
echo "=== Step 2: Creating cgroup (limit=${CGROUP_MB}MB) ==="
sudo mkdir -p "$CGROUP_PATH"
echo "$((CGROUP_MB * 1024 * 1024))" | sudo tee "$CGROUP_PATH/memory.max" > /dev/null

# 记录初始状态
echo "  memory.current (before): $(cat $CGROUP_PATH/memory.current) bytes"
echo "  memory.peak (before): $(cat $CGROUP_PATH/memory.peak) bytes"

# ============================================================
# Step 3: 在 cgroup 内运行 benchmark
# ============================================================
echo "=== Step 3: Running benchmark INSIDE cgroup ==="

# 环境变量
export CACHE_MB=64
export TWO_STAGE=1
export FINE_RERANK=1
export VEC_BLOCKS_PATH="$VECBLOCKS"
export PQ_CODE_PATH="$PQCODES"  
export REFINE_EF=$EF
export FINE_PREAD=1
# 关闭 EVICT_PAGE_CACHE - 我们要在严格模式下看真实的 page cache 行为
export EVICT_PAGE_CACHE=0

# 附加环境变量
for env_arg in "$@"; do
    export "$env_arg"
done

# 将当前 shell 加入 cgroup，然后运行 benchmark
echo $$ | sudo tee "$CGROUP_PATH/cgroup.procs" > /dev/null

# 启动后台 cgroup 监控 (每 100ms 采样)
MONITOR_LOG="/tmp/cgroup_monitor_$$.$DATASET.log"
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

# 运行 benchmark
$BIN "$GRAPH" "$BFS" "$BLOCKS" "$ROUTE" "$DATA" "$QUERY" "$GT" $K $EF $NUMQ 2>&1 | tee /tmp/bench_strict_$$.$DATASET.log
BENCH_EXIT=$?

# 停止监控
kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

# ============================================================
# Step 4: 收集 cgroup 内存统计
# ============================================================
echo ""
echo "=== Step 4: Cgroup memory statistics ==="
echo "  memory.current (after): $(cat $CGROUP_PATH/memory.current) bytes"
echo "  memory.peak:            $(cat $CGROUP_PATH/memory.peak) bytes"
echo "  memory.events:"
cat "$CGROUP_PATH/memory.events"
echo ""
echo "  memory.stat (key fields):"
grep -E "^(anon|file|slab|file_mapped|file_dirty|active_anon|inactive_anon|active_file|inactive_file|workingset_refault|pgmajfault|pgfault)" "$CGROUP_PATH/memory.stat"

echo ""
echo "  Monitor log: $MONITOR_LOG"
echo "  Peak anon (MB): $(awk '{if($3>m) m=$3} END{print m/1024/1024}' "$MONITOR_LOG")"
echo "  Peak file (MB): $(awk '{if($4>m) m=$4} END{print m/1024/1024}' "$MONITOR_LOG")"
echo "  Peak total (MB): $(awk '{if($2>m) m=$2} END{print m/1024/1024}' "$MONITOR_LOG")"

# ============================================================
# Step 5: 验证 - 检查 benchmark 后哪些文件在 page cache 中
# ============================================================
echo ""
echo "=== Step 5: Post-benchmark page cache check ==="
if command -v fincore &>/dev/null; then
    echo "  fincore (after benchmark):"
    fincore "$VECBLOCKS" "$GRAPH" "$PQCODES" "$BFS" "$ROUTE" 2>/dev/null || true
fi

# ============================================================
# Step 6: 清理
# ============================================================
echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>/dev/null || true
sudo rmdir "$CGROUP_PATH" 2>/dev/null || true

exit $BENCH_EXIT
```

### 2.3 对照实验矩阵

跑 4 组对照，确保白嫖 vs 无白嫖的差异可见：

| 实验组 | cgroup | drop_caches | O_DIRECT | 描述 |
|--------|--------|-------------|----------|------|
| **A: 白嫖基线** | 无 | 否 | 否 | 当前默认行为，page cache 任意白嫖 |
| **B: cgroup 但不清 cache** | 512MB | 否 | 否 | 有 cgroup 限制但 page cache 已被 root 预热 |
| **C: cgroup + 清 cache** | 512MB | 是 | 否 | 严格模式，所有 I/O 在 cgroup 内重新记账 |
| **D: cgroup + 清 cache + O_DIRECT** | 512MB | 是 | 是 | 极端严格，vecblocks 走 O_DIRECT 不进 page cache |

### 2.4 执行脚本

```bash
#!/bin/bash
# run_strict_matrix.sh - 跑 4 组对照
set -euo pipefail
cd /home/huawei/hnsw-predictor-ndf

DATASET="${1:-sift1m}"
CGROUP_MB="${2:-512}"

echo "============================================"
echo "  Strict Cgroup Test Matrix: $DATASET @ ${CGROUP_MB}MB"
echo "============================================"

# A: 无 cgroup, 无 drop (白嫖基线)
echo ""
echo ">>> [A] No cgroup, no drop_caches (freeloading baseline)"
sudo bash -c 'echo $$ > /sys/fs/cgroup/cgroup.procs' 2>/dev/null || true
CGROUP_MB=0 bash strict_cgroup_bench.sh "$DATASET" 999999 2>&1 | grep -E "Recall|QPS|RSS|Step|memory\."

# B: cgroup 但不清 cache (部分白嫖)
echo ""
echo ">>> [B] cgroup=${CGROUP_MB}MB, NO drop_caches (partial freeloading)"
# 不调用 drop_caches, 直接创建 cgroup 跑
# 需要修改脚本跳过 Step 1, 或单独执行
NO_DROP=1 bash strict_cgroup_bench_nodrop.sh "$DATASET" "$CGROUP_MB" 2>&1 | grep -E "Recall|QPS|RSS|Step|memory\."

# C: cgroup + drop_caches (严格, 无白嫖)
echo ""
echo ">>> [C] cgroup=${CGROUP_MB}MB + drop_caches (strict, no freeloading)"
bash strict_cgroup_bench.sh "$DATASET" "$CGROUP_MB" 2>&1 | grep -E "Recall|QPS|RSS|Step|memory\.|Peak"

# D: cgroup + drop_caches + O_DIRECT (极端严格)
echo ""
echo ">>> [D] cgroup=${CGROUP_MB}MB + drop_caches + O_DIRECT (maximum strictness)"
bash strict_cgroup_bench.sh "$DATASET" "$CGROUP_MB" "FINE_DIRECT=1" 2>&1 | grep -E "Recall|QPS|RSS|Step|memory\.|Peak"
```

### 2.5 预期结果分析

#### SIFT1M @ 512MB cgroup 预期

| 组 | QPS | Recall | RSS | cgroup memory.peak | 分析 |
|----|-----|--------|-----|---------------------|------|
| A (白嫖) | ~2300 | 95.7% | ~243MB | N/A | vecblocks 496MB 全在 root cache, 白嫖 |
| B (部分白嫖) | ~2300 | 95.7% | ~243MB | ~300MB | graph/PQ 进 cgroup, vecblocks 仍白嫖 |
| C (严格) | ??? | 95.7% | ??? | ~500MB | vecblocks 也进 cgroup 记账, 可能触发回收 |
| D (O_DIRECT) | ??? | 95.7% | ??? | ~350MB | vecblocks 不进 page cache, 但 I/O 更慢 |

**C 组是关键**：
- 如果 QPS 明显下降 -> 说明 benchmark 确实在白嫖 page cache
- 如果 QPS 不变 -> 说明 flat_vec_cache (64MB 进程内缓存) 才是真正的热区, page cache 不是关键因素
- 我们之前的冷启动测试已经暗示是后者, 但那次只验证了 vecblocks, 没有验证 graph/PQ/route

#### DEEP10M @ 2GB cgroup 预期

| 组 | QPS | Recall | RSS | cgroup memory.peak |
|----|-----|--------|-----|---------------------|
| A (白嫖) | ~2340 | 95.1% | ~2422MB | N/A |
| C (严格) | ??? | 95.1% | ??? | ~2GB (逼近限制) |

DEEP10M 的 vecblocks 有 3.7GB，如果全部要在 2GB cgroup 内重新缓存：
- **核心数据**：CSR ~591MB + PQ ~305MB + upper vectors ~228MB = ~1.1GB
- 剩余 ~900MB 给 page cache 和匿名内存
- vecblocks 3.7GB 不可能全装入 -> 必然发生 page cache 回收 -> 可能影响 QPS

---

## 3. 监控指标定义

### 3.1 cgroup 内存指标（从 memory.stat 采集）

| 指标 | 含义 | 关注点 |
|------|------|--------|
| `memory.current` | 总内存 (anon + file) | 应 ≤ memory.max |
| `anon` | 匿名页 (堆/栈/数据结构) | 进程实际占用 |
| `file` | 文件页 (page cache, 本 cgroup 产生) | **关键指标**: 反映真实 I/O 缓存 |
| `active_file` | 活跃文件页 | 热数据 |
| `inactive_file` | 非活跃文件页 | 可被回收 |
| `workingset_refault_file` | 文件页回收后再次访问 | 高 = cache 抖动 |
| `pgmajfault` | major page fault | 高 = I/O 瓶颈 |
| `memory.peak` | 峰值内存 | 应 ≤ memory.max |

### 3.2 进程级指标

| 指标 | 来源 | 含义 |
|------|------|------|
| VmRSS | /proc/self/status | 进程 RSS (含 mmap, 不含 read page cache) |
| VmRSS + cgroup.file | 计算 | 真实内存足迹 |
| BlockCache hit% | benchmark 输出 | 进程内缓存命中率 |
| flat_vec_cache hit% | benchmark 输出 | 热向量缓存命中率 |

### 3.3 系统级验证

```bash
# 方法1: fincore 检查文件在 page cache 中的页数
fincore /path/to/vecblocks.bin
# 输出示例: filename, size, total_pages, cached_pages, cached_bytes

# 方法2: vmtouch 检查文件缓存状态
vmtouch -v /path/to/vecblocks.bin
# 输出示例: Files: 1, Directories: 0
#          Pages in core: 127232/127232 (100%)

# 方法3: 自写 mincore 程序 (项目已有)
# 在 benchmark 前后各跑一次, 对比变化
```

---

## 4. 为什么 drop_caches 是必要的

### 4.1 仅靠 cgroup 不够

```
仅创建 cgroup (不 drop_caches):

  root cgroup page cache
  ┌──────────────────────────────┐
  │ vecblocks 496MB (root 读过)  │  <- benchmark 白嫖这些页
  │ graph 587MB (root 读过)      │
  │ PQ codes 31MB (root 读过)    │
  └──────────────────────────────┘
  
  hnsw_bench cgroup (512MB)
  ┌──────────────────────────────┐
  │ anon: ~150MB (进程数据结构)  │
  │ file: ~50MB (cgroup 新读的)  │  <- 只记这部分
  │ 总计: ~200MB (远低于 512MB)  │  <- 看起来很安全, 实际在白嫖
  └──────────────────────────────┘
```

### 4.2 drop_caches 之后

```
drop_caches 后, benchmark 在 cgroup 内启动:

  root cgroup page cache
  ┌──────────────────────────────┐
  │ (空, 全部被驱逐)              │
  └──────────────────────────────┘
  
  hnsw_bench cgroup (512MB)
  ┌──────────────────────────────┐
  │ anon: ~150MB (进程数据结构)  │
  │ file: ~350MB (benchmark 首次  │  <- 全部记到 cgroup 头上!
  │   读 vecblocks/graph/PQ 产生) │
  │ 总计: ~500MB (逼近 512MB)    │  <- 真实压力!
  │                              │
  │ 如果 file 超过限制:           │
  │   -> kernel 回收 inactive_file│
  │   -> workingset_refault 上升  │
  │   -> QPS 可能下降             │
  └──────────────────────────────┘
```

---

## 5. 方案验证检查清单

- [ ] `drop_caches` 后 `fincore` 确认目标文件 cached_pages = 0
- [ ] benchmark 运行中 cgroup `memory.current` 始终 ≤ `memory.max`
- [ ] benchmark 运行中 `memory.events` 中 `oom` = 0 (没触发 OOM)
- [ ] benchmark 结束后 `memory.peak` 记录真实峰值
- [ ] 对照组 A vs C 的 QPS 差值 = page cache 白嫖的收益
- [ ] cgroup `file` 指标在 C 组显著大于 B 组 (证明记账生效)
- [ ] `workingset_refault_file` 在 C 组如果升高, 说明 cache 在抖动

---

## 6. 实施步骤

1. **安装 fincore/vmtouch 工具**
   ```bash
   sudo apt install linux-tools-common linux-tools-$(uname -r)  # fincore
   # 或
   sudo apt install vmtouch
   ```

2. **将 strict_cgroup_bench.sh 放到项目目录**
   ```bash
   cp strict_cgroup_bench.sh /home/huawei/hnsw-predictor-ndf/scripts/
   chmod +x /home/huawei/hnsw-predictor-ndf/scripts/strict_cgroup_bench.sh
   ```

3. **先跑 SIFT1M 对照**（快，~1分钟/组）
   ```bash
   cd /home/huawei/hnsw-predictor-ndf
   bash scripts/run_strict_matrix.sh sift1m 512
   ```

4. **再跑 DEEP10M 对照**（慢，~10分钟/组）
   ```bash
   bash scripts/run_strict_matrix.sh deep10m 2048
   ```

5. **分析结果**，重点看 C 组 vs A 组的 QPS 差异
