#!/usr/bin/env python3
"""calibrate_s0.py — rp-optuna-tuner R0 driver: DESIGN §2 S0 search-side calibrate
([[BEH-RPT-002]] / [[ARCH-RPT-001]]).

S0 is the 0-rebuild "search-first" slice on the FIXED default graph
(M=16 R0=40 Rup=16 beam=64 α=1.2 rounds=3 seed=42, block=256KB, pq_M=64):
  1. MEASURE the ≥95% REFINE_EF floor on the winner artifact (LEARNED_EF=0 search
     default), top-down over {100, 90, 80, 70}, 16T primary + 1T supplementary.
  2. Per-artifact GBDT retrain (profile → analyze → train → sim margin sweep →
     sustained on/off) via scripts/run_gbdt_probe.sh. Frozen include/gbdt_model.h on/off
     is FORBIDDEN — the on-leg uses harness-bin/benchmark_sustained_poc rebuilt against
     the freshly retrained harness/gbdt_model_active.h.

This reproduces the golden anchor `bl-trunk-<new-sha>` (96.18% / agg QPS 16906.8,
LEARNED_EF=1 GBDT_MARGIN=1.3) and is the "is-this-better-than-golden" reference for all
later hops (S1–S3). It does NOT start S1–S3 (no base rebuild, no α₂ ladder, no Optuna).

Modes:
  --self-check   validate skip gates + paths + binary presence; NO measurement.
  --ef-floor     measure the ef floor only (16T + 1T), LEARNED_EF=0.
  --gbdt         run the per-artifact GBDT probe only.
  (default)      ef floor + GBDT probe (full S0).

Outputs (append-only under tools/rp-optuna-tuner/evidence/):
  s0_ef_floor.csv / s0_state.json / rpt_*_*.log (sustained) / gbdt_probe_*.json
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
TUNER = REPO / "tools" / "rp-optuna-tuner"
EVIDENCE = TUNER / "evidence"
MEASURE_SH = "scripts/run_sustained.sh"
PROBE_SH = "tools/rp-optuna-tuner/scripts/run_gbdt_probe.sh"

CGROUP_MB = int(os.environ.get("RPT_CGROUP_MB", "512"))
THREADS = int(os.environ.get("RPT_THREADS", "16"))
RECALL_TARGET = 95.5  # percent (parse_log returns recall as percent); ≥95% + guard
EF_LADDER = [80, 70, 60, 50, 40]

# Default graph (rp-optuna-tuner S3 winner [[DEC-005]] amends [[DEC-004]]).
WINNER = dict(R0=40, BEAM=64, ALPHA=1.2, BLOCK_SIZE=262144, PQ_M=64)


def sh(cmd, **kw):
    print(f"$ {' '.join(str(c) for c in cmd)}", file=sys.stderr, flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=str(REPO), **kw)


def parse_log(path: Path) -> dict:
    txt = path.read_text() if path.exists() else ""

    def f(pat, cast=float):
        m = re.search(pat, txt)
        return cast(m.group(1)) if m else None

    recall = f(r"Recall@10:\s*([0-9.]+)%")
    qps = f(r"^QPS:\s+([0-9.]+)", lambda s: float(s))
    steady = None
    m = re.search(r"CSV_AGG,\d+,\d+,[0-9.]+,([0-9.]+),[0-9.]+,\d+,([0-9.]+)", txt)
    if m:
        qps = float(m.group(1)); steady = float(m.group(2))
    rss = f(r"^RSS:\s+([0-9]+)\s*MB", int)
    return {"recall": recall, "qps": qps, "steady_qps": steady, "rss_mb": rss}


def measure(ef: int, threads: int, tag: str, learned_ef: int = 0,
            margin: float = 1.3, poc_bin: bool = False) -> dict:
    env = dict(os.environ)
    env.update({
        "CGROUP_MB": str(CGROUP_MB),
        "THREADS": str(threads),
        "EF": str(ef),
        "REFINE_EF": str(ef),
        "BS": str(WINNER["BLOCK_SIZE"]),
        "TAG": tag,
        "OUTDIR": str(EVIDENCE),
    })
    # Search-side knobs MUST be carried into the sudo cgroup script via EXTRA (the inner
    # bash -c only exports what the script emits; raw LEARNED_EF env does not reach the
    # benchmark binary). --config cfg-sla-ef100 is required: it sets CONFIG_VECBLOCKS_PATH
    # non-empty, avoiding a run_sustained.sh empty-expansion bug in its inner bash -c
    # ([[ -n "" ]] -> syntax error) when run without a config.
    if learned_ef:
        env["EXTRA"] = f"export LEARNED_EF=1 GBDT_MARGIN={margin}"
    else:
        env["EXTRA"] = "export LEARNED_EF=0"
    if poc_bin:
        env["BIN"] = "tools/rp-optuna-tuner/harness-bin/benchmark_sustained_poc"
    r = sh(["bash", MEASURE_SH, "--config", "cfg-sla-ef100"], env=env)
    log = EVIDENCE / f"{tag}_{CGROUP_MB}mb_{threads}t_n1000_r15.log"
    res = parse_log(log)
    res["tag"] = tag
    res["ef"] = ef
    res["threads"] = threads
    res["learned_ef"] = learned_ef
    res["rc"] = r.returncode
    return res


def find_ef_floor(tag_prefix: str, threads: int = THREADS) -> dict:
    """Top-down ef ladder on the winner artifact (LEARNED_EF=0); floor = lowest ef with
    measured recall ≥ RECALL_TARGET. Recall is monotone non-decreasing in ef."""
    rows = []
    floor = None
    for ef in EF_LADDER:
        r = measure(ef, threads, f"{tag_prefix}_ef{ef}")
        rows.append(r)
        if r["recall"] is None:
            continue
        if r["recall"] >= RECALL_TARGET:
            floor = r  # keep descending; last passing is the floor
        else:
            break  # below the floor → stop (monotone)
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


def gbdt_artifact_id(floor_ef) -> str:
    return (f"r0{WINNER['R0']}_beam{WINNER['BEAM']}_a{WINNER['ALPHA']}"
            f"_blk{WINNER['BLOCK_SIZE']}_pqm{WINNER['PQ_M']}_ef{floor_ef}_official10k")


def probe_gbdt(floor_ef: int, floor_recall) -> dict:
    artifact_id = gbdt_artifact_id(floor_ef)
    model_export = f"tools/rp-optuna-tuner/harness/gbdt_model_{artifact_id}.h"
    env = dict(os.environ)
    env.update({
        "RPT_ARTIFACT_ID": artifact_id,
        "REFINE_EF": str(floor_ef),
        "RPT_GBDT_MODEL": model_export,
        "RPT_BLOCK_SIZE": str(WINNER["BLOCK_SIZE"]),
        "RPT_R0": str(WINNER["R0"]),
        "RPT_BEAM": str(WINNER["BEAM"]),
        "RPT_ALPHA": str(WINNER["ALPHA"]),
        "RPT_PQ_M": str(WINNER["PQ_M"]),
        "CGROUP_MB": str(CGROUP_MB),
        "PROBE_RESULT": str(EVIDENCE / f"gbdt_probe_{artifact_id}.json"),
    })
    r = sh(["bash", PROBE_SH], env=env)
    return {"decision": "probe", "artifact_id": artifact_id,
            "floor_recall": floor_recall, "floor_ef": floor_ef, "rc": r.returncode}


def self_check() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"{'ok' if cond else 'FAIL'}: {name}")
        if not cond:
            fails += 1

    # skip gate #1 (pinned R6/R8 anchors)
    check("winner 95.57% leftover +0.57pp → skip",
          not (95.57 - 95.0) > 1.0)
    check("high-recall 97.96% leftover +2.96pp → probe",
          (97.96 - 95.0) > 1.0)
    # artifacts present (winner, 256KB block)
    for f in ["output/sift1m_graph.bin", "output/sift1m_bfs.bin",
              "output/sift1m_blocks_256k.bin", "output/sift1m_route_256k.bin",
              "output/sift1m_vecblocks_256k.bin", "output/pqco_sift1m_M64.bin"]:
        check(f"artifact {f} present", (REPO / f).exists())
    # binaries
    check("Trunk benchmark_sustained present", (REPO / "build" / "benchmark_sustained").exists())
    check("profile binary benchmark_llsp present",
          (TUNER / "harness-bin" / "benchmark_llsp").exists())
    # python deps for GBDT retrain
    try:
        import lightgbm  # noqa: F401
        check("lightgbm importable", True)
    except Exception:
        check("lightgbm importable", False)
    # frozen-model guard: on-leg MUST NOT use Trunk include/gbdt_model.h
    check("probe SH uses benchmark_sustained_poc (not Trunk build/)",
          "benchmark_sustained_poc" in (TUNER / "scripts" / "run_gbdt_probe.sh").read_text())

    print(f"=== calibrate_s0 self-check {'PASS' if fails == 0 else 'FAIL'} ===")
    return 0 if fails == 0 else 1


def main() -> int:
    mode = "all"
    args = sys.argv[1:]
    if "--self-check" in args:
        return self_check()
    if "--ef-floor" in args:
        mode = "ef"
    if "--gbdt" in args:
        mode = "gbdt"

    state = {"schema": "ndf-poc-s0-calibrate/v1",
             "topic": "rp-optuna-tuner", "task": "poc_implementation",
             "winner": WINNER, "cgroup_mb": CGROUP_MB, "threads": THREADS,
             "recall_target": RECALL_TARGET}

    floor = None
    if mode in ("ef", "all"):
        print("\n=== S0a: ef floor on winner artifact (LEARNED_EF=0, 16T) ===", flush=True)
        t0 = time.time()
        floor = find_ef_floor("rpt_s0_winner")
        print(f"[S0a] floor_ef={floor['floor_ef']} recall={floor['recall']} "
              f"qps={floor['qps']} rss={floor['rss_mb']} ({time.time()-t0:.0f}s)", flush=True)
        state["ef_floor_16t"] = {k: v for k, v in floor.items() if k != "rows"}

        # 1T supplementary on the floor ef + one step above
        print("\n=== S0a': 1T supplementary (LEARNED_EF=0) ===", flush=True)
        fe = floor["floor_ef"]
        one_t = find_ef_floor("rpt_s0_winner_1t", threads=1)
        state["ef_floor_1t"] = {k: v for k, v in one_t.items() if k != "rows"}
        print(f"[S0a'] 1T floor_ef={one_t['floor_ef']} recall={one_t['recall']} "
              f"qps={one_t['qps']} rss={one_t['rss_mb']}", flush=True)

    if mode in ("gbdt", "all"):
        if floor is None or floor.get("floor_ef") is None:
            print("gbdt probe needs a measured ef floor; run --ef-floor first", file=sys.stderr)
            return 2
        print("\n=== S0b: per-artifact GBDT retrain (profile→train→on/off) ===", flush=True)
        d = probe_gbdt(floor["floor_ef"], floor["recall"])
        state["gbdt_probe"] = d
        print(f"[S0b] gbdt probe decision={d['decision']} artifact={d['artifact_id']} "
              f"rc={d['rc']}", flush=True)

    state["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (EVIDENCE / "s0_state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(f"\n=== S0 done. state -> {EVIDENCE/'s0_state.json'} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
