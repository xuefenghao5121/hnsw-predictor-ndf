# Proposal: 可移植 NDF Harness 包（规范 + 工作流 + 治理） {#PROP-META-NDF-PORTABLE-HARNESS}

> track: process  
> Status: Implemented on 2026-08-04  
> 日期: 2026-08-04  
> 关联: [[CHR-008]], [[BEH-018]], [[BEH-019]], [[BEH-020]], [[BEH-025]], [[BEH-026]], [[ARCH-008]], [[CON-POC-001]], [[DEF-022]], [[DEF-023]], [[DEF-NDF-GRAPH]], [[ADR-META-001]]  
> 场景: 流程推广 / harness 工程化 / 跨仓复用  
> scope: ndf-process  
> depends-on: GOVERNANCE.md（工具治理参考）

## 1. 动机

NDF 已在真实工程中验证可落地：process / product 分层、双轨（poc ↔ promote）、装订器、
多角色协作、以及「taxonomy → index → linter → advise → 人工改 SoT」治理链。

对外推广时，缺的不是「再写一篇介绍」，而是可复制的三件套：

1. **NDF 规范本身**（条款格式、层、状态、process profile——可移植、无产品域内容）  
2. **真实项目工作流**（以 **`AGENTS.md` 为权威操作手册**：track、提案闸门、写入边界、验证路由）  
3. **治理 harness**（index / graphcheck / bindcheck / advise / close + GOVERNANCE）

消费方包括但不限于：**OpenClaw、Claude Code、OpenCode、Cursor** 及其他能读仓库约定 / skill 的 Agent。  
Harness **MUST NOT** 以某一 IDE 或某一 Agent 运行时为唯一入口。

本提案定义 **NDF Portable Harness**：初始化时装上规范与工作流，日常用同一套工具治理。  
**MUST NOT** 把任一具体产品域的条款、SLA、模块名、样板负结果叙事打进通用包。

---

## 2. 一句话产品定义

**NDF Harness = 可移植的 NDF 规范种子 + `AGENTS.md` 工作流 + 审核工具链 + 运行时无关的 Harness Skill 核心；  
各 Agent（OpenClaw / Claude Code / OpenCode / Cursor …）仅通过薄适配层挂载同一核心。  
Init 交付「能按 NDF 指挥开发」的空产品树；Govern 交付治理主链。  
人工闸门写 SoT；工具永不静默写条款 / git。**

---

## 3. 三等产物（缺一不可）

| 优先级 | 产物 | 落点（目标仓） | 说明 |
|--------|------|----------------|------|
| **P0** | **NDF 规范** | `spec/meta/**` + `ndf.yaml` + 空 `spec/00–50` 骨架 | 条款写法、双轨/装订/卫生；**无业务条款** |
| **P0** | **工作流手册 `AGENTS.md`** | 仓库根 `AGENTS.md` | **跨 Agent 的默认入口**：任何会读根目录约定的 Agent 都能按 track 指挥 |
| **P0** | **治理工具 + GOVERNANCE** | `spec/meta/tools/**` | CLI 主链；与 IDE 无关 |
| **P0** | **Harness Skill 核心** | `packages/ndf-harness/skill/`（见 §5） | init / adopt / govern / sync 的**单一正文**；不绑某一运行时 |
| P1 | 运行时适配层 | `adapters/<runtime>/` | 把核心挂到 OpenClaw / Claude Code / OpenCode / Cursor 等 |
| P1 | 实现侧边界片段 | 如 `CLAUDE.md` stub | 编码禁区；由适配层安装到各运行时习惯路径 |

> **`AGENTS.md` 不是可选 stub，也不是 Cursor 专用。** 它是仓库级工作流 SoT；Skill 核心只是把 Init/Govern 步骤写清楚，供各运行时加载。  
> Init 生成的 `AGENTS.md` MUST **产品无关**、**运行时无关**（步骤 1–6、写入边界、场景路由、禁止行为）；`⟨TBD⟩` 只占项目名与实现目录约定。

---

## 4. 打包形态

### 4.1 两阶段

| 阶段 | 形态 | 目的 |
|------|------|------|
| **A（本提案）** | `packages/ndf-harness/`（含 skill 核心 + adapters） | 定契约；可复制到任意仓 |
| **B（另开）** | 独立模板仓 / pin 版本 | 他仓直接取得 |

阶段 A **MUST NOT** 把「升级 `.cursor/skills`」写成唯一交付；Cursor 适配只是 adapters 之一。

### 4.2 目录契约（阶段 A）

```text
packages/ndf-harness/
├── README.md                      # 对外：规范 / AGENTS / 治理 / 多运行时
├── VERSION
├── ndf.profile.yaml
├── norms/                         # ★ NDF 规范种子（产品无关）
│   ├── ndf.yaml.stub
│   ├── CLAUSE-FORMAT.md
│   ├── meta/                      # process profile 正文种子（去产品叙事）
│   └── product-tree/              # 空 00–50 + open/ + decisions/
├── workflow/                      # ★ 真实项目工作流（跨 Agent）
│   └── AGENTS.md                  # 完整指挥手册 → 安装到仓库根
├── governance/                    # ★ 治理（CLI，与 IDE 无关）
│   ├── GOVERNANCE.md
│   ├── tools/README.md + VENDOR.md
│   └── docs/GOVERN.md
├── skill/                         # ★ Harness Skill 核心（运行时无关）
│   ├── SKILL.md                   # init|adopt|govern|sync 正文 SoT
│   ├── MODES.md                   # 四模式检查清单
│   └── reference.md               # 路径铁律、覆盖策略
├── adapters/                      # ★ 薄适配：只声明「如何加载 skill/」
│   ├── README.md                  # 适配约定：禁止在适配层复制业务流程正文
│   ├── openclaw/                  # 例：skills/ndf-harness/ 或 ndf-workflow 指针
│   ├── claude-code/               # 例：.claude/skills/ 或 CLAUDE.md @引用
│   ├── opencode/                  # 例：OpenCode skill / 指令清单路径
│   ├── cursor/                    # 例：.cursor/skills/ndf-harness → 指向或包装 skill/
│   └── generic/                   # 仅 README：请 Agent 阅读 packages/.../skill/SKILL.md + AGENTS.md
├── templates/
│   ├── poc/
│   ├── implementer-boundaries.md  # 通用实现侧禁区（再映射到 CLAUDE.md 等）
│   └── ci/
└── docs/
    ├── QUICKSTART.md
    └── INIT.md
```

**适配层纪律（MUST）**：

1. **业务流程正文只在一处**：`skill/SKILL.md` + `workflow/AGENTS.md` + `norms/` + `governance/`。  
2. `adapters/<runtime>/` 只含：安装路径说明、入口文件（短指针 / frontmatter）、可选运行时特有开关。  
3. **禁止**在 Cursor 适配里写一套完整流程、在 OpenClaw 再写一套——漂移即缺陷。  
4. 新增运行时 = 新增一个 adapter 目录，**不**改 skill 核心语义。

**规范去产品化**：删除具体产品名、产品 SLA、模块路径、产品 DEC 长文；反面教材用抽象表述。

**工具同步**：阶段 A 实现源唯一 = 维护仓 `spec/meta/tools/*.py`；包内 `VENDOR.md` 说明取得方式，不双头复制 `.py`。

### 4.3 目标仓消费面

| 面 | 路径 | 谁读 |
|----|------|------|
| NDF 规范 | `spec/meta/**`、`ndf.yaml` | 任意 Agent / 人 |
| 产品契约 | `spec/00–50`、产品 open/decisions | 任意 Agent / 人 |
| 工作流 | **`AGENTS.md`（根）** | **默认跨运行时入口** |
| Harness Skill | 经 adapter 挂载的 `skill/SKILL.md` | 支持 skill 的运行时；否则读 generic 指引 |
| 治理 CLI | `spec/meta/tools/**` | 人 / Agent / CI（与 IDE 无关） |
| 探索 | `poc/<topic>/ndf/` | sot: false |

纯 process ID MUST NOT 写入产品 adopted 表。

---

## 5. Harness Skill：核心四模式（运行时无关）

正文 SoT：`packages/ndf-harness/skill/SKILL.md`。

| 模式 | 触发（自然语言，不绑产品） | 行为 |
|------|----------------------------|------|
| **init** | 「用 NDF 初始化项目」 | 装 norms + **生成根目录 AGENTS.md** + 治理指引 → 等人工确认 |
| **adopt** | 「棕地接入 NDF」 | 补规范 / 对齐 AGENTS；不覆盖定稿 |
| **govern** | 「NDF 治理」 | 按 GOVERNANCE 主链出 CLI 与报告路径；不自动改 SoT |
| **sync** | 「同步 harness」 | 刷新 norms/模板/VENDOR；diff AGENTS；禁止静默覆盖 |

各 adapter 只用运行时惯用方式暴露上述四模式（slash 命令、skill 名、系统提示引用等），**语义 MUST 一致**。

### 5.1 角色模型（可替换标签，不绑单一产品栈）

| 逻辑角色 | 职责 | 典型落点（示例，非强制） |
|----------|------|--------------------------|
| **指挥** | 读规范 + AGENTS；出提案；不写实现主线 | OpenClaw / 任意指挥会话；入口 `AGENTS.md` |
| **实现** | 按 track 写 `poc/` 或主线实现 | Claude Code / OpenCode / 其他编码 Agent |
| **审核 / 脚手架** | Init、规范卫生、跑治理 CLI、维护 harness | Cursor / OpenCode / 人 + CLI |

Harness **不要求**三者同时存在；单 Agent 仓也可只装 AGENTS + norms + tools。

### 5.2 Init（绿场）

```text
1. 选 profile（默认 dual-track）
2. Draft：norms → spec/；AGENTS.md → 根；governance 文档 → meta/tools；按需装 adapter
3. 等待人工确认后再填 ⟨TBD⟩；跑 index + graphcheck 基线
```

`AGENTS.md` MUST 覆盖：必读序、track 与提案路径、确认闸门、写入边界、场景路由、禁止行为。

### 5.3 Govern（CLI 主链）

```text
ndf_index → graphcheck ‖ bindcheck → advise plan → simulate → 人工改 SoT → recheck
POC 收口：ndf_close plan
```

与是否在 Cursor 内运行无关；输出 MUST 含「sandbox ≠ apply」。

---

## 6. Profile

| Profile | NDF 规范 | AGENTS.md | 工具 | 适用 |
|---------|----------|-----------|------|------|
| **dual-track**（默认） | 完整 meta + poc 骨架 | **强制** | 全套 | 探索/晋升分流 |
| **minimal** | 精简 meta + 00/20/open | **强制** | index + graphcheck | 先规范与工作流 |
| **linter-only** | 不强制 | 不强制（SHOULD 提示补齐） | 工具 + GOVERNANCE | 已有规范，只加治理 |

---

## 7. 确认后落地清单

| 位置 | 动作 |
|------|------|
| `packages/ndf-harness/**` | 新增：norms / workflow / governance / **skill/** / **adapters/** / docs |
| `spec/meta/tools/HARNESS.md` | 分发与多运行时说明（互补 GOVERNANCE） |
| 既有 `.cursor/skills/ndf-harness` | **降级为 adapter**：改为指向或包装 `packages/.../skill/`，删除「仅 Cursor」表述 |
| `spec/meta/README.md`、`tools/README.md` | 导航 |
| 本提案 | Implemented |

不写目标产品业务条款；不改产品 SLA。

---

## 8. 非目标

- 打进任何具体产品域契约 / SLA / 模块 / 历史 DEC 正文  
- 将 Harness **强绑定** Cursor（或任一单一运行时）  
- 在多个 adapter 中复制全套工作流正文  
- 自动 apply 沙盒 / 自动 git commit  
- 用与 NDF 无关的本地项目状态文件充当配置  
- 替换 `ndf-design`（写单条条款）  
- 阶段 B 发版形态（另案）

---

## 9. 与相邻材料

| 名称 | 职责 |
|------|------|
| **`skill/SKILL.md`** | Init/Govern 模式正文（跨运行时 SoT） |
| **`AGENTS.md`** | 仓库级指挥工作流（跨运行时默认入口） |
| **`norms/`** | NDF 规范种子 |
| **`GOVERNANCE.md`** | 工具主链与沙盒 |
| **`adapters/*`** | 仅挂载，不另立流程 |
| **ndf-design** | 把设计写成条款（相邻，非本包） |

---

## 10. 验收（阶段 A）

1. `norms/` 零具体产品业务条款。  
2. `workflow/AGENTS.md` 完整且可安装到任意绿场根目录。  
3. `skill/SKILL.md` 含四模式；**不**出现「仅限 Cursor」或把 `.cursor/` 当唯一路径。  
4. 至少提供 **generic + 不少于两个** 具名 adapter 说明（建议：openclaw、claude-code、opencode、cursor 中任选 ≥2，外加 generic）。  
5. QUICKSTART：装规范 → 装 AGENTS → 选 adapter（可选）→ 治理基线。  
6. VENDOR.md 钉死工具实现源唯一。

---

## 11. 决策摘要（请确认）

1. 三等产物：规范、`AGENTS.md`、治理 CLI；外加 **运行时无关的 skill 核心**。  
2. **多 Agent**：OpenClaw / Claude Code / OpenCode / Cursor 等经 **adapters** 挂载；禁止 Cursor 强绑定。  
3. 去产品化；默认 **dual-track** + 强制 `AGENTS.md`。  
4. 阶段 A：`packages/ndf-harness/`；既有 Cursor skill 改为薄适配。  

## 12. 落地摘要（2026-08-04）

已写入：

- `packages/ndf-harness/`（norms / workflow/AGENTS.md / governance / skill / adapters×5 / docs）
- `spec/meta/tools/HARNESS.md`
- `.cursor/skills/ndf-harness` 降为薄 adapter
- `spec/meta/README.md`、`tools/README.md` 导航

工具 `.py` 仍仅在 `spec/meta/tools/`（VENDOR 单源）。
