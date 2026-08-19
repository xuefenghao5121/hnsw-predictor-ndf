#!/usr/bin/env python3
"""
R1: Cluster Entropy Analysis using PQ-based coarse search simulation.

Instead of groundtruth (which has perfect ranking), we simulate the ACTUAL
coarse search pipeline: PQ ADC distance → top-200 candidates → cluster features.

This gives us realistic candidate distributions where cluster entropy might
actually distinguish "easy" from "hard" queries.
"""

import numpy as np
import struct, sys, os, time, pickle
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIM = 128
M_PQ = 32  # PQ subquantizers
DSUB = DIM // M_PQ  # 4
KSUB = 256
TOP_K = 200
K_NEAREST = 10

def load_ivecs(path, topk=None):
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

def load_fvecs(path):
    with open(path, 'rb') as f:
        dim = struct.unpack('i', f.read(4))[0]
        f.seek(0, 2)
        N = (f.tell() - 4) // (4 + dim * 4)
        f.seek(4)
        vecs = np.zeros((N, dim), dtype=np.float32)
        for i in range(N):
            struct.unpack('i', f.read(4))
            vecs[i] = np.frombuffer(f.read(dim * 4), dtype=np.float32)
    return vecs, dim

def load_pq_codes(path):
    """Load PQ codes: N x M_PQ uint8"""
    with open(path, 'rb') as f:
        data = f.read()
    # File format: N * M_PQ bytes, no header
    N = len(data) // M_PQ
    codes = np.frombuffer(data, dtype=np.uint8).reshape(N, M_PQ)
    return codes

def load_pq_codebook_from_vecs(base_vecs, m_pq, dsub, ksub):
    """Train PQ codebook from base vectors (same as the C++ code would do)."""
    from sklearn.cluster import MiniBatchKMeans
    N = len(base_vecs)
    codebooks = np.zeros((m_pq, ksub, dsub), dtype=np.float32)
    
    for m in range(m_pq):
        subvec = base_vecs[:, m*dsub:(m+1)*dsub].astype(np.float32)
        km = MiniBatchKMeans(n_clusters=ksub, random_state=42, batch_size=10000, max_iter=20, n_init=3)
        km.fit(subvec)
        codebooks[m] = km.cluster_centers_
        if (m+1) % 8 == 0:
            print(f"    PQ subquantizer {m+1}/{m_pq} trained")
    
    return codebooks

def main():
    cluster_npy = sys.argv[1] if len(sys.argv) > 1 \
        else os.path.join(REPO, 'poc/cluster-gbdt/cluster_assignments_1M.npy')
    base_path = sys.argv[2] if len(sys.argv) > 2 \
        else os.path.join(REPO, 'data/sift_base.fvecs')
    query_path = sys.argv[3] if len(sys.argv) > 3 \
        else os.path.join(REPO, 'data/sift_query_official10k.fvecs')
    gt_path = sys.argv[4] if len(sys.argv) > 4 \
        else os.path.join(REPO, 'data/sift_groundtruth_official.ivecs')
    nq_limit = int(sys.argv[5]) if len(sys.argv) > 5 else 2000  # reduce for speed

    print("=" * 70)
    print("R1: Cluster Entropy — PQ-based Coarse Search Simulation")
    print("=" * 70)

    # Load data
    print(f"\n[1] Loading cluster assignments...")
    cluster_ids = np.load(cluster_npy).astype(np.int32)
    num_clusters = len(np.unique(cluster_ids))
    print(f"    {len(cluster_ids)} nodes, {num_clusters} clusters")

    print(f"\n[2] Loading base vectors for PQ training...")
    base_vecs, _ = load_fvecs(base_path)
    print(f"    {len(base_vecs)} base vectors")

    print(f"\n[3] Loading query vectors...")
    queries, _ = load_fvecs(query_path)
    NQ = min(nq_limit, len(queries))
    queries = queries[:NQ]
    print(f"    {NQ} queries")

    print(f"\n[4] Loading groundtruth...")
    gt_ids = load_ivecs(gt_path, K_NEAREST)
    print(f"    {len(gt_ids)} queries, top-{K_NEAREST}")

    # Train PQ codebook (subsample for speed)
    print(f"\n[5] Training PQ codebook (M={M_PQ}, dsub={DSUB}, ksub={KSUB})...")
    t0 = time.time()
    train_sample = base_vecs[:100000]  # 100K for speed
    codebooks = load_pq_codebook_from_vecs(train_sample, M_PQ, DSUB, KSUB)
    print(f"    Done in {time.time()-t0:.1f}s")

    # Encode all base vectors
    print(f"\n[6] Encoding base vectors to PQ codes...")
    t0 = time.time()
    N = len(base_vecs)
    pq_codes = np.zeros((N, M_PQ), dtype=np.uint8)
    for m in range(M_PQ):
        subvec = base_vecs[:, m*DSUB:(m+1)*DSUB].astype(np.float32)
        # Assign to nearest centroid
        dists = np.linalg.norm(subvec[:, None, :] - codebooks[m][None, :, :], axis=2)
        pq_codes[:, m] = np.argmin(dists, axis=1)
        if (m+1) % 8 == 0:
            print(f"    subquantizer {m+1}/{M_PQ} ({time.time()-t0:.1f}s)")
    print(f"    Done in {time.time()-t0:.1f}s")

    # PQ ADC distance: for each query, compute PQ distance to all nodes
    print(f"\n[7] Computing PQ ADC distances for {NQ} queries...")
    t0 = time.time()
    
    # Precompute lookup tables per query
    # LUT[q, m, c] = ||query_subvec_q - codebook_m_c||^2
    coarse_results = []  # list of (sorted_ids, sorted_dists) per query
    
    for q_idx in range(NQ):
        q = queries[q_idx]
        # Build LUT
        lut = np.zeros((M_PQ, KSUB), dtype=np.float32)
        for m in range(M_PQ):
            q_sub = q[m*DSUB:(m+1)*DSUB]
            diff = codebooks[m] - q_sub[None, :]
            lut[m] = np.sum(diff * diff, axis=1)
        
        # ADC: sum over subquantizers
        dists = np.zeros(N, dtype=np.float32)
        for m in range(M_PQ):
            dists += lut[m, pq_codes[:, m]]
        
        # Top-200 candidates
        top_idx = np.argpartition(dists, TOP_K)[:TOP_K]
        top_idx = top_idx[np.argsort(dists[top_idx])]
        coarse_results.append((top_idx, dists[top_idx]))
        
        if (q_idx + 1) % 500 == 0:
            print(f"    {q_idx+1}/{NQ} ({time.time()-t0:.1f}s)")
    
    print(f"    Done in {time.time()-t0:.1f}s")

    # === Feature computation ===
    print(f"\n[8] Computing features from PQ coarse search results...")
    
    dist_feats = np.zeros((NQ, 11), dtype=np.float32)
    cluster_feats = np.zeros((NQ, 3), dtype=np.float32)
    
    trunc_thresh = [10, 15, 20, 30, 50, 100, 200]
    recall_at = np.zeros((NQ, len(trunc_thresh)), dtype=np.float32)
    
    for q_idx in range(NQ):
        ids, dists = coarse_results[q_idx]
        
        # 11 distance features (same as BEH-034)
        n_coarse = float(TOP_K)
        d0 = dists[0]
        d9 = dists[9]
        dk = dists[K_NEAREST-1]
        dk1 = dists[K_NEAREST]
        gap = dk1 / max(dk, 1e-10)
        mean = float(np.mean(dists))
        stdv = float(np.std(dists))
        cv = stdv / max(mean, 1e-10)
        r01 = d0 / max(mean, 1e-10)
        r09 = d9 / max(mean, 1e-10)
        
        dist_feats[q_idx] = [n_coarse, d0, d9, dk, dk1, gap, mean, stdv, cv, r01, r09]
        
        # Cluster features
        top_clusters = cluster_ids[ids]
        counts = Counter(top_clusters)
        total = len(top_clusters)
        probs = np.array(list(counts.values())) / total
        entropy = -np.sum(probs * np.log(probs + 1e-12))
        max_ent = np.log(min(total, num_clusters))
        cluster_feats[q_idx, 0] = entropy / max_ent if max_ent > 0 else 0
        cluster_feats[q_idx, 1] = 1.0 - len(counts) / total
        cluster_feats[q_idx, 2] = max(counts.values()) / total
        
        # Recall at truncation (using groundtruth)
        gt_set = set(gt_ids[q_idx])
        for j, t in enumerate(trunc_thresh):
            recall_at[q_idx, j] = len(gt_set & set(ids[:t])) / K_NEAREST
    
    # === Analysis ===
    print(f"\n[9] Feature distributions:")
    names_c = ['entropy', 'purity', 'dominant_frac']
    for j, name in enumerate(names_c):
        v = cluster_feats[:, j]
        print(f"    {name:15s}: mean={v.mean():.4f} std={v.std():.4f} [{v.min():.4f}, {v.max():.4f}]")
    
    print(f"\n[10] Correlation of ALL features with recall@10:")
    all_names = ['n_coarse','d0','d9','dk','dk1','gap','mean','std','cv','r01','r09'] + names_c
    all_feats = np.hstack([dist_feats, cluster_feats])
    
    print(f"    {'Truncate':<10}", end="")
    for n in all_names:
        print(f" {n[:7]:>8s}", end="")
    print(f"  {'recall':>8s}")
    
    for j, t in enumerate(trunc_thresh):
        r = recall_at[:, j]
        print(f"    trunc={t:<4d}", end="")
        for k in range(all_feats.shape[1]):
            c = np.corrcoef(all_feats[:, k], r)[0, 1]
            print(f" {c:>8.3f}", end="")
        print(f"  {r.mean():>8.4f}")
    
    # === GBDT: distance-only vs distance+cluster ===
    print(f"\n[11] GBDT A/B: distance features vs distance+cluster")
    try:
        import lightgbm as lgb
    except ImportError:
        print("    LightGBM not available"); return
    
    # Target: min candidates for recall@10 >= 100%
    min_cands = np.full(NQ, 200, dtype=np.int32)
    for q_idx in range(NQ):
        gt_set = set(gt_ids[q_idx])
        ids = coarse_results[q_idx][0]
        for j, t in enumerate(trunc_thresh):
            if len(gt_set & set(ids[:t])) >= K_NEAREST:
                min_cands[q_idx] = t
                break
    
    bc = np.bincount(min_cands, minlength=201)
    print(f"    Target distribution (min candidates for recall@10=100%):")
    for v in range(1, 201):
        if bc[v] > 0:
            print(f"      {v:4d}: {bc[v]:5d} ({bc[v]/NQ*100:.1f}%)")
    
    params = dict(objective='regression', metric='rmse', num_leaves=16,
                  max_depth=4, learning_rate=0.1, n_estimators=100,
                  verbose=-1, seed=42, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=5)
    
    variants = {
        '11-dist-only': dist_feats,
        '14-dist+cluster': np.hstack([dist_feats, cluster_feats]),
    }
    
    for name, feats in variants.items():
        data = lgb.Dataset(feats, label=min_cands.astype(float))
        model = lgb.train(params, data)
        preds = model.predict(feats)
        rmse = np.sqrt(np.mean((preds - min_cands) ** 2))
        imp = model.feature_importance()
        feat_n = all_names[:feats.shape[1]]
        top5 = sorted(zip(feat_n, imp), key=lambda x: -x[1])[:5]
        top5_s = ', '.join(f"{n}:{v:.0f}" for n, v in top5)
        print(f"    {name:<20s}: RMSE={rmse:.3f}  top5: {top5_s}")
    
    # === Verdict ===
    print(f"\n{'='*70}")
    print("R1 VERDICT (PQ-based coarse search simulation)")
    print(f"{'='*70}")
    
    r30 = recall_at[:, trunc_thresh.index(30)]
    ent_corr = np.corrcoef(cluster_feats[:, 0], r30)[0, 1]
    pur_corr = np.corrcoef(cluster_feats[:, 1], r30)[0, 1]
    
    print(f"\n  Entropy ↔ recall@30: {ent_corr:.4f}")
    print(f"  Purity  ↔ recall@30: {pur_corr:.4f}")
    print(f"  Mean recall@30: {r30.mean():.4f}")
    
    if abs(ent_corr) > 0.05:
        print("\n  → Cluster entropy has signal ✅ → proceed to runtime A/B")
    elif abs(ent_corr) > 0.02:
        print("\n  → Weak signal ⚠️ → consider k=4096 or entropy-weighted")
    else:
        print("\n  → No incremental signal ❌ → recommend reject")

if __name__ == '__main__':
    main()
