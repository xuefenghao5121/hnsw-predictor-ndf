// simd.h - 架构无关 SIMD 封装
// 根据 CPU 架构自动选择实现: x86 (AVX2) / ARM (NEON) / Scalar fallback
#pragma once

#if defined(__x86_64__) || defined(__amd64__)
  #include "simd_x86.h"
#elif defined(__aarch64__) || defined(__arm__)
  #include "simd_arm.h"
#else
  #include "simd_scalar.h"
#endif
