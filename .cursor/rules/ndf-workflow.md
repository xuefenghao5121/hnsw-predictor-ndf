
```markdown
---
description: NDF规范开发流程 - AI编码时必须遵循的工作流
globs: src/**,tests/**
alwaysApply: true
---

# NDF 规范开发流程

## 1. 编码前检查清单

在编写任何新代码之前，你**必须**完成以下检查：

- [ ] 确认目标功能在 `spec/20-behavior/` 中有对应的 L1 契约（`{#SYS-XXX}` 条款）。
- [ ] 确认 `spec/30-interfaces/` 中已定义该功能的接口（如 API 端点）。
- [ ] 确认 `spec/40-constraints/` 中已定义该功能的 SLA 约束。
- [ ] 如果上述任何一项缺失，**停止编码**，并提示用户：

> 该功能尚未完成 NDF 规范定义。缺失项：
> - [ ] `20-behavior/behavior.md` 中缺少 `{#SYS-XXX}` 条款
>
> 请先通过 OpenClaw 提案流程补充规范，我再进行编码。

## 2. 编码中规范

### 2.1 代码结构与架构
- 严格遵循 `spec/10-architecture/modules.md` 中定义的模块划分。
- 新增的模块或依赖，必须与 `spec/10-architecture/modules.md` 中定义的依赖关系一致。

### 2.2 接口实现
- 严格遵循 `spec/30-interfaces/api.md` 中定义的接口格式（路径、方法、请求/响应结构）。
- 字段级定义（如 `user_id: string`）必须在代码中体现为对应的类型或结构体。

### 2.3 性能与约束
- 确保代码实现不违反 `spec/40-constraints/constraints.md` 中定义的SLA阈值。
- 如果有性能敏感的操作，必须在注释中说明其时间复杂度，并引用对应的SLA条款。

### 2.4 测试要求
- 根据 `spec/50-verification/verification.md` 中的 L3 验收准则，为每个新增功能编写对应的单元测试或集成测试。
- 测试用例的 Given-When-Then 结构，应与 L3 准则保持一致。

## 3. 编码后自查清单

代码完成后，提交前**必须**自查：

- [ ] 代码中所有关键函数都有注释引用 NDF 条款ID（如 `// implements {#SYS-XXX}`）。
- [ ] 所有新增文件或模块在 `spec/10-architecture/` 中有对应的描述。
- [ ] 所有新增接口在 `spec/30-interfaces/` 中有对应的定义。
- [ ] 所有新增测试覆盖了 `spec/50-verification/` 中对应的 L3 准则。

## 4. 遇到规范与代码冲突时的处理

当发现代码与 `spec/` 中的 NDF 条款不一致时：

1. **指出冲突**：明确描述代码中的哪些行为与规范不符。
2. **优先建议修代码**：如果可能，建议修改代码以匹配规范。
3. **如果代码必须修改规范**：
   - 在 `spec/open/` 下创建 `feedback-YYYYMMDD-xxx.md` 文件，描述冲突、建议的规范修改方案及理由。
   - 等待用户确认后，再继续操作。

## 5. 例外情况：紧急修复

如果是紧急 Bug 修复，且该 Bug 对应的 NDF 条款需要修改，允许你先修复代码，然后**必须**：
1. 在代码注释中标注 `// FIX: temporary workaround, NDF clause {#SYS-XXX} needs update`
2. 创建 `spec/open/feedback-YYYYMMDD-xxx.md` 描述需要修改的条款
3. 通知用户跟进规范更新
