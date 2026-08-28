#!/usr/bin/env python3
"""
CAT GBDT probe — train step: LightGBM retrain + sim margin sweep + model export.

Parameterized collapse of the hop-cloned gbdt/train_r5.py / train_r8.py
([[BEH-018]] recipe, sibling poc/gbdt-retrain lineage). One module for every artifact;
the artifact is identified by --artifact-id (the per-artifact model key) and described by
--knobs. The trained model is exported to --model-export (CAT_GBDT_MODEL), a
per-artifact path `harness/gbdt_model_<artifact_id>.h` — MUST NOT be reused on another
graph (INTERFACE CAT_GBDT_MODEL / DESIGN §2 P4).

Model key (DESIGN §2 P4) = `(R0, beam, alpha, block, pq_M, floor_ef, profile_pool)`.
When --artifact-id is omitted it is derived from --r0/--beam/--alpha/--block/--pq-m/
--floor-ef/--pool, so the export path is deterministic per artifact.

Sim margin sweep is skip gate #3 (R6+R8 calibrated; pinned numbers, not invented):
margins {0.8, 1.0, 1.1, 1.3} (or sim-feasible subset). Only margins with SIMULATED
recall >= 95% (prefer >= 95.5%) advance to sustained. Leftover floor recall does NOT
replace the sim gate (R8 m=0.8 still fails at 97.96% floor / ~2.96pp leftover).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from analyze import find_recall_at_n, load_official_gt, parse_llsp_log  # noqa: E402

REPO = _HERE.parents[3]  # repo root (tools/constraint-aware-tuner/gbdt -> repo)

FEAT_COLS = [
    "n_coarse", "d0", "d9", "dk", "dk1", "gap_ratio",
    "d_mean", "d_std", "d_cv", "d_ratio_01", "d_ratio_09",
]

# Pinned recipe (R6/R8): LightGBM 100 trees, depth 4.
LGB_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "num_leaves": 15,
    "max_depth": 4,
    "learning_rate": 0.1,
    "n_estimators": 100,
    "min_child_samples": 5,
    "verbose": -1,
}

# Pinned skip gate #3 sweep (R6/R8 calibrated).
DEFAULT_MARGINS = [0.8, 1.0, 1.1, 1.3]
SIM_FLOOR = 0.95        # must be >= 95% to advance to sustained
SIM_GUARD = 0.955       # preferred >= 95.5% (DESIGN §4 safety margin)


def model_key(r0, beam, alpha, block, pq_m, floor_ef, pool):
    return f"r0{r0}_beam{beam}_a{alpha}_blk{block}_pqm{pq_m}_ef{floor_ef}_{pool}"


def emit_tree(lines, node, var, indent):
    pad = "    " * indent
    if "leaf_value" in node:
        lines.append(f'{pad}{var} = {node["leaf_value"]:.6f}f;')
    else:
        feat = node["split_feature"]
        thresh = node["threshold"]
        lines.append(f'{pad}if (feat[{feat}] <= {thresh:.6f}f) {{')
        emit_tree(lines, node["left_child"], var, indent + 1)
        lines.append(f'{pad}}} else {{')
        emit_tree(lines, node["right_child"], var, indent + 1)
        lines.append(f'{pad}}}')


def generate_cpp_header(model_dump, feat_names, artifact_id, knobs_desc, pool):
    trees = model_dump["tree_info"]
    lines = []
    lines.append(f"// Auto-generated GBDT model — CAT probe retrain on artifact [{artifact_id}]")
    lines.append(f"// Knobs: {knobs_desc}")
    lines.append("// Pool: official SIFT 10K queries (no self-match); labels: official GT min_n (cap 200)")
    lines.append(f"// Features: {', '.join(feat_names)}")
    lines.append(f"// Trees: {len(trees)}, max_depth=4 (LightGBM num_leaves=15, lr=0.1)")
    lines.append("// Per-artifact model (DESIGN §2 P4): MUST NOT be reused on another graph.")
    lines.append("#pragma once")
    lines.append("")
    lines.append("// Feature indices:")
    for i, name in enumerate(feat_names):
        lines.append(f"//   [{i}] {name}")
    lines.append("")
    lines.append("inline float gbdt_predict(const float* feat) {")
    lines.append("    float sum = 0.0f;")
    for ti, tree_info in enumerate(trees):
        tree = tree_info["tree_structure"]
        var = f"t{ti}"
        lines.append(f"    // Tree {ti}")
        lines.append("    {")
        lines.append(f"        float {var} = 0.0f;")
        emit_tree(lines, tree, var, 2)
        lines.append(f"        sum += {var};")
        lines.append("    }")
    lines.append("    return sum;")
    lines.append("}")
    return "\n".join(lines) + "\n"


def sim_recall(model_pred_all, queries, gt, margin):
    """Simulated Recall@10 for GBDT predicted N * margin (clipped to [10,200])."""
    total_found = 0
    total_possible = len(queries) * 10
    avg_n = 0.0
    for i, q in enumerate(queries):
        pred = int(np.ceil(model_pred_all[i] * margin))
        pred = max(10, min(200, pred))
        avg_n += pred
        total_found += find_recall_at_n(q["ids"], gt[i], pred)
    return total_found / total_possible, avg_n / len(queries)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CAT GBDT probe — train step")
    ap.add_argument("--features", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--llsp", required=True, help="PROFILE_LLSP dump (sim recall eval)")
    ap.add_argument("--gt", default="data/sift_groundtruth_official.ivecs")
    ap.add_argument("--model-export", default="", help="CAT_GBDT_MODEL export path")
    ap.add_argument("--artifact-id", default="", help="per-artifact model key")
    ap.add_argument("--knobs", default="", help="knob description for header/trace")
    ap.add_argument("--r0", type=int, default=40)
    ap.add_argument("--beam", type=int, default=64)
    ap.add_argument("--alpha", type=float, default=1.2)
    ap.add_argument("--block", type=int, default=262144)
    ap.add_argument("--pq-m", type=int, default=32)
    ap.add_argument("--floor-ef", type=int, default=70, help="measured ef floor")
    ap.add_argument("--pool", default="official10k", help="profile pool id")
    ap.add_argument("--margins", default=",".join(map(str, DEFAULT_MARGINS)),
                    help="comma-separated sim margin sweep")
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--report", default="", help="optional JSON sim report path")
    args = ap.parse_args(argv)

    artifact_id = args.artifact_id or model_key(
        args.r0, args.beam, args.alpha, args.block, args.pq_m, args.floor_ef, args.pool)
    knobs_desc = args.knobs or (
        f"R0={args.r0} / beam={args.beam} / alpha={args.alpha} / "
        f"block={args.block} / pq_M={args.pq_m} / ef={args.floor_ef} / pool={args.pool}")

    margins = [float(m) for m in args.margins.split(",") if m.strip()]

    features = pd.read_csv(args.features)
    labels = pd.read_csv(args.labels)
    df = features.merge(labels, on="qid")
    df["min_n_capped"] = df["min_n"].clip(upper=200)

    X = df[FEAT_COLS].values
    y = df["min_n_capped"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)
    print(f"[train:{artifact_id}] train={len(X_train)} test={len(X_test)}; "
          f"label min={y.min()} max={y.max()} mean={y.mean():.1f}")

    params = dict(LGB_PARAMS)
    params["n_estimators"] = args.trees
    params["max_depth"] = args.depth
    model = lgb.LGBMRegressor(**params)
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)],
              callbacks=[lgb.log_evaluation(20)])

    mae = mean_absolute_error(y_test, model.predict(X_test))
    print(f"[train:{artifact_id}] MAE={mae:.1f}")

    y_pred_all = model.predict(X)

    queries = parse_llsp_log(args.llsp)
    gt = load_official_gt(args.gt, k=10)
    assert len(queries) == len(y_pred_all) == len(gt), \
        f"length mismatch: {len(queries)} queries vs {len(y_pred_all)} preds vs {len(gt)} GT"

    # skip gate #3: sim margin sweep. Only sim >= floor advances to sustained.
    sim_results = []
    advancing = []
    for margin in margins:
        recall, avg_n = sim_recall(y_pred_all, queries, gt, margin)
        advance = recall >= SIM_FLOOR
        guard = recall >= SIM_GUARD
        if advance:
            advancing.append(margin)
        sim_results.append({
            "margin": margin, "sim_recall": round(recall, 4), "avg_n": round(avg_n, 1),
            "advance": advance, "guard": guard,
        })
        print(f"[train:{artifact_id}] sim margin={margin}: recall={recall:.4f} "
              f"avg_n={avg_n:.1f} advance={advance} guard={guard}")

    dump = model.booster_.dump_model()
    cpp_code = generate_cpp_header(dump, FEAT_COLS, artifact_id, knobs_desc, args.pool)

    export_path = args.model_export or str(
        _HERE.parent / "harness" / f"gbdt_model_{artifact_id}.h")
    Path(export_path).write_text(cpp_code)
    print(f"[train:{artifact_id}] model header -> {export_path} ({len(cpp_code)} bytes)")

    model.booster_.save_model(f"/tmp/cat_{artifact_id}_model.txt")
    print(f"[train:{artifact_id}] LightGBM model -> /tmp/cat_{artifact_id}_model.txt")

    report = {
        "schema": "ndf-poc-gbdt-train/v1",
        "artifact_id": artifact_id,
        "knobs": knobs_desc,
        "model_export": export_path,
        "mae": round(float(mae), 2),
        "trees": args.trees,
        "depth": args.depth,
        "sim_floor": SIM_FLOOR,
        "sim_guard": SIM_GUARD,
        "sim_results": sim_results,
        "advancing_margins": advancing,
        "advance_any": len(advancing) > 0,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(f"[train:{artifact_id}] sim report -> {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
