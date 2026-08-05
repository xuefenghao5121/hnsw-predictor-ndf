# Proposal: NDF 树结构按子系统收敛 {#PROP-NDF-TREE-SPLIT}

> Status: Implemented on 2026-07-31
> 场景: 场景3（规范重构）
> 日期: 2026-07-31
> 关联: 对照 [normative_language](https://github.com/hengliao1972/normative_language) §4.1 / 附录 C

## 动机

NDF 要求 **按子系统组织树**（归属与并行编辑），附录 C 的文件名是秒表投影而非强制名。
本仓库债：`behavior.md` / `api.md` / `limits.md` / `adr.md` 过胖；`archive/` 未在清单声明。

## 落地映射（条款 ID 不变，仅搬家）

### `20-behavior/`
| 新文件 | 条款 |
|--------|------|
| `search.md` | BEH-001…006, BEH-008 |
| `fine-rerank.md` | BEH-007, BEH-011, BEH-014(+L2) |
| `cache.md` | BEH-009(+L2), BEH-010 |
| `prefetch.md` | BEH-012 |
| `metrics.md` | BEH-013 |
| `io-modes.md` | BEH-015(+L2), BEH-016 |

删除：`behavior.md`

### `30-interfaces/`
| 新文件 | 条款 |
|--------|------|
| `cli.md` | API-001…003 |
| `formats.md` | API-004 |
| `cxx-api.md` | API-005…006 |
| `env.md` | API-007 + 冷 I/O env |

删除：`api.md`

### `40-constraints/`
| 新文件 | 条款 |
|--------|------|
| `constants.md` | CON-001…007 |
| `sla.md` | CON-SLA-008…011, CON-HONEST-002 |

删除：`limits.md`

### `decisions/`（主题拆分，非强制一 DEC 一文件）
| 新文件 | 条款 |
|--------|------|
| `01-foundation.md` | DEC-001…016 |
| `02-fine-rerank-experiments.md` | DEC-017…025 |
| `03-scale-and-io.md` | DEC-026…033 |
| `04-p2.md` | DEC-034…039 |
| `05-odirect-floor.md` | DEC-057…060 |
| `adr-ndf-hygiene.md` | 保留 |

删除：`adr.md`, `p2-decisions.md`, `p4-decisions.md`

### `50-verification/`
| 新文件 | 原文件 |
|--------|--------|
| `acceptance.md` | `tests.md` |
| `acceptance-p2.md` | `p2-verification.md` |

### `ndf.yaml`
声明 `archive/` = 冷存储非 SoT；记录布局索引。

## 非本轮
- 不改条款正文语义（除搬家与文件头索引）
- 不强制一 DEC 一 md（主题拆分已足够改善检索）

## 验收

- [x] `20-behavior/` 按子系统拆分，无 `behavior.md`
- [x] `30-interfaces/` / `40-constraints/` 按角色拆分
- [x] `decisions/` 按主题拆分（01…05）
- [x] `50-verification/` 对齐 acceptance 命名
- [x] `ndf.yaml` + `spec/README.md` 声明 archive 非 SoT
- [x] 固定目录无重复 `{#ID}`
