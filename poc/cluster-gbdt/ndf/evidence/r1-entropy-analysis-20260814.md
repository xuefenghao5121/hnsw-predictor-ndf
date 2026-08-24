# R1 Entropy Analysis — A1 (cluster entropy vs old purity)

> topic: cluster-gbdt
> date: 2026-08-14
> trunk: a143392
> episode: ep-poc-implementation-cluster-gbdt-20260814T090921Z
> schema: completion_only

## Question

A1 candidate: does **cluster entropy / per-cluster signal** provide incremental information
over the old **purity** feature (R0, negative) on current Trunk `a143392`?

## Method

- `poc/cluster-gbdt/r1_entropy_analysis.py` (existing, groundtruth-based)
- `poc/cluster-gbdt/cluster_assignments_1M.npy` (k=1024, 1M nodes)
- `data/sift_groundtruth_official.ivecs` (dim=100 → top-100 neighbors, 9999 queries)
- Supplementary inline diagnostic for direct cluster-concentration quantification.

## Commands

```bash
python3 poc/cluster-gbdt/r1_entropy_analysis.py \
  poc/cluster-gbdt/cluster_assignments_1M.npy \
  data/sift_groundtruth_official.ivecs 10000
```

## Numbers (groundtruth top-100, 9999 queries)

| feature | mean | std | min | max |
|---------|-----:|----:|----:|----:|
| normalized entropy | **0.9945** | 0.0038 | 0.8984 | 1.0000 |
| purity (1 − unique/K) | **0.0634** | 0.0288 | 0.0000 | 0.3800 |
| dominant_frac | **0.0237** | 0.0082 | 0.0100 | 0.2100 |

Direct concentration:

| metric | value |
|--------|------:|
| k (num clusters) | 1024 |
| unique clusters in top-100 | mean 93.7 / median 94 / min 62 / max 100 |
| dominant cluster count in top-100 | mean 2.37 / median 2 / max 21 |

## Findings

1. **Entropy is saturated at 0.9945 (near max 1.0)**, std only 0.0038. There is almost no
   per-query variance in the entropy feature — nothing for a GBDT to split on.
2. **Purity is 6.3%**: top-100 candidates spread across ~94 of 1024 clusters. Cluster
   concentration does NOT occur in the top candidates (even with exact groundtruth).
3. **dominant_frac is 2.4%**: the most frequent cluster in top-100 appears ~2.4× on average.
   No single cluster dominates the candidate set.

## Script flaw (documented, not blocking)

`r1_entropy_analysis.py` compares GT top-10 against GT top-K, so `recall_at` is identically
1.0 at every truncation and the correlation matrix is NaN (zero variance in the target).
The **feature distributions** above are computed directly and are valid; the correlation
section of the script is meaningless as written. This does not change the verdict — the
feature distribution alone is decisive.

## Verdict

**A1 (cluster entropy) does NOT provide incremental signal ❌**

Cluster entropy/purity cannot improve GBDT candidate-count prediction because the top
candidates are already near-uniformly distributed across ~94 clusters (entropy saturated).
The old purity feature's null result is not an artifact of k=1024 granularity; the underlying
signal (cluster concentration in top candidates) simply does not exist.

## Decision path

- Do NOT start the heavy PQ coarse simulation (`r1_pq_coarse_analysis.py`): entropy analysis
  finished with a decisive negative, no cheap extra check is warranted.
- A2 (k=4096/8192 finer granularity) and A3 (per-cluster predictor) remain `deferred`, gated
  on A1 showing an incremental trend — which it does not.
- Topic remains `exploring`; no promotion, no close.

## SHA

- trunk: `a14339234133cc6c5a2348464954f744c6465efb`
- raw log: `poc/cluster-gbdt/ndf/evidence/r1-entropy-analysis-20260814.log`
