# Proposal: Close l4-cache-mgmt POC

> track: close
> 日期: 2026-08-06
> Status: Implemented
> Closes: l4-cache-mgmt (all directions explored)
> 关联: [[BEH-024]]、[[BEH-027]]、[[BEH-028]]、[[API-012]]、[[API-013]]、[[CON-SLA-014]]、[[CON-SLA-016]]、[[CON-SLA-018]]、[[DEC-068]]、[[DEC-070]]、[[DEC-073]]、[[DEC-074]]、[[DEC-075]]

## 1. 关闭理由

l4-cache-mgmt POC 已完成全部探索方向:

### 已 Promote 到 Trunk (3 项)

| 方向 | 条款 | 收益 |
|------|------|------|
| R4: flat_vec_cache in FineRerank | BEH-024, DEC-068 | 256MB 7.5x QPS |
| R5a: WILLNEED | BEH-024 amend, API-012, DEC-070 | 256MB 17.7x QPS |
| R2 D2: BG 页合并 | BEH-028, DEC-075 | 256MB 16T +17.5% QPS |

### 否定结果 (6 项)

| 方向 | 结果 | 原因 |
|------|------|------|
| R1: FINE_FADVISE | -17x QPS | 驱逐热 vecblock 页 |
| R5b: Selective DONTNEED (旧) | +14% (1T only) | 被 WILLNEED 取代 |
| R2 D3: DONTNEED (重测) | -18~27% | 与 WILLNEED_BG 冲突 |
| R2 D4: CACHE_MB 调优 | 无影响 | BlockCache 已 O_DIRECT |
| R2 D5: perf 重新定位 | 无单一瓶颈 >10% | 接近 Pareto 前沿 |
| R2 D6: readahead 窗口限制 | 无帮助 | WILLNEED 窗口已最优 |

### R5c mincore 诊断结论

- refault_file = 725 (两种 cgroup 相同) -> WILLNEED_BG 已消除容量缺失
- majfault ≈ 5,120 (冷缺失) -> 不可通过 L4 管理优化
- 页缓存在 Pareto 前沿

## 2. 主题状态变更

`l4-cache-mgmt` status: exploring -> **closed**

## 3. 不做的事

- 不 promote 任何否定方向
- 不新增 SLA 条款
- Trunk 无代码变更

## 4. 后续可能方向 (如果场景变化)

- 如果 DEEP10M 数据集变重要: L4 管理在 DEEP10M 上无效 (I/O 量是瓶颈)
- 如果切换到 SSD: mincore 诊断可能需要重做
- 如果 flat_vec_cache 架构变化 (如 LRU 替换 hash): D1 命中率诊断需重做
