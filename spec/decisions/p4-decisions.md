# P4 决策记录: O_DIRECT 诚实基准测试

> 日期: 2026-07-31
> 关联: DEC-030 (O_DIRECT 诊断模式), DEC-039 (诚实协议)
> 验证报告: spec/open/validation-odirect-20260731.md

---

## D-057: O_DIRECT 诚实基准测试 - Page Cache 水分量化 {#DEC-057}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-030,DEC-039,CHR-003,CON-HONEST-002 source=observed -->

**Context.** DEC-039 确立了诚实协议 (drop_caches + posix_fadvise), 但只解决查询间
page cache 复用。CON-HONEST-002 要求同时报告 Buffered 和 O_DIRECT 两组数字。
本决策记录 O_DIRECT 模式下的实测结果, 量化 page cache 的性能水分。

**Bug 修复**: O_DIRECT + FINE_PREAD 组合下, pread 路径的 `std::make_unique<char[]>`
buffer 不满足 O_DIRECT 的 512 字节对齐要求。改用 `posix_memalign` + 自定义
`AlignedBuf` 结构修复。

**实测结果:**

### SIFT1M (512MB cgroup)

| 模式 | 线程 | Recall | QPS | RSS | 水分倍数 |
|------|------|--------|-----|-----|---------|
| Buffered | 1T | 95.70% | 2450 | 271MB | 基线 |
| O_DIRECT | 1T | 95.70% | 130 | 271MB | **18.8x** |
| Buffered | 4T | 95.70% | 8312 | 277MB | 基线 |
| O_DIRECT | 4T | 95.70% | 502 | 277MB | **16.6x** |

### DEEP10M (3GB cgroup, 4T)

| 模式 | Recall | QPS | RSS | 水分倍数 |
|------|--------|-----|-----|---------|
| Buffered | 95.15% | 1535 | 2502MB | 基线 |
| O_DIRECT | 95.15% | 169 | 2502MB | **9.1x** |

**Decision.**

1. **确认 page cache 水分**: SIFT1M 17-19x, DEEP10M 9x。之前报告的 Buffered
   QPS 数字在 O_DIRECT 下下降一个数量级

2. **修正叙事**: DiskHNSW 的核心价值是**内存节省** (271MB vs hnswlib 726MB),
   而非 QPS 优势。O_DIRECT 下 DiskHNSW 比 hnswlib 慢 23-90x。
   之前 "10x faster" 的说法只在 page cache 充裕时成立, 不具普遍性

3. **Buffered 模式仍为生产推荐**: page cache 是 OS 免费提供的冷热分层,
   在 cgroup 限制内合法使用。但报告 MUST 按 CON-HONEST-002 标注模式

4. **O_DIRECT 单线程 130 QPS 对应 7.7ms/query**: I/O 主导 (100 候选 × 4KB 页
   × NVMe ~50-100μs/读)。这是真实磁盘 I/O 性能, 无任何缓存补贴

5. **100M 规模的必要性确认**: 1M/10M 规模 page cache 可覆盖全部 vecblocks
   (496MB/3.7GB), 无法验证真实磁盘搜索。100M 规模 vecblocks ~50GB,
   page cache 物理上无法覆盖, O_DIRECT 成为必须

**Alternatives rejected.**
- 继续 only 报告 Buffered 数字: 违反 CON-HONEST-002 诚实协议
- 放弃 Buffered 模式: page cache 在 cgroup 内合法, 是生产优势
- 否认水分: 数据清楚, 不诚实无意义

> rationale: 这不是"之前做错了", 而是测量维度的补全。Buffered 在 cgroup 内合法,
> O_DIRECT 揭示了无缓存时的真实性能。两个数字都有价值, 缺一不可。
> DiskHNSW 的真正战场是 100M+ 规模, 那里 O_DIRECT 是唯一可用路径。

---

## D-058: O_DIRECT + pread buffer 对齐 bug 修复 {#DEC-058}
<!-- ndf: kind=decision date=2026-07-31 affects=DEC-030 source=observed -->

**Context.** `FINE_DIRECT=1 FINE_PREAD=1` 组合下, pread 路径使用
`std::make_unique<char[]>(read_bytes)` 分配缓冲区。O_DIRECT 要求缓冲区地址
对齐到 512 字节 (或 block size), 但 `new char[]` 只保证 `alignof(max_align_t)`
(通常 16 字节) 对齐。

**Bug 影响:** `FINE_DIRECT=1 FINE_PREAD=1` 运行时 pread 返回 EINVAL (-1),
候选向量全部丢失, recall 崩到 0%。当前无人触发此组合, bug 未暴露。

**修复:** 引入 `AlignedBuf` 结构, 使用 `posix_memalign(&ptr, 4096, size)` 分配,
4096 对齐满足所有 O_DIRECT 要求。同时为 `unordered_map` 兼容性添加默认构造函数。

**验证:** SIFT1M O_DIRECT 1T recall 95.70% (与 Buffered 一致), 确认 bug 已修复。
