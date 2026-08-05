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
<!-- ndf: amended-by=DEC-067 -->

> **⚠️ AMENDED (2026-08-03, [[DEC-067]])**: 本决策的基线数据（22.9/18.4/22.8/19.5 QPS）
> 因测试脚本环境变量拼写错误（`PQ_CODE_PATH` 应为 `PQ_CODES_PATH`）而无效。
> PQ codes 未加载导致走了 fallback 路径。修正后真实严格隔离基线恢复到 2309/6060/837/3215 QPS，
> 旧 SLA 数字在严格隔离下仍然有效。详见 [[DEC-067]]。

**Context.** [[CON-SLA-014]] 严格 cgroup 隔离测试协议落地后，首次 SIFT1M 基线测试
（2026-08-03, 512MB cgroup, 200 queries, drop_caches 清场）结果与旧 SLA 数字差异巨大：

| 模式 | 线程 | 旧 SLA (白嫖 era) | 严格隔离基线 | 下降 |
|------|------|-------------------|-------------|------|
| Buffered | 1T | ≥2000 (实测 ~2300) | **22.9** | 100x |
| Buffered | 4T | ≥5000 (实测 ~5800) | **18.4** | 315x |
| O_DIRECT | 1T | ≥100 (实测 130) | **22.8** | 5.7x |
| O_DIRECT | 4T | ≥400 (实测 502) | **19.5** | 25.7x |

> **上述数据全部无效（PQ_CODES_PATH 拼写错误）。修正数据见 [[DEC-067]]。**

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

---

## D-067: DEC-066 修正 - 环境变量拼写错误导致假基线 {#DEC-067}
<!-- ndf: kind=decision date=2026-08-03 affects=DEC-066,CHR-006,CON-SLA-011,VER-039,CON-SLA-013 source=observed -->

**Context.** DEC-066 的严格隔离基线（22.9/18.4/22.8/19.5 QPS）因测试脚本环境变量
拼写错误而无效：脚本设 `PQ_CODE_PATH`（无 S），benchmark 代码读 `PQ_CODES_PATH`（有 S）。
PQ codes 未加载 -> `pq_enabled_=false` -> 走 fallback 路径（无 PQ 粗筛）-> Recall=98.35%
但 QPS=23（极慢）。

修正后（PQ_CODES_PATH）在 [[CON-SLA-014]] 严格隔离下重测：

| 模式 | 线程 | DEC-066 假基线 | 修正基线 | 旧 SLA | 达标 |
|------|------|---------------|----------|--------|------|
| Buffered | 1T | ~~22.9~~ | **2309** | ≥2000 | ✅ |
| Buffered | 4T | ~~18.4~~ | **6060** | ≥5000 | ✅ |
| O_DIRECT | 1T | ~~22.8~~ | **837** | ≥100 | ✅ |
| O_DIRECT | 4T | ~~19.5~~ | **3215**⚠️ | ≥400 | ⚠️ recall=13.95% |

cgroup 验证：memory.peak=512MB=memory.max，oom=0，无白嫖。

**Decision.**

1. **DEC-066 基线数据废止**：22.9/18.4/22.8/19.5 标注为环境变量错误导致的假基线
2. **旧 SLA 恢复有效**：Buffered ≥2000/≥5000、O_DIRECT ≥100/≥400 在严格隔离下达标
3. **CHR-006 / CON-SLA-011 恢复旧 SLA must 数字**，附注严格隔离验证已通过
4. **CON-SLA-014 协议不变**：仍为唯一合法测法
5. **O_DIRECT 4T recall 异常待查**：疑为 O_DIRECT+io_uring 多线程问题
6. **环境变量教训**：所有测试脚本 MUST 使用 `PQ_CODES_PATH`（有 S）

> rationale: 22.9 QPS 不是严格隔离的真实性能，是 PQ 未加载的 fallback 路径性能。
> 修正后 2309 QPS 证明 SIFT1M @ 512MB cgroup 的 page cache 预算（~357MB）足以覆盖热工作集，
> 旧 SLA 数字在严格隔离下仍然有效。page cache 白嫖问题在 SIFT1M 规模下影响可忽略。

---

## D-068: Promote l4-cache-mgmt - flat_vec_cache + O_DIRECT 4T fix {#DEC-068}
<!-- ndf: kind=decision date=2026-08-03 affects=BEH-024,CHR-006 source=observed -->
<!-- ndf: promotes=l4-cache-mgmt -->

**Context.** L4 POC 发现两个可 promote 的代码修复：

1. **fine rerank 未查 flat_vec_cache**：候选循环查 BlockCache 后直接走 pread，
   没查 flat_vec_cache（4MB 进程内热向量缓存）。热向量不必要地走磁盘 I/O。
   在 256MB cgroup（page cache 不足）下，增大 flat_vec_cache 到 64MB 后 QPS 提升 7.5x。

2. **O_DIRECT 4T pread 条件错误**：`if (kFinePread && !kFineDirect)` 导致
   O_DIRECT 模式跳过 pread 走了非线程安全 io_uring，4T recall 崩到 12%。

**Decision.** 合入 Trunk `src/`：

1. fine rerank 候选循环加 `getFlatVector()` 检查（+2 行）
2. `if (kFinePread && !kFineDirect)` -> `if (kFinePread)`（1 行改）
3. pread buffer `new char[]` -> `posix_memalign`（3 行改）
4. BEH-024 draft -> stable

**验证**（CON-SLA-014, 512MB cgroup）：

| 用例 | SLA | 实测 | 判定 |
|------|-----|------|------|
| Buffered 1T QPS | ≥2000 | 2365 | ✅ |
| Buffered 4T QPS | ≥5000 | 5765 | ✅ |
| Recall@10 | ≥95% | 95.75% | ✅ |
| O_DIRECT 4T Recall | ≥95% | 95.75% | ✅ |
| RSS 1T | ≤300MB | 155MB | ✅ |
| oom | =0 | 0 | ✅ |

> rationale: 两个修复都不改变搜索逻辑（零 recall 风险），仅优化缓存命中和线程安全。
> flat_vec_cache 增大由用户按需调整（FLAT_VEC_MB），不改默认值。

---

## D-069: Promote flat_vec_cache cap fix {#DEC-069}
<!-- ndf: kind=decision date=2026-08-03 affects=BEH-024 source=observed -->
<!-- ndf: promotes=l4-cache-mgmt -->

**Context.** flat_vec_cache 预算 `vec_budget = std::min(cache_bytes, vec_max_bytes)` 受 CACHE_MB
限制。FLAT_VEC_MB > CACHE_MB 时无法增大。DEEP10M 上 128/256MB 配置无效（slots cap at 173K）。

**Decision.** 合入 Trunk: `vec_budget = vec_max_bytes`（1 行改）。flat_vec_cache 独立于
BlockCache slots 预算。

**验证**: SIFT1M 512MB 无回归 (QPS=2108 ≥ 2000 ✅, Recall=95.75% ✅)。
DEEP10M 2GB: 128MB flat_vec = 698 QPS (+20% vs 581 基线)。
