# Decisions - 严格 cgroup 隔离测试协议 (DEC-065)

> 条款索引: `DEC-065`

## D-065: 严格 cgroup 隔离测试协议确立 {#DEC-065}
<!-- ndf: kind=decision date=2026-08-03 affects=CON-HONEST-002,CHR-006,CON-SLA-011,CON-SLA-014,VER-039 source=deduced -->

**Context.** [[CON-HONEST-002]] 和 [[CHR-001]] 规定 page cache 与 RSS 共享
cgroup 预算（`memory.max ≥ RSS + page_cache`）。但实际测试中，数据准备（root cgroup）
预热的 page cache 不会被重新记账到 benchmark cgroup（cgroup v2 "首次读取者归属"
规则），导致 benchmark 白嫖 root 预热的 cache，实际可用内存远超 cgroup 限制，
性能数字虚高。

**根因分析**：

| 阶段 | 执行者 | cgroup | 行为 | page cache 归属 |
|------|--------|--------|------|----------------|
| 数据准备（离线） | pipeline 工具 | root | 读写数据文件 | root cgroup |
| 检索（在线） | benchmark | hnsw_bench (受限) | 读同一文件 | 不重新记账，仍归属 root |

这不是 bug，是 cgroup v2 的设计。但数据准备和检索是两个独立阶段
（[[CHR-005]] 第 4 点："索引构建是离线 batch"），不应共享 cache 预算。

**真实部署场景**：数据准备在内存充足机器上完成，文件拷贝到内存受限机器上检索。
部署机器上无预热的 page cache，cgroup 记账天然准确。

**Decision.** 确立严格 cgroup 隔离测试协议（[[CON-SLA-014]]）为 **Trunk 一等公民**
（`status=stable` must）：

1. benchmark 前 `sync && echo 3 > /proc/sys/vm/drop_caches` 清空 page cache，
   模拟跨机器部署（文件刚拷贝到新机器，从未被读过）
2. benchmark 在 cgroup 内首次读取文件，page cache 从零开始在 cgroup 内记账积累
3. RSS + page cache 总量受 `memory.max` 严格约束
4. 所有 SLA 验收 MUST 在此条件下执行；未清场对照组 MUST NOT 作验收依据
5. 历史 [[CHR-006]] / [[CON-SLA-011]] 锚点 MUST 按 [[VER-039]] 在严格隔离下复核

page cache 在 cgroup 预算内（limit - RSS）是核心合法加速层。本协议不禁止
page cache，而是保障其在预算内被诚实利用，消除测试中偷用物理机其他空闲
内存导致的性能误差。

**Alternatives rejected.**
- 禁止 page cache（O_DIRECT only）：违反 [[DEC-062]] Buffered 为生产主目标
- 跨物理机器部署测试：成本高，`drop_caches` 在同机上等价模拟
- 修改 cgroup 记账规则：不可能，cgroup v2 设计如此
- posix_fadvise 逐文件驱逐：可行但需代码改动且需知道所有文件路径，
  `drop_caches` 更简单可靠
- 长期保持 CON-SLA-014 为 draft：否决——stable [[CHR-006]] / [[CON-HONEST-002]]
  不得依赖 draft；协议升格为 stable（方案 A，2026-08-03）

> rationale: page cache 在预算内合法且是核心加速层。问题不是"有 page cache"，
> 而是"有超出 cgroup 预算的 page cache"。`drop_caches` 重置 cache 到等价于
> "文件刚到达新机器"的初始态，使 cgroup 记账准确。提案见
> `spec/open/proposal-strict-cgroup-test.md`。

**Note (ID hygiene):** 提案原稿误用 `VER-035`（已占用：FINE_PREAD bug）。
验收条款 ID 更正为 [[VER-039]]。
