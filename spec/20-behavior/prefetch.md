# Behavior — 投机预取

> 条款索引: `BEH-012`

## 投机预取节流 {#BEH-012}
<!-- ndf: kind=req level=may layer=L2 status=stable since=0.1 source=observed -->
<!-- ndf: refines=BEH-001 -->

`SPEC_PREFETCH=1` 时，PQ 模式下每 16 个 top_candidates 更新触发一次投机预取（`disk_hnsw.cpp:688-705`）：收集当前 top_candidates 中不在缓存的 blocks，批量提交 io_uring 预取。使用 `spec_pf_counter_` 节流。

