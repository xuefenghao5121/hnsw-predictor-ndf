// simd_x86.h - x86 AVX2/SSE SIMD 实现
#pragma once

#include <cstdint>
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
