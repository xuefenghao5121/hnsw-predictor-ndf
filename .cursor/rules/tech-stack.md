---
description: 技术栈与编码规范 - AI生成代码时必须遵循的技术约束
globs: src/**
alwaysApply: true
---

# 技术栈与编码规范

## 1. 技术栈

本项目的技术栈定义在 `spec/10-architecture/modules.md` 中。

**当前技术栈**（以 `spec/10-architecture/modules.md` 为准）：

| 类别 | 技术选型 | 版本约束 |
| :--- | :--- | :--- |
| 语言 | Python | 3.11+ |
| Web框架 | FastAPI | 最新稳定版 |
| 数据库 | PostgreSQL | 15+ |
| 缓存 | Redis | 7+ |
| 消息队列 | RabbitMQ | 最新稳定版 |
| 测试 | pytest | 最新稳定版 |
| 代码格式化 | black | 最新稳定版 |
| Lint | ruff | 最新稳定版 |

## 2. 编码风格

### 2.1 Python（如适用）
- 遵循 PEP 8 规范。
- 使用 `black` 进行自动格式化。
- 使用 `ruff` 进行 Lint 检查。
- 类型注解：所有公共函数**必须**包含类型注解（`def func(param: str) -> int:`）。
- 文档字符串：所有公共模块、类、函数**必须**有 docstring（Google 风格）。

### 2.2 命名规范
| 类别 | 规范 | 示例 |
| :--- | :--- | :--- |
| 类 | PascalCase | `OrderService`, `RetryPolicy` |
| 函数/方法 | snake_case | `create_order`, `retry_failed` |
| 变量 | snake_case | `order_id`, `max_retries` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| 私有属性 | 前缀 `_` | `_internal_state` |

### 2.3 代码组织
- 按 `spec/10-architecture/modules.md` 中定义的模块边界组织代码。
- 每个模块应有独立的子目录。
- 模块间通信**必须**通过明确的接口（`spec/30-interfaces/` 中定义），禁止跨模块直接调用内部实现。

## 3. 错误处理

- 所有可能失败的外部调用（数据库、网络、文件IO）**必须**有异常处理。
- 异常类型应与 `spec/20-behavior/` 中的 L1 契约一致。
- 错误信息应清晰、可操作，不泄露敏感信息。

## 4. 日志与可观测性

- 关键操作（订单创建、支付、状态变更）**必须**记录结构化日志。
- 日志级别：
  - `ERROR`：系统错误，需要人工介入。
  - `WARN`：异常但可恢复的情况。
  - `INFO`：关键业务操作。
  - `DEBUG`：调试信息，仅开发环境开启。
