# Process 提案：初始化内完成骨架 stable + 基线复现

> track: process
> status: Implemented
> Status: Implemented on 2026-08-25
> reviewed: 已审核
> plane: process
> control-flow: managed
> proposal-id: meta-genesis-init-freeze
> flow-id: meta-genesis-init-freeze
> 日期: 2026-08-25
> 修改: META-009 薄补；supersedes meta-genesis-promote-guide
> depends-on: META-009, META-006, META-010
> deprecates: meta-genesis-promote-guide
> 范围: bootstrap 收口语义；不改 Trunk 业务代码
> land-targets: spec/meta/process.md, AGENTS.md, .cursor/skills/ndf-workflow/genesis.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/close.md

Status: Implemented on 2026-08-25 (human phrase `已确认`).
Reviewed: 已审核 on 2026-08-25 (human phrase in Composer).

人类原话：不要又臭又长；初始化填好 NDF 后用户审核即可把文档骨架全部 stable（作为优化/二次开发对照目标）；验证目标与金标测试结果也要在初始化阶段复现一次，再 stable；用户不必频繁口令。

## 1. 废止

`proposal-meta-genesis-promote-guide.md`（事后教用户分 A/B promote）——把初始化负担甩到日常，交互过重。标记 `superseded`。

## 2. 干净初始化形状

```text
角色已配置
→ Command 绑内核
→ 人「派发」一次：设计写 spec/00–50 + 复现验证基线
→ 人「GENESIS已审核」→ 骨架与已复现基线一并 status=stable
```

人口令仅两句（加角色向导则三句）。MUST NOT 要求 GENESIS 后再走一轮 promote 才 stable 骨架。

### 2.1 「派发」一次做什么

同一 bootstrap 委派（Control 写契约；测量可由同一 hop 触发或 Implementation 同包串行，对人类仍是一句「派发」）：

1. **设计**：对照 Trunk 写满 `spec/00–50`（先 draft 落盘）。
2. **复现**：按刚写入的 VER 协议跑 `make test` + 约定金标/ sustained（或仓内已有权威入口）；写入
   `spec/50-verification/configs/`、`baselines/`，数字绑定 `observed_trunk_sha`。
3. 磁盘 `ndf-agent-completion/v1` 同时覆盖契约文件 + 基线文件。

测不出（缺数据/机时）：completion MUST 标明 `baseline_status=deferred` 与原因；
`GENESIS已审核` 时 **骨架仍可 stable**，SLA/性能条款保持 `not-established` 直至补测——
补测仍属初始化欠账，用一句「继续」补基线，MUST NOT 展开日常 promote 教程长文。

### 2.2 「GENESIS已审核」做什么

Command（不另派 OpenClaw）落地：

- 非性能骨架条款（CHR/ARCH/BEH/API/非 SLA 约束/VER 协议正文）→ `status=stable`
- 已写入且绑定 Trunk SHA 的 baseline / 对应 `CON-SLA-*` → `status=stable`
- 未复现成功的 SLA → 留 `not-established`（诚实）
- 写/更新 Genesis DEC：骨架 = **优化与二次开发的对照目标**；基线 = **对照测量**

语义：stable 骨架 = 「当前 Trunk 的契约真相」；后续 POC/优化相对此目标与基线比较。

## 3. 日常轨（初始化之后）

优化 / 二次开发 → 开 POC 或 promote；对照 Genesis 冻结的骨架与基线。
MUST NOT 把「把 init 骨架升 stable」再做成日常多轮口令。

## 4. 验收

- META-009 / genesis skill 叙述与 §2 同形，无「GENESIS 后再教 A/B promote」长文
- 本仓若需补基线：一句「继续」即可，不新开用户手册章节
