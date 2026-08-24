# cgroup-v1-support - POC 笔记

> 提案: `../../spec/open/proposal-cgroup-v1-support.md`
> 基线: Trunk b1022c7
> 协议: [[CON-SLA-014]] + [[CON-SLA-016]] + [[CON-SLA-017]] + [[CON-SLA-018]]
> 状态: POC topic 已创建, 待用户审核

## 核心问题

当前测试脚本硬编码 cgroup v2 接口, v1 平台无法运行。
v1 vs v2 路径/文件名/OOM 检测/stat 字段均不同。

## 方案

创建 `scripts/cgroup_utils.sh` 兼容层:
- `cg_detect_version`: 检测 v1/v2
- `cg_create` / `cg_set_limit` / `cg_get_current` / `cg_get_peak`
- `cg_check_oom` / `cg_get_stats_summary`
- `cg_add_proc` / `cg_destroy`

改造 `strict_baseline_sift1m.sh` source 兼容层, 替换硬编码路径。

## 关键设计决策

1. **自动检测优先**: stat -f '%T' /sys/fs/cgroup/ → cgroup2fs = v2, 有 memory/ 子目录 = v1
2. **hybrid 模式**: 优先 v1 (保守, hybrid 下 v2 的 memory controller 可能未启用)
3. **stat 字段映射**: v1 的 workingset_refault 不区分 file/anon, 映射为统一字段名
4. **OOM 检测**: v1 用 memory.failcnt > 0 近似 (不完全等于 oom_kill, 但严格测试中足够)

## 不改的东西

- 不改 C++ 源代码 (cgroup 操作只在测试脚本)
- 不改 NDF spec 条款语义 (SLA 条款描述行为不涉及接口)
- 不做 cgroup v1 性能验证 (无 v1 平台)

## 实验计划

| 轮次 | 配置 | 目标 | 状态 |
|------|------|------|------|
| R0 | 创建 cgroup_utils.sh | 工具库 | pending |
| R1 | 改造 strict_baseline_sift1m.sh | 引用兼容层 | pending |
| R2 | v2 回归验证 | 零回归 | pending |
| R3 | v1 逻辑验证 (FORCE_V1=1) | 代码路径正确 | pending |
