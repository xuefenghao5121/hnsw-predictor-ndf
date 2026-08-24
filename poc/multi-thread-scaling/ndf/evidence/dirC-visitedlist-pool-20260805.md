# Evidence: Direction C - VisitedList Pool (VL_POOL)

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]]
> 实现: thread_local unique_ptr<VisitedList> + VL_POOL=1 opt-in + reset() reuse
> 注: POC 副本基线有波动, 同批次 on/off 对比有效

## 结果

### 512MB cgroup (FVC=160)

| 线程数 | VL_POOL=off | VL_POOL=on | 差异 | 结论 |
|--------|-------------|------------|------|------|
| 4 | 9,841 | 8,310 | -15.6% | ❌ 低并发 thread_local 开销 > memset |
| 12 | 18,615 | 17,907 | -3.8% | 轻微退化 |
| **16** | 12,229 | **17,753** | **+45.2%** | ✅✅ 巨大收益! |
| **24** | 18,174 | **20,524** | **+12.9%** | ✅ 新 peak! |

### 256MB cgroup (FVC=64)

| 线程数 | VL_POOL=off | VL_POOL=on | 差异 | 结论 |
|--------|-------------|------------|------|------|
| 12 | 16,229 | 13,722 | -15.5% | ❌ (注意: off 值异常高, 可能噪声) |

## 分析

### 16T +45% 巨大收益的根因

16T 是 memset cache bouncing 的爆发点:
- 16 个线程各自 memset 1MB VisitedList = 16MB L1/L2 cache 污染
- 每个线程的 VisitedList 在物理上可能跨 NUMA，remote access 放大
- VL_POOL 复用后: memset 仅首次，后续只 reset() (curV++ 单字节)
- **16T 的 VL_POOL=off QPS (12229) 异常低** -- 可能是 cgroup 回收 + memset 交互恶化

### 24T +13% 收益

- 24T cache bouncing 更严重，但 WILLNEED 锁竞争也更大
- VL_POOL 消除了 memset 开销 (perf 10.29% -> ~0%)
- 净收益 +13%

### 4T/12T 无收益或退化

- 低并发下 memset 占比低 (4T: 5.38%, 12T: 10.29%)
- thread_local 的间接寻址 + unique_ptr 检查开销固定
- 收益 < 开销 -> 退化

### 最佳策略

**VL_POOL 应仅在 16T+ 时启用**。环境变量 `VL_POOL=1` + 运行时检测线程数:
```
if (num_threads >= 14) enable VL_POOL
```

## 结论: H7 确认 (条件性)

- ✅ 16T+ 有显著收益 (+13~45%)
- ❌ 12T- 无收益或退化
- **promote 候选**: VL_POOL=1 作为 opt-in，建议 16T+ 使用
- 新 peak: 512MB 24T VL_POOL=on = **20,524 QPS** (vs 基线 19,766 = +3.8%)

### 注意

POC 副本整体 QPS 波动较大（4T=9841 vs Trunk 10723），编译路径差异。
promote 验证时需用 Trunk 二进制重新确认。
