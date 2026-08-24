// simd_arm.h - ARM NEON SIMD 扩展 (D1: pqAdcDistance)
//
// 注意: pqBuildTable_dsub4 / SIMD_PREFETCH 由 Trunk include/simd_arm.h 提供。
// 本 POC 副本只 ADD pqAdcDistance, 不重定义既有函数。
// NEON 无高效 gather, 故 pqAdcDistance 走标量 4-way 展开 (数值与标量路径一致)。
#pragma once

#include <cstdint>
#include <arm_neon.h>

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
