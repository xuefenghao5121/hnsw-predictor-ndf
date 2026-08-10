# API-020: FINE_CQE_PEEK — CQE Peeking Toggle
<!-- ndf: kind=clause id=API-020 level=2 status=stable -->
<!-- ndf: depends-on=API-012 trunk-ref=f16e0bdb8e94635fc515d20906a3ca9a7a895c40 -->
<!-- ndf: source=poc/ssd-parallelism-io/ ; track=promote ; Topic: ssd-parallelism-io -->

## 环境变量

| 变量 | 类型 | 默认 | 范围 | 说明 | 引用 |
|------|------|------|------|------|------|
| `FINE_CQE_PEEK` | int | 1 | 0/1 | 1=CQE peeking 完成顺序处理模式; 0=legacy 批量屏障 | [[BEH-036]] |

## 前置条件

- `FINE_PREAD=0`（启用 io_uring 路径）
- `vec_ring_` 已作为 thread_local per-thread io_uring 初始化
- 内核 io_uring 支持 ≥ 5.1

## 接口影响

- 仅影响 Fine Rerank io_uring 路径的距离计算时序
- 不影响 pread 路径（`FINE_PREAD=1`）
- 不影响粗排 Phase A
- Recall 不变（完成顺序不影响结果正确性）
