#!/usr/bin/env python3
# analyze_cluster_purity.py — R0: correlation between cluster purity and recall
# POC: cluster-gbdt
# Hypothesis: high cluster purity of top-K neighbors → fewer fine rerank candidates needed

import numpy as np, struct, sys, os

def load_fvecs(path):
    with open(path, 'rb') as f:
        dim = struct.unpack('i', f.read(4))[0]
        f.seek(0, 2); N = (f.tell() - 4) // (4 + dim * 4)
        f.seek(4); vecs = np.zeros((N, dim), dtype=np.float32)
        for i in range(N):
            struct.unpack('i', f.read(4))
            vecs[i] = np.frombuffer(f.read(dim * 4), dtype=np.float32)
    return vecs

def load_ivecs(path):
    with open(path, 'rb') as f:
        d = struct.unpack('i', f.read(4))[0]
        f.seek(0, 2); N = (f.tell() - 4) // (4 + d * 4)
        f.seek(4)
        ids = np.zeros((N, d), dtype=np.int32)
        for i in range(N):
            struct.unpack('i', f.read(4))
            for j in range(d):
                ids[i,j] = struct.unpack('i', f.read(4))[0]
                f.read(4)  # skip distance
    return ids

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <kmeans_assignments.npy> <groundtruth.ivecs> [query_count]")
        print("  kmeans_assignments.npy: cluster ID per node (0..K-1)")
        print("  groundtruth.ivecs: top-100 groundtruth")
        sys.exit(1)

    cluster_ids = np.load(sys.argv[1]).astype(np.int32)
    gt_ids = load_ivecs(sys.argv[2])
    NQ = min(int(sys.argv[3]), gt_ids.shape[0]) if len(sys.argv) > 3 else gt_ids.shape[0]

    print(f"Cluster IDs: {len(cluster_ids)} nodes, {len(np.unique(cluster_ids))} clusters")
    print(f"Groundtruth: {gt_ids.shape[0]} queries, top-{gt_ids.shape[1]}")

    # Per query: cluster purity of top-K groundtruth neighbors
    TOP_K_VALUES = [20, 50, 100, 200]
    CANDIDATE_COUNTS = [10, 20, 30, 50, 100, 200]

    results = {}
    for top_k in TOP_K_VALUES:
        purities = []
        for i in range(NQ):
            gids = gt_ids[i, :top_k]
            gclusters = cluster_ids[gids]
            purity = len(np.unique(gclusters)) / top_k
            purities.append(purity)
        results[top_k] = np.array(purities)

    print(f"\n{'TopK':<8} {'Mean purity':>12} {'Std':>8} {'Min':>8} {'Max':>8}")
    print("-" * 48)
    for top_k in TOP_K_VALUES:
        p = results[top_k]
        print(f"{top_k:<8} {1-p.mean():>12.4f} {p.std():>8.4f} {1-p.max():>8.4f} {1-p.min():>8.4f}")

    # Key analysis: group queries by cluster purity, compute recall@10 vs candidate count
    print(f"\n=== Recall@10 by purity group and candidate count ===")
    purity_groups = {0.2: 0, 0.4: 0, 0.6: 0, 0.8: 0}
    N_tests = min(NQ, 500)
    
    for top_k in [100]:
        purities = results[top_k]
        for i in range(N_tests):
            # Compute recall for varying candidate counts
            gt_set = set(gt_ids[i, :10])  # top-10 groundtruth
            topK_set = set(gt_ids[i, :top_k])
            
            gclusters = cluster_ids[list(topK_set)]
            purity = len(np.unique(gclusters)) / top_k
            
            for cands in CANDIDATE_COUNTS:
                # Simulate: if we keep only FIRST 'cands' from groundtruth
                sub_set = set(gt_ids[i, :cands])
                recall = len(gt_set & sub_set) / 10
                # Group by purity
                for pg in [0.3, 0.5, 0.7]:
                    if purity <= pg:
                        key = (pg, cands)
                        if key not in purity_groups:
                            purity_groups[key] = []
                        purity_groups.setdefault(key, []).append(recall)
                        break
    
    print(f"\n{'Purity':<10}", end="")
    for c in CANDIDATE_COUNTS:
        print(f"  cands={c:>3d}", end="")
    print()
    for pg in [0.3, 0.5, 0.7, 1.0]:
        print(f"{'<='+str(pg):<10}", end="")
        for c in CANDIDATE_COUNTS:
            key = (pg, c)
            if key in purity_groups and purity_groups[key]:
                avg_rec = np.mean(purity_groups[key])
                print(f"    {avg_rec:>.3f}", end="")
            else:
                print(f"      N/A", end="")
        print()

    # Conclusion
    print(f"\n=== Conclusion ===")
    low_p = np.percentile(results[100], 33)
    high_p = np.percentile(results[100], 67)
    print(f"Low purity (bottom 33%): < {low_p:.3f}")
    print(f"High purity (top 33%):   > {high_p:.3f}")
    print(f"Gap: {high_p - low_p:.3f}")
    if high_p - low_p > 0.05:
        print("Verdict: cluster purity IS predictive → worth adding to GBDT ✅")
    else:
        print("Verdict: cluster purity NOT predictive → marginal/negative ❌")
