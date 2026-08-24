// simd_arm.h - ARM NEON SIMD 实现
#pragma once

#include <cstdint>
#include <arm_neon.h>

// CPU 预取封装 (GCC 内建, 架构无关)
#define SIMD_PREFETCH(ptr) __builtin_prefetch((ptr), 0, 3)

// ---------------------------------------------------------------------------
// PQ 距离表构建 (dsub=4 专用 NEON 路径)
// NEON float32x4_t: 128-bit, 一次处理 4 floats (1 个 centroid)
// vs x86 AVX2 的 256-bit (2 centroids/iter), NEON 需要更多迭代
// ---------------------------------------------------------------------------
inline void pqBuildTable_dsub4(const float* q, const float* cb, float* t, uint32_t ksub) {
    float32x4_t qv = vld1q_f32(q);
    for (uint32_t k = 0; k < ksub; k++) {
        float32x4_t c = vld1q_f32(cb + (size_t)k * 4);
        float32x4_t d = vsubq_f32(qv, c);
        float32x4_t sq = vmulq_f32(d, d);
        // 水平求和: sq[0]+sq[1]+sq[2]+sq[3]
        float32x2_t sum2 = vpadd_f32(vget_low_f32(sq), vget_high_f32(sq));
        sum2 = vpadd_f32(sum2, sum2);
        t[k] = vget_lane_f32(sum2, 0);
    }
}

// PQ ADC 距离查表 (标量 4-way 展开; NEON 无高效 gather)
inline float pqAdcDistance(const uint8_t* code, const float* t, uint32_t M, uint32_t ksub) {
    float s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    uint32_t m = 0;
    for (; m + 4 <= M; m += 4) {
        s0 += t[(size_t)(m + 0) * ksub + code[m + 0]];
        s1 += t[(size_t)(m + 1) * ksub + code[m + 1]];
        s2 += t[(size_t)(m + 2) * ksub + code[m + 2]];
        s3 += t[(size_t)(m + 3) * ksub + code[m + 3]];
    }
    for (; m < M; m++) s0 += t[(size_t)m * ksub + code[m]];
    return (s0 + s1) + (s2 + s3);
}
