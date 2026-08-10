# BEH-036: io_uring CQE Peeking — Completion-Order Fine Rerank
<!-- ndf: kind=clause id=BEH-036 level=1 status=stable -->
<!-- ndf: refined=BEH-021 depends-on=API-020,API-012 trunk-ref=f16e0bdb8e94635fc515d20906a3ca9a7a895c40 -->
<!-- ndf: source=poc/ssd-parallelism-io/ndf/TOPIC.md ; track=promote ; Topic: ssd-parallelism-io -->

## Behavior

在 Fine Rerank 的 io_uring 路径（`FINE_PREAD=0`）中，
**CQE peeking** 替代原有的批量屏障模式：

1. **CQE 到达后立即处理**：每个 I/O 完成 CQE 到达后，
   立即计算依赖该页的所有候选向量的距离（完成顺序处理）
2. **页-候选索引**：预建 page → candidate 索引表，
   CQE 到达后 O(1) 查找受影响候选
3. **跨页候选延迟**：跨页候选需两页都就绪后才计算
4. **残余处理**：CQE 全部 arrived 后处理未触发的边缘候选

### 对比原有批量屏障

| 维度 | 批量屏障 (legacy) | CQE peeking (BEH-036) |
|------|-------------------|----------------------|
| 距离计算 | 全部 I/O 完成后统一算 | CQE 到达立即算 |
| CPU 空闲 | 等待所有页完成 | 先到先算，CPU 不空闲 |
| I/O 等待 | 固定顺序阻塞 | 完成顺序 (消除屏障) |
| 多线程安全 | 共享 ring (需 pread) | per-thread io_uring |

### 环境变量

- `FINE_CQE_PEEK=0` 回退到 legacy 批量屏障模式（默认开启）
- `FINE_PREAD=0` 启用 io_uring 路径（前置条件）

## Rationale

POC ssd-parallelism-io R0-R3 证据：
- 1T: +3.5% QPS, I/O wait −37%, Fine stage −5%
- 4T: +3.2% QPS
- 16T: +1.0% QPS (收益递减，多线程 pread 并行度已高)
- Profile root cause: first CQE @10us vs pread batch barrier @407us

See: `spec/open/proposal-promote-cqe-peeking.md`, `poc/ssd-parallelism-io/`
