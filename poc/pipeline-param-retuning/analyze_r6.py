#!/usr/bin/env python3
"""
R6.2: 从 LLSP profiling dump 提取特征 + 标签

输入: /tmp/llsp_r6_{m16_ef65,m24_ef60}.txt (PROFILE_LLSP=1 输出, 20K 行 = 10K warmup + 10K measurement)
      data/sift_groundtruth_official.ivecs (官方 GT, 10000×100)

输出: /tmp/llsp_r6_{tag}_features.csv  (特征矩阵)
      /tmp/llsp_r6_{tag}_labels.csv    (标签: min_n)
      /tmp/llsp_r6_{tag}_report.txt    (统计报告)
"""

import numpy as np
import re
import csv
import sys
from pathlib import Path

def parse_llsp_log(path):
    """解析 [LLSP] 行, 返回 list of dict. 取后半 (measurement run)"""
    queries = []
    pattern = re.compile(
        r'\[LLSP\] qid=(\d+) n=(\d+) d0=([\d.]+) d9=([\d.]+) dk=([\d.]+) dk1=([\d.]+) '
        r'gap=([\d.]+) mean=([\d.]+) std=([\d.]+) ids=(.+)'
    )
    with open(path) as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                qid = int(m.group(1))
                ids_str = m.group(10).strip()
                ids = [int(x) for x in ids_str.split(',')] if ids_str else []
                queries.append({
                    'qid': qid,
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
    
    # Take second half (measurement run, skip warmup)
    half = len(queries) // 2
    print(f"Total LLSP entries: {len(queries)}, taking last {half} (measurement)")
    return queries[half:]

def load_official_gt(path, k=10):
    """加载官方 ground truth"""
    with open(path, 'rb') as f:
        # ivecs format: [n][k] where each row is [dim, id0, id1, ...]
        # Actually sift_groundtruth_official.ivecs is in ivecs format
        # Each vector: 4 bytes dim + dim*4 bytes int32
        gt = []
        while True:
            dim_bytes = f.read(4)
            if len(dim_bytes) < 4:
                break
            dim = np.frombuffer(dim_bytes, dtype=np.int32)[0]
            row = np.frombuffer(f.read(dim * 4), dtype=np.int32)
            gt.append(row[:k].tolist())
    return gt

def find_min_n(candidate_ids, gt_ids, k=10):
    """找到最小 N 使得前 N 个候选中包含 >= k 个 GT"""
    gt_set = set(gt_ids[:k])
    found = 0
    for i, cid in enumerate(candidate_ids):
        if cid in gt_set:
            found += 1
            if found >= k:
                return i + 1
    return len(candidate_ids)  # 未找到 k 个, 返回全部

def analyze(tag, llsp_path, gt_path):
    queries = parse_llsp_log(llsp_path)
    print(f"Parsed {len(queries)} queries from {llsp_path}")
    
    gt = load_official_gt(gt_path, k=10)
    print(f"Loaded {len(gt)} GT entries from official ivecs")
    
    assert len(queries) == len(gt), f"Mismatch: {len(queries)} queries vs {len(gt)} GT"
    
    features = []
    labels = []
    
    for i, q in enumerate(queries):
        gt_ids = gt[i]
        min_n = find_min_n(q['ids'], gt_ids, k=10)
        
        d_ratio_01 = q['d0'] / q['mean'] if q['mean'] > 0 else 1.0
        d_ratio_09 = q['d9'] / q['mean'] if q['mean'] > 0 else 1.0
        cv = q['std'] / q['mean'] if q['mean'] > 0 else 0
        
        features.append({
            'qid': i,
            'n_coarse': q['n'],
            'd0': q['d0'],
            'd9': q['d9'],
            'dk': q['dk'],
            'dk1': q['dk1'],
            'gap_ratio': q['gap'],
            'd_mean': q['mean'],
            'd_std': q['std'],
            'd_cv': cv,
            'd_ratio_01': d_ratio_01,
            'd_ratio_09': d_ratio_09,
        })
        labels.append({'qid': i, 'min_n': min_n})
    
    # Write features CSV
    feat_path = f'/tmp/llsp_r6_{tag}_features.csv'
    with open(feat_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=features[0].keys())
        writer.writeheader()
        writer.writerows(features)
    print(f"Features: {feat_path}")
    
    # Write labels CSV
    lab_path = f'/tmp/llsp_r6_{tag}_labels.csv'
    with open(lab_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['qid', 'min_n'])
        writer.writeheader()
        writer.writerows(labels)
    print(f"Labels: {lab_path}")
    
    # Statistics
    min_ns = [l['min_n'] for l in labels]
    print(f"\n=== {tag} Statistics ===")
    print(f"min_n: min={min(min_ns)}, max={max(min_ns)}, mean={np.mean(min_ns):.1f}, median={np.median(min_ns):.0f}")
    for t in [10, 20, 30, 40, 50, 60, 80, 100, 200]:
        count = sum(1 for n in min_ns if n <= t)
        print(f"  min_n <= {t}: {count}/{len(min_ns)} ({count*100/len(min_ns):.1f}%)")
    
    # Recall at fixed N
    for n in [65, 100, 200]:
        found_total = 0
        for i, q in enumerate(queries):
            gt_set = set(gt[i][:10])
            found = sum(1 for cid in q['ids'][:n] if cid in gt_set)
            found_total += found
        recall = found_total / (len(queries) * 10)
        print(f"  Fixed N={n}: recall={recall:.4f}")
    
    return features, labels

if __name__ == '__main__':
    gt_path = '/home/huawei/hnsw-predictor-ndf/data/sift_groundtruth_official.ivecs'
    
    print("=" * 60)
    print("R6.2: Feature extraction for M=16 EF=65")
    print("=" * 60)
    f1, l1 = analyze('m16_ef65', '/tmp/llsp_r6_m16_ef65.txt', gt_path)
    
    print()
    print("=" * 60)
    print("R6.2: Feature extraction for M=24 EF=60")
    print("=" * 60)
    f2, l2 = analyze('m24_ef60', '/tmp/llsp_r6_m24_ef60.txt', gt_path)
    
    print()
    print("=== Comparison ===")
    n1 = [l['min_n'] for l in l1]
    n2 = [l['min_n'] for l in l2]
    print(f"M=16 EF=65: mean min_n={np.mean(n1):.1f}, median={np.median(n1):.0f}")
    print(f"M=24 EF=60: mean min_n={np.mean(n2):.1f}, median={np.median(n2):.0f}")
    print(f"Difference: M=16 is {'more' if np.mean(n1) > np.mean(n2) else 'less'} conservative by {abs(np.mean(n1)-np.mean(n2)):.1f}")
