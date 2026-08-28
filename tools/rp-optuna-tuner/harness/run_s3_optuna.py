#!/usr/bin/env python3
"""run_s3_optuna.py — rp-optuna-tuner S3 Optuna TPE over the RESIDUAL rebuild axes
([[BEH-RPT-003]] / [[ARCH-RPT-001]] / [[CON-RPT-001]]).

Implements the binder_amend-pinned S3 Implementation slice:

  S3  Optuna TPE (RPT_OPTUNA_SAMPLER=TPE; CMA-ES optional) over the leftover rebuild
      axes — RPT_BLOCK_LADDER {32K,64K,128K,256K} (power-of-two, 4096-aligned, no 4KB,
      no >256KB) and RPT_PQ_M {16,32,64}. beam·R0 is NOT re-swept (covered by S1:
      beam=64 / R0=40 already beats golden). Each trial = 1 full rebuild against
      RPT_BUDGET_REBUILDS (remaining <=11 = 14 - 3 spent). Start from the S1 incumbent
      (beam=64 / alpha=1.2 / block=256KB / pq_M=32, GBDT on m=1.3 -> 95.76% / 15726.6).

  After every rebuild: ef floor (LEARNED_EF=0) + per-artifact GBDT retrain + 16T/1T
  sustained via run_rp_sustained.sh (frozen include/gbdt_model.h forbidden — each
  artifact gets its own harness/gbdt_model_<id>.h). Recall >=95% is a HARD constraint
  (never a soft loss): infeasible trials are excluded from winner ranking.

  Stop: RPT_OPTUNA_N_TRIALS exhausted, or no improvement vs S1 incumbent (recall >=95%
  and QPS not better). Hours of wall time are OK; a long trial is never aborted as
  "too slow".

Does NOT write Trunk src/include/tests; does NOT forge GATES approved_by; does NOT
re-open constraint-aware-tuning / hierarchical-vamana.

Modes:
  --self-check   validate paths/binaries/optuna/space; NO measurement.
  --dry-run      print the full plan; NO measurement.
  --from <i>     resume the trial loop at 0-based index i (state in evidence/s3_optuna_state.json).
  (default)      run the TPE loop.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import optuna
    HAVE_OPTUNA = True
except Exception:
    HAVE_OPTUNA = False

REPO = Path(__file__).resolve().parents[3]
POC = REPO / "poc" / "rp-optuna-tuner"
EVIDENCE = POC / "evidence"
NDF_EVIDENCE = POC / "ndf" / "evidence"
BIN_DIR = POC / "harness-bin"

SUSTAINED_SH = "tools/rp-optuna-tuner/scripts/run_rp_sustained.sh"
GBDT_PROBE_SH = "tools/rp-optuna-tuner/scripts/run_gbdt_probe.sh"
SUSTAINED_POC_BIN = str(BIN_DIR / "benchmark_sustained_poc")

CGROUP_MB = int(os.environ.get("RPT_CGROUP_MB", "512"))
RECALL_TARGET = 95.5   # percent; >=95% + guard (avoid measurement noise erasing the line)
RECALL_FLOOR = 95.0    # percent; the HARD floor (never a soft loss)
EF_LADDER = [100, 90, 80, 70, 60, 50, 40]
BLOCK_LADDER = [32768, 65536, 131072, 262144]
PQ_M_LADDER = [16, 32, 64]
N_TRIALS = int(os.environ.get("RPT_OPTUNA_N_TRIALS", "11"))
TPE_SEED = 42

# S1 incumbent (baseline — already measured in the S1 hop; NOT re-measured here).
BASE = dict(R0=40, BEAM=64, ALPHA=1.2, BLOCK_SIZE=262144, PQ_M=32)
INCUMBENT = dict(block_size=262144, pq_M=32, recall=95.76, qps=15726.6,
                 steady_qps=25049.9, label="S1 incumbent (beam=64/a=1.2/256KB/pq_M=32)")
BASE_PREFIX = "output/sift1m_rptbase"


def blksuf(bs: int) -> str:
    return f"{bs // 1024}k"


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


def run_sustained(prefix, vecblocks, ef, threads, tag, extra="", pq=None, bs=262144) -> dict:
    env = dict(os.environ)
    env.update({
        "CGROUP_MB": str(CGROUP_MB), "THREADS": str(threads),
        "EF": str(ef), "BS": str(bs),
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


def find_ef_floor(prefix, vecblocks, tag_prefix, bs=262144, pq=None, threads=16) -> dict:
    rows = []
    floor = None
    for ef in EF_LADDER:
        r = run_sustained(prefix, vecblocks, ef, threads, f"{tag_prefix}_ef{ef}",
                          "export LEARNED_EF=0", pq=pq, bs=bs)
        rows.append(r)
        if r["recall"] is None:
            continue
        if r["recall"] >= RECALL_TARGET:
            floor = r
        else:
            break  # recall monotone non-decreasing in ef -> stop below this
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


def run_gbdt(prefix, vecblocks, artifact_id, floor_ef, knobs, bs, pq) -> dict:
    model_export = f"tools/rp-optuna-tuner/harness/gbdt_model_{artifact_id}.h"
    pq_path = f"output/pqco_sift1m_M{pq}.bin" if pq != 32 else "output/pqco_sift1m_M32_correct.bin"
    env = dict(os.environ)
    env.update({
        "RPT_ARTIFACT_ID": artifact_id,
        "REFINE_EF": str(floor_ef),
        "RPT_GBDT_MODEL": model_export,
        "RPT_DATA_PREFIX": prefix,
        "RPT_VEC_BLOCKS_PATH": vecblocks,
        "RPT_PQ_CODES_PATH": pq_path,
        "RPT_BLOCK_SIZE": str(bs),
        "RPT_R0": str(knobs["R0"]),
        "RPT_BEAM": str(knobs["BEAM"]),
        "RPT_ALPHA": str(knobs["ALPHA"]),
        "RPT_PQ_M": str(pq),
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


def train_pq(pq: int) -> int:
    """Train PQ codes for M=pq into output/pqco_sift1m_M{pq}.bin (idempotent)."""
    out = f"output/pqco_sift1m_M{pq}.bin"
    if (REPO / out).exists():
        print(f"[pq] {out} already present, skip train", flush=True)
        return 0
    t0 = time.time()
    r = sh(["python3", "scripts/train_pq.py", "data/sift_base.fvecs", out, str(pq)])
    print(f"[pq] train M={pq} rc={r.returncode} ({time.time()-t0:.0f}s)", flush=True)
    return r.returncode


def build_trial(block: int, pq: int) -> dict:
    """Set up the artifact files for a (block, pq_M) trial under a unique prefix.

    The Vamana graph is FIXED (beam=64 / alpha=1.2) — identical for every trial — so the
    graph + bfs are symlinked from the S1 base. block layout (blocks/route/vecblocks) is
    regenerated when block != 256KB; PQ codes are trained when pq_M != 32. This is the
    "1 full rebuild" (layout/PQ rebuild; graph invariant) counted toward the budget.
    """
    prefix = f"output/sift1m_rpt_s3_blk{block}_pqm{pq}"
    suf = blksuf(block)

    # graph + bfs: shared (graph invariant across block/pq_M)
    for s in ["graph.bin", "bfs.bin"]:
        link = f"{prefix}_{s}"
        target = f"{REPO}/{BASE_PREFIX}_{s}"
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(target, link)

    if block == 262144:
        # 256KB layout is shared with the S1 base
        for s in [f"blocks_{suf}.bin", f"route_{suf}.bin", f"vecblocks_{suf}.bin"]:
            link = f"{prefix}_{s}"
            target = f"{REPO}/{BASE_PREFIX}_{s}"
            if os.path.lexists(link):
                os.remove(link)
            os.symlink(target, link)
    else:
        # regenerate block layout for the new block size
        sh(["./build/write_blocks_veconly", f"{BASE_PREFIX}_graph.bin", f"{BASE_PREFIX}_bfs.bin",
            f"{prefix}_vecblocks_{suf}.bin", str(block)])
        sh(["./build/write_blocks", f"{BASE_PREFIX}_graph.bin", f"{BASE_PREFIX}_bfs.bin",
            f"{prefix}_blocks_{suf}.bin", str(block)])
        sh(["./build/gen_route", f"{prefix}_blocks_{suf}.bin", f"{prefix}_route_{suf}.bin"])

    # PQ codes
    pq_path = "output/pqco_sift1m_M32_correct.bin" if pq == 32 else f"output/pqco_sift1m_M{pq}.bin"
    if pq != 32:
        train_pq(pq)

    return {"prefix": prefix, "vecblocks": f"{prefix}_vecblocks_{suf}.bin",
            "pq_path": pq_path, "suf": suf}


def measure_trial(block: int, pq: int) -> dict:
    """1 full rebuild + ef floor + per-artifact GBDT retrain + 16T/1T sustained."""
    artifact_id = f"s3_blk{block}_pqm{pq}"
    out = {"block_size": block, "pq_M": pq, "artifact_id": artifact_id}
    print(f"\n=== S3 TRIAL block={block} pq_M={pq} ({artifact_id}) ===", flush=True)

    t0 = time.time()
    bt = build_trial(block, pq)
    knobs = dict(BASE)
    out["rebuild"] = 1
    out["build_seconds"] = round(time.time() - t0, 1)

    print(f"[{artifact_id}] ef floor (16T, LEARNED_EF=0) ...", flush=True)
    floor = find_ef_floor(bt["prefix"], bt["vecblocks"], f"rpt_{artifact_id}",
                          bs=block, pq=bt["pq_path"])
    out["ef_floor_16t"] = {k: v for k, v in floor.items() if k != "rows"}
    print(f"[{artifact_id}] floor_ef={floor['floor_ef']} recall={floor['recall']} "
          f"qps={floor['qps']} feasible={floor['feasible']}", flush=True)

    if floor["floor_ef"] is not None:
        print(f"[{artifact_id}] 1T supplementary @ ef={floor['floor_ef']} ...", flush=True)
        one_t = run_sustained(bt["prefix"], bt["vecblocks"], floor["floor_ef"], 1,
                              f"rpt_{artifact_id}_1t_ef{floor['floor_ef']}",
                              "export LEARNED_EF=0", pq=bt["pq_path"], bs=block)
        out["ef_floor_1t"] = {k: v for k, v in one_t.items() if k != "rows"}
        print(f"[{artifact_id}] 1T recall={one_t['recall']} qps={one_t['qps']}", flush=True)

        print(f"[{artifact_id}] GBDT probe @ ef={floor['floor_ef']} ...", flush=True)
        g = run_gbdt(bt["prefix"], bt["vecblocks"], artifact_id, floor["floor_ef"],
                     knobs, block, pq)
        out["gbdt"] = g
        print(f"[{artifact_id}] GBDT decision={g['decision']} reason={g.get('reason','')} "
              f"rc={g['rc']}", flush=True)
    else:
        out["ef_floor_1t"] = None
        out["gbdt"] = {"decision": "infeasible", "reason": "no_ef_floor"}

    # ---- objective: best feasible QPS at recall >=95% (hard floor) ----
    out["best_recall"] = None
    out["best_qps"] = None
    out["best_leg"] = None
    if floor["floor_ef"] is not None:
        off_recall = floor["recall"]
        off_qps = floor["qps"]
        # GBDT-on m=1.3 leg (only if the probe advanced to a model)
        on_log = EVIDENCE / f"{artifact_id}_on_m1.3_{CGROUP_MB}mb_16t_n1000_r15.log"
        on = parse_log(on_log)
        # candidate legs: on (if measured + recall>=95%) vs off (recall>=95%)
        cands = []
        if on["recall"] is not None and on["recall"] >= RECALL_FLOOR:
            cands.append(("on_m1.3", on["recall"], on["qps"]))
        if off_recall is not None and off_recall >= RECALL_FLOOR:
            cands.append(("off", off_recall, off_qps))
        if cands:
            best = max(cands, key=lambda c: c[2] if c[2] is not None else -1.0)
            out["best_leg"], out["best_recall"], out["best_qps"] = best
    out["feasible"] = out["best_qps"] is not None and out["best_recall"] >= RECALL_FLOOR
    out["seconds"] = round(time.time() - t0, 1)
    print(f"[{artifact_id}] best={out['best_leg']} recall={out['best_recall']} "
          f"qps={out['best_qps']} feasible={out['feasible']} ({out['seconds']}s)", flush=True)
    return out


def self_check() -> int:
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"{'ok' if cond else 'FAIL'}: {name}")
        if not cond:
            fails += 1

    check("benchmark_sustained_poc exists", Path(SUSTAINED_POC_BIN).exists())
    check("benchmark_llsp exists", (BIN_DIR / "benchmark_llsp").exists())
    check("build_index exists", (REPO / "build" / "build_index").exists())
    check("write_blocks exists", (REPO / "build" / "write_blocks").exists())
    check("write_blocks_veconly exists", (REPO / "build" / "write_blocks_veconly").exists())
    check("gen_route exists", (REPO / "build" / "gen_route").exists())
    check("S1 base graph present", (REPO / f"{BASE_PREFIX}_graph.bin").exists())
    check("sift_base present", (REPO / "data" / "sift_base.fvecs").exists())
    check("PQ M32 correct present", (REPO / "output" / "pqco_sift1m_M32_correct.bin").exists())
    check("block ladder valid", all(bs in {32768, 65536, 131072, 262144} for bs in BLOCK_LADDER))
    check("pq_M ladder valid", all(m in {16, 32, 64} for m in PQ_M_LADDER))
    check("N_TRIALS <= 11", N_TRIALS <= 11)
    check("incumbent excluded from residual space",
          (INCUMBENT["block_size"], INCUMBENT["pq_M"]) == (262144, 32))
    # lightgbm/faiss are used by the SHELLED-OUT system python3 (train_pq.py + gbdt
    # scripts), not by this interpreter (which may be the optuna venv).
    lgbm = subprocess.run(["python3", "-c", "import lightgbm"], cwd=str(REPO))
    check("lightgbm importable (system python3)", lgbm.returncode == 0)
    faiss_r = subprocess.run(["python3", "-c", "import faiss"], cwd=str(REPO))
    check("faiss importable (system python3)", faiss_r.returncode == 0)
    check("optuna importable (TPE)", HAVE_OPTUNA)
    if HAVE_OPTUNA:
        check("optuna version", optuna.__version__)
    print(f"=== run_s3_optuna self-check {'PASS' if fails == 0 else 'FAIL'} ===")
    return 0 if fails == 0 else 1


def dry_run() -> int:
    print("=== rp-optuna-tuner S3 Optuna dry-run plan ===")
    print(f"sampler: TPE (optuna available: {HAVE_OPTUNA}) | n_trials={N_TRIALS} | seed={TPE_SEED}")
    print(f"residual axes: block {BLOCK_LADDER} x pq_M {PQ_M_LADDER}")
    print(f"incumbent (S1): {INCUMBENT}")
    print(f"cgroup={CGROUP_MB}MB | recall_target={RECALL_TARGET}% (guard) | floor={RECALL_FLOOR}%")
    print(f"each trial = 1 rebuild + ef floor + GBDT retrain + 16T/1T sustained")
    n = len(BLOCK_LADDER) * len(PQ_M_LADDER) - 1  # minus incumbent
    print(f"residual space size = {n} combos (12 - 1 incumbent)")
    print(f"stop: budget {N_TRIALS} exhausted, or no improvement vs incumbent QPS={INCUMBENT['qps']}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--self-check" in args:
        return self_check()
    if "--dry-run" in args:
        return dry_run()

    state_path = EVIDENCE / "s3_optuna_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}

    state.setdefault("schema", "ndf-poc-s3/v1")
    state.setdefault("topic", "rp-optuna-tuner")
    state.setdefault("task", "poc_implementation")
    state.setdefault("base", BASE)
    state.setdefault("incumbent", INCUMBENT)
    state.setdefault("cgroup_mb", CGROUP_MB)
    state.setdefault("recall_target", RECALL_TARGET)
    state.setdefault("recall_floor", RECALL_FLOOR)
    state.setdefault("block_ladder", BLOCK_LADDER)
    state.setdefault("pq_m_ladder", PQ_M_LADDER)
    state.setdefault("n_trials", N_TRIALS)
    state.setdefault("optuna_available", HAVE_OPTUNA)
    state.setdefault("trials", [])

    def persist():
        state["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    done = state["trials"]
    measured_combos = {(t["block_size"], t["pq_M"]) for t in done if t.get("measured")}

    # Residual space (exclude incumbent).
    combos = [(b, m) for b in BLOCK_LADDER for m in PQ_M_LADDER
              if (b, m) != (INCUMBENT["block_size"], INCUMBENT["pq_M"])]

    # Resume index (0-based into the optuna sequence).
    start = 0
    if "--from" in args:
        start = int(args[args.index("--from") + 1])

    if HAVE_OPTUNA:
        # TPE: reconstruct study from completed trials (deterministic given seed + order),
        # then continue with ask/tell.
        study = optuna.create_study(
            sampler=optuna.samplers.TPESampler(seed=TPE_SEED),
            direction="maximize")
        dist = {
            "block_size": optuna.distributions.CategoricalDistribution(BLOCK_LADDER),
            "pq_M": optuna.distributions.CategoricalDistribution(PQ_M_LADDER),
        }
        for t in done:
            study.add_trial(optuna.trial.create_trial(
                params={"block_size": t["block_size"], "pq_M": t["pq_M"]},
                distributions=dist,
                value=t.get("objective", -1.0)))
        for i in range(len(done), N_TRIALS):
            if i < start:
                continue
            trial = study.ask()
            block = trial.suggest_categorical("block_size", BLOCK_LADDER)
            pq = trial.suggest_categorical("pq_M", PQ_M_LADDER)
            combo = (block, pq)
            print(f"\n[TPE trial {i}] proposed block={block} pq_M={pq}", flush=True)
            # never rebuild the S1 incumbent (it is the baseline, already measured)
            if combo == (INCUMBENT["block_size"], INCUMBENT["pq_M"]):
                print(f"[TPE trial {i}] proposed incumbent {combo}, skip (baseline already measured)",
                      flush=True)
                study.tell(trial, -1.0)
                done.append({"block_size": block, "pq_M": pq, "measured": False,
                             "incumbent_skip": True, "objective": -1.0})
                persist()
                continue
            if combo in measured_combos:
                print(f"[TPE trial {i}] duplicate combo {combo}, skip (no rebuild)", flush=True)
                # tell with a neutral value and mark duplicate
                study.tell(trial, -1.0)
                done.append({"block_size": block, "pq_M": pq, "measured": False,
                             "duplicate": True, "objective": -1.0})
                persist()
                continue
            res = measure_trial(block, pq)
            objective = res["best_qps"] if res["feasible"] else -1.0
            res["objective"] = objective
            res["measured"] = True
            study.tell(trial, objective)
            done.append(res)
            measured_combos.add(combo)
            persist()
            # early stop: if we've already beaten the incumbent, we still continue to
            # sweep the remaining space (per intent: run until budget, hours OK).
        best = study.best_trial
        state["best_trial_number"] = best.number
        state["best_value"] = best.value
        state["best_params"] = best.params
    else:
        # Deterministic closed-ladder fallback (documented graceful degradation).
        state["fallback"] = "closed_ladder"
        for i, (block, pq) in enumerate(combos):
            if i < start or (block, pq) in measured_combos:
                continue
            if i >= N_TRIALS:
                break
            res = measure_trial(block, pq)
            res["objective"] = res["best_qps"] if res["feasible"] else -1.0
            res["measured"] = True
            done.append(res)
            persist()

    # ---- winner determination (HARD constraint: recall >= 95%) ----
    feasible = [t for t in done if t.get("measured") and t.get("feasible")]
    winner = max(feasible, key=lambda t: t["best_qps"] or -1.0, default=None)
    state["winner"] = winner["artifact_id"] if winner else None
    state["winner_qps"] = winner["best_qps"] if winner else None
    state["winner_recall"] = winner["best_recall"] if winner else None
    incumbent_qps = INCUMBENT["qps"]
    beats_incumbent = bool(winner and winner["best_qps"] and winner["best_qps"] > incumbent_qps)
    state["beats_incumbent"] = beats_incumbent
    state["rebuild_count"] = sum(1 for t in done if t.get("measured"))
    state["rebuild_budget"] = 14
    state["h3"] = ("confirmed" if beats_incumbent else "falsified")
    persist()

    print(f"\n=== S3 done. winner={state['winner']} qps={state['winner_qps']} "
          f"recall={state['winner_recall']} beats_incumbent={beats_incumbent} "
          f"(incumbent {incumbent_qps}) ===", flush=True)
    print(f"rebuild_count={state['rebuild_count']}/14 | H3 {state['h3']} | state -> {state_path}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
