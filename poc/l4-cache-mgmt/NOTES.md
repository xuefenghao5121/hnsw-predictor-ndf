# L4 Page Cache 主动管理 - POC 笔记

> 提案: `spec/open/proposal-l4-cache-mgmt.md`（Implemented）
> 条款: [[BEH-024]] draft
> 基线: SIFT1M 严格隔离 ([[DEC-067]] 修正后)
> 状态: R0-R3 v2 + 紧 cgroup 实验 + O_DIRECT 4T bug 修复完成
> 口径: 以提案 / [[BEH-024]] 为准；禁止把 `EVICT_PAGE_CACHE` 当有效旋钮
> 环境变量教训: 所有脚本 MUST 使用 `PQ_CODES_PATH`（有 S）

## 预算公式

```text
page_cache_budget ≈ memory.max − Peak_RSS
```

## ⚠️ 环境变量拼写错误 (2026-08-03)

**R0-R3 v1 全部作废。** benchmark 读 `PQ_CODES_PATH`（带 S），v1 脚本设的是 `PQ_CODE_PATH`（不带 S）。
PQ 未加载 -> `pq_enabled_=false` -> 走 fallback 路径 -> QPS=23（假基线）。
修正后 QPS=2309（100x 差异）。详见 [[DEC-067]]。

## O_DIRECT 4T recall bug 修复 (2026-08-03)

**根因**: `if (kFinePread && !kFineDirect)` 条件导致 O_DIRECT 模式跳过 pread 路径，
走了非线程安全的 io_uring 路径。4T 并发提交 SQE/CQE 竞争 -> 丢失 I/O -> recall 崩。

**修复**: 改为 `if (kFinePread)`，buffer 改用 `posix_memalign` 满足 O_DIRECT 对齐。

| 配置 | 修复前 | 修复后 |
|------|--------|--------|
| O_DIRECT 4T Recall | 12.40% ❌ | 95.75% ✅ |
| O_DIRECT 4T QPS | 2826 (虚假) | 585 (真实) |
| O_DIRECT 1T Recall | 95.75% ✅ | 95.75% ✅ (无回归) |

## R0-R3 v2 结果 (PQ_CODES_PATH 修正后, CON-SLA-014, 512MB cgroup, 200q, 1T)

| 指标 | R0 (Buffered) | R1 (+FADVISE) | R2 (+EvictMeta) | R3 (+Both) |
|------|---------------|--------------|-----------------|------------|
| QPS | **2309** | **133** | **2383** | **132** |
| Recall | 95.75% | 95.75% | 95.75% | 95.75% |
| RSS | 155MB | 155MB | 155MB | 155MB |
| peak file | 420MB | 428MB | 393MB | 407MB |
| file (end) | 374MB | 370MB | 181MB | 143MB |
| workingset_refault | 0 | 0 | 0 | 0 |

### R0-R3 结论

- **FINE_FADVISE 有害** (-17x)：驱逐 vecblocks 页破坏跨 query page cache 预热
- **L4_EVICT_META 微正** (+3%)：驱逐 graph 页释放预算给 vecblocks
- **512MB 下 page cache 充裕**（357MB > 热工作集），workingset_refault=0

## 紧 cgroup 实验：构造 disk I/O 场景 (2026-08-03)

用更紧的 cgroup 在 SIFT1M 上构造 page cache 不足的真实场景：

| cgroup | RSS | page cache 预算 | QPS | pread(热) | max events | refault | majfault | 场景 |
|--------|-----|----------------|-----|-----------|------------|---------|----------|------|
| 512MB | 155MB | 357MB | **2309** | 4.8ms | 1654 | 0 | 6 | page cache 充裕 |
| 256MB | 153MB | 103MB | **126** | 8.4ms | 3625 | 30326 | 5078 | **page cache 不足** |
| 192MB | 130MB | 62MB | **134** | 8.4ms | 4468 | 31212 | 13535 | 同上 |
| 160MB | 120MB | 40MB | **124** | 8.7ms | 4705 | 35376 | 30544 | 同上 |

### 关键发现

1. **512MB -> 256MB 是分水岭**：QPS 从 2309 暴跌到 126（18x 下降）
   - page cache 预算从 357MB 降到 103MB
   - `workingset_refault` 从 0 飙到 30326 -- 热页被反复淘汰再读回
   - `pgmajfault` 从 6 飙到 5078 -- 大量磁盘 I/O

2. **256/192/160MB 性能几乎相同**（126/134/124 QPS）
   - page cache 预算再小也没用 -- 热工作集 > 100MB，怎么都不够
   - pread 热态从 4.8ms 涨到 8.4ms（page cache miss -> 磁盘读）

3. **512MB 下 page cache 充裕**（357MB > 热工作集），所以白嫖问题不显现
   - 256MB 下 page cache 不足（103MB < 热工作集），refault 暴涨

4. **L4_EVICT_META 在所有配置下都开了**，但 256MB 以下帮助有限
   - graph 页被驱逐了，但 vecblocks 热页仍被 LRU 反复淘汰

### 对 POC 方向的指导

- **512MB cgroup 不是 L4 管理的有效场景**：热工作集 fits in budget
- **256MB cgroup 是 L4 管理的有效场景**：refault=30326 证明 LRU 在误杀热页
- **后续 R4+ 实验应在 256MB cgroup 下进行**：测试 L4_DONTNEED/WILLNEED/选择性驱逐能否减少 refault
- **DEEP10M @ 2GB 天然是有效场景**：vecblocks 3.7GB，page cache 预算仅 ~390MB

## 下一步

- [ ] R4: 在 256MB cgroup 下测试 L4_DONTNEED（选择性驱逐冷 vecblocks 页）
- [ ] R5: 在 256MB cgroup 下测试 WILLNEED（提示热 block 保留）
- [ ] 目标：减少 workingset_refault，抬升 QPS 从 126 向 2309 逼近
- [ ] DEEP10M 严格隔离基线测试

## 进度

- [x] 提案确认
- [x] R0-R3 v1（作废：PQ_CODES_PATH 拼写错误）
- [x] R0-R3 v2（修正后，512MB cgroup）
- [x] O_DIRECT 4T bug 修复
- [x] 紧 cgroup 实验（256/192/160MB）
- [ ] R4+: 在 256MB cgroup 下测试 L4 管理机制
- [ ] 决策
