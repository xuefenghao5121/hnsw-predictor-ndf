# Proposal: Promote perf-gap-4t D1+D6

> track: promote
> 日期: 2026-08-05
> Status: Implemented on 2026-08-05
> Promotes: perf-gap-4t
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[CON-HONEST-002]]、[[BEH-024]]、[[DEC-068]]、[[DEC-069]]、[[DEC-070]]
> POC 证据: `poc/perf-gap-4t/ndf/TOPIC.md`

## 1. 变更概述

### D1: flat_vec_cache 默认值调整 (代码变更)

将 `src/core/block_cache.cpp` 中 `FLAT_VEC_MB` 默认值从 **4MB → 64MB**。

- POC 证据: FVC=160 在 512MB cgroup 下 +23.4% QPS，64MB 是 256MB cgroup 下最优
- 4MB 默认值过小，无法覆盖足够热向量
- 64MB 是平衡点: 256MB cgroup 最优，512MB cgroup 下用户可显式调大到 160

### D6: SIFT1M 256MB cgroup 配置 SLA (新增条款)

新增 SLA 条款记录 256MB cgroup 可行配置:

| 配置 | cgroup | QPS (4T) | Recall | vs hnswlib | 内存比 |
|------|--------|----------|--------|-----------|--------|
| 标准 | 512MB | ≥2000 | ≥95% | - | - |
| **紧凑** | **256MB** | **≥5000** | **≥95%** | 48% | 35% |

## 2. 具体改动

### src/ 改动 (D1)

**文件**: `src/core/block_cache.cpp` 第 244 行

```cpp
// 旧:
size_t vec_max_bytes = 4 * 1024 * 1024;  // 4MB 默认
// 新:
size_t vec_max_bytes = 64 * 1024 * 1024;  // 64MB 默认 (perf-gap-4t D1, DEC-073)
```

注释更新: 推荐值 64MB (256MB cgroup) / 160MB (512MB cgroup)

### spec/ 改动 (D6)

新增 SLA 条款 `{#CON-SLA-016}`: SIFT1M 紧凑 cgroup 配置

### 新增 DEC

`DEC-073`: flat_vec_cache 默认值调优

## 3. draft → stable ID 清单

| ID | 变更 | 类型 |
|----|------|------|
| `CON-SLA-016` | 新增: SIFT1M 256MB cgroup SLA | new stable |

现有条款无变更 (BEH-024 / DEC-068 / DEC-069 / DEC-070 不修改)

## 4. 证据摘要

| 方向 | 配置 | QPS | Recall | Evidence |
|------|------|-----|--------|---------|
| D1 | 512MB cgroup, FVC=160, 4T | 11,421 | 95.75% | d1-fvc-sweep-20260805.md |
| D6 | 256MB cgroup, FVC=64, 4T | 8,838 | 95.80% | d6-256mb-cgroup-20260805.md |
| D2 | PQ M=64 | 6,818 | 95.75% | ❌ 否定 |
| D3 | batch pread | 6,834 | - | ❌ 否定 |
| D4 | VisitedList pool | 8,276 | - | ❌ 否定 |
| D5 | REFINE_EF=200 | 5,703 | 97.20% | ❌ 无收益 |

## 5. 语义核决策 ([[META-004]] / [[BEH-019]] §6)

**决策: 不要**

理由: 本次 promote 是参数调优 (FLAT_VEC_MB 默认值) + 新增 SLA 配置点，
不涉及新行为或新接口。现有 L1 条款 [[BEH-024]] (L4 cache 管理) + [[CON-SLA-014]] 
已覆盖语义。VER 验证通过即可，无需蒸馏 L3 语义核模型。

## 6. 不做的事

- 不改 WILLNEED 默认值 (保持 opt-in)
- 不改 REFINE_EF 默认值 (保持 100)
- 不改 PQ M 默认值 (保持 32)
- 不改 CON-SLA-014 协议
