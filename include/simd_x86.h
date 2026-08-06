// simd_x86.h - x86 AVX2/SSE SIMD 实现
#pragma once

#include <immintrin.h>

// CPU 预取封装
#define SIMD_PREFETCH(ptr) _mm_prefetch((const char*)(ptr), _MM_HINT_T0)

// ---------------------------------------------------------------------------
// PQ 距离表构建 (dsub=4 专用 AVX2 路径)
// 接口: void pqBuildTable_dsub4(q, cb, t, ksub)
//   q:    查询子向量 [4 floats]
//   cb:   码本子块  [ksub * 4 floats]
//   t:    输出距离表 [ksub floats]
//   ksub: 子量化器聚类数 (通常 256)
// ---------------------------------------------------------------------------
inline void pqBuildTable_dsub4(const float* q, const float* cb, float* t, uint32_t ksub) {
    __m128 qv = _mm_loadu_ps(q);
    __m256 q2 = _mm256_insertf128_ps(_mm256_castps128_ps256(qv), qv, 1);
    uint32_t k = 0;
    for (; k + 2 <= ksub; k += 2) {
        __m256 c2 = _mm256_loadu_ps(cb + (size_t)k * 4);
        __m256 d = _mm256_sub_ps(q2, c2);
        __m256 sq = _mm256_mul_ps(d, d);
        __m128 lo = _mm256_castps256_ps128(sq);
        __m128 hi = _mm256_extractf128_ps(sq, 1);
        __m128 h = _mm_hadd_ps(lo, hi);
        h = _mm_hadd_ps(h, h);
        t[k]   = _mm_cvtss_f32(h);
        t[k+1] = _mm_cvtss_f32(_mm_shuffle_ps(h, h, 0x55));
    }
    for (; k < ksub; k++) {
        __m128 c = _mm_loadu_ps(cb + (size_t)k * 4);
        __m128 d = _mm_sub_ps(qv, c);
        __m128 sq = _mm_mul_ps(d, d);
        __m128 h = _mm_hadd_ps(sq, sq);
        h = _mm_hadd_ps(h, h);
        t[k] = _mm_cvtss_f32(h);
    }
}
