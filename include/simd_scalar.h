// simd_scalar.h - 纯标量 fallback (无 SIMD)
#pragma once

#include <cstdint>

#define SIMD_PREFETCH(ptr) ((void)0)

inline void pqBuildTable_dsub4(const float* q, const float* cb, float* t, uint32_t ksub) {
    for (uint32_t k = 0; k < ksub; k++) {
        const float* c = cb + (size_t)k * 4;
        float d0 = q[0] - c[0];
        float d1 = q[1] - c[1];
        float d2 = q[2] - c[2];
        float d3 = q[3] - c[3];
        t[k] = d0*d0 + d1*d1 + d2*d2 + d3*d3;
    }
}

// PQ ADC 距离查表 (标量 4-way 展开, 与原 Trunk 基线一致)
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
