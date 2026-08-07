# D-085: CSR 上磁盘负结果 - 性能恶化不可接受

> date: 2026-08-07
> affects: BEH-036(draft), API-020(draft), DEC-010
> Rejects: csr-on-disk

## Context

CSR compact（delta+varint 压缩邻接表）占 SIFT1M init RSS 的 30%（47MB）。
本 POC 尝试将其从内存移到磁盘（mmap + page cache），以压缩 RSS。

探索了两种 I/O 路径：
- 方案 A: mmap + MADV_RANDOM（R0）
- 方案 C: mmap + madvise(WILLNEED) 预取（R2）

## 实测结果（sustained, N=1000, R=15, seed=42）

| 配置 | BASE QPS | CSR-DISK QPS | 下降 | RSS 节省 |
|------|---------|-------------|------|---------|
| 512MB 1T | 1,322 | 993 | **-24.9%** | -44MB |
| 512MB 16T | 4,160 | 3,402 | **-18.2%** | -44MB |
| 256MB 1T | 1,079 | 562 | **-47.9%** | -65MB |
| 256MB 16T | 2,041 | 1,650 | **-19.2%** | -44MB |

recall 96.00% 不变（CSR 内容未变，仅存储位置改变）。

## Decision

**REJECTED.** CSR 上磁盘减少了 RSS（-44MB），但在所有配置下 QPS 均显著下降
（-18% ~ -48%）。优化目标是"在减少内存的情况下提升性能"，
而非"牺牲性能换取内存"。性能恶化使本方案不可接受。

## 根因

1. **Phase A I/O 量与 Phase B 相当**：每次搜索 ~200-400 次 CSR 访问，每次 ~49 bytes。
   CSR 上磁盘后，Phase A 从纯内存变为 I/O bound，新增 page fault 开销。

2. **page cache 竞争**：CSR pages 与 vecblocks pages 共享 cgroup page cache 预算。
   256MB 下两者互相挤压，1T 场景 QPS 暴跌 48%。

3. **BFS 局部性不足以消除 I/O**：虽然 BFS 重排使图相邻节点在文件中相邻
   （4KB page 容纳 83 个 CSR entries），但 HNSW 搜索路径的跳跃性使实际 page cache
   命中率不够高。

4. **WILLNEED 预取有副作用**：inline madvise syscall 开销在 page cache 充足时
   超过收益。仅在 256MB 1T（极度 I/O bound）有正收益（+59%），但该场景仍不达标。

## Alternatives considered

| 方案 | 评估 |
|------|------|
| 分页 BlockCache（方案 B） | 更显式控制，但 I/O 量不变，无法解决根本问题 |
| BG 线程预取（SPSC） | 减少	inline 开销，但 I/O 总量不变 |
| 压缩率提升（BVGraph） | [[DEC-005]] 已拒绝（Jaccard=0.023） |
| 图裁剪 R_max=16 | [[DEC-038]] 已在 DEEP10M 验证为负结果 |
| PQ codes 上磁盘 | PQ codes 30MB，小于 CSR 47MB，且访问更频繁 |

## 保留路径

CSR 上磁盘在 **100M 规模**（CSR = 4.7GB）下是必需的——届时 RSS 节省的绝对量
（4.7GB）远超 QPS 下降的代价。本负结果仅针对 1M-10M 规模。

P3（100M）启动时重新评估，届时应考虑：
- 方案 B（分页 BlockCache）+ BG 线程预取
- 1-hop CSR 预取（掩盖 I/O 延迟）
- 更激进的图裁剪（减少 CSR 总量）

## Source

- POC: `poc/csr-on-disk/`
- Evidence: `poc/csr-on-disk/ndf/evidence/r0-mmap-baseline-20260807.md`,
  `poc/csr-on-disk/ndf/evidence/r2-willneed-prefetch-20260807.md`
- 提案: `spec/open/proposal-csr-on-disk.md`
