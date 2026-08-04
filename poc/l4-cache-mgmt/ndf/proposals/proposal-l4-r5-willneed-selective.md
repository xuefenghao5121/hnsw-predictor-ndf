# Proposal: L4 R5 - WILLNEED + Selective DONTNEED + mincore {#PROP-L4-R5}

> track: poc  
> Status: Implemented on 2026-08-04 (WILLNEED promoted to Trunk; Selective DONTNEED remains POC)  
> 日期: 2026-08-04  
> Role: amend  
> Parent: `spec/archive/2026-08/proposal-l4-cache-mgmt.md` (Implemented)  
> 主题装订器: `poc/l4-cache-mgmt/ndf/TOPIC.md`（[[BEH-025]]）  
> 关联: [[BEH-024]](stable), [[CON-SLA-014]], [[DEC-067]], [[DEC-068]]  
> 基线: SIFT1M 严格隔离 256MB cgroup + flat_vec_cache=64MB（promoted 后稳态）

## 1. 动机

L4 POC R4 promoted 了 flat_vec_cache 在 fine rerank 中的命中（7.5x QPS），但原提案中的三个机制（A/B/C）尚未测试。256MB cgroup + 64MB flat_vec_cache 下仍有 4048 refault / 5119 majfault，说明 OS page cache 仍有优化空间。

R1 测试的 FINE_FADVISE 是 **blanket 驱逐所有 vecblocks 页**（-17x），但**选择性驱逐冷 block**（仅驱逐不在当前搜索路径上的 block）尚未测试。WILLNEED 和 mincore 也未验证。

## 2. 实验设计

### 基线（promoted 后）

| 配置 | QPS | refault | majfault | RSS |
|------|-----|---------|----------|-----|
| 256MB + flat_vec=64MB (R4 promoted) | 947 | 4048 | 5119 | 194MB |

### R5a: WILLNEED 预取热 block

**假设**：对 fine rerank 即将读取的 vecblock 调用 `posix_fadvise(WILLNEED)`，提示内核预读。

**实现**：在 fine rerank 循环中，pread 之前对目标 offset+length 调 `posix_fadvise(fd, offset, len, POSIX_FADV_WILLNEED)`。

**预期**：低收益。flat_vec_cache 已覆盖最热向量，WILLNEED 主要影响 warm vector 的 pread 延迟。可能减少 majfault 但不显著提升 QPS。

**风险**：fadvise 系统调用开销可能抵消预取收益。

### R5b: 选择性 DONTNEED 冷 block

**假设**：在 coarse search 阶段，对已确定不会在 fine rerank 中访问的 vecblock 调用 `posix_fadvise(DONTNEED)`，释放 page cache 给热 block。

**实现**：coarse search 完成后，遍历候选列表，对不在候选邻居中的 block 调 `posix_fadvise(DONTNEED)`。

**与 R1 FINE_FADVISE 的区别**：R1 驱逐**所有** vecblocks 页（包括正在被后续 query 使用的热页）；R5b 只驱逐**冷 block**（当前 query 不需要的 block）。

**预期**：不确定。可能减少 refault（热页不被 LRU 误杀），但也可能增加 I/O（冷 block 被后续 query 重新读取）。

**风险**：如果跨 query 局部性强（同一 block 被多个 query 访问），DONTNEED 会适得其反。

### R5c: mincore 探测 page cache 命中

**假设**：在 pread 之前用 `mincore()` 检查目标页是否已在 page cache，命中则跳过 pread（直接从已映射区域读），未命中才走 pread。

**实现**：`mmap` vecblocks 文件（或保持 pread），fine rerank 中先 `mincore` 检查页驻留状态。

**预期**：中等。可避免重复 I/O（如果页已在 cache 中，pread 仍是系统调用 + 拷贝）。但 mincore 本身也有开销，且需要 mmap 或额外逻辑。

**风险**：mincore 开销可能 > 节省的 pread；实现复杂度高。

## 3. 实验协议

- **数据集**：SIFT1M
- **cgroup**：256MB（page cache 不足的有效场景）
- **flat_vec_cache**：64MB（promoted 后默认配置）
- **线程**：1T（排除多线程干扰）
- **queries**：200
- **基线**：R4 promoted 状态（QPS=947, refault=4048）
- **采集**：memory.stat + QPS/Recall/RSS + workingset_refault + majfault
- **前置**：每组前 `drop_caches` + 重建 cgroup

### 实验矩阵

| 轮次 | 机制 | 环境变量 | 说明 |
|------|------|----------|------|
| R5-base | 基线（promoted） | flat_vec=64MB | 复跑确认 947 可复现 |
| R5a | WILLNEED | +L4_WILLNEED=1 | fine rerank pread 前 fadvise(WILLNEED) |
| R5b | Selective DONTNEED | +L4_SELECTIVE_DONTNEED=1 | coarse 后驱逐冷 block |
| R5c | mincore | +L4_MINCORE=1 | pread 前 mincore 检查 |
| R5d | 组合最优 | 最佳机制组合 | 根据 R5a-c 结果 |

## 4. 成功标准（探索，非 Trunk must）

| 指标 | 基线 | 目标 | 说明 |
|------|------|------|------|
| QPS | 947 | ≥ 947 × 1.1 | 至少 +10% 才有净收益 |
| refault | 4048 | 明显下降 | 主监控指标 |
| Recall | 95.75% | ≥ 95% | must 门槛 |
| RSS | 194MB | ≤ 220MB | 不显著增加 |

## 5. NDF 变更

- 本提案为 `poc/l4-cache-mgmt` 的 amendment，不改 stable 条款
- 如有正结果 -> 另开 promote 提案
- 如全部负结果 -> 关闭 topic（status=rejected for remaining hypotheses），写 DEC
- TOPIC.md status 从 `promoted` 改回 `exploring`（promoted 子集已在 Trunk）

## 6. 非目标

- 不改 Trunk `src/` 生产默认路径
- 不改 BEH-024 stable 条款
- 不改 FLAT_VEC_MB 默认值
- 不测试 512MB cgroup（page cache 充裕，无 L4 管理空间）
