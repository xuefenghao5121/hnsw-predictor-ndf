# Draft 状态并发映射

> role: ndf-process-mapping
> product_behavior: false
> sot: true（Draft **演进状态**）；false（产品 stable must）
> 提案: `spec/meta/open/proposal-meta-draft-mapping.md`

本目录是 Control 流程映射面，与固定 8 模块正文并发存在、互不写回。
它不是 Trunk SoT：`status=stable` 产品条款仍只写在 `spec/00–50`
（[[ARCH-008]] / [[CHR-008]]）。

Canvas MUST NOT 手改本目录映射行；只重嵌官方 `canvas-json` SNAPSHOT。

## 条目 schema（最低字段）

每个 draft 条款一条目。推荐 `spec/meta/open/draft-map/<clause-id>.md`：

```text
> clause_id: BEH-XXX
> topic: <poc-topic 或 meta>
> topic_ndf: poc/<topic>/ndf/TOPIC.md
> proposed_status: exploring | closing | rejected
> refs: <proposal / DEC / evidence>
> sha: <条目内容哈希>
```

| 字段 | 含义 |
|------|------|
| `clause_id` | draft 条款 ID（或拟新增稳定条款的目标 ID） |
| `topic` | 绑定 `poc/<topic>/` 或 `meta` workflow 主题 |
| `topic_ndf` | 装订器 `TOPIC.md` 路径（[[DEF-022]] / [[BEH-025]]） |
| `proposed_status` | `exploring` / `closing`（晋升编排）/ `rejected`（负结果关闭） |
| `refs` | 提案 / DEC / 证据指针 |
| `sha` | 条目内容哈希，供 [[META-010]] 回执校验漂移 |

本轮只建立目录语义与扫描；**不**自动生成既有 draft 的条目文件。
具体条目生成器由后续 process 提案落地。

## 晋升受控路径（[[BEH-019]]）

```text
exploring → closing → archived → 固定模块正文写入 status=stable
```

1. 提案确认把条目 `proposed_status` 从 `exploring` 标为 `closing`。
2. 全部闸门通过后，条目迁入 `archive/`（或保留等效摘要指针）。
3. 然后才允许固定模块正文写入对应 `status=stable` 条款。
4. MUST NOT 在条目仍 `exploring` 时把正文写成 stable。

负结果（[[BEH-020]]）MUST 将 `proposed_status` 标 `rejected` 并归档；
MUST NOT 静默删除条目抹平历史。

## 扫描

`ndf_workflow_status.py` 对固定 8 模块中 `status=draft` 且无对应映射行的条款
记 `draft_map_warnings`（warning，非 hard_error）。
