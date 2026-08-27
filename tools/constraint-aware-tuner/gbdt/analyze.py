#!/usr/bin/env python3
"""
CAT GBDT probe — analyze step: labels + features from per-artifact profiling.

Parameterized collapse of the hop-cloned gbdt/analyze_r5.py / analyze_r8.py
([[BEH-018]] recipe, sibling poc/gbdt-retrain/analyze_r0.py lineage). One module for
every artifact; the artifact is identified by --tag (the per-artifact model key) and
described by --knobs (optional, echoed into the report for traceability).

Input:
  --llsp <path>      PROFILE_LLSP dump (last-10000 [LLSP] lines, timed pass, qid order
                     == official pool order under NUM_THREADS=1)
  --gt <path>        official GT ivecs (10000x100), default data/sift_groundtruth_official.ivecs

Output:
  --features <path>  per-query feature CSV (11 features)
  --labels <path>    per-query label CSV (min_n: smallest candidate prefix covering all 10 GT)
  --report <path>    JSON report with min_n distribution (P25/P50/P75/P90, unreachable)
                     — the P75 min_n feeds skip gate #2 (list headroom) in run_gbdt_probe.sh.

The min_n P75 is the "list headroom" signal: if P75 min_n is stuck at the candidate
list cap (≈ floor_ef), GBDT has no headroom to buy (winner artifact P75=71 ≈ cap);
if P75 is well below the cap (high-recall beam=64 P75=38), the probe may pay off.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

GT_DEFAULT = "data/sift_groundtruth_official.ivecs"

# 11 features shared by every artifact (BEH-010 learned-pruning feature set).
FEAT_FIELDS = [
    "qid", "n_coarse", "d0", "d9", "dk", "dk1", "gap_ratio",
    "d_mean", "d_std", "d_cv", "d_ratio_01", "d_ratio_09",
]

_LLSP_RE = re.compile(
    r'\[LLSP\] qid=(\d+) n=(\d+) d0=([\d.]+) d9=([\d.]+) dk=([\d.]+) dk1=([\d.]+) '
    r'gap=([\d.]+) mean=([\d.]+) std=([\d.]+) ids=(.+)'
)


def parse_llsp_log(path):
    """Parse a PROFILE_LLSP dump into a list of per-query dicts."""
    queries = []
    with open(path) as f:
        for line in f:
            m = _LLSP_RE.match(line.strip())
            if m:
                queries.append({
                    "qid": int(m.group(1)), "n": int(m.group(2)),
                    "d0": float(m.group(3)), "d9": float(m.group(4)),
                    "dk": float(m.group(5)), "dk1": float(m.group(6)),
                    "gap": float(m.group(7)), "mean": float(m.group(8)),
                    "std": float(m.group(9)),
                    "ids": [int(x) for x in m.group(10).split(",")],
                })
    return queries


def load_official_gt(path, k=10):
    """Load official GT ivecs rows (each row = top-k ground-truth labels)."""
    gt = []
    with open(path, "rb") as f:
        while True:
            dim_data = f.read(4)
            if len(dim_data) < 4:
                break
            dim = int(np.frombuffer(dim_data, dtype=np.int32)[0])
            row = np.frombuffer(f.read(dim * 4), dtype=np.int32)
            gt.append(row[:k].tolist())
    return gt


def find_min_n(cand_ids, gt_ids):
    """Smallest prefix of cand_ids covering ALL gt_ids; len+1 if some gt_id absent."""
    max_pos = 0
    for gt_id in gt_ids:
        try:
            pos = cand_ids.index(gt_id)
            max_pos = max(max_pos, pos + 1)
        except ValueError:
            return len(cand_ids) + 1  # unreachable at this ef
    return max_pos


def find_recall_at_n(cand_ids, gt_ids, n):
    found = 0
    for gt_id in gt_ids:
        try:
            if cand_ids.index(gt_id) < n:
                found += 1
        except ValueError:
            pass
    return found


def build_features(queries, gt):
    """Return (features list of dicts, min_n labels list)."""
    features, labels = [], []
    for i, q in enumerate(queries):
        gt_ids = gt[i]
        min_n = find_min_n(q["ids"], gt_ids)
        mean = q["mean"]
        d_ratio_01 = q["d0"] / mean if mean > 0 else 1.0
        d_ratio_09 = q["d9"] / mean if mean > 0 else 1.0
        cv = q["std"] / mean if mean > 0 else 0.0
        features.append({
            "qid": i, "n_coarse": q["n"], "d0": q["d0"], "d9": q["d9"],
            "dk": q["dk"], "dk1": q["dk1"], "gap_ratio": q["gap"],
            "d_mean": mean, "d_std": q["std"], "d_cv": cv,
            "d_ratio_01": d_ratio_01, "d_ratio_09": d_ratio_09,
        })
        labels.append(min_n)
    return features, labels


def min_n_stats(min_ns):
    arr = np.asarray(min_ns, dtype=np.float64)
    pct = {p: float(np.percentile(arr, p)) for p in (10, 25, 50, 75, 90)}
    unreachable = int((arr > 200).sum())
    return {
        "n_queries": int(len(arr)),
        "min": float(arr.min()), "max": float(arr.max()), "mean": float(arr.mean()),
        "p10": pct[10], "p25": pct[25], "p50": pct[50], "p75": pct[75], "p90": pct[90],
        "unreachable_gt200": unreachable,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="CAT GBDT probe — analyze step")
    ap.add_argument("--llsp", required=True, help="PROFILE_LLSP dump path")
    ap.add_argument("--gt", default=GT_DEFAULT, help="official GT ivecs path")
    ap.add_argument("--features", default="/tmp/cat_features.csv")
    ap.add_argument("--labels", default="/tmp/cat_labels.csv")
    ap.add_argument("--tag", default="artifact", help="per-artifact id / model key")
    ap.add_argument("--knobs", default="", help="optional knob description (traceability)")
    ap.add_argument("--report", default="", help="optional JSON report path")
    args = ap.parse_args(argv)

    queries = parse_llsp_log(args.llsp)
    print(f"[analyze:{args.tag}] parsed {len(queries)} queries from {args.llsp}")
    gt = load_official_gt(args.gt, k=10)
    print(f"[analyze:{args.tag}] loaded {len(gt)} GT entries from {args.gt}")
    if len(queries) != len(gt):
        print(f"[analyze:{args.tag}] ERROR: {len(queries)} queries vs {len(gt)} GT — "
              f"qid order mismatch", file=sys.stderr)
        return 2

    features, labels = build_features(queries, gt)
    stats = min_n_stats(labels)

    print(f"[analyze:{args.tag}] min_n: P25={stats['p25']:.0f} P50={stats['p50']:.0f} "
          f"P75={stats['p75']:.0f} P90={stats['p90']:.0f} unreachable>200={stats['unreachable_gt200']}")

    # prefix-cut recall@10 at a few N (for the report / cross-check with sustained)
    recall_by_n = {}
    for n_test in (10, 20, 30, 40, 50, 70, 100):
        tot = sum(find_recall_at_n(q["ids"], gt[i], n_test) for i, q in enumerate(queries))
        recall_by_n[n_test] = tot / (len(queries) * 10)

    with open(args.features, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEAT_FIELDS)
        w.writeheader()
        w.writerows(features)
    with open(args.labels, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qid", "min_n"])
        for i, mn in enumerate(labels):
            w.writerow([i, mn])

    report = {
        "schema": "ndf-poc-gbdt-analyze/v1",
        "tag": args.tag,
        "knobs": args.knobs,
        "min_n": stats,
        "prefix_recall_by_n": {f"N={n}": round(r, 4) for n, r in recall_by_n.items()},
        "features": args.features,
        "labels": args.labels,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(f"[analyze:{args.tag}] report -> {args.report}")

    print(f"[analyze:{args.tag}] features -> {args.features}; labels -> {args.labels}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
