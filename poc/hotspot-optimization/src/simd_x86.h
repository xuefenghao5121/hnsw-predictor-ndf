// simd_x86.h - x86 AVX2 SIMD 扩展 (D1: pqAdcDistance)
//
// 注意: pqBuildTable_dsub4 / SIMD_PREFETCH 由 Trunk include/simd_x86.h 提供
// (经 include/block_cache.h -> include/simd.h 链)。本 POC 副本只 ADD 新函数,
// 不重定义既有函数, 避免与 Trunk 头文件 redefinition 冲突。
#pragma once

#include <cstdint>
#include <immintrin.h>

// ---------------------------------------------------------------------------
// PQ ADC 距离查表 (D1): sum_m t[m*ksub + code[m]]
// 接口: float pqAdcDistance(code, t, M, ksub)
//   code: 节点 PQ code [M bytes], 每字节 = 子量化器 centroid 索引 (0..ksub-1)
//   t:    预计算距离表 [M * ksub floats] (buildPqDistTable 产出)
//   M:    子量化器数 (SIFT=32)
//   ksub: 每子量化器聚类数 (256)
// AVX2: 一次 gather 8 个子量化器的表项 (8 次 32-bit gather 单指令)。距离数值与
// 标量 4-way 展开一致 (8-lane 树归约 + 尾数标量), ULP 级差异不影响 Recall@10。
// ---------------------------------------------------------------------------
inline float pqAdcDistance(const uint8_t* code, const float* t, uint32_t M, uint32_t ksub) {
    __m256 acc = _mm256_setzero_ps();
    uint32_t m = 0;
    for (; m + 8 <= M; m += 8) {
        __m128i code8 = _mm_loadl_epi64((const __m128i*)(code + m));   // 8 bytes
        __m256i idx   = _mm256_cvtepu8_epi32(code8);                    // 8 x uint32 [0..255]
        __m256i base  = _mm256_setr_epi32(
            (int)((m + 0) * ksub), (int)((m + 1) * ksub),
            (int)((m + 2) * ksub), (int)((m + 3) * ksub),
            (int)((m + 4) * ksub), (int)((m + 5) * ksub),
            (int)((m + 6) * ksub), (int)((m + 7) * ksub));
        __m256i full  = _mm256_add_epi32(base, idx);
        __m256  vals  = _mm256_i32gather_ps(t, full, 4);                // t[full[i]]
        acc = _mm256_add_ps(acc, vals);
    }
    // 8-lane 水平归约
    __m128 lo  = _mm256_castps256_ps128(acc);
    __m128 hi  = _mm256_extractf128_ps(acc, 1);
    __m128 sum = _mm_add_ps(lo, hi);
    sum = _mm_hadd_ps(sum, sum);
    sum = _mm_hadd_ps(sum, sum);
    float result = _mm_cvtss_f32(sum);
    // 尾数 (M 非 8 的倍数时)
    for (; m < M; m++) result += t[(size_t)m * ksub + code[m]];
    return result;
}
