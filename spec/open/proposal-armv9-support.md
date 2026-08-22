# Proposal: ARMv9 (AArch64) 架构支持

> track: boundary (项目边界拓展)
> 日期: 2026-08-06
> Status: **draft (待审核)**
> 关联: [[DEF-022]]、[[BEH-024]]、[[DEC-068]]、[[DEC-070]]
> 目标平台: 鲲鹏 930 (AArch64, SVE 支持), openEuler 24.03

## 1. 背景与动机

### 1.1 当前状态

DiskHNSW 主线已稳定 (SIFT1M 30K QPS @512MB 16T, DEEP10M 2.3K QPS @2GB 12T),
但仅支持 x86 架构。代码中有 3 类 x86 硬绑定依赖, 阻止了 ARM 平台编译。

### 1.2 x86 硬绑定清单 (3 类, 5 个文件)

#### 类型 1: SIMD intrinsic (PQ 距离表构建) ★ 核心

**文件**: `src/core/disk_hnsw.cpp` 第 270-295 行

```cpp
#include <immintrin.h>  // x86 专属

void buildPqDistTable(const float* query) {
    if (dsub == 4) {
        __m128 qv = _mm_loadu_ps(q_sub);
        __m256 q2 = _mm256_insertf128_ps(...);
        __m256 c2 = _mm256_loadu_ps(...);
        __m256 d = _mm256_sub_ps(q2, c2);
        __m256 sq = _mm256_mul_ps(d, d);
        __m128 h = _mm_hadd_ps(lo, hi);
        // ... AVX2 专属 intrinsic
    }
}
```

**影响**: PQ 粗筛的核心热路径, 每次 query 都会调用
**ARM 对应**: NEON (float32x4_t) 或 SVE

#### 类型 2: CPU 预取 (_mm_prefetch) ★ 中等

**文件**: `src/core/disk_hnsw.cpp` (6 处), `include/block_cache.h` (2 处)

```cpp
_mm_prefetch((const char*)&route_table_[pfn], _MM_HINT_T0);
_mm_prefetch((const char*)&pq_codes_[...], _MM_HINT_T0);
_mm_prefetch((const char*)&flat_vec_owners_[slot], _MM_HINT_T0);
```

**影响**: 图遍历时预取 route_table / PQ codes / flat_vec_cache
**ARM 对应**: `__builtin_prefetch(ptr, 0, 3)` (GCC 内建, 架构无关)

#### 类型 3: 编译选项 (-march=native)

**文件**: `Makefile`

```makefile
CXXFLAGS = -O3 -std=c++17 -march=native  # x86 上展开为 AVX2/AVX512
```

**影响**: 编译器自动向量化依赖 x86 指令集
**ARM 对应**: `-march=native` 在 ARM 上展开为 NEON/SVE, 通用

### 1.3 外部依赖兼容性

| 依赖 | ARM 兼容性 | 说明 |
|------|-----------|------|
| hnswlib | ✅ 已支持 | 纯 C++ 模板, 无 SIMD |
| faiss (Python) | ✅ 已支持 | faiss-cpu 支持 ARM64 |
| io_uring (liburing) | ✅ 已支持 | Linux 内核子系统, 架构无关 |
| std::atomic / __sync | ✅ 已支持 | GCC 内建, 架构无关 |
| g++ C++17 | ✅ 已支持 | openEuler 24.03 自带 |

### 1.4 目标平台

**鲲鹏 930 服务器:**
- 连接: `ssh kunpeng` (跳板 192.168.137.2 -> 192.168.90.45)
- OS: openEuler 24.03 (Linux 6.6, ARM64)
- CPU: 鲲鹏 930, 120 核 ARMv9, SVE 256-bit
- 内存: 充裕 (可跑 DEEP10M 全量)

## 2. 提议的改造方案

### 2.1 核心原则: 抽象层而非 `#ifdef` 泛滥

创建 `include/simd.h` 统一封装 SIMD 操作, 源文件按架构分离:

```
include/
  simd.h              ← 公共接口 (架构无关)
  simd_x86.h           ← x86 AVX2 实现
  simd_arm.h           ← ARM NEON/SVE 实现
```

源文件中只 include `simd.h`, 不再直接调用 `_mm_*` 或 NEON intrinsic。

### 2.2 具体改造 (3 步)

#### Step 1: 创建 SIMD 抽象层 (`include/simd.h`)

```cpp
// include/simd.h - 架构无关 SIMD 封装
#pragma once

#if defined(__x86_64__) || defined(__amd64__)
  #include "simd_x86.h"
#elif defined(__aarch64__) || defined(__arm__)
  #include "simd_arm.h"
#else
  #include "simd_scalar.h"  // 纯标量 fallback
#endif
```

#### Step 2: 封装 PQ 距离表构建 (核心改动)

**x86 版 (`simd_x86.h`):**
```cpp
// 封装现有 AVX2 代码, 接口:
// void pqDistTable_dsub4(const float* q, const float* cb, float* t, uint32_t ksub);
```

**ARM 版 (`simd_arm.h`):**
```cpp
#include <arm_neon.h>
// NEON float32x4_t 实现:
// - 一次处理 1 个 centroid (4 floats)
// - vld1q_f32 / vsubq_f32 / vmulq_f32 / vaddvq_f32
```

**SVE 版 (鲲鹏 930 专属优化, 可选):**
```cpp
#include <arm_sve.h>
// SVE 256-bit 实现:
// - 一次处理 2 个 centroid (8 floats)
// - svld1_f32 / svsub_f32_x / svmul_f32_x / svaddv_f32
// - 需要 -march=armv9-a+sve 编译选项
```

#### Step 3: 统一 CPU 预取 (简单改动)

```cpp
// include/simd.h
#if defined(__x86_64__)
  #include <immintrin.h>
  #define SIMD_PREFETCH(ptr) _mm_prefetch((const char*)(ptr), _MM_HINT_T0)
#elif defined(__aarch64__)
  #define SIMD_PREFETCH(ptr) __builtin_prefetch((ptr), 0, 3)
#else
  #define SIMD_PREFETCH(ptr) ((void)0)
#endif
```

全局替换:
- `_mm_prefetch((const char*)X, _MM_HINT_T0)` → `SIMD_PREFETCH(X)`
- 共 8 处 (disk_hnsw.cpp 6 处 + block_cache.h 2 处)

### 2.3 Makefile 改造

```makefile
# 自动检测架构
ARCH := $(shell uname -m)

ifeq ($(ARCH),x86_64)
  CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I./hnswlib -I./include -march=native
else ifeq ($(ARCH),aarch64)
  CXXFLAGS = -O3 -std=c++17 -Wall -Wextra -I./hnswlib -I./include -march=native
  # 鲲鹏 930 额外: -mcpu=klein -mtune=klein (可选)
  # SVE 支持: -march=armv9-a+sve (如需 SVE 路径)
endif
```

**`-march=native` 对两个平台都是正确的**: x86 上展开为 AVX2, ARM 上展开为 NEON。
不需要手动指定指令集。

### 2.4 不做的事

- **不改搜索算法** (两阶段搜索逻辑不变)
- **不改数据格式** (二进制格式跨架构兼容)
- **不改 io_uring** (架构无关)
- **不改 hnswlib** (已兼容 ARM)
- **不改 NDF spec 条款** (BEH/DEC/CON-SLA 架构无关)
- **不做交叉编译** (在目标平台原生编译)

## 3. 影响评估

### 3.1 代码变更量

| 文件 | 变更类型 | 估算行数 |
|------|---------|---------|
| `include/simd.h` | 新建 | 20 |
| `include/simd_x86.h` | 新建 (封装现有 AVX2) | 50 |
| `include/simd_arm.h` | 新建 (NEON 实现) | 50 |
| `src/core/disk_hnsw.cpp` | 替换 intrinsic | ~30 行改 |
| `include/block_cache.h` | 替换 prefetch 宏 | 2 行改 |
| `Makefile` | 架构检测 | 5 行改 |

**总计: ~150 行新增/修改, 核心改动 ~30 行**

### 3.2 性能预期

| 平台 | PQ 表构建 (dsub=4) | 预期 QPS | 说明 |
|------|-------------------|---------|------|
| x86 AVX2 (当前) | 256-bit, 2 centroid/iter | 3,366 (SIFT 1T) | 基线 |
| ARM NEON | 128-bit, 1 centroid/iter | ~70-80% of x86 | NEON 128-bit vs AVX2 256-bit |
| ARM SVE (鲲鹏 930) | 256-bit, 2 centroid/iter | ~90-100% of x86 | SVE 256-bit ≈ AVX2 256-bit |

**NEON 性能预期较低 (128-bit)**, 但:
1. PQ 表构建不是唯一瓶颈 (Phase A 还包括 CSR 遍历, Phase B 包括 I/O)
2. 鲲鹏 930 有 120 核, 多线程并行度远超 16 核 x86
3. SVE 256-bit 可以接近 AVX2 性能 (如果启用)

### 3.3 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| NEON 性能低于预期 | 中 | -20% QPS | SVE 路径作为备选 |
| 数据跨平台不一致 | 低 | recall 偏差 | 浮点精度: x86 和 ARM IEEE754 一致 |
| hnswlib ARM 编译问题 | 低 | 构建失败 | hnswlib 已在 ARM CI 上验证 |
| faiss ARM 兼容性 | 低 | PQ 训练失败 | faiss-cpu 已支持 ARM64 |

## 4. 验证计划

### 4.1 编译验证

```bash
# 在鲲鹏 930 上
ssh kunpeng
cd /path/to/hnsw-predictor-ndf
make clean && make all  # 必须零错误零警告
```

### 4.2 数据兼容性验证

```bash
# x86 上生成的数据 (SIFT1M) 直接拷到 ARM 上使用
scp -r output/ kunpeng:/path/to/hnsw-predictor-ndf/
# 运行 benchmark, recall 必须一致 (≥95%)
```

### 4.3 性能验证

| 测试 | 平台 | 配置 | 目标 |
|------|------|------|------|
| SIFT1M 1T 512MB | x86 (i7-13700) | 基线 | 3,366 QPS |
| SIFT1M 1T 512MB | ARM NEON | 同配置 | ≥2,000 QPS |
| SIFT1M 1T 512MB | ARM SVE | 同配置 | ≥2,500 QPS |
| SIFT1M 16T 512MB | ARM (120核) | 同配置 | ≥20,000 QPS |
| recall 一致性 | 双平台 | 同数据 | 差异 <0.1pp |

### 4.4 回归验证

x86 上 `make clean && make all && make test` 必须零回归。
ARM 改造不改变 x86 代码路径 (通过编译时分支)。

## 5. POC 执行计划

### 阶段 1: 编译通过 (鲲鹏 930)

1. 创建 SIMD 抽象层 (`simd.h` + `simd_x86.h` + `simd_arm.h`)
2. 改造 `disk_hnsw.cpp` 和 `block_cache.h`
3. 改造 `Makefile`
4. 在鲲鹏 930 上编译

### 阶段 2: 功能正确

5. 拷贝 SIFT1M 数据到鲲鹏 930
6. 运行 benchmark, 验证 recall ≥95%
7. 验证数据跨平台一致性

### 阶段 3: 性能验证

8. SIFT1M 1T/4T/16T benchmark (NEON)
9. (可选) SVE 路径实现 + benchmark
10. DEEP10M benchmark (利用 120 核)

### 阶段 4: Trunk promote

11. x86 回归测试 (零回归)
12. NDF spec 更新 (新增 ARCH 条款)
13. Promote 到 Trunk

## 6. 草稿条款

| ID | 类型 | 描述 |
|----|------|------|
| DEF-024 (draft) | definition | 架构抽象层定义 (simd.h 接口) |
| BEH-030 (draft) | behavior | ARM 平台 PQ 距离表构建行为 |
| BEH-031 (draft) | behavior | ARM 平台 CPU 预取行为 |
| API-015 (draft) | interface | Makefile ARCH 自动检测 |
| DEC-077 (draft) | decision | NEON vs SVE 实现选择 |
| DEC-078 (draft) | decision | 跨架构数据兼容性保证 |
| CON-SLA-019 (draft) | sla | ARM 平台性能 SLA (鲲鹏 930) |

## 7. 开放问题

### Q-003: NEON 还是 SVE 优先? → **NEON 优先**

- NEON 通用路径先实现, SVE 暂不做

### Q-004: 是否需要双架构 CI? → **否**

- 不需要双架构 CI

### 补充决策 (2026-08-06)

- 目标平台 (鲲鹏 930) 信息已失效, 目前缺少真实 ARM 验证平台
- **本次仅做代码兼容性修改, 不做 ARM 验证**
- x86 回归验证照常执行

## 8. 不影响现有条款

现有 BEH/DEC/CON-SLA 条款均架构无关 (描述行为和 SLA, 不涉及指令集)。
本提案新增 ARCH 类条款, 不修改现有条款。

---

**审核要点:**

1. ✅ 改造范围明确 (3 类依赖, 5 个文件, ~150 行)
2. ✅ 不改搜索算法 / 数据格式 / NDF spec
3. ✅ x86 零回归 (编译时分支)
4. ✅ 目标平台就绪 (鲲鹏 930, openEuler 24.03)
5. ⚠️ NEON 性能可能低于 x86 (128-bit vs 256-bit), 需实测验证
6. ⚠️ SVE 可选但需要额外实现工作
