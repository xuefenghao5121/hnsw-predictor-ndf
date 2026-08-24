# Proposal: 性能 SLA ↔ 环境变量图依赖 + trunk-ref {#PROP-SLA-ENV-GRAPH}

> track: bug  
> Status: Implemented on 2026-08-06  
> 日期: 2026-08-06  
> 关联: [[CON-SLA-016]], [[CON-SLA-017]], [[CON-SLA-018]], [[API-012]], [[BEH-024]], [[BEH-027]], [[BEH-028]], [[CON-SLA-014]], [[CON-002]], [[DEC-070]], [[DEC-073]], [[DEC-074]], [[DEC-075]], [[META-001]], [[META-005]], [[DEF-024]]  
> 场景: 规范卫生 / 图依赖回填（无 `src/` 行为变更）

## 1. 动机

Trunk 最优性能 SLA（CON-SLA-016/017/018）的测量 env 只写在正文配置串，未
`depends-on` 到 API；`WILLNEED_BG` 等无独立 `{#API-*}`；`FLAT_VEC_MB` 默认仍写
4MB 而 Trunk 自 `d922f838…` 起为 64MB；条款未绑定 git SHA/tag。

## 2. 决策

### 2.1 新增 / 调整 API（`30-interfaces/env.md`）

| ID | 变更 | `trunk-ref`（feat tip） |
| :--- | :--- | :--- |
| `API-011` | 新增：公共调参 env（FLAT_VEC_MB / CACHE_MB / FINE_* / NUM_THREADS / REFINE_EF / TWO_STAGE） | `d922f8388e3769072ad6f7f621f1a54f45ca26da` |
| `API-012` | 补 `trunk-ref`；仅保留 `L4_WILLNEED` | `2f008f7f60229e68416d20f7e4fdba4071604969` |
| `API-013` | 新增：WILLNEED_BG / VL_POOL_THREADS / PAGE_MERGE_BG（从 API-012 散文迁出） | `162377ee75dbb6a3042572bce47686b92a86aa42`（PAGE_MERGE 正文注明 `edddd232…`） |

默认值列 = 该 `trunk-ref` 上 `src/` 默认；测量常用值另列。

### 2.2 SLA 图边 + trunk-ref（`40-constraints/sla.md`）

| ID | `depends-on` 增补 | `trunk-ref` |
| :--- | :--- | :--- |
| CON-SLA-016 | API-011, API-012 | `d922f8388e3769072ad6f7f621f1a54f45ca26da` |
| CON-SLA-017 | API-011, API-012, API-013 | `162377ee75dbb6a3042572bce47686b92a86aa42` |
| CON-SLA-018 | API-011, API-012, API-013 | `edddd232947c5ec5bde27065add3b1a60621cb80` |

正文保留配置串；补「Trunk: … / [[API-*]]」。`since=` 可保留，不以之为 Trunk 号。

### 2.3 默认值漂移修正

- [[CON-002]]：Default flat_vec_cache **4MB → 64MB**（`block_cache.cpp` + DEC-073）
- `30-interfaces/cli.md`：FLAT_VEC_MB 默认同步 64MB

### 2.4 产品定义 + VER

- [[DEF-024]]：性能配置点 = 一组 env + 绑定的 `trunk-ref`
- VER-040 / VER-041 / VER-042：分别 `verifies` CON-SLA-016/017/018；验收表含 env + cgroup + `trunk-ref`

### 2.5 layout

`ndf.yaml`：env.md 列入 API-011/012/013；language META-005；glossary DEF-024。

## 3. 非目标

- 不改 Trunk `src/` 行为
- 不新建 annotated tag（本轮）
- 不修齐既有 DEC `stable_dep` 全量

## 4. 验收

- `ndf_index.py index`；`graphcheck --product` 本 diff 不新增 cycle
- CON-SLA-016/017/018 的 `depends-on` 含对应 API；API/SLA 含 `trunk-ref=`
- CON-002 / cli 默认与 `d922f838…` 树一致
