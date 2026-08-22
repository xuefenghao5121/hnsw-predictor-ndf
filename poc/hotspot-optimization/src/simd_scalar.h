// simd_scalar.h - 纯标量 fallback 扩展 (D1: pqAdcDistance)
//
// 注意: pqBuildTable_dsub4 / SIMD_PREFETCH 由 Trunk include/simd_scalar.h 提供。
// 本 POC 副本只 ADD pqAdcDistance, 不重定义既有函数。
#pragma once

#include <cstdint>

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
