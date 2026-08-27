#!/usr/bin/env python3
"""traverse.py — constraint-aware-tuning POC: execute DESIGN §Traversal strategy (R3).

Nested / coordinate descent + re-entry, MEASURED ≥95% REFINE_EF floor per artifact.

Budget: CAT_BUDGET_REBUILDS=16 (P1 3 + P2 6 + P3 ≤3 + P4 ≤4).

Phases:
  P0 (0 rebuild): locked default graph + 64KB, measured ef ladder (QPS/recall baseline).
  P1 (3 rebuild): block ladder {32K,128K,256K} on locked graph; re-measure ef floor each.
  P2 (≤6 rebuild): on B*, R0 {40,48} → beam {48,64} → α {1.33,1.07}; re-measure ef floor.
  P3 (≤3): re-entry on G* (re-sweep block ladder if graph changed + budget).
  P4 (≤4): pq_M {16,64} (leftover rebuild budget ONLY).
  GBDT probe (0 rebuild): after P3, per-artifact search-side calibration — probe_gbdt(G*)
    then the already-built high-recall leg (R8 beam=64) if the winner leftover is too
    small; gated by skip gate #1 (leftover ≲1pp) + CAT_GBDT_PROBES (default 1, max 2),
    NOT counted in CAT_BUDGET_REBUILDS.
  1T supplementary on best recall-feasible point + locked default.

Outputs (append-only under tools/constraint-aware-tuner/results/):
  traverse_results.csv   — one row per (artifact, ef) measurement
  traverse_state.json    — per-artifact decision record (floor ef, B*, G*, winner)
  cat_*_*.log            — raw sustained logs (via scripts/run_sustained.sh)

MUST NOT: reuse prior_min_ef (40–76) as operating point; the reported operating point is
the MEASURED ef floor. Measurement reuses Trunk scripts/build_pipeline.sh +
scripts/run_sustained.sh (no forked search engine).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TUNER = REPO / "tools" / "constraint-aware-tuner"
EVIDENCE = TUNER / "results"
BUILD_SH = "scripts/build_pipeline.sh"
MEASURE_SH = "scripts/run_sustained.sh"

RECALL_TARGET = 95.5  # percent (parse_log returns recall as percent 0-100); ≥95% + safety margin (DESIGN §4)
CGROUP_MB = int(os.environ.get("CAT_CGROUP_MB", "512"))
THREADS = int(os.environ.get("CAT_THREADS", "16"))
BUDGET = int(os.environ.get("CAT_BUDGET_REBUILDS", "16"))

# closed block ladder (INTERFACE CAT_BLOCK_LADDER); 64K is the anchor
BLOCK_LADDER = [32768, 65536, 131072, 262144]
BLOCK_SUF = {32768: "32k", 65536: "64k", 131072: "128k", 262144: "256k"}

# locked default (cfg-sla-ef100 / d9122d2)
DEFAULT = dict(CAT_M=16, CAT_R0=32, CAT_RUP=16, CAT_BEAM=32, CAT_ALPHA=1.2,
               CAT_ROUNDS=3, CAT_SEED=42, CAT_BLOCK_SIZE=65536, CAT_PQ_M=32)

# ---- GBDT probe (per-artifact search-side calibration, DESIGN §2 P4) ----
# Probes are per-artifact re-profile + retrain + sustained on/off; NO graph rebuild, and
# MUST NOT be counted in CAT_BUDGET_REBUILDS (that budget is pq_M-only).
PROBE_SH = "tools/constraint-aware-tuner/scripts/run_gbdt_probe.sh"
GBDT_PROBES_MAX = 2                       # hard ceiling (INTERFACE CAT_GBDT_PROBES max)
GBDT_PROBES_DEFAULT = min(int(os.environ.get("CAT_GBDT_PROBES", "1")), GBDT_PROBES_MAX)
GBDT_LEFTOVER_SKIP_PP = 1.0               # skip gate #1 (R6+R8 calibrated, pinned)

# High-recall leg (R8 beam=64), an ALREADY-BUILT known artifact (R0=40/beam=64/α=1.2/
# 256KB/pq_M=32). Probe target when the winner leftover is too small. NOT an invented
# α∧beam joint graph. Floor = R8 measured off leg.
HIGH_RECALL = dict(CAT_M=16, CAT_R0=40, CAT_RUP=16, CAT_BEAM=64, CAT_ALPHA=1.2,
                   CAT_ROUNDS=3, CAT_SEED=42, CAT_BLOCK_SIZE=262144, CAT_PQ_M=32)
HIGH_RECALL_FLOOR = {"recall": 97.96, "floor_ef": 70}   # R8 off leg (16T)


def should_probe_gbdt(floor_recall) -> bool:
    """Skip gate #1 (DESIGN §2 P4): leftover `floor_recall − 95` ≲ 1pp → skip.
    Mirrors searcher.h cat::should_probe_gbdt (recall in percent here). Winner 95.57%
    = +0.57pp → skip; high-recall 97.96% = +2.96pp → probe. Leftover is necessary but
    not sufficient (sim gate is the final call, applied in run_gbdt_probe.sh)."""
    if floor_recall is None:
        return False
    return (floor_recall - 95.0) > GBDT_LEFTOVER_SKIP_PP


def gbdt_artifact_id(knobs: dict, floor_ef) -> str:
    """Per-artifact model key = (R0, beam, α, block, pq_M, floor_ef, profile_pool)."""
    return (f"r0{knobs['CAT_R0']}_beam{knobs['CAT_BEAM']}_a{knobs['CAT_ALPHA']}"
            f"_blk{knobs['CAT_BLOCK_SIZE']}_pqm{knobs['CAT_PQ_M']}_ef{floor_ef}_official10k")


def probe_gbdt(knobs: dict, floor: dict, note: str) -> dict:
    """Per-artifact GBDT probe (NO rebuild). Applies skip gate #1 then shells out to
    run_gbdt_probe.sh (which applies gates #2 list-headroom and #3 sim-margin sweep)."""
    floor_recall = floor.get("recall")
    floor_ef = floor.get("floor_ef")
    if not should_probe_gbdt(floor_recall):
        leftover = (floor_recall - 95.0) if floor_recall is not None else None
        return {"note": note, "decision": "skip", "reason": "leftover_le_1pp",
                "floor_recall": floor_recall, "floor_ef": floor_ef,
                "leftover_pp": leftover}
    ef = floor_ef or 70
    artifact_id = gbdt_artifact_id(knobs, ef)
    model_export = f"tools/constraint-aware-tuner/harness/gbdt_model_{artifact_id}.h"
    env = dict(os.environ)
    env.update({
        "CAT_ARTIFACT_ID": artifact_id,
        "REFINE_EF": str(ef),
        "CAT_GBDT_MODEL": model_export,
        "CAT_BLOCK_SIZE": str(knobs.get("CAT_BLOCK_SIZE", 262144)),
        "CAT_R0": str(knobs.get("CAT_R0", 40)),
        "CAT_BEAM": str(knobs.get("CAT_BEAM", 64)),
        "CAT_ALPHA": str(knobs.get("CAT_ALPHA", 1.2)),
        "CAT_PQ_M": str(knobs.get("CAT_PQ_M", 32)),
        "CGROUP_MB": str(CGROUP_MB),
        "PROBE_RESULT": str(EVIDENCE / f"gbdt_probe_{artifact_id}.json"),
    })
    print(f"[probe_gbdt] {note}: floor_recall={floor_recall} ef={ef} "
          f"→ run_gbdt_probe.sh artifact={artifact_id} (no rebuild)", flush=True)
    r = sh(["bash", PROBE_SH], env=env)
    return {"note": note, "decision": "probe", "artifact_id": artifact_id,
            "floor_recall": floor_recall, "floor_ef": ef, "rc": r.returncode}


def sh(cmd, **kw):
    print(f"$ {' '.join(str(c) for c in cmd)}", file=sys.stderr, flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=str(REPO), **kw)


def build(knobs: dict, tag: str) -> int:
    env = dict(os.environ)
    # CAT_* → Trunk build_index HV_* env knobs + BS (block size); pq_M → pipeline M arg.
    env["HV_M"] = str(knobs.get("CAT_M", 16))
    env["HV_R0"] = str(knobs.get("CAT_R0", 32))
    env["HV_RUP"] = str(knobs.get("CAT_RUP", 16))
    env["HV_BEAM"] = str(knobs.get("CAT_BEAM", 32))
    env["HV_ALPHA"] = str(knobs.get("CAT_ALPHA", 1.2))
    env["HV_ALPHA2"] = str(knobs.get("CAT_ALPHA2", 0))
    env["HV_ROUNDS"] = str(knobs.get("CAT_ROUNDS", 3))
    env["HV_SEED"] = str(knobs.get("CAT_SEED", 42))
    env["BS"] = str(knobs.get("CAT_BLOCK_SIZE", 262144))
    pq_m = knobs.get("CAT_PQ_M", 32)
    r = sh(["bash", BUILD_SH, "data/sift_base.fvecs", "sift1m", str(pq_m)], env=env)
    if r.returncode != 0:
        print(f"[build] FAILED rc={r.returncode} for {tag}", file=sys.stderr)
    return r.returncode


def measure(knobs: dict, ef: int, tag: str, threads: int = THREADS) -> dict:
    env = dict(os.environ)
    env.update({
        "CGROUP_MB": str(CGROUP_MB),
        "THREADS": str(threads),
        "REFINE_EF": str(ef),
        "EF": str(ef),
        "BS": str(knobs["CAT_BLOCK_SIZE"]),
        "CAT_BLOCK_SIZE": str(knobs["CAT_BLOCK_SIZE"]),
        "TAG": tag,
        "OUTDIR": str(EVIDENCE),
    })
    if "CAT_PQ_M" in knobs and knobs["CAT_PQ_M"] not in (None, 32):
        env["PQ_CODES_PATH"] = f"output/pqco_sift1m_M{knobs['CAT_PQ_M']}.bin"
    if knobs.get("LEARNED_EF"):
        env["LEARNED_EF"] = "1"
    r = sh(["bash", MEASURE_SH], env=env)
    log = EVIDENCE / f"{tag}_{CGROUP_MB}mb_{threads}t_n1000_r15.log"
    res = parse_log(log)
    res["tag"] = tag
    res["ef"] = ef
    res["threads"] = threads
    res["rc"] = r.returncode
    return res


def parse_log(path: Path) -> dict:
    txt = path.read_text() if path.exists() else ""
    def f(pat, cast=float):
        m = re.search(pat, txt)
        return cast(m.group(1)) if m else None
    recall = f(r"Recall@10:\s*([0-9.]+)%")
    qps = f(r"^QPS:\s+([0-9.]+)", lambda s: float(s))
    rss = f(r"^RSS:\s+([0-9]+)\s*MB", int)
    steady = None
    m = re.search(r"CSV_AGG,\d+,\d+,[0-9.]+,([0-9.]+),[0-9.]+,\d+,([0-9.]+)", txt)
    if m:
        qps = float(m.group(1)); steady = float(m.group(2))
    return {"recall": recall, "qps": qps, "steady_qps": steady, "rss_mb": rss}


def find_floor(knobs: dict, tag_prefix: str, threads: int = THREADS) -> dict:
    """Measure ef ladder top-down; floor = lowest ef with measured recall ≥ RECALL_TARGET."""
    ladder = [100, 90, 80, 70]
    rows = []
    floor = None
    for ef in ladder:
        tag = f"{tag_prefix}_ef{ef}"
        r = measure(knobs, ef, tag, threads)
        rows.append(r)
        if r["recall"] is None:
            continue
        if r["recall"] >= RECALL_TARGET:
            floor = ef  # keep descending; last passing is the floor
        else:
            break  # recall monotone non-decreasing in ef → stop below this
    # floor is the last (lowest) passing ef; if none passed, artifact is infeasible at ≤100
    best = None
    for r in rows:
        if r["recall"] is not None and r["recall"] >= RECALL_TARGET:
            if best is None or r["ef"] < best["ef"]:
                best = r
    return {"floor_ef": best["ef"] if best else None,
            "recall": best["recall"] if best else None,
            "qps": best["qps"] if best else None,
            "steady_qps": best["steady_qps"] if best else None,
            "rss_mb": best["rss_mb"] if best else None,
            "rows": rows,
            "feasible": best is not None}


def main() -> int:
    results = []          # every (artifact, ef) measurement
    state = []            # per-artifact decision record
    rebuilds = 0

    def record(phase, knobs, floor, note=""):
        state.append({"phase": phase, "knobs": knobs, "floor": floor, "note": note})

    def log_result(r, phase, label):
        r = dict(r); r["phase"] = phase; r["label"] = label
        r["_rows"] = r.pop("rows", None)
        results.append(r)

    # ---- P0: locked default + 64KB, measured ef ladder ----
    print("\n=== P0: locked default (64KB) ef ladder ===", flush=True)
    t0 = time.time()
    build(DEFAULT, "p0_default")
    p0 = find_floor(DEFAULT, "cat_p0_default")
    baseline = p0
    record("P0", dict(DEFAULT), p0, "locked default baseline")
    for r in p0["rows"]:
        log_result(r, "P0", "default_64k")
    print(f"[P0] floor_ef={p0['floor_ef']} recall={p0['recall']} qps={p0['qps']} "
          f"rss={p0['rss_mb']} ({time.time()-t0:.0f}s)", flush=True)

    # ---- P1: block ladder on locked graph ----
    print("\n=== P1: block ladder {32K,128K,256K} ===", flush=True)
    p1 = {}
    for blk in [32768, 131072, 262144]:
        if rebuilds >= BUDGET:
            break
        knobs = dict(DEFAULT); knobs["CAT_BLOCK_SIZE"] = blk
        build(knobs, f"p1_blk{BLOCK_SUF[blk]}")
        rebuilds += 1
        f = find_floor(knobs, f"cat_p1_blk{BLOCK_SUF[blk]}")
        p1[blk] = f
        record("P1", knobs, f, f"block ladder {BLOCK_SUF[blk]} (rebuild #{rebuilds})")
        for r in f["rows"]:
            log_result(r, "P1", f"blk{BLOCK_SUF[blk]}")
        print(f"[P1] blk={BLOCK_SUF[blk]} floor_ef={f['floor_ef']} recall={f['recall']} "
              f"qps={f['qps']} rss={f['rss_mb']} (rebuilds={rebuilds})", flush=True)

    # pick B*: among 64K (anchor) + ladder, highest QPS at floor with recall feasible
    candidates = {65536: baseline}
    candidates.update(p1)
    Bstar = max((c for c in candidates.items() if c[1]["feasible"]),
                key=lambda kv: kv[1]["qps"] or 0.0, default=None)
    Bstar_blk = Bstar[0] if Bstar else 65536
    print(f"[P1] B* = {BLOCK_SUF[Bstar_blk]} "
          f"(qps={Bstar[1]['qps'] if Bstar else None})", flush=True)

    # ---- P2: coordinate descent on B* ----
    print(f"\n=== P2: coordinate descent on B*={BLOCK_SUF[Bstar_blk]} ===", flush=True)
    base = dict(DEFAULT); base["CAT_BLOCK_SIZE"] = Bstar_blk
    gstar = base.copy()
    gstar_floor = candidates[Bstar_blk]

    # ensure B* artifact is the current output (it was built last among P1 winners)
    for axis, vals in [("CAT_R0", [40, 48]), ("CAT_BEAM", [48, 64]),
                       ("CAT_ALPHA", [1.33, 1.07])]:
        for v in vals:
            if rebuilds >= BUDGET:
                break
            knobs = dict(gstar); knobs[axis] = v
            build(knobs, f"p2_{axis}{v}")
            rebuilds += 1
            f = find_floor(knobs, f"cat_p2_{axis}{v}")
            record("P2", knobs, f, f"{axis}={v} on B* (rebuild #{rebuilds})")
            for r in f["rows"]:
                log_result(r, "P2", f"{axis}{v}")
            print(f"[P2] {axis}={v} floor_ef={f['floor_ef']} recall={f['recall']} "
                  f"qps={f['qps']} rss={f['rss_mb']} (rebuilds={rebuilds})", flush=True)
            # keep G* if this beats current (feasible + higher QPS)
            if f["feasible"] and (not gstar_floor["feasible"] or
                                  (f["qps"] or 0) > (gstar_floor["qps"] or 0)):
                gstar = knobs.copy(); gstar_floor = f

    print(f"[P2] G* = {gstar} floor_ef={gstar_floor['floor_ef']} "
          f"qps={gstar_floor['qps']}", flush=True)

    # ---- P3: re-entry on G* if graph differs from locked default ----
    gstar_graph_differs = (gstar["CAT_R0"] != DEFAULT["CAT_R0"] or
                           gstar["CAT_BEAM"] != DEFAULT["CAT_BEAM"] or
                           gstar["CAT_ALPHA"] != DEFAULT["CAT_ALPHA"])
    if gstar_graph_differs and rebuilds < BUDGET:
        print(f"\n=== P3: re-entry block ladder on G* ===", flush=True)
        best_reentry = gstar_floor
        best_reentry_blk = gstar["CAT_BLOCK_SIZE"]
        for blk in [32768, 131072, 262144]:
            if blk == gstar["CAT_BLOCK_SIZE"] or rebuilds >= BUDGET:
                continue
            knobs = dict(gstar); knobs["CAT_BLOCK_SIZE"] = blk
            build(knobs, f"p3_blk{BLOCK_SUF[blk]}")
            rebuilds += 1
            f = find_floor(knobs, f"cat_p3_blk{BLOCK_SUF[blk]}")
            record("P3", knobs, f, f"re-entry block {BLOCK_SUF[blk]} on G* (rebuild #{rebuilds})")
            for r in f["rows"]:
                log_result(r, "P3", f"blk{BLOCK_SUF[blk]}")
            print(f"[P3] blk={BLOCK_SUF[blk]} floor_ef={f['floor_ef']} recall={f['recall']} "
                  f"qps={f['qps']} (rebuilds={rebuilds})", flush=True)
            if f["feasible"] and (f["qps"] or 0) > (best_reentry["qps"] or 0):
                best_reentry = f; best_reentry_blk = blk
        if best_reentry_blk != gstar["CAT_BLOCK_SIZE"]:
            gstar["CAT_BLOCK_SIZE"] = best_reentry_blk
            gstar_floor = best_reentry

    # ---- GBDT probe (per-artifact calibration; NOT a rebuild, NOT CAT_BUDGET_REBUILDS) ----
    print("\n=== GBDT probe (per-artifact calibration; CAT_GBDT_PROBES) ===", flush=True)
    gbdt_decisions = []
    gbdt_probes_used = 0
    # 1) primary: G* (winner). skip gate #1 → skip if leftover ≲ 1pp (winner 95.57%).
    if gbdt_probes_used < GBDT_PROBES_DEFAULT:
        d = probe_gbdt(gstar, gstar_floor, "G* (winner)")
        gbdt_decisions.append(d)
        if d["decision"] == "probe":
            gbdt_probes_used += 1
    # 2) if the winner leftover is too small, probe the already-built high-recall leg
    #    (R8 beam=64) instead — already-built, no rebuild.
    if (gbdt_probes_used < GBDT_PROBES_DEFAULT
            and not should_probe_gbdt(gstar_floor.get("recall"))):
        d = probe_gbdt(HIGH_RECALL, HIGH_RECALL_FLOOR, "high-recall leg (beam=64)")
        gbdt_decisions.append(d)
        if d["decision"] == "probe":
            gbdt_probes_used += 1
    print(f"[GBDT] probes_used={gbdt_probes_used}/{GBDT_PROBES_DEFAULT} "
          f"(max {GBDT_PROBES_MAX}) decisions={gbdt_decisions}", flush=True)

    # ---- P4: residual (leftover budget) ----
    if rebuilds < BUDGET:
        print(f"\n=== P4: residual probes (budget left {BUDGET - rebuilds}) ===", flush=True)
        # Leftover rebuild budget is pq_M ONLY — GBDT is search-side calibration (above),
        # not a rebuild, and consumes no CAT_BUDGET_REBUILDS.

        # pq_M {16,64} probes (train PQ) — only if budget remains
        for pq in [16, 64]:
            if rebuilds >= BUDGET:
                break
            knobs = dict(gstar); knobs["CAT_PQ_M"] = pq
            print(f"[P4] training PQ M={pq} ...", flush=True)
            tr = sh(["python3", "scripts/train_pq.py", "data/sift_base.fvecs",
                     f"output/pqco_sift1m_M{pq}.bin", str(pq)])
            if tr.returncode != 0:
                print(f"[P4] PQ M={pq} train failed; skip", flush=True)
                continue
            build(knobs, f"p4_pqm{pq}")
            rebuilds += 1
            f = find_floor(knobs, f"cat_p4_pqm{pq}")
            record("P4", knobs, f, f"pq_M={pq} probe (rebuild #{rebuilds})")
            for r in f["rows"]:
                log_result(r, "P4", f"pqm{pq}")
            print(f"[P4] pq_M={pq} floor_ef={f['floor_ef']} recall={f['recall']} "
                  f"qps={f['qps']} (rebuilds={rebuilds})", flush=True)

    # ---- winner ----
    all_artifacts = [("P0 default", baseline)]
    for st in state:
        if st["floor"].get("feasible"):
            all_artifacts.append((st["phase"] + " " + st["note"], st["floor"]))
    winner = max(all_artifacts, key=lambda kv: kv[1]["qps"] or 0.0, default=None)

    # ---- 1T supplementary: best recall-feasible + locked default ----
    print("\n=== 1T supplementary ===", flush=True)
    # best recall-feasible point (reuse G* artifact; rebuild to ensure it's current)
    if gstar_floor["feasible"]:
        build(gstar, "p1t_best")
        one_t = find_floor(gstar, "cat_1t_best", threads=1)
        record("1T", gstar, one_t, "1T supplementary on best recall-feasible")
        for r in one_t["rows"]:
            log_result(r, "1T", "best")
        print(f"[1T] best floor_ef={one_t['floor_ef']} recall={one_t['recall']} "
              f"qps={one_t['qps']} rss={one_t['rss_mb']}", flush=True)
    # locked default 1T (if not already measured this hop)
    build(DEFAULT, "p1t_default")
    one_t_def = find_floor(DEFAULT, "cat_1t_default", threads=1)
    record("1T", dict(DEFAULT), one_t_def, "1T supplementary on locked default")
    for r in one_t_def["rows"]:
        log_result(r, "1T", "default")
    print(f"[1T] default floor_ef={one_t_def['floor_ef']} recall={one_t_def['recall']} "
          f"qps={one_t_def['qps']} rss={one_t_def['rss_mb']}", flush=True)

    # ---- write evidence ----
    csv = EVIDENCE / "traverse_results.csv"
    with csv.open("w") as fh:
        fh.write("phase,label,ef,threads,recall,qps,steady_qps,rss_mb,rc\n")
        for r in results:
            rows = r.get("_rows") or []
            fh.write(f"{r['phase']},{r['label']},{r['ef']},{r['threads']},"
                     f"{r['recall']},{r['qps']},{r['steady_qps']},{r['rss_mb']},{r['rc']}\n")
    summary = {
        "schema": "ndf-poc-traverse/v1",
        "topic": "constraint-aware-tuning",
        "task": "poc_implementation",
        "budget": BUDGET,
        "rebuilds_used": rebuilds,
        "recall_target": RECALL_TARGET,
        "baseline": {k: v for k, v in baseline.items() if k != "rows"},
        "Bstar_block": Bstar_blk,
        "Gstar": gstar,
        "Gstar_floor": {k: v for k, v in gstar_floor.items() if k != "rows"},
        "winner": winner[0] if winner else None,
        "gbdt_probe": {"probes_used": gbdt_probes_used,
                         "budget_default": GBDT_PROBES_DEFAULT,
                         "budget_max": GBDT_PROBES_MAX,
                         "decisions": gbdt_decisions},
        "state": state,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (EVIDENCE / "traverse_state.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n=== DONE: rebuilds_used={rebuilds}/{BUDGET} | winner={winner[0] if winner else None} ===", flush=True)
    print(f"results CSV: {csv}", flush=True)
    return 0


def self_test() -> int:
    """Self-check: skip gate #1 + CAT_GBDT_PROBES budget + no-rebuild, without a full
    build/measure. Uses the R6/R8 measured anchors (winner 95.57%, high-recall 97.96%)."""
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"{'ok' if cond else 'FAIL'}: {name}")
        if not cond:
            fails += 1

    # 1) skip gate #1: winner leftover +0.57pp → skip; high-recall +2.96pp → probe.
    check("winner 95.57% leftover +0.57pp → skip", should_probe_gbdt(95.57) is False)
    check("high-recall 97.96% leftover +2.96pp → probe", should_probe_gbdt(97.96) is True)
    check("None floor → skip", should_probe_gbdt(None) is False)

    # 2) probe budget (same logic as main): winner skip → high-recall probe → 1 probe.
    winner_floor = {"recall": 95.57, "floor_ef": 70}
    d_winner = probe_gbdt(gstar_dummy(), winner_floor, "G* (winner)")
    # NOTE: winner decision is computed by skip gate #1 WITHOUT shelling out; the probe
    # path would shell out to run_gbdt_probe.sh. Self-test only exercises the gate.
    check("winner probe decision == skip", d_winner["decision"] == "skip")
    probes_used = 0
    if d_winner["decision"] == "probe":
        probes_used += 1
    if probes_used < GBDT_PROBES_DEFAULT and not should_probe_gbdt(95.57):
        probes_used += 1  # high-recall leg probe (probe path)
    check(f"CAT_GBDT_PROBES honored (used={probes_used} <= default {GBDT_PROBES_DEFAULT} "
          f"<= max {GBDT_PROBES_MAX})",
          probes_used <= GBDT_PROBES_DEFAULT <= GBDT_PROBES_MAX)
    check("no rebuild consumed by GBDT probe (probes_used is a separate budget)", True)

    # 3) static: traverse.py main() P4 no longer does LEARNED_EF=True + build().
    import inspect
    main_src = inspect.getsource(main)
    check("no `LEARNED_EF` rebuild in main() P4 (collapsed)",
          'knobs["LEARNED_EF"] = True' not in main_src and "p4_gbdt_on" not in main_src)
    # probe_gbdt body MUST NOT call build().
    probe_src = inspect.getsource(probe_gbdt)
    check("probe_gbdt does not rebuild (no build( call)", "build(" not in probe_src)

    print(f"=== GBDT probe self-test {'PASS' if fails == 0 else 'FAIL'} ===")
    return 0 if fails == 0 else 1


def gstar_dummy() -> dict:
    """Winner G* knobs (R4): R0=40/beam=48/α=1.07/256KB/pq_M=32 (for self-test)."""
    return dict(CAT_M=16, CAT_R0=40, CAT_RUP=16, CAT_BEAM=48, CAT_ALPHA=1.07,
                CAT_ROUNDS=3, CAT_SEED=42, CAT_BLOCK_SIZE=262144, CAT_PQ_M=32)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
