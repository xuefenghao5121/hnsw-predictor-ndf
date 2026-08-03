# Proposal: I/O 行为修正 + pipe_ring_ 在严格隔离下重做 POC {#PROP-IO-BEHAVIOR-CORRECTION}

> track: poc
> Status: Pending
> 日期: 2026-08-03
> 修订: r2 — 对齐 [[CON-SLA-014]] / [[DEC-065]]（严格 cgroup 一等公民）后重开验证
> 关联: [[DEC-063]]、[[DEC-064]]、[[DEC-065]]、[[BEH-021]]、[[CON-SLA-013]]、[[CON-SLA-014]]、[[CON-HONEST-002]]、[[CON-POC-001]]、[[VER-039]]、[[CHR-008]]
> 前序: `spec/open/proposal-io-behavior-correction.md` r1（2026-08-02）在白嫖/幽灵变量口径下设计；**本 r2 废止 r1 验证计划，保留问题诊断**

## 0. 为何重开

1. **测试协议升格**：[[CON-SLA-014]] 已为 Trunk **stable 一等公民**。一切相对 QPS / 是否 promote `pipe_ring_` 的结论，MUST 在 C 组（`drop_caches` + 受限 cgroup）下取得；B 组仅作白嫖对照，MUST NOT 作证据。
2. **历史证据失效口径**：[[DEC-063]] / [[DEC-064]] 中标注 `EVICT_PAGE_CACHE=1` 的点，以及未按 [[CON-SLA-014]] 清场的 Buffered 点，**不得**再支撑「pipe 无收益 / +162%」类 promote 叙事，直至本 POC 在 C 组重测。
3. **探索轨边界**：本提案只动 `poc/io-pipelining/` + draft 条款备注；MUST NOT 立刻改 [[CHR-006]] / [[CON-SLA-011]] 数字（[[CON-POC-001]]）。

---

## 1. 问题陈述（诊断保留）

### 1.1 `EVICT_PAGE_CACHE` 幽灵变量

`EVICT_PAGE_CACHE=1` 在实现中**不存在**（no-op）。真实查询间驱逐旋钮是 `FINE_FADVISE=1`。

**影响**：[[DEC-063]] / [[DEC-064]] 中凡写「EVICT_PAGE_CACHE=1 冷态」的数据点，实际未驱逐 page cache → 标称冷态多为热态/半热态。

**固定目录债（本 POC 不顺手改 stable）**：[[API-008]] / [[BEH-016]] / [[CON-SLA-010]] 仍文档化 `EVICT_PAGE_CACHE`。另开 **process** 提案对齐 SoT↔代码（建议 deprecates EVICT → 文档/行为指向 `FINE_FADVISE`，或实现幽灵变量）。本 r2 只要求 POC 脚本与 NOTES **禁止**再写 EVICT 当有效旋钮。

### 1.2 page cache 是 Buffered 设计的一部分

```
可用 page cache 预算 ≈ memory.max − RSS   （[[CON-HONEST-002]] / [[DEC-062]]）
```

- 人为 `FINE_FADVISE` 每查询清空 = 极端 I/O 参考，**不是** Buffered 主场景
- 白嫖 root 预热 cache = 违反 [[CON-SLA-014]]，数字虚高
- **主场景** = 严格隔离后，预算内自然积累的 page cache + 热集溢出时的真实 miss I/O

### 1.3 旧结论状态（待本 POC 改写，不在此提案直接改 DEC 正文）

| 条目 | 原记录 | r2 立场 |
|------|--------|---------|
| DEC-063 EVICT「冷态」 | 标称冷 | **口径错误**（幽灵变量） |
| DEC-063 DEEP10M +162.6% | pipe 收益 | 相对对比可能有 I/O，但**未按 CON-SLA-014**；promote 含义搁置 |
| DEC-064「pipe 无收益」 | post-memopt R1≈R0 | 基于错误/未严格隔离口径 → **对 BEH-021 的负结论搁置**，待 C 组重测 |
| FINE_FADVISE +28.5% | 极端驱逐下 pipe 有收益 | 仅作 **极端参考组 E**，不作 promote 主证据 |

---

## 2. 验证矩阵（对齐 CON-SLA-014）

所有 DEEP10M / SIFT1M 主结论组 MUST：

1. `sync && echo 3 > /proc/sys/vm/drop_caches`
2. 进程入 `memory.max` = 实验规定值的 cgroup
3. 采集 `memory.peak` / `memory.stat`（anon+file）/ `memory.events`（oom=0）
4. 报告标注：`protocol=CON-SLA-014` + cgroup 限额 + 线程数 + query 数

| 组 | cgroup | drop_caches | 额外旋钮 | 用途 |
|----|--------|-------------|---------|------|
| **C** | 规定值 | **是** | 无 FINE_FADVISE | **主证据**（跨机部署模拟） |
| B | 同 C | 否 | 无 | 白嫖对照（B−C = 虚高幅度）；不作验收 |
| E | 同 C | 是 | `FINE_FADVISE=1` | 极端 I/O 上界参考；不作 Buffered 主结论 |
| D | 同 C | 是 | `FINE_DIRECT=1` | Honest 地板辅表（[[CON-SLA-013]] 辅表） |

默认规模建议：

| 数据集 | C 组 memory.max | 备注 |
|--------|-----------------|------|
| SIFT1M | 512MB | 对齐 [[CHR-006]]；热集可能大部分进预算 |
| DEEP10M | 2GB（及可选 3GB） | 2GB=历史 SLA 锚；3GB=post-memopt 宽松预算对照 |

---

## 3. POC 阶段（仅 `poc/io-pipelining/`）

### Phase 0: 工具与卫生

- 更新 `poc/io-pipelining/NOTES.md` / `run_bench.sh`：强制 CON-SLA-014 步骤；删除 EVICT 文档
- 确认 patch 仍只打在 `poc/`（[[ARCH-008]]）
- 输出模板含 memory.peak / anon / file / oom

### Phase 1: C 组基线 I/O 画像（R0，PIPE_FINE=0）

DEEP10M @ 2GB（必做）与可选 3GB：

1. `iostat` / `/proc/<pid>/io` `read_bytes`
2. 可选 `mincore`/`fincore` 看 vecblocks 驻留
3. 记录 QPS / Recall / RSS / cgroup file

**目标**：在严格隔离、自然预算下，热集是否溢出 → 是否存在可被 pipe 隐藏的 I/O。

### Phase 2: 调节至「部分 miss」临界（仍为 C 组）

若 Phase 1 几乎无磁盘读：增大 query 数、收紧 cgroup（在可行 RSS 下）、或换更大 working set；**禁止**用未清场 B 组制造假 I/O。
组 E 仅在需要「确认 pipe 机械能力仍在」时各跑一轮。

### Phase 3: R0 vs R1（C 组主对比）

| 轮次 | 配置 |
|------|------|
| R0 | `PIPE_FINE=0` |
| R1 | `PIPE_FINE=1`（L5 only，对齐 [[CON-SLA-013]]） |

判定（探索目标，非 Trunk must）：

- R1 QPS ≥ R0 × 1.03 且 Recall 不降 → 支持继续 R2–R4 / 未来 promote 讨论
- R1 ≈ R0 且 Phase 1 证实几乎无 I/O → **预算内全命中**，pipe 无舞台（负结果可走 [[BEH-020]]，但须写明 CON-SLA-014 口径）
- R1 ≈ R0 但有显著 `read_bytes` → 实现/阈值问题，继续 POC 调参，不急着写死负结论

### Phase 4: 4T C 组

同 Phase 3；关注 cache 竞争与 `pipe_*` thread_local 正确性（已知历史 4T bug 已修）。

### Phase 5（可选）: SIFT1M C 组烟测

预期多为预算内命中 → pipe 无收益可接受；用于确认协议与脚本，不单独否定 DEEP10M。

---

## 4. 拟触及的 draft / 决策（确认后落地口径）

| 动作 | ID | 说明 |
|------|-----|------|
| 备注证据作废 | [[CON-SLA-013]] 证据表 | 标注「DEC-063/064 pipe 行待 CON-SLA-014 重测；本 POC 产出前不得引用为 promote」 |
| 决策补丁（POC 结束后） | DEC-063 / DEC-064 或新 DEC-066 | 用 C 组结果 amend；**本提案确认时不改 DEC 正文** |
| 保持 draft | [[BEH-021]] / API-010 | 直至 C 组正结果 + promote 提案 |
| 另案 process | EVICT SoT 对齐 | 不阻塞本 POC |

**不在本提案写入 stable must 新 SLA。**

---

## 5. 成功 / 失败定义

| 结果 | 后续 |
|------|------|
| C 组 R1 稳定优于 R0（Recall 合规） | 更新 NOTES + 起草 promote 或继续 R2–R4 |
| C 组无 I/O 舞台且 R1≈R0 | [[BEH-020]] 负结果关闭 BEH-021 promote 路径（写明协议） |
| 仅 E 组有收益、C 组无 | **不得** promote；记录「仅极端驱逐有价值」 |
| 协议/环境失败（oom、无法 drop_caches） | 记 `open/feedback-*.md`，人工介入 |

---

## 6. 非目标

- 不改 `src/` Trunk；不默认打开 PIPE_*
- 不把 B 组或未标注协议的旧数字写回 [[CHR-006]]
- 不把 FINE_FADVISE 主场景化
- 不在本轮实现幽灵 `EVICT_PAGE_CACHE`（除非另开 bug/process）

---

## 7. 开放问题

| # | 问题 | 由谁回答 |
|---|------|----------|
| Q-001 | DEEP10M C@2GB 是否 oom / peak 逼近上限？ | Phase 1 |
| Q-002 | 自然预算下是否存在可测 miss I/O？ | Phase 1–2 |
| Q-003 | 旧 +28.5%（E 组）在 CON-SLA-014 下是否复现？ | 可选 Phase E |
| Q-004 | EVICT SoT 对齐走单独 process 提案？ | 人工确认后另开 |
