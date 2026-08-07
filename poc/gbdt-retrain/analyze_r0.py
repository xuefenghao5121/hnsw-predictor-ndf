#!/usr/bin/env python3
"""
R0 profiling 分析 (GBDT 重训练): 从 LLSP dump 提取特征 + 标签

关键改动 vs 原 analyze_r0.py:
  - GT 使用官方 sift_groundtruth.ivecs (无 self-match)
  - query 来自官方 10K query 池 (非 base-sampled)

输入:
  - /tmp/llsp_retrain_real.txt (PROFILE_LLSP=1 输出, 后 10000 行)
  - data/sift_groundtruth_official.ivecs (官方 GT, 10000×100)

输出:
  - /tmp/llsp_retrain_features.csv  (特征矩阵)
  - /tmp/llsp_retrain_labels.csv    (标签: min_n)
  - /tmp/llsp_retrain_report.txt    (统计报告)
"""

import numpy as np
import re
import sys
import csv
from pathlib import Path

def parse_llsp_log(path):
    """解析 [LLSP] 行, 返回 list of dict"""
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
                n = int(m.group(2))
                d0 = float(m.group(3))
                d9 = float(m.group(4))
                dk = float(m.group(5))
                dk1 = float(m.group(6))
                gap = float(m.group(7))
                mean = float(m.group(8))
                std = float(m.group(9))
                ids = [int(x) for x in m.group(10).split(',')]
                queries.append({
                    'qid': qid, 'n': n, 'd0': d0, 'd9': d9,
                    'dk': dk, 'dk1': dk1, 'gap': gap,
                    'mean': mean, 'std': std, 'ids': ids,
                })
    return queries

def load_official_gt(path, k=10):
    """
    加载官方 GT (ivecs 格式)
    格式: 每行 [int32 dim] [dim × int32 indices]
    """
    gt = []
    with open(path, 'rb') as f:
        while True:
            dim_data = f.read(4)
            if len(dim_data) < 4:
                break
            dim = int(np.frombuffer(dim_data, dtype=np.int32)[0])
            row = np.frombuffer(f.read(dim * 4), dtype=np.int32)
            gt.append(row[:k].tolist())
    return gt

def find_min_n(cand_ids, gt_ids):
    """
    找到包含全部 gt_ids 的最小候选数。
    即: gt_ids 在 cand_ids 中的最大位置 + 1。
    如果某个 gt_id 不在候选中, 返回 len(cand_ids)+1 (不可达)。
    """
    max_pos = 0
    for gt_id in gt_ids:
        try:
            pos = cand_ids.index(gt_id)
            max_pos = max(max_pos, pos + 1)
        except ValueError:
            return len(cand_ids) + 1  # 不可达
    return max_pos

def find_recall_at_n(cand_ids, gt_ids, n):
    """在候选前 n 个中找到多少 gt_ids"""
    found = 0
    for gt_id in gt_ids:
        try:
            pos = cand_ids.index(gt_id)
            if pos < n:
                found += 1
        except ValueError:
            pass
    return found

def main():
    log_path = '/tmp/llsp_retrain_real.txt'
    gt_path = '/home/huawei/hnsw-predictor-ndf/data/sift_groundtruth_official.ivecs'
    
    queries = parse_llsp_log(log_path)
    print(f"Parsed {len(queries)} queries from profiling log")
    
    gt = load_official_gt(gt_path, k=10)
    print(f"Loaded {len(gt)} GT entries from official ivecs")
    
    assert len(queries) == len(gt), f"Mismatch: {len(queries)} queries vs {len(gt)} GT"
    
    # 为每个 query 计算特征 + 标签
    features = []
    labels_min_n = []
    recall_by_n = {n: [] for n in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]}
    
    for i, q in enumerate(queries):
        gt_ids = gt[i]
        min_n = find_min_n(q['ids'], gt_ids)
        
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
        labels_min_n.append(min_n)
        
        for n_test in recall_by_n:
            found = find_recall_at_n(q['ids'], gt_ids, n_test)
            recall_by_n[n_test].append(found)
    
    # 统计
    min_ns = np.array(labels_min_n)
    print(f"\n=== 标签统计: min_n (包含全部 10 个 GT 的最小候选数) ===")
    print(f"  Min: {min_ns.min()}, Max: {min_ns.max()}, Mean: {min_ns.mean():.1f}, Median: {np.median(min_ns):.1f}")
    print(f"  P10: {np.percentile(min_ns, 10):.0f}, P25: {np.percentile(min_ns, 25):.0f}, "
          f"P50: {np.percentile(min_ns, 50):.0f}, P75: {np.percentile(min_ns, 75):.0f}, "
          f"P90: {np.percentile(min_ns, 90):.0f}")
    
    print(f"\n=== min_n 分布 ===")
    for threshold in [10, 20, 30, 40, 50, 60, 80, 100, 150, 200]:
        count = (min_ns <= threshold).sum()
        print(f"  min_n ≤ {threshold}: {count}/{len(min_ns)} ({count*100/len(min_ns):.1f}%)")
    
    # 不可达统计
    unreachable = (min_ns > 200).sum()
    print(f"\n  不可达 (min_n > 200): {unreachable}/{len(min_ns)} ({unreachable*100/len(min_ns):.1f}%)")
    
    # Aggregate recall at different N
    print(f"\n=== Aggregate Recall@10 at different N ===")
    for n_test in sorted(recall_by_n):
        total_found = sum(recall_by_n[n_test])
        total_possible = len(queries) * 10
        recall = total_found / total_possible
        print(f"  N={n_test:3d}: recall={recall:.4f}")
    
    # 写 CSV
    feat_path = '/tmp/llsp_retrain_features.csv'
    with open(feat_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=features[0].keys())
        w.writeheader()
        w.writerows(features)
    
    lab_path = '/tmp/llsp_retrain_labels.csv'
    with open(lab_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['qid', 'min_n'])
        for i, mn in enumerate(labels_min_n):
            w.writerow([i, mn])
    
    print(f"\n特征已写入: {feat_path}")
    print(f"标签已写入: {lab_path}")
    
    # 与原 POC (base-sampled) 对比
    print(f"\n=== 与原 POC 对比 (self-match 污染影响) ===")
    print(f"  原 POC (base-sampled, 含 self-match):")
    print(f"    P50=21, P75=30, P90=50 (min_n 系统性偏低)")
    print(f"    68% query 只需 ≤30 候选")
    print(f"  本 POC (官方池, 无 self-match):")
    print(f"    P50={np.median(min_ns):.0f}, P75={np.percentile(min_ns, 75):.0f}, P90={np.percentile(min_ns, 90):.0f}")
    print(f"    {((min_ns <= 30).sum()*100/len(min_ns)):.1f}% query 只需 ≤30 候选")
    
    if np.median(min_ns) > 21:
        print(f"\n  ✅ 确认: self-match 污染使原标签系统性偏低")
        print(f"     官方池 P50={np.median(min_ns):.0f} vs 原 P50=21 (+{np.median(min_ns)-21:.0f})")
    else:
        print(f"\n  ⚠️ 意外: 官方池 P50 与原 POC 接近，self-match 影响可能不显著")

if __name__ == '__main__':
    main()
