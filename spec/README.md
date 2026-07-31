# DiskHNSW NDF Spec Index

对照 [NDF / normative_language](https://github.com/hengliao1972/normative_language)：树按**子系统归属**，语义靠条款 ID 图，历史靠 git。附录 C 的文件名是秒表样例，本仓库按软件域命名。

| 目录 | 角色 | 本仓库文件 |
|------|------|------------|
| `00-charter/` | 范围与术语 | `charter.md`, `glossary.md` |
| `10-architecture/` | 分解 | `modules.md` |
| `20-behavior/` | 行为契约 | `search`, `fine-rerank`, `cache`, `prefetch`, `metrics`, `io-modes` |
| `30-interfaces/` | 对外契约（软件版 pins） | `cli`, `formats`, `cxx-api`, `env` |
| `40-constraints/` | 性能/资源 | `constants`, `sla` |
| `50-verification/` | 验收（类 PICS） | `acceptance.md`, `acceptance-p2.md` |
| `decisions/` | ADR（按主题） | `01-foundation` … `05-odirect-floor`, `adr-ndf-hygiene` |
| `open/` | 开放项 | 仅 Pending / Q / 未关闭 CONFLICT |
| `archive/` | **非 SoT 冷存储** | 见 `ndf.yaml` `archive:` |

检索：`rg '\{#DEC-059\}' spec/` 或 `rg '\{#BEH-014\}' spec/20-behavior/`。
