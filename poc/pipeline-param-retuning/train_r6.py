#!/usr/bin/env python3
"""
R6.3: 训练 LightGBM 模型 for M=16 EF=65 和 M=24 EF=60

输入: /tmp/llsp_r6_{tag}_features.csv + /tmp/llsp_r6_{tag}_labels.csv
输出: poc/pipeline-param-retuning/gbdt_model_{tag}.h (C++ header)
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import json
import sys
sys.path.insert(0, 'poc/gbdt-retrain')
from train_r2 import generate_cpp_header

def train_model(tag):
    print(f"\n{'='*60}")
    print(f"Training GBDT for {tag}")
    print(f"{'='*60}")
    
    features = pd.read_csv(f'/tmp/llsp_r6_{tag}_features.csv')
    labels = pd.read_csv(f'/tmp/llsp_r6_{tag}_labels.csv')
    
    df = features.merge(labels, on='qid')
    
    # Cap labels at 200 (same as original)
    df['min_n_capped'] = df['min_n'].clip(upper=200)
    
    feat_cols = ['n_coarse', 'd0', 'd9', 'dk', 'dk1', 'gap_ratio', 'd_mean', 'd_std', 'd_cv', 'd_ratio_01', 'd_ratio_09']
    X = df[feat_cols].values
    y = df['min_n_capped'].values
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"Label range: {y.min()} ~ {y.max()}, mean={y.mean():.1f}, median={np.median(y):.0f}")
    
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
    
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    print(f"\n=== Model Performance ===")
    print(f"MAE: {mae:.1f}")
    
    # Predict on all data
    y_pred_all = model.predict(X)
    pred_n = np.ceil(y_pred_all).astype(int)
    
    print(f"\n=== GBDT Predicted N Distribution ===")
    print(f"  Min: {pred_n.min()}, Max: {pred_n.max()}, Mean: {pred_n.mean():.1f}, Median: {np.median(pred_n):.0f}")
    for t in [10, 20, 30, 40, 50, 60, 80, 100]:
        count = (pred_n <= t).sum()
        print(f"  pred_n <= {t}: {count}/{len(pred_n)} ({count*100/len(pred_n):.1f}%)")
    
    # Simulated recall with different margins
    print(f"\n=== Simulated Recall (GBDT predicted N × margin) ===")
    # Load original data to compute recall
    from analyze_r6 import parse_llsp_log, load_official_gt, find_min_n
    
    tag_suffix = tag  # e.g. "m16_ef65"
    llsp_path = f'/tmp/llsp_r6_{tag_suffix}.txt'
    gt_path = '/home/huawei/hnsw-predictor-ndf/data/sift_groundtruth_official.ivecs'
    
    queries = parse_llsp_log(llsp_path)
    gt = load_official_gt(gt_path, k=10)
    
    for margin in [0.6, 0.7, 0.8, 0.9, 1.0]:
        total_found = 0
        total_possible = len(queries) * 10
        for i, q in enumerate(queries):
            pred = int(np.ceil(y_pred_all[i] * margin))
            pred = max(10, min(200, pred))
            found = sum(1 for cid in q['ids'][:pred] if cid in set(gt[i][:10]))
            total_found += found
        recall = total_found / total_possible
        avg_n = np.mean([max(10, min(200, int(np.ceil(y_pred_all[i] * margin)))) for i in range(len(queries))])
        print(f"  margin={margin}: recall={recall:.4f}, avg_n={avg_n:.1f}")
    
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
    output_path = f'/home/huawei/hnsw-predictor-ndf/poc/pipeline-param-retuning/gbdt_model_{tag}.h'
    with open(output_path, 'w') as f:
        f.write(cpp_code)
    print(f"C++ header 已导出: {output_path} ({len(cpp_code)} bytes)")
    
    return model, mae, pred_n

# Train both models
m1, mae1, pred1 = train_model('m16_ef65')
m2, mae2, pred2 = train_model('m24_ef60')

print(f"\n{'='*60}")
print(f"Comparison")
print(f"{'='*60}")
print(f"M=16 EF=65: MAE={mae1:.1f}, pred mean={pred1.mean():.1f}, median={np.median(pred1):.0f}")
print(f"M=24 EF=60: MAE={mae2:.1f}, pred mean={pred2.mean():.1f}, median={np.median(pred2):.0f}")
print(f"\nOld model (gbdt-retrain, M=16 EF=200): MAE=46.3, pred mean=30, median=21")
print(f"Old model (M=24 EF=200, pipeline):     MAE=15.16, pred mean=~60")
