#!/usr/bin/env python3
"""run_s1_s2.py — rp-optuna-tuner S1 + S2 (dense traversal) orchestrator
([[ARCH-RPT-001]] / [[BEH-RPT-001]] / [[BEH-RPT-002]]).

Implements the binder_amend-pinned Implementation slice:
  S1  build denser RP base graph beam=64 / α=1.2 (1 rebuild), then ef floor +
      per-artifact GBDT retrain + 16T/1T sustained.
  S2  RP-Tuning α₂ ladder (0 rebuild graph rewrite) over the densified pin
      [1.2, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8]; each α₂ = robust_prune_pass
      + ef floor + per-artifact GBDT retrain + 16T/1T sustained.
  H2  at least one full Vamana rebuild at α₂=1.0 (MRNG); α₂=0.9 if budget remains.

Does NOT start S3 Optuna; does NOT write Trunk src/include/tests; does NOT forge
GATES approved_by. All artifacts under output/sift1m_rptbase_* / output/sift1m_a2_* /
output/sift1m_h2_*. Evidence under tools/rp-optuna-tuner/evidence/.

Modes:
  --self-check      validate paths/binaries/gates; NO measurement.
  --dry-run         print the full plan; NO measurement.
  --from <stage>    resume from a stage: build | s1 | s2 | h2.
  (default)         run build → s1 → s2 → h2.
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
POC = REPO / "poc" / "rp-optuna-tuner"
EVIDENCE = POC / "evidence"
NDF_EVIDENCE = POC / "ndf" / "evidence"
BIN_DIR = POC / "harness-bin"

SUSTAINED_SH = "tools/rp-optuna-tuner/scripts/run_rp_sustained.sh"
GBDT_PROBE_SH = "tools/rp-optuna-tuner/scripts/run_gbdt_probe.sh"
BUILD_SH = "tools/rp-optuna-tuner/scripts/build_rptbase.sh"
ROBUST_PRUNE = str(BIN_DIR / "robust_prune_main")
SUSTAINED_POC_BIN = str(BIN_DIR / "benchmark_sustained_poc")

CGROUP_MB = int(os.environ.get("RPT_CGROUP_MB", "512"))
RECALL_TARGET = 95.5  # percent; >=95% + guard
EF_LADDER = [100, 90, 80, 70, 60, 50, 40]
ALPHA2_LADDER = [1.2, 1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8]
PINNED = {1.2, 1.1, 1.0, 0.9, 0.8}

# S1 RP base graph knobs ([[INTERFACE]] RPT_BASE_GRAPH)
BASE = dict(R0=40, BEAM=64, ALPHA=1.2, BLOCK_SIZE=262144, PQ_M=32)
BASE_PREFIX = "output/sift1m_rptbase"
BLKSUF = "256k"


def sh(cmd, **kw):
    print(f"$ {' '.join(str(c) for c in cmd)}", file=sys.stderr, flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=str(REPO), **kw)


def parse_log(path: Path) -> dict:
    txt = path.read_text() if path.exists() else ""

    def f(pat, cast=float):
        m = re.search(pat, txt)
        return cast(m.group(1)) if m else None

    recall = f(r"Recall@10:\s*([0-9.]+)%")
    qps = f(r"^QPS:\s+([0-9.]+)")
    steady = None
    m = re.search(r"CSV_AGG,\d+,\d+,[0-9.]+,([0-9.]+),[0-9.]+,\d+,([0-9.]+)", txt)
    if m:
        qps = float(m.group(1))
        steady = float(m.group(2))
    rss = f(r"^RSS:\s+([0-9]+)\s*MB", int)
    return {"recall": recall, "qps": qps, "steady_qps": steady, "rss_mb": rss}


def run_sustained(prefix, vecblocks, ef, threads, tag, extra="", pq=None) -> dict:
    env = dict(os.environ)
    env.update({
        "CGROUP_MB": str(CGROUP_MB), "THREADS": str(threads),
        "EF": str(ef), "BS": str(BASE["BLOCK_SIZE"]),
        "DATA_PREFIX": prefix, "VEC_BLOCKS_PATH": vecblocks,
        "PQ_CODES_PATH": pq or "output/pqco_sift1m_M32_correct.bin",
        "EXTRA": extra, "TAG": tag, "OUTDIR": str(EVIDENCE),
        "BIN": SUSTAINED_POC_BIN,
    })
    r = sh(["bash", SUSTAINED_SH], env=env)
    log = EVIDENCE / f"{tag}_{CGROUP_MB}mb_{threads}t_n1000_r15.log"
    res = parse_log(log)
    res.update(tag=tag, ef=ef, threads=threads, rc=r.returncode)
    return res


def find_ef_floor(prefix, vecblocks, tag_prefix, threads=16) -> dict:
    rows = []
    floor = None
    for ef in EF_LADDER:
        r = run_sustained(prefix, vecblocks, ef, threads, f"{tag_prefix}_ef{ef}", "export LEARNED_EF=0")
        rows.append(r)
        if r["recall"] is None:
            continue
        if r["recall"] >= RECALL_TARGET:
            floor = r  # keep descending; last passing is the floor
        else:
            break  # below floor -> stop (recall monotone non-decreasing in ef)
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
            "rows": rows, "feasible": best is not None}


def run_gbdt(prefix, vecblocks, artifact_id, floor_ef, knobs) -> dict:
    model_export = f"tools/rp-optuna-tuner/harness/gbdt_model_{artifact_id}.h"
    env = dict(os.environ)
    env.update({
        "RPT_ARTIFACT_ID": artifact_id,
        "REFINE_EF": str(floor_ef),
        "RPT_GBDT_MODEL": model_export,
        "RPT_DATA_PREFIX": prefix,
        "RPT_VEC_BLOCKS_PATH": vecblocks,
        "RPT_PQ_CODES_PATH": "output/pqco_sift1m_M32_correct.bin",
        "RPT_BLOCK_SIZE": str(knobs["BLOCK_SIZE"]),
        "RPT_R0": str(knobs["R0"]),
        "RPT_BEAM": str(knobs["BEAM"]),
        "RPT_ALPHA": str(knobs["ALPHA"]),
        "RPT_PQ_M": str(knobs["PQ_M"]),
        "CGROUP_MB": str(CGROUP_MB),
        "PROBE_RESULT": str(EVIDENCE / f"gbdt_probe_{artifact_id}.json"),
    })
    r = sh(["bash", GBDT_PROBE_SH], env=env)
    probe_path = EVIDENCE / f"gbdt_probe_{artifact_id}.json"
    probe = {}
    if probe_path.exists():
        try:
            probe = json.loads(probe_path.read_text())
        except Exception:
            pass
    return {"decision": probe.get("decision", "error"),
            "reason": probe.get("reason", ""),
            "artifact_id": artifact_id, "rc": r.returncode, "probe": probe}


def prune(base_graph, base_vec, out_graph, alpha2) -> dict:
    r = sh([ROBUST_PRUNE, base_graph, base_vec, out_graph, str(alpha2)],
           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    txt = r.stdout or ""
    m = re.search(r"edge reduction\s*:\s*([0-9.]+)%", txt)
    mb = re.search(r"edges after\s*:\s*(\d+)", txt)
    return {"rc": r.returncode, "edge_reduction_pct": float(m.group(1)) if m else None,
            "edges_after": int(mb.group(1)) if mb else None, "log": txt}


def a2_prefix(alpha2: float) -> str:
    return f"output/sift1m_a2_{alpha2:.2f}"


def setup_a2_symlinks(prefix: str) -> None:
    for suffix, src in [
        ("bfs.bin", f"{BASE_PREFIX}_bfs.bin"),
        ("blocks_256k.bin", f"{BASE_PREFIX}_blocks_256k.bin"),
        ("route_256k.bin", f"{BASE_PREFIX}_route_256k.bin"),
        ("vecblocks_256k.bin", f"{BASE_PREFIX}_vecblocks_256k.bin"),
    ]:
        link = f"{prefix}_{suffix}"
        target = f"{REPO}/{src}"
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(target, link)


def self_check() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"{'ok' if cond else 'FAIL'}: {name}")
        if not cond:
            fails += 1

    check("robust_prune_main exists", Path(ROBUST_PRUNE).exists())
    check("benchmark_sustained_poc exists", Path(SUSTAINED_POC_BIN).exists())
    check("benchmark_llsp exists", (BIN_DIR / "benchmark_llsp").exists())
    check("build_index exists", (REPO / "build" / "build_index").exists())
    check("sift_base present", (REPO / "data" / "sift_base.fvecs").exists())
    check("PQ codes present", (REPO / "output" / "pqco_sift1m_M32_correct.bin").exists())
    check("alpha2 ladder hits all pinned", PINNED.issubset(set(ALPHA2_LADDER)))
    try:
        import lightgbm  # noqa: F401
        check("lightgbm importable", True)
    except Exception:
        check("lightgbm importable", False)
    print(f"=== run_s1_s2 self-check {'PASS' if fails == 0 else 'FAIL'} ===")
    return 0 if fails == 0 else 1


def build_base() -> dict:
    if (REPO / f"{BASE_PREFIX}_graph.bin").exists() and (REPO / f"{BASE_PREFIX}_vecblocks_256k.bin").exists():
        print(f"[build] base already present ({BASE_PREFIX}_*), skipping rebuild", flush=True)
        return {"status": "already_built"}
    t0 = time.time()
    r = sh(["bash", BUILD_SH])
    return {"status": "built" if r.returncode == 0 else "failed",
            "rc": r.returncode, "seconds": round(time.time() - t0, 1)}


def measure_artifact(prefix, vecblocks, artifact_id, knobs, note) -> dict:
    out = {"artifact_id": artifact_id, "prefix": prefix, "note": note}
    print(f"\n=== MEASURE {artifact_id} ({note}) ===", flush=True)

    print(f"[{artifact_id}] ef floor (16T, LEARNED_EF=0) ...", flush=True)
    floor = find_ef_floor(prefix, vecblocks, f"rpt_{artifact_id}")
    out["ef_floor_16t"] = {k: v for k, v in floor.items() if k != "rows"}
    print(f"[{artifact_id}] floor_ef={floor['floor_ef']} recall={floor['recall']} "
          f"qps={floor['qps']} feasible={floor['feasible']}", flush=True)

    if floor["floor_ef"] is not None:
        # 1T supplementary at the floor ef
        print(f"[{artifact_id}] 1T supplementary @ ef={floor['floor_ef']} ...", flush=True)
        one_t = run_sustained(prefix, vecblocks, floor["floor_ef"], 1,
                              f"rpt_{artifact_id}_1t_ef{floor['floor_ef']}", "export LEARNED_EF=0")
        out["ef_floor_1t"] = {k: v for k, v in one_t.items() if k != "rows"}
        print(f"[{artifact_id}] 1T recall={one_t['recall']} qps={one_t['qps']}", flush=True)

        # per-artifact GBDT retrain (profile -> analyze -> train -> sustained on/off)
        print(f"[{artifact_id}] GBDT probe @ ef={floor['floor_ef']} ...", flush=True)
        g = run_gbdt(prefix, vecblocks, artifact_id, floor["floor_ef"], knobs)
        out["gbdt"] = g
        print(f"[{artifact_id}] GBDT decision={g['decision']} reason={g.get('reason','')} rc={g['rc']}",
              flush=True)
    else:
        out["ef_floor_1t"] = None
        out["gbdt"] = {"decision": "infeasible", "reason": "no_ef_floor"}

    return out


def stage_s1(state: dict) -> None:
    if state.get("s1"):
        print("[s1] already done, skipping", flush=True)
        return
    knobs = BASE
    state["s1"] = measure_artifact(BASE_PREFIX, f"{BASE_PREFIX}_vecblocks_256k.bin",
                                   f"s1_beam{BASE['BEAM']}_a{BASE['ALPHA']}", knobs,
                                   f"S1 RP base beam={BASE['BEAM']}/alpha={BASE['ALPHA']}")
    state["s1"]["rebuild"] = 1


def stage_s2(state: dict) -> None:
    if state.get("s2"):
        print("[s2] already done, skipping", flush=True)
        return
    base_graph = f"{BASE_PREFIX}_graph.bin"
    base_vec = "data/sift_base.fvecs"
    results = []
    for a2 in ALPHA2_LADDER:
        prefix = a2_prefix(a2)
        out_graph = f"{prefix}_graph.bin"
        print(f"\n=== S2 prune α₂={a2:.2f} ===", flush=True)
        pr = prune(base_graph, base_vec, out_graph, a2)
        if pr["rc"] != 0:
            results.append({"alpha2": a2, "prune": pr, "error": "prune_failed"})
            continue
        setup_a2_symlinks(prefix)
        knobs = dict(BASE, ALPHA=a2)  # α₂ recorded as the prune angle
        rec = measure_artifact(prefix, f"{prefix}_vecblocks_256k.bin",
                               f"s2_a2_{a2:.2f}", knobs,
                               f"S2 α₂={a2:.2f} RP-pruned (0 rebuild)")
        rec["alpha2"] = a2
        rec["prune"] = {k: v for k, v in pr.items() if k != "log"}
        rec["rebuild"] = 0
        results.append(rec)
    state["s2"] = results


def stage_h2(state: dict) -> None:
    if state.get("h2"):
        print("[h2] already done, skipping", flush=True)
        return
    results = []
    for a2 in [1.0, 0.9]:
        prefix = f"output/sift1m_h2_a{a2:.1f}"
        print(f"\n=== H2 full Vamana rebuild α={a2:.1f} ===", flush=True)
        env = dict(os.environ)
        env.update(HV_M="16", HV_R0="40", HV_RUP="16", HV_BEAM="64", HV_ALPHA=f"{a2}",
                   HV_ALPHA2="0", HV_ROUNDS="3", HV_SEED="42")
        r = sh(["./build/build_index", "data/sift_base.fvecs", f"{prefix}_graph.bin"], env=env)
        if r.returncode != 0:
            results.append({"alpha": a2, "error": "build_failed", "rc": r.returncode})
            continue
        sh(["./build/bfs_reorder", f"{prefix}_graph.bin", f"{prefix}_bfs.bin"])
        sh(["./build/write_blocks_veconly", f"{prefix}_graph.bin", f"{prefix}_bfs.bin",
            f"{prefix}_vecblocks_256k.bin", str(BASE["BLOCK_SIZE"])])
        sh(["./build/write_blocks", f"{prefix}_graph.bin", f"{prefix}_bfs.bin",
            f"{prefix}_blocks_256k.bin", str(BASE["BLOCK_SIZE"])])
        sh(["./build/gen_route", f"{prefix}_blocks_256k.bin", f"{prefix}_route_256k.bin"])
        knobs = dict(BASE, ALPHA=a2)
        rec = measure_artifact(prefix, f"{prefix}_vecblocks_256k.bin",
                               f"h2_a{a2:.1f}", knobs,
                               f"H2 full Vamana rebuild α={a2:.1f} (MRNG)" if a2 == 1.0
                               else f"H2 full Vamana rebuild α={a2:.1f}")
        rec["alpha"] = a2
        rec["rebuild"] = 1
        results.append(rec)
    state["h2"] = results


def dry_run() -> int:
    print("=== rp-optuna-tuner S1+S2 dry-run plan ===")
    print(f"BASE: {BASE}  prefix={BASE_PREFIX}  cgroup={CGROUP_MB}MB")
    print(f"EF_LADDER: {EF_LADDER}")
    print(f"ALPHA2_LADDER (densified): {ALPHA2_LADDER}")
    print(f"pinned must-hit: {sorted(PINNED)}")
    print(f"S1: 1 rebuild + ef floor + GBDT + 16T/1T sustained")
    print(f"S2: {len(ALPHA2_LADDER)} α₂ graph rewrites (0 rebuild each) + ef floor + GBDT + 16T/1T")
    print(f"H2: full Vamana rebuild at α=1.0 (+0.9 if budget); 1 rebuild each")
    print(f"rebuild budget: 14 (S1=1, H2=1..2 => total {1 + 2})")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--self-check" in args:
        return self_check()
    if "--dry-run" in args:
        return dry_run()

    state_path = EVIDENCE / "s1_s2_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}

    state.setdefault("schema", "ndf-poc-s1s2/v1")
    state.setdefault("topic", "rp-optuna-tuner")
    state.setdefault("task", "poc_implementation")
    state.setdefault("base", BASE)
    state.setdefault("cgroup_mb", CGROUP_MB)
    state.setdefault("recall_target", RECALL_TARGET)
    state.setdefault("alpha2_ladder", ALPHA2_LADDER)

    stage = "build"
    if "--from" in args:
        stage = args[args.index("--from") + 1]

    def persist():
        state["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    if stage in ("build", "s1", "s2", "h2"):
        if stage == "build":
            state["build"] = build_base()
            persist()
            stage = "s1"
        if stage == "s1":
            stage_s1(state)
            persist()
            stage = "s2"
        if stage == "s2":
            stage_s2(state)
            persist()
            stage = "h2"
        if stage == "h2":
            stage_h2(state)
            persist()
    else:
        print(f"unknown stage: {stage}", file=sys.stderr)
        return 2

    # rebuild count
    rebuild = 0
    if state.get("s1"):
        rebuild += state["s1"].get("rebuild", 0)
    for r in state.get("h2", []):
        rebuild += r.get("rebuild", 0)
    state["rebuild_count"] = rebuild
    state["rebuild_budget"] = 14
    persist()
    print(f"\n=== S1+S2+H2 done. rebuild_count={rebuild}/14. state -> {state_path} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
