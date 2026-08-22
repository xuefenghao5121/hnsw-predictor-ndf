#!/usr/bin/env python3
"""
R0 profiling 分析: 从 LLSP dump 提取特征 + 标签

输入:
  - /tmp/llsp_r0_profile.txt (PROFILE_LLSP=1 输出)
  - GT bin 文件 (sift1m_gt200.bin, uint64, shape=[200, 10])

输出:
  - /tmp/llsp_r0_features.csv  (特征矩阵)
  - /tmp/llsp_r0_labels.csv    (标签: 每个 query 的最小候选数)
"""

import numpy as np
import re
import sys
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

def load_gt(path, num_queries=200, k=10):
    """加载 GT bin (uint64, 有 8B 头部)"""
    with open(path, 'rb') as f:
        header = np.frombuffer(f.read(8), dtype=np.uint32)
        n_q, kk = int(header[0]), int(header[1])
        print(f'GT header: n_queries={n_q}, k={kk}')
        gt = np.frombuffer(f.read(), dtype=np.uint64).reshape(n_q, kk)
    return gt

def find_min_n(cand_ids, gt_ids):
    """
    找到包含所有 gt_ids 的最小候选数。
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
    log_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/llsp_r0_profile.txt'
    gt_path = sys.argv[2] if len(sys.argv) > 2 else '/home/huawei/hnsw-predictor-ndf/data/sift1m_gt200.bin'
    
    queries = parse_llsp_log(log_path)
    
    # 去掉 warmup (前一半)
    # warmup 是 qid=0..199, 实测是 qid=200..399 (但 counter 是全局的)
    # 实际上单线程 warmup 也会递增 query_idx_, 所以取后半部分
    # 200 queries: warmup 0-199, real 200-399
    # warmup = qid 0..N-1, real = qid N..2N-1
    # 但单线程 warmup 遍历所有 query, 所以 warmup 数 = total/2
    # 检测: warmup 的 query 与 real 的 query 顺序相同 (重复跑)
    n_warmup = len(queries) // 2
    real_queries = queries[n_warmup:]
    # GT 也用同样数量
    n_real = len(real_queries)
    print(f"Total parsed: {len(queries)}, warmup: {n_warmup}, real: {n_real}")
    
    gt = load_gt(gt_path)
    
    # 为每个 query 计算标签
    features = []
    labels_min_n = []  # 包含所有 10 个 GT 的最小候选数
    labels_recall10 = []  # 在 N 个候选中找到的 GT 数
    
    for i, q in enumerate(real_queries):
        gt_ids = gt[i].tolist()
        min_n = find_min_n(q['ids'], gt_ids)
        
        # 额外特征: 候选距离的比率
        d_ratio_01 = q['d0'] / q['mean'] if q['mean'] > 0 else 1.0
        d_ratio_09 = q['d9'] / q['mean'] if q['mean'] > 0 else 1.0
        cv = q['std'] / q['mean'] if q['mean'] > 0 else 0  # 变异系数
        
        # 候选距离分布的前 K 个间隔
        # d0/d_mean: 最近候选距离与均值之比
        
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
        
        # 在不同 N 下的 recall
        for n_test in [10, 20, 30, 40, 50, 60, 70, 80, 100]:
            found = find_recall_at_n(q['ids'], gt_ids, n_test)
            labels_recall10.append({'qid': i, 'n': n_test, 'found': found})
    
    # 输出统计
    min_ns = np.array(labels_min_n)
    print(f"\n=== 标签统计: min_n (包含所有 10 个 GT 的最小候选数) ===")
    print(f"  Min: {min_ns.min()}, Max: {min_ns.max()}, Mean: {min_ns.mean():.1f}, Median: {np.median(min_ns):.1f}")
    print(f"  P25: {np.percentile(min_ns, 25):.0f}, P50: {np.percentile(min_ns, 50):.0f}, "
          f"P75: {np.percentile(min_ns, 75):.0f}, P90: {np.percentile(min_ns, 90):.0f}")
    
    # 分布
    print(f"\n=== min_n 分布 ===")
    for threshold in [10, 20, 30, 40, 50, 60, 80, 100]:
        count = (min_ns <= threshold).sum()
        print(f"  min_n ≤ {threshold}: {count}/{len(min_ns)} ({count*100/len(min_ns):.1f}%)")
    
    # 固定 N=100 (基线), N=50 (easy), N=200 (hard) 的 aggregate recall
    print(f"\n=== Aggregate Recall@10 at different N ===")
    for n_test in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        total_found = sum(r['found'] for r in labels_recall10 if r['n'] == n_test)
        total_possible = len(real_queries) * 10
        recall = total_found / total_possible
        print(f"  N={n_test:3d}: recall={recall:.4f}")
    
    # 写 CSV
    import csv
    feat_path = '/tmp/llsp_r0_features.csv'
    with open(feat_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=features[0].keys())
        w.writeheader()
        w.writerows(features)
    
    lab_path = '/tmp/llsp_r0_labels.csv'
    with open(lab_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['qid', 'min_n'])
        for i, mn in enumerate(labels_min_n):
            w.writerow([i, mn])
    
    print(f"\n特征已写入: {feat_path}")
    print(f"标签已写入: {lab_path}")

if __name__ == '__main__':
    main()
