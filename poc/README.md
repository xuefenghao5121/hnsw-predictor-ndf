# POC — 探索轨（非 SoT）

本目录 **不是** NDF 权威源，也 **不是** 生产实现树。

| 规则 | 条款 |
|------|------|
| 非 SoT | `ndf.yaml` `poc.sot: false`；[[ARCH-008]] |
| 探索纪律 | [[BEH-018]] |
| 晋升闸门 | [[BEH-019]] |
| 负结果 | [[BEH-020]]；样板 [[DEC-061]] |
| 勿占用 | `spec/models/`（L3 参考模型专用） |

## 用法

```text
poc/<topic>/
  NOTES.md          # 假设、配置、正/负结果 → 链到 proposal / DEC
  # 可选：独立源码树、patch、bench 脚本（默认 make 不链入）
```

主题命名建议与 `proposal-*` / DEC 方向一致（例：`poc/io-pipelining/`）。

多轮深入（v1→v2）在**同一** `<topic>/` 追加证据；未晋升前 **禁止** 改写
`spec/20–50` 的 `status=stable` must，也 **禁止** 把实验默认打开合入 `src/`。
