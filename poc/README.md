# POC — 探索轨（非 SoT）

本目录 **不是** NDF 权威源，也 **不是** 生产实现树。

流程纪律正文在 **`spec/meta/`**（[[ADR-META-001]]）；下表 ID 仍有效。

按 [[META-008]]，本目录是三工作空间的 POC 工作副本：DESIGN/INTERFACE 属设计空间，
topic 内代码与 COMMITS 属实现空间，PERF_BASELINE/evidence 属测试空间；DELTA 是设计↔测试
变化账本。装订器读序与口令只作交互编排，不改变 Trunk SoT。

| 规则 | 条款 |
|------|------|
| 非 SoT | `ndf.yaml` `poc.sot: false`；[[ARCH-008]]（`spec/meta/architecture.md`） |
| 探索纪律 | [[BEH-018]]（含写入隔离：禁写 Trunk `src/`/`include/`/`tests/`） |
| 主题装订 | [[BEH-025]] / [[DEF-022]] / [[DEF-023]]（含 DESIGN / DELTA / INTERFACE） |
| 晋升闸门 | [[BEH-019]] |
| 有条件并行 / 基线 stale | [[BEH-025]]（`explore_surface` / `baseline_trunk_sha` / `baseline_status`） |
| 金标唯一绑定 | [[META-007]]：`vs` × `config_id` × `measure_script`（PERF_BASELINE 头） |
| 性能线卡 | [[META-007]] / [[BEH-025]]：`perf_baseline` → `PERF_BASELINE.md` |
| Δ 逻辑空间 | [[BEH-025]]：`ndf/DELTA.md`（Feature / Hotspot / Bind snapshot / Rounds） |
| 设计面 | [[BEH-025]]：分段门禁 TOPIC已审核 → DESIGN已审核 →（绑定+DELTA）→ 可以开始实现 |
| 门禁回执 | [[META-010]]：`ndf/GATES.md` 绑定审批人/时间/内容 SHA；文件存在不等于已审核 |
| 关闭后重启 | [[BEH-025]]：禁同 topic 重开；平级新 topic + `depends_on_topics` |
| 负结果 | [[BEH-020]]；样板 [[DEC-061]] |
| 勿占用 | `spec/models/`（L3 参考模型专用） |

## 用法

```text
poc/<topic>/
  NOTES.md                 # 实验日志（可粗）；关闭时头 status MUST 镜像 TOPIC（[[BEH-025]]）
  <code / patches / benches>
  ndf/                     # 主题装订器（MUST，[[BEH-025]]）
    TOPIC.md               # 状态机 + 表面 + 基线钉扎 + 提案索引
    DESIGN.md              # 软件设计（开题实现前 MUST）
    PERF_BASELINE.md       # 金标绑定头（DESIGN已审核后 MUST）；Numbers 于 R0
    DELTA.md               # 功能/热点逻辑空间（DESIGN已审核后 MUST）
    INTERFACE.md           # 接口设计（开题实现前 MUST）
    GATES.md               # append-only 人工门禁回执（新主题；历史主题可无）
    proposals/             # 本主题提案或 stub → spec/open/
    evidence/              # validation-*.md
    COMMITS.md             # code_sha ↔ proposals/clauses/protocol
```

TOPIC 头字段（摘）：`explore_surface`、`baseline_trunk_sha`、`baseline_status`、
`perf_baseline`、`depends_on_topics`、`conflicts_with_topics`。  
实现前读序：TOPIC → **DESIGN** → **PERF_BASELINE（绑定）** → **DELTA** → **INTERFACE**
→ **GATES** → proposals。  
比性能读序：TOPIC → PERF_BASELINE + DELTA →（按需）`spec/50-verification/{configs,baselines}/`。  
设计/Δ/门禁模板：`spec/meta/templates/poc/{DESIGN,DELTA,INTERFACE,GATES}.md.stub`。  
性能线模板：`spec/50-verification/baselines/PERF_BASELINE.topic-template.md`。  
NOTES 头在 promote/reject 后 MUST 与 TOPIC `status` 对齐（无 NOTES 则 N/A）；勿把 NOTES 当 must。  
开题前：`python3 spec/meta/tools/ndf_index.py poc-topics` 扫相交表面。  
Promote 后：兄弟 exploring 通常 `baseline_status=stale`，回主题先重测 R0。  
已 `rejected` / 全量 `promoted`：**禁止**同 `topic_id` 改回 exploring；再试开平级新
topic（例 `poc/io-pipelining-v2/`），`depends_on_topics` 含旧题与使能依赖（[[BEH-025]]）。
partial 仍 exploring：同题继续，非重启。

历史 POC 不强制回填 `GATES.md`；工具应显示 `legacy/unknown`，不得伪造审批。新项目在进入
本目录前先按 [[META-009]] 完成 Project Genesis；既有健康棕地可 `operational_legacy`
继续运作并可选补 adopt。

```text
NDF（唯一呈现面）：poc/<topic>/ndf/TOPIC.md
设计面：poc/<topic>/ndf/DESIGN.md + INTERFACE.md（[[BEH-025]]）
金标绑定 + 数字：poc/<topic>/ndf/PERF_BASELINE.md（[[META-007]]）
Δ 逻辑空间：poc/<topic>/ndf/DELTA.md（[[BEH-025]]）
复现与口径：poc/<topic>/ndf/COMMITS.md + ndf/evidence/
Trunk must 仍在：spec/00-50（status=stable）
金标 configs/baselines：spec/50-verification/
```

主题命名建议与 `proposal-*` / DEC 方向一致（例：`poc/io-pipelining/`、`poc/l4-cache-mgmt/`）。

### 开题清单

1. 创建目录骨架：`poc/<topic>/ndf/{proposals/,evidence/,COMMITS.md}`；可拷 stub 占位，
   正文按门禁串行填写
2. 写可审的 `TOPIC.md`（status=`exploring`，`baseline_protocol`、draft 条款）+ 首份
   `proposals/` stub → 等用户 **`TOPIC已审核`**；将回执追加到 `GATES.md`
3. 写可审的 `DESIGN.md` → 等用户 **`DESIGN已审核`**；将回执追加到 `GATES.md`
4. 写 `PERF_BASELINE.md` **金标唯一绑定头**（`vs` × `config_id` × `measure_script`；
   Numbers 可 pending R0）+ TOPIC `perf_baseline`，以及 `DELTA.md` 骨架
5. 写可审的 `INTERFACE.md` → 等用户 **`可以开始实现`**；将绑定内容 SHA 的回执追加到
   `GATES.md`（未获准或 SHA 失效 MUST NOT 写主题代码）
6. 首次 R0 后：完善 `PERF_BASELINE.md` Numbers + `baseline_trunk_sha`；更新 DELTA Rounds；
   SHOULD：`python3 spec/meta/tools/ndf_perf_baseline.py check --topic <topic>`
7. **改头/源**：先把相关 `.h`/`.cpp` **复制进本 topic** 再改；MUST NOT 写 Trunk
   `include/` / `src/` / `tests/`（[[BEH-018]]）。MAY 只读链未改动的 Trunk 对象。
8. 之后改测法 / 新 idea → **追加**提案并更新 TOPIC（实质改 DESIGN/INTERFACE 则重新过闸；
   改绑/大改 DELTA SHOULD 请用户过目），勿无登记改 Trunk stable
9. SHOULD：`python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>`

口令与产品提案「已确认 / 已审核」分开。模板：`spec/meta/templates/poc/*.stub`。

### Commit 纪律

代码或验证脚本提交 MUST 带 trailers：

```text
Topic: <topic>
Proposals: ...
Clauses: ...
```

并追加 `ndf/COMMITS.md` 一行。

多轮深入在**同一** `<topic>/`；未晋升前 **禁止** 改写 `spec/20–50` 的 `status=stable` must，
也 **禁止** 把实验默认打开合入 `src/`。

**硬规则**：探索代码 MUST 写在本目录；MUST NOT 先改 Trunk `src/` 再「补 POC」。
若已误改，按 `AGENTS.md` §6.2a 矫正检查清单处理（[[BEH-018]]）。

列出各主题状态：`python3 spec/meta/tools/ndf_index.py poc-topics`
