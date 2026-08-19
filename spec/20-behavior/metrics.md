# Behavior — 指标提取

> 条款索引: `BEH-013`

## QPS/Recall/RSS 指标提取 {#BEH-013}
<!-- ndf: kind=req level=must layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

benchmark MUST 在 `benchmark_diskhnsw.cpp` 中：
1. Warmup: CPU spin + 全 query 预跑一轮
2. 计时搜索: `high_resolution_clock` 测总耗时 → QPS = N / total_s
3. Recall: 搜索结果 ∩ GT / K
4. RSS: 读取 `/proc/self/status` VmRSS
5. 多轮取峰值（排除调频噪声）

