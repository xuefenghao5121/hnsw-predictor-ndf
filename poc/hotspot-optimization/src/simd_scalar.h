// simd_scalar.h - 纯标量 fallback (无 SIMD)
#pragma once

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
