# INTERFACE.md — POC call surface

> topic_id: cluster-gbdt
> status: draft
> created: 2026-08-13
> links: DESIGN.md

**非** `spec/30-interfaces/` stable SoT。POC 调用面，不替代产品 L1 API。

<!-- ndf:gate-slice begin=interface_contract -->
## Entry points

- **Scripts (offline analysis)**:
  - `poc/cluster-gbdt/analyze_cluster_purity.py` — cluster purity vs recall 相关性分析
  - `poc/cluster-gbdt/train_cluster_gbdt.py` — 12-feature LightGBM 训练 + C header 生成
- **Library symbols**: N/A (POC scripts, no runtime library)
- **Generated artifacts**:
  - `poc/cluster-gbdt/cluster_assignments_100k.npy` — k-means assignments
  - `poc/cluster-gbdt/cluster_gbdt_model.h` — generated C header (POC-only, not in include/)

## Types and signatures

```python
# analyze_cluster_purity.py
def load_fvecs(path: str) -> np.ndarray
def load_ivecs(path: str) -> np.ndarray
# CLI: python3 analyze_cluster_purity.py <kmeans.npy> <groundtruth.ivecs> [query_count]

# train_cluster_gbdt.py
def load_fvecs(path: str) -> tuple[np.ndarray, int]
def load_ivecs(path: str, topk: int | None = None) -> tuple[np.ndarray, np.ndarray]
def load_cluster_assignments(kmeans_npy_path: str) -> np.ndarray
# CLI: python3 train_cluster_gbdt.py <kmeans.npy> <query_fvecs> <groundtruth_ivecs>
```

## Config / env / flags

| name | meaning | default |
|------|---------|---------|
| `K` (const) | cluster count for k-means | 1024 |
| `TOP_K` (const) | coarse candidate count for purity computation | 200 |
| `K_DEFAULT` (const) | fine rerank target k | 10 |
| LightGBM `num_leaves` | tree complexity | 16 |
| LightGBM `max_depth` | tree depth | 4 |
| LightGBM `n_estimators` | tree count | 100 |
| LightGBM `learning_rate` | shrinkage | 0.1 |
| LightGBM `seed` | reproducibility | 42 |

## Errors and invariants

- File not found → script exits with usage message (exit code 1)
- cluster_assignments length MUST ≥ max node_id in groundtruth; otherwise IndexError
- Generated `cluster_gbdt_model.h` uses heuristic thresholds (not actual LightGBM tree dump)

## Threading / lifetime

N/A — offline Python scripts, single-threaded execution.

## Draft API-* map

| draft id | this surface | note |
|----------|--------------|------|
| N/A | No draft API clauses | POC is offline analysis only; no runtime interface proposed for Trunk |
<!-- ndf:gate-slice end=interface_contract -->

## R0 结论对接口的影响

R0 负结果 → 无接口需要晋升到 Trunk。`cluster_gbdt_model.h` 保留在 POC 目录作为
负结果证据，MUST NOT 链入 `include/`。
