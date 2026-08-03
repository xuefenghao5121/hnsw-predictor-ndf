# Proposal: Promote flat_vec_cache cap fix {#PROP-PROMOTE-FV-CAP}

> track: promote
> Status: Implemented on 2026-08-03
> 日期: 2026-08-03
> Promotes: l4-cache-mgmt
> 关联 TOPIC: `poc/l4-cache-mgmt/ndf/TOPIC.md`
> 关联: [[BEH-024]], [[CHR-006]], [[DEC-068]]

## 动机

flat_vec_cache 预算 `vec_budget = std::min(cache_bytes, vec_max_bytes)` 受 CACHE_MB 限制。
当 FLAT_VEC_MB > CACHE_MB 时，flat_vec_cache 无法增大，导致 DEEP10M 上 128/256MB 配置无效。

## 变更

`src/core/block_cache.cpp` line 252:
```cpp
// 旧: size_t vec_budget = std::min(cache_bytes, vec_max_bytes);
// 新: size_t vec_budget = vec_max_bytes;  // flat_vec 独立于 BlockCache slots 预算
```

1 行改。flat_vec_cache 独立于 BlockCache 的 64KB block slots 预算。

## 证据

### DEEP10M 2GB cgroup, Buffered 1T

| flat_vec | CACHE_MB | 修复前 slots | 修复后 slots | QPS (修复前) | QPS (修复后) |
|----------|----------|-------------|-------------|-------------|-------------|
| 64MB | 64 | 173K | 173K | 651 | 651 (无变化) |
| 128MB | 128 | 173K (cap) | 346K | 664 | 698 |
| 256MB | 256 | 173K (cap) | 692K | 659 | 699 |

### SIFT1M 无回归

512MB cgroup 下 flat_vec_cache 默认 4MB，不受 cap 影响。

## 验证计划

1. 编译验证
2. SIFT1M 512MB: QPS ≥ 2000 (1T), Recall ≥ 95%
3. DEEP10M 2GB: Recall ≥ 95%, QPS ≥ 580 (基线)
