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

- [x] R4: 在 256MB cgroup 下测试 flat_vec_cache 在 fine rerank 中的命中
- [x] R4b: 增大 flat_vec_cache (8/16/32/64MB) 扫描
- [ ] R5: 在 256MB cgroup 下测试 WILLNEED（提示热 block 保留）
- [ ] 决策：flat_vec_cache 增大是否值得 promote 到 Trunk
- [ ] DEEP10M 严格隔离基线测试

## R4 结果：flat_vec_cache 在 fine rerank 中命中 (2026-08-03)

**发现**：fine rerank 代码未查 flat_vec_cache，热向量走 pread 读磁盘。加入 `getFlatVector()` 检查后：

### 256MB cgroup, flat_vec_cache 扫描

| flat_vec_cache | slots | RSS | QPS | refault | majfault | vs 基线 |
|---------------|-------|-----|-----|---------|----------|---------|
| 4MB (原默认) | 8K | 153MB | 126 | 30326 | 5078 | 基线 |
| 8MB | 16K | 157MB | **216** | 16414 | 5043 | +71% |
| 16MB | 32K | 165MB | **464** | 6888 | 4997 | +268% |
| 32MB | 65K | 179MB | **621** | 5339 | 4901 | +393% |
| 64MB | 130K | 194MB | **947** | 4048 | 5119 | **+651%** |

### 关键发现

1. **flat_vec_cache 64MB: QPS 126->947 (7.5x)**，refault 30326->4048 (-87%)
2. RSS 只增 41MB，用 41MB 匿名内存换 7.5x QPS 提升
3. Recall 不变 (95.75-95.80%)
4. **核心洞察**：在 page cache 不足场景下，把热向量从 page cache (OS 管理) 移到 flat_vec_cache (进程内管理) 更有效--不受 cgroup 回收影响

### 512MB cgroup, R4 vs R2

| 配置 | QPS | refault | 说明 |
|------|-----|---------|------|
| R2 (512MB, 4MB flat_vec) | 2383 | 0 | 基线 |
| R4 (512MB, 4MB flat_vec + rerank check) | 2326 | 32 | -2% (噪声) |

512MB 下 flat_vec_cache 增大无必要（page cache 充裕）。

## 进度

- [x] 提案确认
- [x] R0-R3 v1（作废：PQ_CODES_PATH 拼写错误）
- [x] R0-R3 v2（修正后，512MB cgroup）
- [x] O_DIRECT 4T bug 修复
- [x] 紧 cgroup 实验（256/192/160MB）
- [ ] R4+: 在 256MB cgroup 下测试 L4 管理机制
- [ ] 决策

## DEEP10M 严格隔离基线 + flat_vec_cache 实验 (2026-08-03)

### 基线 (CON-SLA-014, 2GB cgroup, GT=deep10m_gt_k10.bin)

| 模式 | 线程 | QPS | Recall | RSS | peak | oom | refault | majfault |
|------|------|-----|--------|-----|------|-----|---------|----------|
| Buffered | 1T | 580 | 95.05% | 1156MB | 2GB | 0 | 318 | 73005 |
| Buffered | 4T | 1562 | 95.05% | 1205MB | 2GB | 0 | 367 | 70025 |
| O_DIRECT | 1T | 43 | 95.05% | 1157MB | 2GB | 0 | - | - |

- vecblocks 3.7GB vs 预算 ~850MB -> 天然 page cache 不足
- majfault=73005 (极高, vs SIFT1M 512MB 的 6)
- pread 热态 21ms (vs SIFT1M 4.8ms)

### flat_vec_cache 扫描 (2GB cgroup, Buffered 1T)

| flat_vec | slots | QPS | refault | majfault | RSS | vs基线 |
|----------|-------|-----|---------|----------|-----|--------|
| 4MB | 10K | 581 | 263 | 73019 | 1156 | 基线 |
| 32MB | 86K | 637 | 285 | 72176 | 1185 | +10% |
| 64MB | 173K | 660 | 284 | 70791 | 1215 | +14% |
| 128MB | 173K | 664 | 322 | 69654 | 1214 | +14% (cap?) |
| 256MB | 173K | 659 | 317 | 68838 | 1215 | +13% (cap?) |

### DEEP10M vs SIFT1M 对比

| 场景 | SIFT1M 256MB | DEEP10M 2GB |
|------|-------------|-------------|
| flat_vec 4->64MB QPS 提升 | 7.5x (126->947) | 1.14x (581->660) |
| 热工作集覆盖率 | 高 (64MB/1M vec) | 低 (64MB/10M vec) |
| majfault 变化 | 5078->5119 (不变) | 73019->70791 (-3%) |

### 结论

- flat_vec_cache 在 DEEP10M 上效果有限 (+14%)，因为 10M 向量的热工作集远大于 cache
- 128/256MB slots 没增长（173K cap，待查代码）
- DEEP10M 的瓶颈是 I/O 量本身（majfault=73K），不是 page cache 管理
- 后续方向：减少候选数（降 REFINE_EF）或改善 PQ 质量

### GT 文件修正

- `data/deep10m_gt.bin` (kk=100) 格式不匹配（read_gt 读 k=10 导致错位）
- `data/deep10m_gt_k10.bin` (kk=10, n=10000) 正确，Recall=95.05%
