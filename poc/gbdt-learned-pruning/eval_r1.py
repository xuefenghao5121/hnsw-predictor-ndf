#!/usr/bin/env python3
"""
R1 精确评估: 用 GBDT 预测的 N 值精确计算 recall
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
import re
import sys

def parse_llsp_log(path):
    queries = []
    pattern = re.compile(
        r'\[LLSP\] qid=(\d+) n=(\d+) d0=([\d.]+) d9=([\d.]+) dk=([\d.]+) dk1=([\d.]+) '
        r'gap=([\d.]+) mean=([\d.]+) std=([\d.]+) ids=(.+)'
    )
    with open(path) as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                ids = [int(x) for x in m.group(10).split(',')]
                queries.append({
                    'qid': int(m.group(1)),
                    'n': int(m.group(2)),
                    'd0': float(m.group(3)),
                    'd9': float(m.group(4)),
                    'dk': float(m.group(5)),
                    'dk1': float(m.group(6)),
                    'gap': float(m.group(7)),
                    'mean': float(m.group(8)),
                    'std': float(m.group(9)),
                    'ids': ids,
                })
    return queries

def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/llsp_10k.txt'
    gt_path = sys.argv[2] if len(sys.argv) > 2 else '/home/huawei/hnsw-predictor-ndf/data/sift1m_gt10k.bin'
    
    queries = parse_llsp_log(log_path)
    n_warmup = len(queries) // 2
    real = queries[n_warmup:]
    
    # Load GT
    with open(gt_path, 'rb') as f:
        header = np.frombuffer(f.read(8), dtype=np.uint32)
        n_q, kk = int(header[0]), int(header[1])
        gt = np.frombuffer(f.read(), dtype=np.uint64).reshape(n_q, kk)
    
    # Load model
    booster = lgb.Booster(model_file='/tmp/llsp_model.txt')
    
    # Build features
    feat_cols = ['n_coarse', 'd0', 'd9', 'dk', 'dk1', 'gap_ratio', 'd_mean', 'd_std', 'd_cv', 'd_ratio_01', 'd_ratio_09']
    
    correct_fixed = {n: 0 for n in [20, 30, 40, 50, 100]}
    correct_gbdt = 0
    correct_gbdt_margin = 0  # GBDT + 20% safety margin
    correct_heuristic = 0   # ADAPTIVE_EF style
    total = 0
    
    # Collect features for batch predict
    feats = []
    for i, q in enumerate(real):
        mean = q['mean']
        std = q['std']
        cv = std / mean if mean > 0 else 0
        r01 = q['d0'] / mean if mean > 0 else 1
        r09 = q['d9'] / mean if mean > 0 else 1
        feats.append([q['n'], q['d0'], q['d9'], q['dk'], q['dk1'], q['gap'], mean, std, cv, r01, r09])
    
    feats = np.array(feats)
    preds = booster.predict(feats)
    
    for i, q in enumerate(real):
        gt_set = set(gt[i].tolist())
        cand = q['ids']
        
        # Fixed N
        for n_fix in [20, 30, 40, 50, 100]:
            n_eff = min(n_fix, len(cand))
            for cid in cand[:n_eff]:
                if cid in gt_set:
                    correct_fixed[n_fix] += 1
        
        # GBDT: use predicted N (clamped to [10, 200])
        pred_n = int(max(10, min(200, np.ceil(preds[i]))))
        n_eff = min(pred_n, len(cand))
        for cid in cand[:n_eff]:
            if cid in gt_set:
                correct_gbdt += 1
        
        # GBDT + margin: pred_n * 1.2
        pred_n_m = int(max(10, min(200, np.ceil(preds[i] * 1.2))))
        n_eff = min(pred_n_m, len(cand))
        for cid in cand[:n_eff]:
            if cid in gt_set:
                correct_gbdt_margin += 1
        
        # Heuristic: 3-level gap_ratio (same as ADAPTIVE_EF)
        gap = q['gap']
        if gap >= 1.006:
            hef = 50
        elif gap <= 1.002:
            hef = 200
        else:
            hef = 100
        n_eff = min(hef, len(cand))
        for cid in cand[:n_eff]:
            if cid in gt_set:
                correct_heuristic += 1
        
        total += kk
    
    print("=== Precise Recall Comparison (10K queries) ===\n")
    print(f"{'Method':<25} {'Recall':>8} {'Avg N':>8} {'Reduction':>10}")
    print("-" * 55)
    
    for n_fix in [20, 30, 40, 50, 100]:
        recall = correct_fixed[n_fix] / total * 100
        print(f"Fixed N={n_fix:<20} {recall:>7.2f}% {n_fix:>8} {(100-n_fix):>9.0f}%")
    
    # GBDT
    recall_gbdt = correct_gbdt / total * 100
    avg_n_gbdt = np.mean(np.clip(np.ceil(preds), 10, 200))
    print(f"{'GBDT':<25} {recall_gbdt:>7.2f}% {avg_n_gbdt:>8.0f} {(100-avg_n_gbdt):>9.0f}%")
    
    # GBDT + margin
    recall_margin = correct_gbdt_margin / total * 100
    avg_n_margin = np.mean(np.clip(np.ceil(preds * 1.2), 10, 200))
    print(f"{'GBDT +20% margin':<25} {recall_margin:>7.2f}% {avg_n_margin:>8.0f} {(100-avg_n_margin):>9.0f}%")
    
    # Heuristic
    recall_heur = correct_heuristic / total * 100
    # Calculate avg N for heuristic
    heur_ns = []
    for q in real:
        gap = q['gap']
        if gap >= 1.006: heur_ns.append(min(50, q['n']))
        elif gap <= 1.002: heur_ns.append(min(200, q['n']))
        else: heur_ns.append(min(100, q['n']))
    avg_n_heur = np.mean(heur_ns)
    print(f"{'Heuristic (ADAPTIVE_EF)':<25} {recall_heur:>7.2f}% {avg_n_heur:>8.0f} {(100-avg_n_heur):>9.0f}%")

if __name__ == '__main__':
    main()
