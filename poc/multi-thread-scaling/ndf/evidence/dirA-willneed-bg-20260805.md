# Evidence: Direction A - WILLNEED Background Thread

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]]
> 实现: 后台线程 + mutex/cv 队列，搜索线程 enqueue pages，后台线程统一 fadvise

## 结果

### 512MB cgroup (FVC=160)

| 线程数 | baseline | WILLNEED_BG=on | 差异 | 结论 |
|--------|----------|----------------|------|------|
| 4 | 10,758 | 11,542 | +7.3% | ✅ 低并发有收益 (mutex 竞争小) |
| 8 | 15,218 | 10,800 | -29.0% | ❌ mutex 竞争 > fadvise 锁 |
| 12 | 18,058 | 17,209 | -4.7% | 轻微退化 |
| 16 | 18,075 | 18,870 | +4.4% | 小收益 |
| 24 | 20,069 | 18,818 | -6.2% | 退化 |

### 256MB cgroup (FVC=64)

| 线程数 | baseline | WILLNEED_BG=on | 差异 | 结论 |
|--------|----------|----------------|------|------|
| 4 | 8,287 | 7,923 | -4.4% | 小退化 |
| **12** | 10,826 | **12,342** | **+14.0%** | ✅ 显著收益 |
| **24** | 10,550 | **11,547** | **+9.4%** | ✅ 收益 |

## 分析

### 双刃剑: mutex 替换了 fadvise 锁

后台线程方案将竞争从 **内核 fadvise 锁** 转移到 **用户态 mutex**：
- 512MB 8T: mutex 竞争比 fadvise 锁更糟 (-29%)
- 256MB 12T: mutex 竞争可控，fadvise 锁消除 -> +14%

### 256MB 收益根因

256MB 下 WILLNEED 更关键（page cache 极度紧张）。后台线程:
1. 消除了 fadvise 内核锁竞争
2. **保留了 readahead 功能** (不像方向 B 直接禁用)
3. 批量提交可能让 I/O 调度器更高效

### 512MB 无收益根因

512MB page cache 充裕 (file ~300MB)，fadvise 的 readahead 价值更小。
锁竞争消除的收益被 mutex 开销抵消。

### 方案优化方向 (未来)

当前实现用 mutex + cv，引入新竞争。可优化为:
1. **无锁 SPSC 队列** (每搜索线程一个)
2. **io_uring fadvise** (内核异步 hint，无需用户态线程)
3. **madvise(MADV_WILLNEED)** 替代 fadvise (不同锁路径)

但复杂度较高，当前 POC 阶段不做。

## 结论: H5 条件性确认

- ✅ 256MB 12T +14%, 24T +9% (核心场景有收益)
- ❌ 512MB 8T -29% (mutex 引入新瓶颈)
- ❌ 512MB 24T -6% (mutex 竞争 > fadvise 锁消除)

**与方向 B/C 对比**:

| 方向 | 512MB 最佳 | 256MB 最佳 | promote? |
|------|-----------|-----------|----------|
| B (disable) | 12T +6.7% | 全部 -30~50% | ❌ |
| C (VL pool) | 16T +45%, 24T +13% | 12T -15% | ✅ 16T+ |
| A (bg thread) | 4T +7.3% | 12T +14%, 24T +9% | ⚠️ 256MB only |

**推荐组合**: 512MB 16T+ 用 C (VL_POOL)，256MB 12T+ 用 A (WILLNEED_BG)。
