#!/usr/bin/env python3
"""
R1: 训练 LightGBM 模型预测 per-query 最小候选数

输入: /tmp/llsp_r0_features.csv + /tmp/llsp_r0_labels.csv
输出: 
  /tmp/llsp_model.txt (LightGBM model)
  /tmp/llsp_model_predict.c (C++ if-else 规则表导出)
  /tmp/llsp_r1_report.txt (训练报告)
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import sys

def main():
    features = pd.read_csv('/tmp/llsp_r0_features.csv')
    labels = pd.read_csv('/tmp/llsp_r0_labels.csv')
    
    # 合并
    df = features.merge(labels, on='qid')
    
    # 不可达的 (min_n > 500) cap 到 500
    df['min_n_capped'] = df['min_n'].clip(upper=200)
    
    # 特征列
    feat_cols = ['n_coarse', 'd0', 'd9', 'dk', 'dk1', 'gap_ratio', 'd_mean', 'd_std', 'd_cv', 'd_ratio_01', 'd_ratio_09']
    X = df[feat_cols].values
    y = df['min_n_capped'].values
    
    # 80/20 划分
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"Label range: {y.min()} ~ {y.max()}, mean={y.mean():.1f}")
    
    # 训练 GBDT
    params = {
        'objective': 'regression',
        'metric': 'mae',
        'num_leaves': 15,       # ≤ 2^depth, depth=4
        'max_depth': 4,         # 浅树, 快推理
        'learning_rate': 0.1,
        'n_estimators': 100,
        'min_child_samples': 5, # 小数据集
        'verbose': -1,
    }
    
    model = lgb.LGBMRegressor(**params)
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.log_evaluation(20)])
    
    # 评估
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    print(f"\n=== Model Performance ===")
    print(f"MAE: {mae:.1f}")
    
    # 更有意义的评估: 如果用预测值做候选上限, recall 会怎样?
    # 回到原始数据, 对每个 query 用 pred_n 和实际 min_n 比较
    y_pred_all = model.predict(X)
    
    # 模拟: 如果用 pred_n (向上取整) 作为候选上限
    correct = 0
    total = 0
    for i in range(len(df)):
        pred_n = int(np.ceil(y_pred_all[i]))
        actual_min_n = df['min_n'].iloc[i]
        if pred_n >= actual_min_n:
            # 预测的候选数够大, 全部 10 个 GT 应该都在
            correct += 10
        else:
            # 不够大, 按 ratio 估算 (粗略)
            # 实际需要精确计算, 这里用近似
            ratio = min(1.0, pred_n / max(1, actual_min_n))
            correct += int(10 * ratio)
        total += 10
    
    print(f"Simulated recall (GBDT predicted N): {correct/total*100:.2f}%")
    
    # 对比: 固定 N=100 的 recall
    correct_fix100 = sum(min(10, max(0, 10)) if 100 >= df['min_n'].iloc[i] 
                         else int(10 * 100 / max(1, df['min_n'].iloc[i]))
                         for i in range(len(df)))
    print(f"Simulated recall (fixed N=100): {correct_fix100/total*100:.2f}%")
    
    # 对比: 固定 N=50
    correct_fix50 = sum(1 if 50 >= df['min_n'].iloc[i] else 0 for i in range(len(df)))
    print(f"Coverage (fixed N=50): {correct_fix50}/{len(df)} = {correct_fix50/len(df)*100:.1f}%")
    
    # 对比: 固定 N=30
    correct_fix30 = sum(1 if 30 >= df['min_n'].iloc[i] else 0 for i in range(len(df)))
    print(f"Coverage (fixed N=30): {correct_fix30}/{len(df)} = {correct_fix30/len(df)*100:.1f}%")
    
    # GBDT 预测的候选数分布
    pred_n = np.ceil(y_pred_all).astype(int)
    print(f"\n=== GBDT Predicted N Distribution ===")
    print(f"  Min: {pred_n.min()}, Max: {pred_n.max()}, Mean: {pred_n.mean():.1f}, Median: {np.median(pred_n):.0f}")
    for t in [20, 30, 40, 50, 80, 100, 200]:
        count = (pred_n <= t).sum()
        print(f"  pred_n ≤ {t}: {count}/{len(pred_n)} ({count*100/len(pred_n):.1f}%)")
    
    # 平均候选数 (对比固定 100)
    avg_n = pred_n.mean()
    print(f"\n=== 候选数对比 ===")
    print(f"  Fixed N=100: avg=100")
    print(f"  GBDT: avg={avg_n:.1f} (节省 {100-avg_n:.1f}%, {(100-avg_n)/100*100:.1f}% I/O reduction)")
    
    # 保存模型
    model.booster_.save_model('/tmp/llsp_model.txt')
    print(f"\n模型已保存: /tmp/llsp_model.txt")
    
    # 特征重要性
    importance = model.feature_importances_
    print(f"\n=== Feature Importance ===")
    for name, imp in sorted(zip(feat_cols, importance), key=lambda x: -x[1]):
        print(f"  {name:15s}: {imp}")
    
    # 导出 C++ 规则表 (简单的 if-else 从 GBDM 树提取)
    # LightGBM 模型可以直接 dump 为 if-else
    dump_text = model.booster_.dump_model()
    num_trees = len(dump_text['tree_info'])
    print(f"\n模型树数: {num_trees}")
    
    # 导出为可被 C++ 加载的格式
    # 最简单: 保存模型文件, 运行时用轻量 C++ LightGBM 推理器加载
    # 或者: 导出为 if-else 代码
    print(f"\n=== 导出 C++ if-else 规则 ===")
    
    cpp_code = generate_cpp_rules(dump_text, feat_cols)
    with open('/tmp/llsp_model_predict.c', 'w') as f:
        f.write(cpp_code)
    print(f"C++ 代码已导出: /tmp/llsp_model_predict.c ({len(cpp_code)} bytes)")
    
    # 模拟推理延迟
    import time
    t0 = time.perf_counter()
    for _ in range(10000):
        model.predict(X[:1])
    t1 = time.perf_counter()
    us_per_pred = (t1 - t0) / 10000 * 1e6
    print(f"\nPython 推理延迟: {us_per_pred:.2f} μs/prediction (10K avg)")
    print(f"注: C++ if-else 推理预期 <0.1 μs (无 Python overhead)")

def generate_cpp_rules(model_dump, feat_names):
    """从 LightGBM 模型 dump 生成 C++ if-else 预测函数"""
    trees = model_dump['tree_info']
    
    lines = []
    lines.append('// Auto-generated GBDT prediction (from LightGBM)')
    lines.append(f'// Features: {", ".join(feat_names)}')
    lines.append(f'// Trees: {len(trees)}')
    lines.append('')
    lines.append('#include <array>')
    lines.append('#include <cstdint>')
    lines.append('')
    # 特征索引
    lines.append(f'// Feature indices:')
    for i, name in enumerate(feat_names):
        lines.append(f'//   [{i}] {name}')
    lines.append('')
    lines.append('float gbdt_predict(const float* feat) {')
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
    """递归生成 if-else"""
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

if __name__ == '__main__':
    main()
