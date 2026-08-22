NDF Harness 工具化架构设计方案

版本：v1.0
目标：将 NDF Harness 前端按钮映射为原子化 Command/Skill，并建立 WebSocket 自动更新机制，实现"点击按钮 → 执行工具 → 自动刷新"的完整闭环。

一、整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         用户交互层                                      │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │               NDF Harness 可视化面板 (静态HTML)                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │   │
│  │  │生成提案   │ │审批Gate  │ │委派实现  │ │查看历史  │       │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │   │
│  └───────┼────────────┼────────────┼────────────┼──────────────┘   │
│          │            │            │            │                     │
│          ▼            ▼            ▼            ▼                     │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    工具触发层                                   │   │
│  │  每个按钮 → 触发一个 Command → 执行一个 Skill 或原子操作       │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                   执行层 (Cursor / OpenClaw / Claude Code)     │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    状态更新层 (WebSocket)                       │   │
│  │  执行完成 → 推送事件 → 前端自动刷新                             │   │
│  └────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

二、按钮 → Command/Skill 映射设计

2.1 Command 与 Skill 的定位

概念 定位 粒度 触发方式
Command 原子操作，单个确定动作 细粒度 /command-name
Skill 工作流编排器，组合多个 Command 粗粒度 自动发现或 /skill-name

设计原则：前端按钮直接触发 Command（原子操作），多个 Command 组合成 Skill（完整工作流）。

2.2 按钮→Command 映射表

前端按钮 触发 Command 功能描述
"生成提案" /ndf-proposal-generate 根据需求生成 NDF 提案文档
"审批 Gate" /ndf-gate-check 检查并审批门禁状态
"晋升 POC" /ndf-gate-promote 将 Draft 晋升为正式规范
"委派实现" /ndf-code-implement 委派 Claude Code 实现代码
"运行验证" /ndf-test-run 触发编译和性能验证
"查看历史" /ndf-episode-list 显示最近的执行历史
"查看详情" /ndf-episode-detail 显示特定 Episode 的完整信息
"漂移检测" /ndf-diagnose-drift 检测代码与规范的漂移
"健康检查" /ndf-diagnose-health 检查 Harness 整体健康度

2.3 Command 文件结构

每个 Command 是一个 .cursor/commands/ 下的 Markdown 文件：

```markdown
# /ndf-proposal-generate

## 描述
根据用户需求生成符合 NDF 规范的提案文档。

## 参数
- `requirement`: 需求描述（必填）
- `target_modules`: 涉及的 NDF 模块（可选）

## 执行步骤
1. 读取 `spec/` 下相关模块的现有条款
2. 调用 OpenClaw 分析需求与现有规范的差异
3. 生成 `spec/open/proposal-*.md` 文件
4. 输出提案路径和 Gate 状态
5. 触发 WebSocket 事件：`proposal_generated`

## 输出格式
```json
{
  "proposal_path": "spec/open/proposal-20260819-xxx.md",
  "gate_status": "pending_approval",
  "event": "proposal_generated"
}
```

审核等待

生成后等待人类回复以下关键词：

· 同意 / approved / ok / 可以 → 进入 Gate 审批
· 拒绝 / rejected / 不行 / 驳回 → 终止流程，记录原因
· 修改后同意 / 已修改 → 检测文件变化，用新版本继续

```

### 2.4 Skill 文件结构（工作流编排器）

```markdown
# NDF Harness 完整工作流

## 描述
NDF 规范驱动开发的完整工作流编排器，组合多个 Command。

## 触发条件
- 用户说 "按 NDF 流程开发 [功能]"
- 用户说 "走一遍 NDF Harness"
- 用户输入 `/ndf-workflow`

## 工作流步骤
1. 调用 `/ndf-proposal-generate` → 生成提案
2. 等待人类审核（同意/拒绝/修改）
3. 调用 `/ndf-gate-check` → 检查门禁
4. 调用 `/ndf-code-implement` → 委派实现
5. 调用 `/ndf-test-run` → 运行验证
6. 调用 `/ndf-episode-record` → 记录执行历史
```

三、前端按钮触发机制

3.1 触发方式

前端按钮通过复制命令到剪贴板，让用户粘贴到 Cursor 中执行：

```html
<!-- 前端按钮 -->
<button onclick="triggerCommand('ndf-proposal-generate', {requirement: '...'})">
  📝 生成提案
</button>
```

```javascript
// 触发函数
function triggerCommand(commandName, params) {
  // 构建命令字符串
  let cmd = `/${commandName}`;
  if (params.requirement) {
    cmd += ` "${params.requirement}"`;
  }
  if (params.target_modules) {
    cmd += ` --modules ${params.target_modules.join(',')}`;
  }
  
  // 复制到剪贴板
  navigator.clipboard.writeText(cmd);
  
  // 显示提示
  showToast('✅ 命令已复制到剪贴板，请粘贴到 Cursor 中执行');
}
```

3.2 执行流程

```
用户点击按钮 → 命令复制到剪贴板 → 粘贴到 Cursor → 
Cursor 识别 Command → 执行 → 完成 → WebSocket 推送 → 前端刷新
```

四、WebSocket 自动更新机制

4.1 架构设计

```
┌─────────────┐    WebSocket     ┌─────────────┐    HTTP API      ┌─────────────┐
│  前端面板   │ ◄─────────────── │ WebSocket   │ ◄────────────── │  后端服务   │
│  (静态HTML) │                  │   Server    │                 │  (状态源)   │
└─────────────┘                  └─────────────┘                 └─────────────┘
       │                                │                                │
       │ 1. 连接                        │ 2. 注册事件                     │
       │                                │ 3. Command执行完成 → 触发事件   │
       │ 4. 接收事件 → 自动刷新         │                                │
```

4.2 WebSocket Server 实现

```javascript
// websocket-server.js
const WebSocket = require('ws');
const http = require('http');

// WebSocket 服务器
const wss = new WebSocket.Server({ port: 8080 });
const clients = new Set();

// 事件类型
const EVENTS = {
  PROPOSAL_GENERATED: 'proposal_generated',
  GATE_APPROVED: 'gate_approved',
  CODE_IMPLEMENTED: 'code_implemented',
  TEST_RUN_COMPLETED: 'test_run_completed',
  EPISODE_RECORDED: 'episode_recorded',
  DRIFT_DETECTED: 'drift_detected',
  HEALTH_CHECKED: 'health_checked',
  NDF_UPDATED: 'ndf_updated'  // 通用更新事件
};

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log(`Client connected. Total: ${clients.size}`);
  
  ws.on('close', () => {
    clients.delete(ws);
    console.log(`Client disconnected. Total: ${clients.size}`);
  });
});

// 触发更新事件
function triggerUpdate(eventType, data) {
  const message = JSON.stringify({
    event: eventType,
    data: data,
    timestamp: new Date().toISOString()
  });
  
  clients.forEach(ws => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(message);
    }
  });
}

// HTTP 触发接口（供 Command 完成后调用）
http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/trigger') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      const payload = JSON.parse(body);
      triggerUpdate(payload.event, payload.data);
      res.end(JSON.stringify({ status: 'ok' }));
    });
  }
}).listen(8081);

module.exports = { EVENTS, triggerUpdate };
```

4.3 前端 WebSocket 集成

```html
<!-- 前端页面：连接 WebSocket 并自动刷新 -->
<script>
  const WS_URL = 'ws://localhost:8080';
  let ws = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_ATTEMPTS = 5;

  function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
      console.log('WebSocket 已连接');
      reconnectAttempts = 0;
    };
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('收到事件:', message);
      
      // 根据事件类型决定刷新策略
      handleEvent(message);
    };
    
    ws.onclose = () => {
      console.log('WebSocket 已断开');
      attemptReconnect();
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error);
    };
  }

  function handleEvent(message) {
    const { event, data, timestamp } = message;
    
    switch(event) {
      case 'proposal_generated':
        // 刷新提案列表区域
        refreshSection('proposals');
        break;
        
      case 'ndf_updated':
        // 完全刷新面板
        location.reload();
        break;
        
      case 'gate_approved':
        // 刷新门禁状态
        refreshSection('gates');
        break;
        
      case 'code_implemented':
        // 刷新代码状态区域
        refreshSection('implementation');
        break;
        
      case 'test_run_completed':
        // 刷新验证结果区域
        refreshSection('validation');
        break;
        
      default:
        // 未知事件：完全刷新
        location.reload();
    }
  }

  function refreshSection(sectionId) {
    // 通过 AJAX 重新加载特定区域
    fetch(`/api/sections/${sectionId}`)
      .then(r => r.text())
      .then(html => {
        document.getElementById(`section-${sectionId}`).innerHTML = html;
      });
  }

  function attemptReconnect() {
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      setTimeout(() => {
        console.log(`尝试重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
        connectWebSocket();
      }, 1000 * reconnectAttempts);
    }
  }

  // 启动连接
  connectWebSocket();
</script>
```

五、Command 执行完成后触发 WebSocket

5.1 Command 完成回调

每个 Command 在执行完成后，应通过 HTTP 调用触发 WebSocket 推送：

```bash
#!/bin/bash
# ndf-proposal-generate.sh

# 1. 执行提案生成
openclaw proposal generate --requirement "$1" --output "$OUTPUT_PATH"

# 2. 触发 WebSocket 推送
curl -X POST http://localhost:8081/trigger \
  -H "Content-Type: application/json" \
  -d "{\"event\": \"proposal_generated\", \"data\": {\"proposal_path\": \"$OUTPUT_PATH\"}}"

echo "✅ 提案已生成，面板将自动刷新"
```

5.2 Python 版本

```python
# ndf_tools.py
import subprocess
import requests
import json

def execute_command(command_name, params):
    # 1. 执行命令
    result = subprocess.run(
        ["openclaw", command_name, *params],
        capture_output=True,
        text=True
    )
    
    # 2. 解析结果
    event_type = map_event_type(command_name)
    
    # 3. 触发 WebSocket
    requests.post(
        "http://localhost:8081/trigger",
        json={"event": event_type, "data": {"result": result.stdout}}
    )
    
    return result

def map_event_type(command_name):
    mapping = {
        "proposal-generate": "proposal_generated",
        "gate-check": "gate_approved",
        "code-implement": "code_implemented",
        "test-run": "test_run_completed",
    }
    return mapping.get(command_name, "ndf_updated")
```

六、完整的流程示例

6.1 生成提案流程

```
1. 用户在面板点击 "生成提案" 按钮
   → 命令复制到剪贴板：`/ndf-proposal-generate "订单模块增加重试机制"`

2. 用户粘贴到 Cursor 对话中

3. Cursor 执行 Command：
   a. 读取 spec/ 相关模块
   b. 调用 OpenClaw 分析需求
   c. 生成 spec/open/proposal-20260819-xxx.md
   d. 输出提案摘要
   e. 等待人类审核

4. 人类回复 "同意" 或 "拒绝" 或 "修改后同意"

5. 审核通过后：
   a. 更新提案状态
   b. 触发 WebSocket 推送：{event: "proposal_generated", data: {...}}

6. 前端收到 WebSocket 事件：
   a. 自动刷新相关区域
   b. 显示最新状态
```

6.2 时序图

```
前端面板          WebSocket Server      Command/Skill        人类
   │                    │                    │                  │
   │ 点击"生成提案"     │                    │                  │
   │ ──────────────────►│                    │                  │
   │                    │ 触发 Command       │                  │
   │                    │ ──────────────────►│                  │
   │                    │                    │ 执行 Command     │
   │                    │                    │ ────────────────►│
   │                    │                    │                  │ 审核
   │                    │                    │ ◄───────────────│
   │                    │                    │ 完成，触发事件   │
   │                    │ ◄─────────────────│                  │
   │ 接收事件，刷新     │                    │                  │
   │ ◄─────────────────│                    │                  │
```

七、事件类型与刷新策略

事件类型 触发时机 前端刷新策略
proposal_generated 提案生成完成 刷新提案列表区域
proposal_approved 提案审核通过 刷新 Gate 状态区域
proposal_rejected 提案被拒绝 刷新提案列表，显示拒绝状态
proposal_modified_approved 修改后通过 刷新提案列表+Gate状态
gate_approved 门禁通过 刷新实现状态区域
code_implemented 代码实现完成 刷新验证状态区域
test_run_completed 验证完成 刷新验证结果区域
episode_recorded 历史记录完成 刷新历史列表
ndf_updated 通用更新 完全刷新面板

八、总结

本设计方案将 NDF Harness 的每个功能按钮抽象为原子化的 Command，通过 WebSocket 实现执行完成后的自动刷新，形成"点击按钮 → 复制命令 → 执行 → 自动更新"的完整闭环。

核心优势：

1. 工具原子化：每个按钮对应一个确定的 Command，逻辑清晰可测试
2. 实时反馈：WebSocket 推送让前端始终展示最新状态
3. 零额外操作：人类只需在对话中回复关键词即可完成审核闭环
4. 轻量部署：仅需一个 WebSocket Server 文件 + 数个 Command 文件
5. 可扩展：新增功能只需增加对应的 Command 和事件类型
