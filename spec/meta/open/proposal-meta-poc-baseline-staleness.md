# Proposal: POC 有条件并行 + Promote 基线失效 {#PROP-META-POC-BASELINE-STALENESS}

> track: process  
> Status: Implemented on 2026-08-05  
> 日期: 2026-08-05  
> 关联: [[BEH-018]], [[BEH-019]], [[BEH-025]], [[DEF-022]], [[DEF-023]], [[CHR-008]], [[META-004]]  
> 场景: 规范卫生 / 装订  
> 原则: Trunk 线性；POC 仅表面不相交可并行；收益默认非可加；产品无关正文

## 1. 动机

Promote/partial 推进 Trunk 后，exploring POC 仍引用旧 R0；完全并行会掩盖同路径优化冲突。

## 2. 决策

1. [[BEH-025]]：`explore_surface` / `baseline_trunk_sha` / `baseline_status` / `conflicts_with_topics`；
   有条件并行；stale/重测；禁止默认可加收益。
2. [[BEH-019]]：promote/partial 触发基线失效 + 相交主题冲突检查（close §4c/§4d）。
3. [[BEH-018]]：开题前扫描活跃 `explore_surface`。
4. `ndf_close.py`：§4c/§4d；`poc-topics` 输出新字段；`AGENTS.md` / `poc/README` 薄指针。
5. 活跃 exploring TOPIC 补字段并标 `baseline_status=stale`（承认 Trunk 已动）。

## 3. 验收

- `ndf_graphcheck.py --meta` hard_errors=0
- `ndf_close plan --mode promote|partial` 含 §4c/§4d；reject 为 N/A
- `ndf_index.py poc-topics` 可见 surface / baseline_status
