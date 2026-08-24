# Proposal: POC 装订器软件设计 + 接口设计面 {#PROP-META-POC-DESIGN-DOCS}

> track: process  
> Status: Implemented on 2026-08-11  
> 日期: 2026-08-11  
> 关联: [[BEH-025]], [[DEF-022]], [[ARCH-008]]  
> 场景: 装订器增加可指导编码的 DESIGN / INTERFACE  
> 原则: 只改 NDF 工作流；不代写现有 POC 正文；不蒸馏 harness

## 1. 动机

装订器（[[BEH-025]]）现有 `TOPIC` / `proposals` / `evidence` / `COMMITS` / `PERF_BASELINE`
解决状态机、draft L1 与可复现，但实现方缺少**可编码**的模块划分与 POC 内调用面契约。
散文假设无法替代软件设计与接口设计。

## 2. 决策

1. 装订器新增 **`ndf/DESIGN.md`**（软件设计）与 **`ndf/INTERFACE.md`**（接口设计）
2. **与 draft L1 分工**：
   - `proposals/` + draft 条款 = WHAT（行为与验收意图）
   - `DESIGN.md` = HOW（模块、数据流、文件落点、Trunk 拷贝边界）
   - `INTERFACE.md` = POC 内调用面（类型/签名/env/错误）；**不**替代 `spec/30-interfaces/` stable
3. **开题门禁**：无 TOPIC + DESIGN + INTERFACE（节标题齐即可先占位）→ MUST NOT 开始主题代码实现
4. 阅读顺序：TOPIC → DESIGN → INTERFACE → PERF_BASELINE（若有）→ proposals → evidence → COMMITS
5. 模板：`spec/meta/templates/poc/{DESIGN,INTERFACE}.md.stub`
6. 历史 exploring/已关闭缺两文件：bindcheck **warning**（不 exit 1）；新开题 / 平级重启 MUST
7. promote：接口切片走 draft→stable；MUST NOT 把整份 DESIGN 搬进 `spec/models/`

## 3. 非范围

- 不代填任何现有 `poc/*/ndf/DESIGN.md` / `INTERFACE.md`
- 不动 `packages/ndf-harness`
- 不改产品 stable L1 / `src/`

## 4. 验收

条款 + 模板 + AGENTS/poc README/CLAUDE 薄同步 + bindcheck warning；
`graphcheck --meta` hard_errors=0。
