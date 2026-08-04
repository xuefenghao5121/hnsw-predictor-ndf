# POC — 探索轨（非 SoT）

本目录 **不是** NDF 权威源，也 **不是** 生产实现树。

流程纪律正文在 **`spec/meta/`**（[[ADR-META-001]]）；下表 ID 仍有效。

| 规则 | 条款 |
|------|------|
| 非 SoT | `ndf.yaml` `poc.sot: false`；[[ARCH-008]]（`spec/meta/architecture.md`） |
| 探索纪律 | [[BEH-018]]（`spec/meta/process.md`） |
| 主题装订 | [[BEH-025]] / [[DEF-022]] / [[DEF-023]] |
| 晋升闸门 | [[BEH-019]] |
| 负结果 | [[BEH-020]]；样板 [[DEC-061]] |
| 勿占用 | `spec/models/`（L3 参考模型专用） |

## 用法

```text
poc/<topic>/
  NOTES.md                 # 实验日志（可粗）
  <code / patches / benches>
  ndf/                     # 主题装订器（MUST，[[BEH-025]]）
    TOPIC.md               # 状态机 + 提案索引 + 基线协议
    proposals/             # 本主题提案或 stub → spec/open/
    evidence/              # validation-*.md
    COMMITS.md             # code_sha ↔ proposals/clauses/protocol
```

```text
NDF（唯一呈现面）：poc/<topic>/ndf/TOPIC.md
复现与口径：poc/<topic>/ndf/COMMITS.md + ndf/evidence/
Trunk must 仍在：spec/00-50（status=stable）
```

主题命名建议与 `proposal-*` / DEC 方向一致（例：`poc/io-pipelining/`、`poc/l4-cache-mgmt/`）。

### 开题清单

1. 创建 `poc/<topic>/ndf/{TOPIC.md,proposals/,evidence/,COMMITS.md}`
2. 首份提案写入 `ndf/proposals/`（可在 `spec/open/` 留 stub 链接）
3. `TOPIC.md` status=`exploring`，登记 `baseline_protocol` 与 draft 条款
4. 之后改测法 / 新 idea → **追加**提案并更新 TOPIC，勿无登记改 Trunk stable

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
