# Proposal: cgroup v1 严格内存限制测试方案

> track: boundary (测试方案拓展)
> 日期: 2026-08-06
> Status: **draft (待审核)**
> 关联: [[CON-SLA-014]]、[[CON-SLA-016]]、[[CON-SLA-017]]、[[CON-SLA-018]]、[[BEH-024]]、[[DEC-005]]

## 1. 背景与动机

### 1.1 当前状态

项目所有测试脚本和 SLA 协议均基于 **cgroup v2** (unified hierarchy)。当前开发平台
(Ubuntu 24.04, kernel 7.0.0) 使用 cgroup v2 (`cgroup2fs`)。

测试脚本 `scripts/strict_baseline_sift1m.sh` 和 POC 脚本中的 cgroup 操作全部使用 v2 接口。

### 1.2 问题

**部分目标平台使用 cgroup v1**，包括：

| 平台 | OS | cgroup 版本 | 说明 |
|------|-----|------------|------|
| 鲲鹏 930 (openEuler 24.03) | Linux 6.6 | v1 (hybrid) | 默认 v1, 可切 v2 |
| CentOS 7 / RHEL 7 | Linux 3.10 | v1 only | 老旧服务器常见 |
| Debian 10 (buster) | Linux 4.19 | v1 (hybrid) | 默认 v1 |
| Docker 默认配置 | - | v1 (多数) | 容器化场景常见 |

**cgroup v1 和 v2 的接口完全不同**，当前脚本在 v1 平台上无法运行。

### 1.3 cgroup v1 vs v2 接口差异

| 操作 | cgroup v2 (当前) | cgroup v1 (需支持) |
|------|-----------------|-------------------|
| 挂载点 | `/sys/fs/cgroup/` (unified) | `/sys/fs/cgroup/memory/` (memory controller) |
| 创建 cgroup | `mkdir /sys/fs/cgroup/<name>` | `mkdir /sys/fs/cgroup/memory/<name>` |
| **设置内存限制** | `echo VAL > memory.max` | `echo VAL > memory.limit_in_bytes` |
| 当前内存用量 | `memory.current` | `memory.usage_in_bytes` |
| 内存峰值 | `memory.peak` | `memory.max_usage_in_bytes` |
| **OOM 事件** | `memory.events` (含 oom, oom_kill) | `memory.oom_control` + `memory.failcnt` |
| 统计信息 | `memory.stat` (anon, file, ...) | `memory.stat` (字段名不同) |
| 进程加入 | `cgroup.procs` | `cgroup.procs` (相同) |
| drop caches | `echo 3 > /proc/sys/vm/drop_caches` | 相同 |

**关键差异:**

1. **路径不同**: v2 在统一层级下, v1 在 memory controller 子层级下
2. **文件名不同**: `memory.max` vs `memory.limit_in_bytes` 等
3. **OOM 检测不同**: v2 用 `memory.events`, v1 用 `memory.oom_control` + `memory.failcnt`
4. **stat 字段名部分不同**: v2 有 `anon`/`file`, v1 有 `total_inactive_anon`/`total_active_file` 等

### 1.4 stat 字段映射

| 指标 | cgroup v2 | cgroup v1 |
|------|-----------|-----------|
| 匿名内存 | `anon` | `(total_active_anon + total_inactive_anon)` |
| 文件缓存 | `file` | `(total_active_file + total_inactive_file)` |
| slab | `slab` | `total_slab` (近似, v1 有 per-cpu 误差) |
| refault | `workingset_refault_file` | `workingset_refault` (不区分 file/anon) |
| major fault | `pgmajfault` | `total_pgmajfault` |
| minor fault | `pgfault` | `total_pgfault` |

## 2. 提议的方案

### 2.1 核心原则: 自动检测 + 统一接口

创建 `scripts/cgroup_utils.sh` 工具库，自动检测 cgroup 版本并提供统一函数：

```bash
# scripts/cgroup_utils.sh - cgroup v1/v2 兼容工具库

# 检测 cgroup 版本
cg_detect_version() {
    if stat -f -c '%T' /sys/fs/cgroup/ 2>/dev/null | grep -q cgroup2fs; then
        echo "v2"
    elif [ -d /sys/fs/cgroup/memory ]; then
        echo "v1"
    else
        echo "unknown"
    fi
}

# 创建 cgroup
cg_create() {
    local name=$1
    local ver=$(cg_detect_version)
    case $ver in
        v2) sudo mkdir -p "/sys/fs/cgroup/$name" ;;
        v1) sudo mkdir -p "/sys/fs/cgroup/memory/$name" ;;
    esac
}

# 设置内存限制 (MB)
cg_set_limit() {
    local name=$1 mb=$2
    local bytes=$((mb * 1024 * 1024))
    case $(cg_detect_version) in
        v2) echo "$bytes" | sudo tee "/sys/fs/cgroup/$name/memory.max" > /dev/null ;;
        v1) echo "$bytes" | sudo tee "/sys/fs/cgroup/memory/$name/memory.limit_in_bytes" > /dev/null ;;
    esac
}

# 获取当前内存用量 (bytes)
cg_get_current() {
    case $(cg_detect_version) in
        v2) cat "/sys/fs/cgroup/$CGROUP_NAME/memory.current" 2>/dev/null ;;
        v1) cat "/sys/fs/cgroup/memory/$CGROUP_NAME/memory.usage_in_bytes" 2>/dev/null ;;
    esac
}

# 获取内存峰值 (bytes)
cg_get_peak() { ... }

# 检查 OOM
cg_check_oom() { ... }

# 获取统计信息 (统一格式输出)
cg_get_stats() { ... }

# 将进程加入 cgroup
cg_add_proc() { ... }
```

### 2.2 改造现有脚本

`scripts/strict_baseline_sift1m.sh` 改为 source `cgroup_utils.sh`，将所有硬编码的
v2 路径替换为兼容函数调用。

### 2.3 具体改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `scripts/cgroup_utils.sh` | **新建** | v1/v2 兼容工具库 (~100 行) |
| `scripts/strict_baseline_sift1m.sh` | 改造 | 引用 cgroup_utils.sh, 替换硬编码路径 |
| `docs/detailed-design.md` | 更新 | 5.1 节补充 v1/v2 双协议说明 |
| `README.md` | 更新 | cgroup 隔离测试说明补充 v1 支持 |

### 2.4 不做的事

- 不改 C++ 源代码 (cgroup 操作只在测试脚本中)
- 不改 NDF spec 条款 (SLA 条款描述行为不涉及接口)
- 不做 cgroup v1 性能验证 (无 v1 平台)
- 不处理 cgroup v1 的 hierarchy 复杂性 (只使用 leaf node)

## 3. 设计细节

### 3.1 cgroup_utils.sh 接口

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `cg_detect_version` | 无 | `v2` / `v1` / `unknown` | 检测当前系统 cgroup 版本 |
| `cg_create` | name | 无 | 创建 cgroup (v1: memory controller) |
| `cg_set_limit` | name, MB | 无 | 设置内存限制 |
| `cg_get_current` | name | bytes | 当前内存用量 |
| `cg_get_peak` | name | bytes | 内存峰值 |
| `cg_check_oom` | name | `0` / `1` | 是否发生 OOM (v2: events.oom_kill, v1: oom_control) |
| `cg_get_stat` | name, field | value | 获取指定统计字段 (统一字段名) |
| `cg_get_stats_summary` | name | 多行文本 | 输出关键统计 (anon/file/refault/majfault) |
| `cg_add_proc` | name, pid | 无 | 将进程加入 cgroup |
| `cg_destroy` | name | 无 | 删除 cgroup |

### 3.2 统一 stat 字段

`cg_get_stats_summary` 输出统一格式（屏蔽 v1/v2 差异）:

```
anon:           209715200    # 匿名内存 (bytes)
file:           66060288     # 文件缓存 (bytes)
workingset_refault: 725      # 页面回收重用计数
pgmajfault:     5114         # major page fault
pgfault:        123456       # minor page fault
oom:            0            # OOM kill 次数
```

### 3.3 OOM 检测差异处理

**v2:**
```bash
# memory.events 包含 oom 和 oom_kill 计数
oom_kill=$(grep "^oom_kill " /sys/fs/cgroup/$name/memory.events | awk '{print $2}')
```

**v1:**
```bash
# 方案 A: memory.oom_control (需要 enabling)
# 方案 B: memory.failcnt (超过限制的次数, 作为 OOM 近似)
failcnt=$(cat /sys/fs/cgroup/memory/$name/memory.failcnt)
# v1 的 failcnt > 0 表示有内存分配被拒绝, 不完全等于 OOM kill
# 但在严格测试中, failcnt > 0 即视为违规
```

### 3.4 hybrid 模式处理

部分系统 (如 openEuler) 支持 hybrid 模式 (v1 + v2 共存)。`cg_detect_version` 的策略：

1. 先检查 `/sys/fs/cgroup/` 是否为 `cgroup2fs` → v2
2. 否则检查 `/sys/fs/cgroup/memory/` 是否存在 → v1
3. 如果两者都存在 (hybrid)，优先 v1 (保守选择，因为 v2 在 hybrid 下可能未启用 memory controller)

## 4. 验证计划

### 4.1 x86 (cgroup v2) 回归

```bash
# 当前平台, 确保改造后 v2 路径零回归
bash scripts/strict_baseline_sift1m.sh
# 结果应与改造前一致
```

### 4.2 v1 逻辑验证 (模拟)

当前无 cgroup v1 平台，但可验证脚本的 v1 分支逻辑：

```bash
# 强制使用 v1 路径 (即使系统是 v2, 验证代码路径正确性)
CGROUP_FORCE_V1=1 bash scripts/strict_baseline_sift1m.sh
# 预期: 检测到 v1 路径不存在, 输出 warning 并回退 v2 或跳过
```

### 4.3 待 ARM 平台验证

有真实 cgroup v1 平台后：

```bash
# openEuler 24.03 (鲲鹏 930)
bash scripts/strict_baseline_sift1m.sh
# 应自动检测 v1 并使用正确接口
```

## 5. 草稿条款

| ID | 类型 | 描述 |
|----|------|------|
| BEH-032 (draft) | behavior | cgroup v1/v2 自动检测行为 |
| API-016 (draft) | interface | cgroup_utils.sh 函数接口 |
| DEC-079 (draft) | decision | cgroup v1 stat 字段映射策略 |
| VER-025 (draft) | verification | cgroup v1 平台验证协议 |

## 6. 不影响现有条款

现有 CON-SLA-014/016/017/018 描述的是**行为和结果** (recall ≥95%, oom=0, peak ≤limit),
不涉及 cgroup 接口细节。本提案不影响这些条款的语义，只补充实现路径。

---

**审核要点:**

1. ✅ 改动范围明确 (1 个新文件 + 1 个改文件 + 2 个文档更新)
2. ✅ 不改 C++ 源码 (cgroup 操作只在测试脚本)
3. ✅ 不改 NDF spec 条款语义
4. ✅ v2 回归零影响 (自动检测, v2 路径不变)
5. ⚠️ 无真实 v1 平台验证 (仅逻辑验证, 待 ARM 平台)
6. ⚠️ v1 stat 字段映射有精度差异 (workingset_refault 不区分 file/anon)
