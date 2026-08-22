# NDF Harness Replay 功能设计指导文档

**版本**：v1.0  
**目标读者**：AI 开发团队  
**用途**：指导 Replay 功能的设计、实现与集成


## 一、功能概述

### 1.1 一句话定义

> **Replay 是在隔离分支上重建历史时间轴切片，重新执行当时的指挥动作，并将结果与主线状态进行 Diff 对比的验证机制。**

### 1.2 核心理念

| 概念 | 说明 |
|---|---|
| **时间轴切片** | 每个 Episode 记录了一个时刻的完整状态（Git + 文件 + 指挥动作） |
| **快照恢复** | 在独立分支上重建该时刻的完整上下文 |
| **指挥重放** | 重新执行 Episode 中记录的 Command/Skill |
| **对比验证** | 回放结果与主线后续状态进行 Diff 分析 |


## 二、数据模型

### 2.1 Episode 完整结构

```json
{
  "episode_id": "ep_20260819_143025_001",
  "type": "command_execution | replay | fork",
  
  // ========== 1. 时间轴定位 ==========
  "timeline": {
    "started_at": "2026-08-19T14:30:25Z",
    "completed_at": "2026-08-19T14:30:33Z",
    "duration_ms": 8200
  },
  
  // ========== 2. 触发信息 ==========
  "trigger": {
    "source": "frontend_button | cursor_command | cli",
    "button_id": "btn_proposal_generate",
    "user_input": "订单模块增加重试机制",
    "user": "zhangsan"
  },
  
  // ========== 3. Git 快照（回放基点） ==========
  "git_snapshot": {
    "head_sha": "abc123def456789",
    "branch": "poc/order-retry",
    "is_dirty": false,
    "dirty_files": [],
    "tag": "ndf-v1.0",
    "commit_message": "feat: 添加订单重试机制"
  },
  
  // ========== 4. 文件快照（完整状态） ==========
  "file_snapshot": {
    "before": {
      "spec/20-behavior/behavior.md": "sha256:aaa111...",
      "spec/30-interfaces/api.md": "sha256:bbb222..."
    },
    "after": {
      "spec/open/proposal-20260819-001.md": "sha256:ccc333...",
      "spec/20-behavior/behavior.md": "sha256:ddd444..."
    }
  },
  
  // ========== 5. 指挥面快照（可重放） ==========
  "command": {
    "name": "/ndf-proposal-generate",
    "parameters": {
      "requirement": "订单模块增加重试机制",
      "target_modules": ["20-behavior", "30-interfaces"]
    },
    "skill_chain": ["proposal-generate", "gate-check"]
  },
  
  // ========== 6. 执行过程 ==========
  "execution": {
    "steps": [
      {"step": 1, "action": "读取 spec/20-behavior/behavior.md", "status": "success"},
      {"step": 2, "action": "调用 OpenClaw 分析需求", "status": "success"},
      {"step": 3, "action": "生成提案文件", "status": "success"}
    ],
    "status": "completed",
    "retry_count": 0
  },
  
  // ========== 7. 决策记录 ==========
  "decision": {
    "status": "approved",
    "reviewer": "zhangsan",
    "reviewed_at": "2026-08-19T14:45:00Z",
    "comment": "契约表述清晰，批准",
    "modifications_detected": false
  },
  
  // ========== 8. 主线后续状态（对比基线） ==========
  "mainline_next_state": {
    "head_sha": "xyz789ghi012",
    "commit_message": "feat: 合并订单重试机制PR",
    "changed_files": [
      "src/order/retry.py",
      "spec/20-behavior/behavior.md"
    ],
    "diff_summary": {
      "files_added": 1,
      "files_modified": 1,
      "files_deleted": 0,
      "insertions": 89,
      "deletions": 3
    }
  },
  
  // ========== 9. 回放元数据 ==========
  "replay_meta": {
    "is_replay": false,
    "source_episode_id": null,
    "replay_branch": null
  }
}
```

### 2.2 Episode 状态机

```
Draft → Completed → Approved → Archived
                ↓
            Rejected
                ↓
           Archived
```


## 三、回放执行流程

### 3.1 核心流程图

```
用户选择 Episode
    ↓
读取 Episode 数据
    ↓
创建回放分支 (replay/<episode_id>/<timestamp>)
    ↓
基于 git_snapshot.head_sha 创建分支
    ↓
恢复 before 文件状态
    ↓
执行 command（重放指挥动作）
    ↓
获取主线 HEAD（当前主线状态）
    ↓
对比回放结果 vs 主线状态
    ↓
生成 Diff 报告
    ↓
记录新 Episode（标记为 replay）
    ↓
前端展示对比结果
```

### 3.2 分支命名规范

```
replay/<episode_id>/<timestamp>

示例：
  replay/ep_20260819_143025_001/20260820_150000
  replay/ep_20260819_143025_001/v2
```

### 3.3 回放的三种模式

| 模式 | 操作 | 是否创建分支 | 是否执行命令 |
|---|---|---|---|
| **查看模式** | 显示 Episode 的静态内容 | ❌ | ❌ |
| **验证模式** | 检查当前状态与记录的差异 | ❌ | ❌ |
| **执行模式** | 创建分支 → 恢复状态 → 执行回放 | ✅ | ✅ |

### 3.4 回放执行详细步骤

```bash
#!/bin/bash
# ndf-replay.sh

# 1. 读取 Episode 数据
EPISODE_ID=$1
EPISODE_DATA=$(cat .openclaw/episodes/$EPISODE_ID.json)

# 2. 提取关键信息
HEAD_SHA=$(echo $EPISODE_DATA | jq -r '.git_snapshot.head_sha')
BRANCH_NAME=$(echo $EPISODE_DATA | jq -r '.git_snapshot.branch')
COMMAND=$(echo $EPISODE_DATA | jq -r '.command.name')
PARAMS=$(echo $EPISODE_DATA | jq -r '.command.parameters')

# 3. 创建回放分支
REPLAY_BRANCH="replay/${EPISODE_ID}/$(date +%Y%m%d_%H%M%S)"
git checkout -b $REPLAY_BRANCH $HEAD_SHA

# 4. 恢复文件状态
for file in $(echo $EPISODE_DATA | jq -r '.file_snapshot.before | keys[]'); do
  SHA=$(echo $EPISODE_DATA | jq -r ".file_snapshot.before[\"$file\"]")
  git checkout $SHA -- $file
done

# 5. 执行指挥动作
ndf-execute --command "$COMMAND" --params "$PARAMS"

# 6. 获取主线 HEAD
MAINLINE_HEAD=$(git rev-parse main)

# 7. 生成 Diff 报告
git diff $MAINLINE_HEAD..HEAD > replay.diff

# 8. 记录回放 Episode
ndf-episode-record \
  --type replay \
  --source "$EPISODE_ID" \
  --branch "$REPLAY_BRANCH" \
  --diff "replay.diff"
```


## 四、Diff 对比报告

### 4.1 对比目标

| 对比项 | 说明 |
|---|---|
| **回放分支** | `replay/ep_xxx/20260820_150000`（回放执行后的状态） |
| **主线对比点** | Episode 中记录的 `mainline_next_state.head_sha` |
| **对比命令** | `git diff replay/xxx..mainline_next_state` |

### 4.2 对比结果分类

| 分类 | 说明 | 颜色标识 |
|---|---|---|
| **一致** | 回放结果与主线状态完全相同 | 🟢 绿色 |
| **差异** | 回放结果与主线状态有差异，但差异可解释 | 🟡 黄色 |
| **冲突** | 回放结果与主线状态存在冲突 | 🔴 红色 |
| **新增** | 回放结果中独有的内容 | 🔵 蓝色 |
| **缺失** | 主线状态中存在的回放结果中缺失的内容 | 🟣 紫色 |

### 4.3 报告结构

```json
{
  "replay_report": {
    "episode_id": "ep_20260819_143025_001",
    "replay_branch": "replay/ep_001/20260820_150000",
    "mainline_head": "xyz789ghi012",
    "comparison_summary": {
      "identical_files": ["spec/20-behavior/behavior.md"],
      "diff_files": ["src/order/retry.py"],
      "replay_only_files": [],
      "mainline_only_files": ["src/order/retry_test.py"]
    },
    "detailed_diff": {
      "src/order/retry.py": {
        "status": "modified",
        "insertions": 23,
        "deletions": 2,
        "diff": "..."
      }
    },
    "conclusion": "回放结果与主线状态基本一致，差异为主线的后续优化"
  }
}
```


## 五、前端展示设计

### 5.1 Replay Tab 主视图

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔄 Replay                                                           │
│  ───────────────────────────────────────────────────────────────────  │
│  [📋 全部] [📝 生成提案] [✅ 审核] [💻 实现] [🔧 验证]              │
│                                                                       │
│  Episode #004  2026-08-19 14:30:25  [🔵 已回放 1 次]               │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  📝 生成提案                                                    │ │
│  │  ➜ 基线: abc123 (poc/order-retry)  │  状态: ✅ 已审核         │ │
│  │  产出: proposal-20260819-001.md     │  耗时: 8.2秒             │ │
│  │  ───────────────────────────────────────────────────────────────│ │
│  │  [▶️ 回放]  [📊 查看]  [📋 命令]                              │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  Episode #005  2026-08-20 15:00:00  [🔄 回放结果]                  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  🔄 回放: 提案生成 (来自 #004)                                  │ │
│  │  ➜ 分支: replay/ep_004/20260820_150000                        │ │
│  │  ➜ 对比主线: xyz789                                           │ │
│  │  ───────────────────────────────────────────────────────────────│ │
│  │  对比结果: 🟡 有差异 (1 个文件)                               │ │
│  │  [📊 查看报告]  [🔀 合并]  [🗑️ 丢弃]                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 对比报告视图

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📊 回放对比报告                                                      │
│  基线: abc123 (2026-08-19) → 回放: replay/ep_004 (2026-08-20)      │
│  对比目标: xyz789 (主线下一步)                                       │
│  ───────────────────────────────────────────────────────────────────  │
│                                                                       │
│  📊 对比摘要                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  🟢 一致: 2 个文件                                             │ │
│  │  🟡 差异: 1 个文件                                             │ │
│  │  🔵 回放独有: 0 个文件                                         │ │
│  │  🟣 主线独有: 1 个文件                                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  📄 差异详情                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  🟡 src/order/retry.py                                         │ │
│  │  ───────────────────────────────────────────────────────────────│ │
│  │  @@ -42,7 +42,7 @@                                             │ │
│  │   def retry_order(order_id):                                  │ │
│  │  -    max_retries = 3                                         │ │
│  │  +    max_retries = 5  ← 主线已调整重试次数                   │ │
│  │       retry_delay = 1000                                      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  🎯 结论                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  回放结果与主线状态基本一致。                                   │ │
│  │  差异仅为主线的后续优化，不影响提案的核心内容。                 │ │
│  │  建议：保留回放结果，主线后续优化可保留。                       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  操作:                                                               │
│  [📂 切换到回放分支]  [🔀 合并到主线]  [🗑️ 丢弃]  [📤 导出]       │
└─────────────────────────────────────────────────────────────────────────┘
```


## 六、实现要点

### 6.1 Episode 存储

```
.openclaw/episodes/
└── 2026-08-19/
    └── episode_143025_001.json
```

### 6.2 关键接口

| 接口 | 功能 |
|---|---|
| `ndf-episode-record` | 记录 Episode |
| `ndf-episode-list` | 列出 Episode |
| `ndf-episode-detail` | 查看 Episode 详情 |
| `ndf-replay-execute` | 执行回放 |
| `ndf-replay-report` | 生成对比报告 |
| `ndf-replay-cleanup` | 清理回放分支 |

### 6.3 命令示例

```bash
# 记录 Episode
ndf-episode-record \
  --type command_execution \
  --command "/ndf-proposal-generate" \
  --input "订单模块增加重试机制"

# 执行回放
ndf-replay-execute --episode ep_20260819_143025_001

# 生成对比报告
ndf-replay-report --episode ep_20260819_143025_001

# 清理回放分支
ndf-replay-cleanup --older-than 7d
```


## 七、给 AI 开发者的提示词指令

### 7.1 当用户要求实现 Replay 功能时

```
你正在为 NDF Harness 实现 Replay 功能。

Replay 的核心设计：
1. 每个 Episode 是时间轴上的一个切片，记录了当时的完整状态
2. 回放是在隔离分支上重建该切片，重新执行指挥动作
3. 回放结果与主线下一步状态进行 Diff 对比
4. 对比报告展示差异，供人类决策

请实现以下模块：
- Episode 数据模型（JSON Schema）
- Episode 存储与检索
- 回放执行引擎（创建分支 → 恢复状态 → 执行命令）
- Diff 对比生成器
- 回放报告生成器
- 回放分支清理器

参考数据结构见本文档第二节。
```

### 7.2 当用户要求实现回放 UI 时

```
你正在为 NDF Harness 的 Replay Tab 实现回放界面。

核心交互：
1. 显示 Episode 列表（时间轴视图）
2. 每个 Episode 显示：时间、按钮类型、输入、产出、状态
3. 操作按钮：查看详情、执行回放
4. 回放执行后，显示对比报告
5. 报告包含：一致/差异/独有文件列表、Diff 详情、结论

参考 UI 设计见本文档第五节。
```

### 7.3 当用户要求实现前端 WebSocket 联动时

```
Replay 执行完成后，通过 WebSocket 推送事件：

事件类型：replay_completed
事件数据：{
  episode_id: string,
  replay_branch: string,
  comparison_summary: {...},
  report_url: string
}

前端收到事件后：
1. 自动刷新 Replay Tab
2. 高亮显示新的回放 Episode
3. 如果用户在查看详情页，自动加载对比报告
```


## 八、总结

| 概念 | 说明 |
|---|---|
| **Episode** | 时间轴上的一个切片，记录了完整状态 |
| **快照** | 执行时刻的 Git 状态 + 文件 SHA |
| **指挥面快照** | 执行的 Command + 参数 + 用户输入 |
| **回放** | 在隔离分支上重建切片并重现执行 |
| **对比** | 回放结果与主线下一状态进行 Diff |
| **报告** | 展示差异，供人类决策 |

**核心原则**：Replay 是“时间轴切片 → 快照恢复 → 指挥重放 → 状态对比 → 差异报告”的完整闭环。
