# Proposal: Partial Promote l4-cache-mgmt R2 D2 (BG Page Merge)

> track: promote
> 日期: 2026-08-06
> Status: Implemented on 2026-08-06
> Promotes: l4-cache-mgmt (partial -- D2 only)
> 关联: [[BEH-024]]、[[BEH-027]]、[[API-013]]、[[CON-SLA-014]]、[[CON-SLA-016]]、[[DEC-070]]、[[DEC-074]]、[[CON-POC-001]]
> POC 证据: `poc/l4-cache-mgmt/ndf/TOPIC.md`

## 1. 变更概述

### D2: WILLNEED BG 页合并 (代码变更)

在 WILLNEED_BG 后台线程中，将 pages_needed 排序后合并连续页为单次 fadvise 调用，
减少 syscall 数量。仅在 256MB cgroup 下有显著收益。

- 环境变量: `PAGE_MERGE_BG=1` (opt-in, 默认关闭)
- 文件: `src/core/disk_hnsw.cpp` BG 线程段
- 预期: 256MB 16T +17.5%, 512MB 无收益/有害 (不推荐使用)

### 新增 DEC-075

BG 页合并决策记录。

## 2. draft → stable ID 清单

| ID | 变更 | 类型 |
|----|------|------|
| `BEH-028` | 新增: WILLNEED BG 页合并行为 | new stable |
| `CON-SLA-018` | 新增: SIFT1M 256MB BG+merge SLA | new stable |
| `DEC-075` | 新增: BG 页合并决策 | new stable |

API-013 扩展: PAGE_MERGE_BG 环境变量 (已有 API-013 中追加)

## 3. src/ 改动概述

在 WILLNEED_BG 的后台线程循环中，PAGE_MERGE_BG=1 时对 slot.pages 排序并合并连续页：

```cpp
// 旧: 每页单独 fadvise
for (uint32_t pg : slot.pages) {
    posix_fadvise(fd, (off_t)pg << 12, 4096, POSIX_FADV_WILLNEED);
}
// 新: 排序后合并连续页
if (kPageMergeBg && pages.size() > 1) {
    sort(pages);
    // 合并连续段: [10,11,12,15,16] -> fadvise(10, 3页) + fadvise(15, 2页)
}
```

## 4. 证据摘要

### 256MB (FVC=64, 有效 ✅)

| 线程数 | BG only | BG+merge | 差异 |
|--------|---------|----------|------|
| 8 | 13,713 | 15,218 | +11.0% |
| 12 | 16,037 | 18,213 | +13.6% |
| **16** | 15,891 | **18,675** | **+17.5%** |
| 24 | 15,476 | 18,218 | +17.7% |

### 512MB (FVC=160, 有害 ❌ -- 不推荐)

| 线程数 | BG only | BG+merge | 差异 |
|--------|---------|----------|------|
| 8 | 19,816 | 15,026 | -24.2% |
| 16 | 30,832 | 29,935 | -2.9% |

## 5. 语义核决策 ([[META-004]] / [[BEH-019]] §6)

**决策: 不要**

理由: 页合并是 I/O 调度优化，不涉及新搜索行为。现有 [[BEH-027]] 已覆盖 BG 线程语义。
PAGE_MERGE_BG 仅是 BG 线程内部实现细节。

## 6. 不做的事

- 不改 WILLNEED_BG 默认值 (保持 opt-in)
- 不改 PAGE_MERGE_BG 为默认开启 (512MB 有害)
- 不 promote D1/D3/D4/D5/D6 (诊断或否定)
- l4-cache-mgmt 主题保持 exploring (R5b/R5c 未关闭)
