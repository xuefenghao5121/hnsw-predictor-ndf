# R0: mmap 基线验证

> 日期: 2026-08-07
> Topic: csr-on-disk
> 基线 Trunk: 8520366
> 测量: N=1000, R=15, seed=42, sustained, 严格 cgroup 隔离

## 配置

- 方案 A: mmap + MADV_RANDOM
- CSR compact 写入 /tmp/csr_compact.bin (44.1MB), mmap 后释放内存
- 对比: BASE (CSR in-mem, 原有行为) vs CSR-DISK (mmap)

## 结果

### 512MB cgroup

| 配置 | RSS init | 聚合 QPS | 稳态 QPS | Recall | vs BASE |
|------|---------|---------|---------|--------|---------|
| 1T BASE | 157MB | 1,322 | 1,503 | 96.00% | - |
| 1T CSR-DISK | **113MB** | 993 | 936 | 96.00% | **-24.9%** |
| 16T BASE | 157MB | 4,160 | 6,201 | 96.00% | - |
| 16T CSR-DISK | **113MB** | 3,288 | 4,611 | 96.00% | **-21.0%** |

### 256MB cgroup

| 配置 | RSS init | 聚合 QPS | 稳态 QPS | Recall | vs BASE |
|------|---------|---------|---------|--------|---------|
| 1T BASE | 135MB | 1,079 | 1,175 | 96.00% | - |
| 1T CSR-DISK | **70MB** | 356 | 361 | 96.00% | **-67.0%** ❌ |
| 16T BASE | 134MB | 2,041 | 2,351 | 96.00% | - |
| 16T CSR-DISK | **90MB** | 1,650 | 1,758 | 96.00% | **-19.2%** |

## 分析

### ✅ 达标项

1. **recall 96.00% 不变** - CSR 内容未变，仅存储位置改变
2. **RSS 下降 44MB** - 从 157MB -> 113MB（512MB）, 135MB -> 70MB（256MB）
3. **512MB 全配置 QPS 下降 < 30%** - 1T: -24.9%, 16T: -21.0%
4. **256MB 16T QPS 下降 < 30%** - -19.2%

### ❌ 未达标项

5. **256MB 1T QPS 下降 67%** - page cache 预算不足以同时容纳 CSR + vecblocks

### 根因分析

256MB 1T 下：
- RSS init 仅 70MB，剩余 ~186MB page cache 预算
- CSR compact = 44MB, vecblocks = 496MB
- 两者共享 186MB page cache，CSR pages 挤压 vecblocks pages
- 单线程下 I/O 串行化，page cache miss 直接变成延迟

512MB 下：
- RSS init 113MB，剩余 ~399MB page cache 预算
- 足以容纳大部分 CSR pages + 部分 vecblocks pages
- QPS 下降主要来自额外的 page fault 开销

16T 下多线程掩盖了部分 I/O 延迟。

## 验收

| 条件 | 结果 |
|------|------|
| recall ≥ 95% | ✅ 96.00% |
| QPS 下降 < 30% (512MB) | ✅ -21.0% ~ -24.9% |
| RSS 下降 ≥ 40MB | ✅ -44MB |
| 256MB 可工作 | ⚠️ 16T 可, 1T 灾难 (-67%) |

## 结论

方案 A (mmap) 在 512MB 全配置和 256MB 16T 下达标。
256MB 1T 需要方案 C (WILLNEED 预取) 或方案 B (分页 BlockCache) 改善。

建议：R0 结果已足够支撑 512MB 场景的 promote。
256MB 1T 可作为已知限制记录，或 R2 预取改善后重测。
