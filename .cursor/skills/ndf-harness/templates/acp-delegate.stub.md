# ACP 委派模板 stub（OpenClaw → Claude Code）

> Status: Draft  
> 用法：OpenClaw 在「已审核」后粘贴到 ACP；按 track 选一块。

## track=poc

```text
【track=poc】主题: ⟨TBD: topic⟩
只允许修改: poc/⟨topic⟩/
禁止: src/、stable must SLA、spec/models/ 生产补丁
任务: ⟨TBD⟩
证据写到: poc/⟨topic⟩/NOTES.md
完成后输出摘要（文件列表 + 如何复现）。
```

## track=promote

```text
【track=promote】条款: ⟨TBD: IDs⟩
阅读已落地 stable L1，细化 L2/L3 与 VER，字段写入 30-interfaces（若需要）。
干净合入 src/（最小切片），注释引用条款 ID。
然后执行编译验证；性能验证对照 stable CON-SLA。
禁止改 00-charter / 10-architecture / L0-L1。
完成后输出摘要。
```

## track=process

```text
【track=process】无 src 任务。若收到此委派，回复无需编码并退出。
```
