#!/usr/bin/env python3
"""
R2: 用官方 query 池特征训练新 GBDT 模型

关键改动 vs 原 train_r1.py:
  - 输入: /tmp/llsp_retrain_features.csv (官方池, 无 self-match)
  - 标签 cap: 200 (原 POC 也是 200)
  - 相同 LightGBM 参数 (便于对比)
  - 导出 C++ 规则表到 poc/gbdt-retrain/gbdt_model.h
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import sys

def generate_cpp_header(model_dump, feat_names):
    """从 LightGBM 模型 dump 生成 C++ header (gbdt_model.h)"""
    trees = model_dump['tree_info']
    
    lines = []
    lines.append('// Auto-generated GBDT model (official 10K query pool, no self-match)')
    lines.append(f'// Features: {", ".join(feat_names)}')
    lines.append(f'// Trees: {len(trees)}, max_depth=4')
    lines.append(f'// Trained: 2026-08-07')
    lines.append(f'// Source: poc/gbdt-retrain/ (retrain from official pool)')
    lines.append('')
    lines.append('#pragma once')
    lines.append('')
    lines.append(f'// Feature indices:')
    for i, name in enumerate(feat_names):
        lines.append(f'//   [{i}] {name}')
    lines.append('')
    lines.append('inline float gbdt_predict(const float* feat) {')
    lines.append(f'    float sum = 0.0f;')
    
    for ti, tree_info in enumerate(trees):
        tree = tree_info['tree_structure']
        var = f't{ti}'
        lines.append(f'    // Tree {ti}')
        lines.append(f'    {{')
        lines.append(f'        float {var} = 0.0f;')
        emit_tree(lines, tree, var, 2)
        lines.append(f'        sum += {var};')
        lines.append(f'    }}')
    
    lines.append('    return sum;')
    lines.append('}')
    
    return '\n'.join(lines)

def emit_tree(lines, node, var, indent):
    pad = '    ' * indent
    if 'leaf_value' in node:
        lines.append(f'{pad}{var} = {node["leaf_value"]:.6f}f;')
    else:
        feat = node['split_feature']
        thresh = node['threshold']
        lines.append(f'{pad}if (feat[{feat}] <= {thresh:.6f}f) {{')
        emit_tree(lines, node['left_child'], var, indent + 1)
        lines.append(f'{pad}}} else {{')
        emit_tree(lines, node['right_child'], var, indent + 1)
        lines.append(f'{pad}}}')

def main():
    features = pd.read_csv('/tmp/llsp_retrain_features.csv')
    labels = pd.read_csv('/tmp/llsp_retrain_labels.csv')
    
    df = features.merge(labels, on='qid')
    
    # Cap labels at 200 (same as original)
    df['min_n_capped'] = df['min_n'].clip(upper=200)
    
    feat_cols = ['n_coarse', 'd0', 'd9', 'dk', 'dk1', 'gap_ratio', 'd_mean', 'd_std', 'd_cv', 'd_ratio_01', 'd_ratio_09']
    X = df[feat_cols].values
    y = df['min_n_capped'].values
    
    # 80/20 split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"Label range: {y.min()} ~ {y.max()}, mean={y.mean():.1f}, median={np.median(y):.0f}")
    
    # Same params as original POC
    params = {
        'objective': 'regression',
        'metric': 'mae',
        'num_leaves': 15,
        'max_depth': 4,
        'learning_rate': 0.1,
        'n_estimators': 100,
        'min_child_samples': 5,
        'verbose': -1,
    }
    
    model = lgb.LGBMRegressor(**params)
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.log_evaluation(20)])
    
    # Evaluate
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    print(f"\n=== Model Performance ===")
    print(f"MAE: {mae:.1f}")
    
    # Predict on all data
    y_pred_all = model.predict(X)
    pred_n = np.ceil(y_pred_all).astype(int)
    
    print(f"\n=== GBDT Predicted N Distribution ===")
    print(f"  Min: {pred_n.min()}, Max: {pred_n.max()}, Mean: {pred_n.mean():.1f}, Median: {np.median(pred_n):.0f}")
    for t in [20, 30, 40, 50, 80, 100, 200]:
        count = (pred_n <= t).sum()
        print(f"  pred_n ≤ {t}: {count}/{len(pred_n)} ({count*100/len(pred_n):.1f}%)")
    
    # Simulated recall with GBDT predictions
    print(f"\n=== Simulated Recall (GBDT predicted N, margin=1.0) ===")
    # Load original data to compute recall
    from analyze_r0 import parse_llsp_log, load_official_gt, find_recall_at_n
    
    queries = parse_llsp_log('/tmp/llsp_retrain_real.txt')
    gt = load_official_gt('/home/huawei/hnsw-predictor-ndf/data/sift_groundtruth_official.ivecs', k=10)
    
    for margin in [0.7, 0.8, 0.9, 1.0, 1.1]:
        total_found = 0
        total_possible = len(queries) * 10
        for i, q in enumerate(queries):
            pred = int(np.ceil(y_pred_all[i] * margin))
            pred = max(10, min(200, pred))
            found = find_recall_at_n(q['ids'], gt[i], pred)
            total_found += found
        recall = total_found / total_possible
        avg_n = np.mean([max(10, min(200, int(np.ceil(y_pred_all[i] * margin)))) for i in range(len(queries))])
        print(f"  margin={margin}: recall={recall:.4f}, avg_n={avg_n:.1f}")
    
    # Compare: fixed N=100
    total_fix100 = sum(find_recall_at_n(q['ids'], gt[i], 100) for i, q in enumerate(queries))
    print(f"\n  Fixed N=100: recall={total_fix100/(len(queries)*10):.4f}, avg_n=100.0")
    
    # Feature importance
    importance = model.feature_importances_
    print(f"\n=== Feature Importance ===")
    for name, imp in sorted(zip(feat_cols, importance), key=lambda x: -x[1]):
        print(f"  {name:15s}: {imp}")
    
    # Export C++ header
    dump_text = model.booster_.dump_model()
    num_trees = len(dump_text['tree_info'])
    print(f"\n模型树数: {num_trees}")
    
    cpp_code = generate_cpp_header(dump_text, feat_cols)
    output_path = '/home/huawei/hnsw-predictor-ndf/poc/gbdt-retrain/gbdt_model.h'
    with open(output_path, 'w') as f:
        f.write(cpp_code)
    print(f"C++ header 已导出: {output_path} ({len(cpp_code)} bytes)")
    
    # Save model
    model.booster_.save_model('/tmp/llsp_retrain_model.txt')
    print(f"LightGBM 模型已保存: /tmp/llsp_retrain_model.txt")
    
    # Compare with original model
    print(f"\n=== 与原模型对比 ===")
    print(f"  原模型 (base-sampled, 含 self-match):")
    print(f"    MAE=46.3, P50 pred=21, avg pred ~30")
    print(f"  新模型 (官方池, 无 self-match):")
    print(f"    MAE={mae:.1f}, P50 pred={np.median(pred_n):.0f}, avg pred={pred_n.mean():.1f}")
    
    if pred_n.mean() > 35:
        print(f"\n  ✅ 新模型预测候选数更高 -> 更保守, 不会因过度裁剪导致 recall 下降")
    else:
        print(f"\n  ⚠️ 新模型预测候选数与原模型接近, 需检查是否学到有效信号")

if __name__ == '__main__':
    main()
