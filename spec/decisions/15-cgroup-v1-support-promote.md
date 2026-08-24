# Decisions - cgroup v1/v2 兼容层 (DEC-079)

> 条款索引: `DEC-079`

## D-079: cgroup v1 stat 字段映射 + failcnt 严格策略 {#DEC-079}
<!-- ndf: kind=decision status=stable date=2026-08-06 affects=BEH-032,API-016 source=observed -->
<!-- ndf: depends-on=CON-SLA-014,CON-SLA-016 -->

> **track: promoted** - 提案 `spec/open/proposal-cgroup-v1-support.md`（2026-08-06）。
> source: poc/cgroup-v1-support/ndf/TOPIC.md ; ../../spec/open/proposal-cgroup-v1-support.md

### Context

cgroup v1 和 v2 的 stat 字段名不同，需要统一映射。同时 v1 的 OOM 检测机制
（`memory.failcnt`）与 v2（`memory.events`）语义不同。

### Decision

#### stat 字段映射

| 统一字段 | cgroup v2 | cgroup v1 |
|----------|-----------|-----------|
| anon | `anon` | `total_active_anon + total_inactive_anon` |
| file | `file` | `total_active_file + total_inactive_file` |
| workingset_refault | `workingset_refault_file` | `workingset_refault`（不区分 file/anon） |
| pgmajfault | `pgmajfault` | `total_pgmajfault` |
| pgfault | `pgfault` | `total_pgfault` |

**已知限制**: v1 的 `workingset_refault` 不区分 file/anon，精度略低于 v2。
在严格测试中不影响违规判定（违规由 failcnt 捕获）。

#### OOM/violation 检测策略

| 版本 | 检测文件 | 语义 | 严格性 |
|------|---------|------|--------|
| v2 | `memory.events` (oom, oom_kill) | 仅 OOM 事件 | 标准 |
| v1 | `memory.failcnt` | 任何内存分配被拒绝 | **更严格** |

**决策**: v1 下 `failcnt > 0` 即视为违规。这比 v2 更严格，因为：
- failcnt 在内核尝试分配内存超过 limit 时立即递增
- 即使内核通过 reclaim 避免了 OOM kill，failcnt 仍然计数
- 这意味着任何"偷用内存未遂"的行为都被捕获

#### swap 禁用

v1 MUST 显式禁用 swap：
- `memory.memsw.limit_in_bytes=0`（禁止 swap 总量）
- `memory.swappiness=0`（禁用 swap 倾向）

v2 默认 `memory.swap.max=0`，无需额外操作。

#### hybrid 模式处理

hybrid 模式（v1 + v2 共存）下优先选择 v1（保守策略），
因为 hybrid 下 v2 的 memory controller 可能未完全启用。

### Alternatives considered

1. **仅支持 v2**: 不可行，目标平台（openEuler/CentOS 7）使用 v1
2. **v1 用 oom_control 替代 failcnt**: 需要额外启用，且语义不如 failcnt 直接
3. **hybrid 下优先 v2**: 有风险，memory controller 可能未启用

> rationale: failcnt > 0 策略确保严格隔离要求（[[BEH-032]]）。
> v1 stat 字段映射的精度差异在 refault 维度可接受（不影响违规判定）。
> source: poc/cgroup-v1-support/ndf/TOPIC.md
