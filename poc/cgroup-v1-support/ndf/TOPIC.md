# TOPIC: cgroup-v1-support

> topic_id: cgroup-v1-support
> status: promoted
> baseline_protocol: [[CON-SLA-014]] + [[CON-SLA-016]] + [[CON-SLA-017]] + [[CON-SLA-018]]
> baseline_trunk_sha: b1022c7
> promote_trunk_sha: 8b0679f
> baseline_status: promoted
> explore_surface: test-infra,cgroup
> depends_on_topics: (none)
> binder: [[DEF-022]]

## Active hypothesis

当前测试脚本全部硬编码 cgroup v2 接口, 在 cgroup v1 平台上无法运行。
创建 `scripts/cgroup_utils.sh` 兼容层, 自动检测 v1/v2, 提供统一接口。

## 基线 (Trunk b1022c7)

脚本: `scripts/strict_baseline_sift1m.sh` (v2 hardcoded)
平台: Ubuntu 24.04, kernel 7.0.0, cgroup v2 (cgroup2fs)

## 实验进展

### R0: 创建 cgroup_utils.sh ✅
- 11 个函数: cg_detect_version / cg_init / cg_create / cg_set_limit /
  cg_get_memory / cg_get_peak / cg_check_violations / cg_stats_summary /
  cg_start_monitor / cg_stop_monitor / cg_verify / cg_destroy / cg_drop_caches
- 自动检测: stat -f '%T' /sys/fs/cgroup → cgroup2fs=v2, 有 memory/=v1
- hybrid 模式优先 v1 (保守)
- 严格验证: peak ≤ limit AND violations = 0
- 环境变量 CGROUP_FORCE_V1=1 支持强制 v1 (用于逻辑测试)

### R1: 改造 strict_baseline_sift1m.sh ✅
- 引入 source scripts/cgroup_utils.sh
- 所有硬编码路径替换为 cg_* 函数调用
- 支持 [cgroup_mb] 参数 (默认 512)
- 新增 sudo -v 缓存避免 prompt 挂起

### R2: v2 回归验证 ✅ (512MB 1T+4T)
| 指标 | 1T | 4T |
|------|-----|-----|
| Recall | 95.75% | 95.75% |
| QPS | 3,234 | 11,228 |
| peak | 512MB (= limit) | 512MB (= limit) |
| violations | 0 | 0 |
| Peak total (监控) | 512.08 MB | 512.00 MB |
| SLA | ✅ 通过 | ✅ 通过 |

**零回归确认** — 与改造前数据一致

### R3: v1 逻辑验证 ✅ (CGROUP_FORCE_V1=1)
- 版本检测: ✅ 输出 "v1"
- 路径构造: ✅ /sys/fs/cgroup/memory/<name>
- stat 字段映射: ✅ anon/file 正确解析
- OOM 检测: ✅ memory.failcnt > 0 (比 v2 更严格)
- swap 禁用: ✅ memory.memsw.limit_in_bytes=0 + swappiness=0
- 待真实 v1 平台验证

## 严格隔离机制 (核心设计)

### 用户要求: "不允许任何用户测试时产生偷用内存的行为被遗漏"

#### v2 严格性
- memory.events.oom + oom_kill > 0 → 违规
- memory.peak > memory.max → 违规
- 监控采样: anon + file + total 每 100ms

#### v1 严格性 (更严格)
- memory.failcnt > 0 → 违规 (任何分配被拒绝都算)
- memory.max_usage_in_bytes > memory.limit_in_bytes → 违规
- memory.memsw.limit_in_bytes = 0 → 禁止 swap 偷用
- memory.swappiness = 0 → 禁用 swap 倾向
- 监控采样: anon + file + total 每 100ms

#### v1 比 v2 更严格的点
1. **failcnt > 0 即违规**: v2 的 oom event 只在真正触发 OOM 时计数, v1 的 failcnt 在任何内存分配被拒绝时递增 (即使没有 kill)
2. **swap 禁用**: v1 显式禁用 swap (memsw.limit_in_bytes=0), v2 隐式 (memory.swap.max 默认 0)

## Next gate

- [x] R0: 创建 cgroup_utils.sh ✅
- [x] R1: 改造 strict_baseline_sift1m.sh ✅
- [x] R2: v2 回归验证 (零回归) ✅
- [x] R3: v1 逻辑验证 (CGROUP_FORCE_V1=1) ✅
- [ ] 决策: promote (等用户指令)

## Draft clauses

_(none — promoted to Trunk)_

## Promoted clauses

| ID | In spec/? | Notes |
|----|-----------|-------|
| BEH-032 | yes (`status=stable`) | cgroup v1/v2 自动检测行为 |
| API-016 | yes (`status=stable`) | cgroup_utils.sh 函数接口 |
| DEC-079 | yes | cgroup v1 stat 字段映射 + failcnt 严格策略 |

## Proposals

| Role | Path | Status |
|------|------|--------|
| root | `../../spec/open/proposal-cgroup-v1-support.md` | Implemented (promoted) |

## Evidence

| ID | Path | Description |
|----|------|-------------|
| R2-v2 | /tmp/cgroup_v2_512.log | v2 回归 512MB 1T+4T (零回归) |
| R2-mon-1t | /tmp/cgroup_monitor_sift1m_baseline.log | v2 1T 监控采样 |
| R2-mon-4t | /tmp/cgroup_monitor_sift1m_baseline_4t.log | v2 4T 监控采样 |
| R3-v1 | (stdout) | v1 逻辑验证 (FORCE_V1=1) |

## Commits

见 [COMMITS.md](COMMITS.md)
