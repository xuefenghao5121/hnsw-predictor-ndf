// simd_arm.h - ARM NEON SIMD 实现
#pragma once

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
