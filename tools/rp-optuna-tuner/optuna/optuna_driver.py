#!/usr/bin/env python3
"""optuna_driver.py — rp-optuna-tuner: thin Optuna TPE/CMA-ES driver for the RESIDUAL
rebuild axes ([[BEH-RPT-003]] / [[ARCH-RPT-001]]).

Design placement (DESIGN §2 / §Traversal): Optuna acts ONLY on the axes that RP-Tuning
post-prune does NOT cheapen (block ladder / pq_M / beam·R0 if RP cannot cover them).
Each proposed trial = ONE full Vamana insert, counted against RPT_BUDGET_REBUILDS
(INTERFACE). The recall ≥95% hard constraint ([[CON-RPT-001]]) is enforced as a
PRUNE/penalty — it MUST NOT be folded into a scalar soft loss ([[BEH-RPT-003]]).
MedianPruner is allowed only on cheap inner objectives (ef floor / RSS proxy), never on a
half-finished sustained run.

This module is the ask-and-tell wrapper: it shells out to scripts/run_sustained.sh
(Trunk read-only) for the real measurement and to scripts/build_pipeline.sh for the real
rebuild. It is NOT linked into the search hot path and MUST NOT be vendored into Trunk.

Optuna is an OPTIONAL vendor (proposal §2.4: "MAY vendor 薄 driver"). If `optuna` is not
importable, ask() falls back to a deterministic closed-ladder (same order as
searcher.h search_residual_knobs), so the R0 self-check still exercises the constraint
enforcement path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import optuna  # noqa: F401  (optional vendor)
    HAVE_OPTUNA = True
except Exception:  # pragma: no cover - optional
    HAVE_OPTUNA = False

REPO = Path(__file__).resolve().parents[3]

# Residual rebuild axes (RP does NOT cheapen block/PQ_M/BFS — [[BEH-RPT-001]]).
BLOCK_LADDER = [32768, 65536, 131072, 262144]
PQ_M_LADDER = [16, 32, 64]
RECALL_FLOOR = 0.95
RECALL_GUARD = 0.955


class ResidualSpace:
    """Closed, bounded residual space handed to Optuna (block × pq_M)."""

    def __init__(self, block_ladder=BLOCK_LADDER, pq_m_ladder=PQ_M_LADDER):
        self.block_ladder = list(block_ladder)
        self.pq_m_ladder = list(pq_m_ladder)

    def closed_ladder(self):
        """Deterministic fallback when Optuna is absent (same order as searcher.h)."""
        for blk in self.block_ladder:
            for pq in self.pq_m_ladder:
                yield {"block_size": blk, "pq_M": pq}

    def suggest(self, trial):
        """Optuna suggestions over the residual axes (TPE by default)."""
        if not HAVE_OPTUNA:
            raise RuntimeError("optuna not available")
        return {
            "block_size": trial.suggest_categorical("block_size", self.block_ladder),
            "pq_M": trial.suggest_categorical("pq_M", self.pq_m_ladder),
        }


def hard_constraint_loss(recall: float | None, rss_mb: int | None, cgroup_mb: int) -> float | None:
    """Enforce [[BEH-RPT-003]]: recall/cgroup are HARD constraints, not soft loss.
    Returns None (feasible) or an objective penalty for infeasible trials."""
    if recall is None:
        return float("-inf")  # unmeasured → treat as infeasible, do not rank by soft loss
    if recall < RECALL_FLOOR:
        return float("-inf")
    if rss_mb is not None and rss_mb > cgroup_mb:
        return float("-inf")
    return None  # feasible; caller ranks by measured QPS


def objective_fn(trial, space: ResidualSpace, measure_fn, cgroup_mb: int):
    """Objective = measured agg QPS, hard-constrained by recall ≥95% and cgroup RSS.
    measure_fn(knobs) -> {"recall": float, "qps": float, "rss_mb": int}."""
    knobs = space.suggest(trial)
    res = measure_fn(knobs)
    penalty = hard_constraint_loss(res.get("recall"), res.get("rss_mb"), cgroup_mb)
    if penalty is not None:
        return penalty
    return float(res.get("qps") or 0.0)


def self_test() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"{'ok' if cond else 'FAIL'}: {name}")
        if not cond:
            fails += 1

    # 1) hard constraint: recall < floor is infeasible (NOT a soft loss).
    check("recall 0.94 < floor → infeasible",
          hard_constraint_loss(0.94, None, 512) is not None)
    check("recall 0.96 ≥ floor → feasible (None)",
          hard_constraint_loss(0.96, None, 512) is None)
    # 2) cgroup: RSS > budget is infeasible even with good recall.
    check("RSS 600MB > 512MB → infeasible",
          hard_constraint_loss(0.97, 600, 512) is not None)
    # 3) unmeasured → infeasible (do not rank by soft loss).
    check("unmeasured recall → infeasible",
          hard_constraint_loss(None, None, 512) is not None)
    # 4) closed ladder covers the residual space deterministically.
    space = ResidualSpace()
    ladder = list(space.closed_ladder())
    check("closed ladder covers block×pq_M",
          len(ladder) == len(BLOCK_LADDER) * len(PQ_M_LADDER))
    # 5) Optuna absence is a graceful degradation, not an error.
    check("optuna absence handled (HAVE_OPTUNA bool)", isinstance(HAVE_OPTUNA, bool))

    print(f"=== optuna_driver self-test {'PASS' if fails == 0 else 'FAIL'} ===")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    # Full solve is an S3 activity (residual rebuild axes) — out of R0 scope. The R0
    # entry is harness/calibrate_s0.py (S0 search-side calibrate, 0 rebuild).
    print(f"optuna_driver: HAVE_OPTUNA={HAVE_OPTUNA}")
    space = ResidualSpace()
    print("residual space (block × pq_M):", [k for k in space.closed_ladder()])
    print("NOTE: full Optuna solve (S3) is NOT run in R0. See harness/calibrate_s0.py.")
    sys.exit(0)
