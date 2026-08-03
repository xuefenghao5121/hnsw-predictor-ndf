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

---

## D-066: 旧 SLA 数字废止 - 严格隔离基线确立 {#DEC-066}
<!-- ndf: kind=decision date=2026-08-03 affects=CHR-006,CON-SLA-011,CON-SLA-008,CON-SLA-013,DEC-057,DEC-059,VER-039 source=observed -->

**Context.** [[CON-SLA-014]] 严格 cgroup 隔离测试协议落地后，首次 SIFT1M 基线测试
（2026-08-03, 512MB cgroup, 200 queries, drop_caches 清场）结果与旧 SLA 数字差异巨大：

| 模式 | 线程 | 旧 SLA (白嫖 era) | 严格隔离基线 | 下降 |
|------|------|-------------------|-------------|------|
| Buffered | 1T | ≥2000 (实测 ~2300) | **22.9** | 100x |
| Buffered | 4T | ≥5000 (实测 ~5800) | **18.4** | 315x |
| O_DIRECT | 1T | ≥100 (实测 130) | **22.8** | 5.7x |
| O_DIRECT | 4T | ≥400 (实测 502) | **19.5** | 25.7x |

**根因**：旧测试未执行 drop_caches，数据准备阶段（root cgroup）预热的 page cache
（vecblocks ~450MB + graph ~587MB + PQ ~31MB）被 benchmark 进程白嫖，实际可用内存
远超 512MB cgroup 限制。严格隔离后，cgroup 撞满 512MB，内核疯狂回收 page cache
（max events 1523-7141 次），每次查询都重新读盘。

**Decision.**

1. **测法一等公民**：[[CON-SLA-014]] 为后续一切 SLA/POC 对齐的唯一合法口径
2. **旧 QPS must 废止**：Buffered ≥2000/≥5000、Honest ≥100/≥400 **不再有效**
3. **观测对齐基线确立**：上表 QPS 写入 [[CHR-006]] / [[CON-SLA-011]] 作为 R0 锚点；
   **不是** must 点承诺。回归 SHOULD ≥ 基线 × 0.9；优化在同协议下抬升基线
4. **Must 门槛保留/修订**：Recall≥95%、oom=0、peak≤512；RSS **1T≤300 / 4T≤450**
   （4T 实测 416–426，旧统≤300 在严格隔离多线程下不成立）
5. **后续优化**：压低 RSS、改善 I/O、或审慎评估提高 cgroup——均须在严格隔离下复测

**Alternatives rejected.**
- 保留旧 SLA 数字：不诚实，违反 [[CON-SLA-014]]
- 把 22.9 写成 must 下限并宣告「达标」：混淆观测与承诺；基线过低且 200q 样本偏薄
- 上调 cgroup 仅为刷回旧数字：掩盖问题，非真实受限场景
- 继续用白嫖对照作优化证据：否决

> rationale: 严格隔离符合「数据准备与检索分离」的部署语义，是当前最合理测法。
> 基线虽低，但是 512MB 下的真实地板；后续优化目标是在该协议下抬升 QPS，
> 而非假装白嫖数字仍然有效。补全提案见 `spec/open/proposal-strict-baseline-semantics.md`。
> 详细报告见 `spec/open/validation-20260803-strict-baseline.md`。
