# INTERFACE.md — hierarchical-vamana

> topic_id: hierarchical-vamana
> status: draft
> links: draft BEH-HV-001 / DESIGN.md

非 `spec/30-interfaces/` SoT。

<!-- ndf:gate-slice begin=interface_contract -->
## Entry points

- Build CLI / script: `poc/hierarchical-vamana/build/`（实现后钉死具体二进制或脚本名）
- Measure: `scripts/run_sustained.sh`（经 POC 索引路径 env / flag）
- Library symbols（目标，实现期可迭代）:
  - `assign_levels(...)`
  - `vamana_build_layer(...)` / `robust_prune(...)`
  - `export_adjacency_for_diskhnsw(...)`

## Types and signatures

```text
// conceptual
struct BuildParams {
  int M;              // max out-degree target (per layer may differ)
  int beam_width;     // GreedySearch / construction beam
  float alpha;        // RobustPrune
  float alpha2;       // optional second pass (>1)
  int max_level;      // or geometric level assign
};

void assign_levels(span<node_id>, BuildParams, span<int> out_level);
void vamana_build_layer(int layer, vectors, BuildParams, Graph& g);
void export_adjacency_for_diskhnsw(const Graph&, path out_prefix);
```

## Config / env / flags

| name | meaning | default |
|------|---------|---------|
| HV_M | HNSW 层分配基准 M（mL=1/ln M） | 16 |
| HV_R0 | L0 层 RobustPrune 候选出度上限 R | 32 |
| HV_RUP | 上层（L≥1）RobustPrune 候选出度上限 R | 16 |
| HV_BEAM | 建图 beam（GreedySearch/construction） | 32 |
| HV_ALPHA | RobustPrune α | 1.2 |
| HV_ALPHA2 | 二遍 α（0=关闭） | 0 |
| HV_ROUNDS | 建图迭代轮数 | 3 |
| HV_SEED | 随机种子 | 42 |
| HV_INDEX_DIR | POC 索引输出目录 | poc/hierarchical-vamana/output/ |

## Errors and invariants

- 层分配与边端点层关系必须一致（无指向更高层非法边，按选定语义）
- 导出后 L0 邻接可被现搜索路径加载，或文档化不兼容点
- 测量 MUST 声明是否使用 POC 索引

## Threading / lifetime

建图可多线程；与 Trunk 相同：索引写完后再开 sustained 查询线程池。

## Draft API-* map

| draft id | this surface | note |
|----------|--------------|------|
| N/A | build/export CLI | 晋升时再开 API-* |
<!-- ndf:gate-slice end=interface_contract -->
