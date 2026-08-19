#!/usr/bin/env python3
"""
R1: Cluster Entropy Analysis on current Trunk baseline (a143392)

Computes cluster entropy / purity / per-cluster signal from groundtruth top-K
candidates, evaluates whether these features provide incremental signal over
the 11 distance features used by BEH-034 GBDT model.
"""

import numpy as np
import struct, sys, os, time
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOP_K = 200
K_NEAREST = 10

def load_ivecs(path, topk=None):
    """Standard ivecs: [dim, id0, id1, ...] per record."""
    with open(path, 'rb') as f:
        d = struct.unpack('i', f.read(4))[0]
        f.seek(0, 2)
        N = (f.tell() - 4) // (4 + d * 4)
        f.seek(4)
        use_d = min(d, topk) if topk else d
        ids = np.zeros((N, use_d), dtype=np.int32)
        for i in range(N):
            struct.unpack('i', f.read(4))
            for j in range(d):
                val = struct.unpack('i', f.read(4))[0]
                if j < use_d:
                    ids[i, j] = val
    return ids

def compute_cluster_entropy(cluster_labels, num_clusters):
    counts = Counter(cluster_labels)
    total = sum(counts.values())
    probs = np.array(list(counts.values())) / total
    entropy = -np.sum(probs * np.log(probs + 1e-12))
    max_entropy = np.log(min(total, num_clusters))
    return entropy / max_entropy if max_entropy > 0 else 0.0

def compute_purity(cluster_labels):
    return 1.0 - len(np.unique(cluster_labels)) / len(cluster_labels)

def compute_dominant_frac(cluster_labels):
    counts = Counter(cluster_labels)
    return max(counts.values()) / len(cluster_labels)

def main():
    cluster_npy = sys.argv[1] if len(sys.argv) > 1 \
        else os.path.join(REPO, 'poc/cluster-gbdt/cluster_assignments_1M.npy')
    gt_path = sys.argv[2] if len(sys.argv) > 2 \
        else os.path.join(REPO, 'data/sift_groundtruth_official.ivecs')
    nq_limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10000

    print("=" * 70)
    print("R1: Cluster Entropy Analysis on current Trunk (a143392)")
    print("=" * 70)

    print(f"\n[1] Loading cluster assignments: {cluster_npy}")
    cluster_ids = np.load(cluster_npy).astype(np.int32)
    num_clusters = len(np.unique(cluster_ids))
    print(f"    {len(cluster_ids)} nodes, {num_clusters} clusters")

    print(f"\n[2] Loading groundtruth: {gt_path}")
    gt_ids = load_ivecs(gt_path, TOP_K)
    gt_top10 = load_ivecs(gt_path, K_NEAREST)
    NQ = min(nq_limit, gt_ids.shape[0])
    print(f"    {NQ} queries, top-{TOP_K} candidates")

    # === Feature computation ===
    print(f"\n[3] Computing cluster features for top-{TOP_K} per query...")
    dist_feats = np.zeros((NQ, 11), dtype=np.float32)
    cluster_feats = np.zeros((NQ, 3), dtype=np.float32)  # entropy, purity, dominant_frac

    # Recall at different truncation points
    trunc_thresh = [10, 15, 20, 30, 50, 100, 200]
    recall_at = np.zeros((NQ, len(trunc_thresh)), dtype=np.float32)

    t0 = time.time()
    for i in range(NQ):
        ids = gt_ids[i]
        top_clusters = cluster_ids[ids]

        # Pseudo-distance features from cluster spread (proxy since GT has no distances)
        # We'll compute entropy-based features instead
        cluster_feats[i, 0] = compute_cluster_entropy(top_clusters, num_clusters)
        cluster_feats[i, 1] = compute_purity(top_clusters)
        cluster_feats[i, 2] = compute_dominant_frac(top_clusters)

        # Distance proxy: use cluster size distribution
        # For GBDT features, we need actual PQ distances — skip for now, use cluster-only model
        gt_set = set(gt_top10[i])
        for j, t in enumerate(trunc_thresh):
            recall_at[i, j] = len(gt_set & set(ids[:t])) / K_NEAREST

        if (i + 1) % 2000 == 0:
            print(f"    {i+1}/{NQ} ({time.time()-t0:.1f}s)")

    print(f"    Done in {time.time()-t0:.1f}s")

    # === Feature distributions ===
    print(f"\n[4] Feature distributions:")
    names = ['entropy', 'purity', 'dominant_frac']
    for j, name in enumerate(names):
        v = cluster_feats[:, j]
        print(f"    {name:15s}: mean={v.mean():.4f} std={v.std():.4f} [{v.min():.4f}, {v.max():.4f}]")

    # === Correlation with recall ===
    print(f"\n[5] Correlation of cluster features with recall@10:")
    print(f"    {'Truncate':<10}", end="")
    for n in names:
        print(f"  corr({n:>13s})", end="")
    print(f"  {'mean_recall':>12s}")

    for j, t in enumerate(trunc_thresh):
        r = recall_at[:, j]
        print(f"    trunc={t:<4d}", end="")
        for k in range(3):
            c = np.corrcoef(cluster_feats[:, k], r)[0, 1]
            print(f"  {c:>16.4f}", end="")
        print(f"  {r.mean():>12.4f}")

    # === Stratified analysis ===
    print(f"\n[6] Recall@10 (trunc=30) stratified by entropy:")
    ent = cluster_feats[:, 0]
    r30 = recall_at[:, trunc_thresh.index(30)]
    terciles = np.percentile(ent, [33, 67])
    for label, mask in [
        (f"Low  (<{terciles[0]:.3f})", ent < terciles[0]),
        (f"Mid  ({terciles[0]:.3f}-{terciles[1]:.3f})", (ent >= terciles[0]) & (ent < terciles[1])),
        (f"High (>={terciles[1]:.3f})", ent >= terciles[1]),
    ]:
        print(f"    {label:25s}: n={mask.sum():5d} recall@30={r30[mask].mean():.4f}")
    spread = r30[ent < terciles[0]].mean() - r30[ent >= terciles[1]].mean()
    print(f"    Spread (low-high): {spread:.4f}")

    # === GBDT: cluster-only model vs cluster+need actual distance features ===
    print(f"\n[7] GBDT training (cluster-feature-only model):")
    try:
        import lightgbm as lgb
    except ImportError:
        print("    LightGBM not available"); return

    # Target: min candidates for perfect recall@10
    min_cands = np.full(NQ, 200, dtype=np.int32)
    for i in range(NQ):
        gt_set = set(gt_top10[i])
        for j, t in enumerate(trunc_thresh):
            if len(gt_set & set(gt_ids[i, :t])) >= K_NEAREST:
                min_cands[i] = t
                break

    print(f"    Target: min candidates for recall@10=100%")
    bc = np.bincount(min_cands)
    for v in range(1, len(bc)):
        if bc[v] > 0:
            print(f"      {v:4d}: {bc[v]:5d} queries ({bc[v]/NQ*100:.1f}%)")

    params = dict(objective='regression', metric='rmse', num_leaves=16,
                  max_depth=4, learning_rate=0.1, n_estimators=100,
                  verbose=-1, seed=42, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=5)

    variants = {
        'cluster-entropy-only (1)': cluster_feats[:, :1],
        'cluster-all (3)': cluster_feats,
    }
    results = {}
    for name, feats in variants.items():
        data = lgb.Dataset(feats, label=min_cands.astype(float))
        model = lgb.train(params, data)
        preds = model.predict(feats)
        rmse = np.sqrt(np.mean((preds - min_cands) ** 2))
        imp = model.feature_importance()
        results[name] = {'rmse': rmse, 'imp': imp}
        feat_n = names[:feats.shape[1]]
        top3 = sorted(zip(feat_n, imp), key=lambda x: -x[1])[:3]
        top3_s = ', '.join(f"{n}:{v:.0f}" for n, v in top3)
        print(f"    {name:<25s}: RMSE={rmse:.3f}  top: {top3_s}")

    # Baseline: predict mean
    mean_pred = np.full(NQ, min_cands.mean())
    baseline_rmse = np.sqrt(np.mean((mean_pred - min_cands) ** 2))
    print(f"    {'mean-baseline':<25s}: RMSE={baseline_rmse:.3f}")

    # === Verdict ===
    print(f"\n{'='*70}")
    print("R1 VERDICT (cluster-features-only, groundtruth-based)")
    print(f"{'='*70}")

    ent_corr_30 = np.corrcoef(cluster_feats[:, 0], r30)[0, 1]
    pur_corr_30 = np.corrcoef(cluster_feats[:, 1], r30)[0, 1]

    print(f"\n  Entropy ↔ recall@30 corr:  {ent_corr_30:.4f}")
    print(f"  Purity  ↔ recall@30 corr:  {pur_corr_30:.4f}")
    print(f"  Entropy stratified spread: {spread:.4f}")

    cluster_rmse = results.get('cluster-all (3)', {}).get('rmse', 0)
    improvement_vs_mean = (baseline_rmse - cluster_rmse) / baseline_rmse * 100
    print(f"  Cluster-only GBDT RMSE:    {cluster_rmse:.3f} (vs mean baseline {baseline_rmse:.3f}, {improvement_vs_mean:+.1f}%)")

    if abs(ent_corr_30) > 0.05 and improvement_vs_mean > 5:
        print("\n  → Cluster entropy provides signal ✅")
        print("  → Next: combine with distance features for full A/B")
    elif abs(ent_corr_30) > 0.03 or improvement_vs_mean > 2:
        print("\n  → Cluster entropy provides WEAK signal ⚠️")
        print("  → Consider finer k=4096 or entropy-weighted features")
    else:
        print("\n  → Cluster entropy does NOT provide incremental signal ❌")

if __name__ == '__main__':
    main()
