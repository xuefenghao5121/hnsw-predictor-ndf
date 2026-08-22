# Process 提案：提案平面按落点目录分类 {#PROP-META-PROPOSAL-PLANE-BY-PATH}

> track: process
> Status: Implemented on 2026-08-12
> refines: META-011
> depends-on: META-011
> 关联: [[META-011]], [[ADR-META-001]]

## 背景

Workflow 投影把未关闭提案分成 Business Project 与 NDF Control 两列。
已落地的三平面分离要求「产品 proposal 与 process proposal 分类无混入」。

现行分类器在路径判断之外，还把头部 `track: process` 的文件送进 Control。
于是落在产品 `spec/open/` 的提案只要误标 track，就会出现在 Governance 的
process 列表。平面 SoT 是目录，不是 track 头。

## 决策

1. 提案平面 MUST 按落点目录分类：
   - `spec/open/` → Business Project（`product_proposals`）
   - `spec/meta/open/proposal-meta-*.md` → NDF Control（`process_proposals`）
2. `track` 头 MUST NOT 把产品目录文件投影到 Control，也 MUST NOT 把 meta
   目录文件投影到 Product。
3. 路径与 track 不一致时 MUST 记 warning，MUST NOT 改平面。
4. 产品域误标 `track: process` 的提案 MUST 留在 `spec/open/`，MUST NOT 迁入
   `spec/meta/`。

## 变更

- [[META-011]]：三平面段补一句路径分类纪律。
- `spec/meta/tools/ndf_workflow_status.py`：`scan_proposals()` 只按路径分平面；
  `control.spec_health.proposal_plane_warnings` 记录路径/track 不一致。
- 纠正产品 `spec/open/` 中误标 `track: process` 且仍开放的提案头部（仍留在
  产品目录）。已关闭/Implemented 的误标文件不在本次改正文，由 warning 暴露。

## 验收

1. Governance process 列表不含 `spec/open/` 文件。
2. 产品 `spec/open/` 的开放提案出现在 Product 提案列表。
3. 路径/track 不一致时 snapshot 含 `proposal_plane_warnings`。
4. `python3 spec/meta/tools/ndf_graphcheck.py --meta` hard_errors=0。
5. Canvas 不手改 process 行，只重嵌官方 `canvas-json` SNAPSHOT。
