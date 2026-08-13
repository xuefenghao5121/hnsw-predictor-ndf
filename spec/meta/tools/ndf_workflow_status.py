#!/usr/bin/env python3
"""NDF Workflow Canvas projection, trusted dispatch, and Replay (META-009..013).

This tool never approves gates, mutates NDF, starts agents, or writes
.openclaw/state.json. Snapshot and pack commands only write explicit,
gitignored evidence when Replay or embedded-projection verification is
requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec"
META = SPEC / "meta"
POC = ROOT / "poc"
TOOLS = META / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_context  # noqa: E402
import ndf_replay  # noqa: E402
from ndf_workflow_evidence import (  # noqa: E402
    append_lease,
    bundle_sha as evidence_bundle_sha,
    canonical_json_sha,
    chained_event,
    git_mutation_snapshot,
    read_leases,
    runtime_lease_binding_proof,
    safe_tmp_report_path,
    validate_evidence_bundle,
    validate_event_chain,
    validate_receipt,
    validate_recorded_runtime_lease_binding,
    validate_runtime_lease_binding,
    workspace_truth,
)

ACTION_LOG = ROOT / "tmp" / "ndf-workflow-actions.jsonl"
HEALTH_DIR = ROOT / "tmp" / "ndf-workflow-health"
LEASE_LOG = ROOT / "tmp" / "ndf-workflow-leases.jsonl"
CLOSE_EVIDENCE_DIR = ROOT / "tmp" / "ndf-close-evidence"
PROJECTION_EVIDENCE_DIR = ROOT / "tmp" / "ndf-projection-evidence"

GATE_COLUMNS = (
    "gate",
    "phrase",
    "approved_by",
    "approved_at",
    "approved_content_sha",
    "source_ref",
    "status",
)
GATE_PHRASES = {
    "topic_review": "TOPIC已审核",
    "design_review": "DESIGN已审核",
    "implementation_approval": "可以开始实现",
}
CONTROL_TASKS = frozenset(
    {
        "legacy_gate_audit",
        "gate_sha_audit",
        "gate_receipt_draft",
        "binder_amend",
        "control_proposal",
    }
)
IMPLEMENTATION_REPAIR_TASKS = frozenset(
    {
        "poc_isolation_repair",
        "poc_measurement",
    }
)
PROJECT_CONTROL_TASKS = frozenset({"ndf_improvement_proposal"})
POC_FILES = ("TOPIC.md", "DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md")
CODE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".py", ".sh", ".rs", ".go"}
CAPABILITY_MAP = {
    "Search core": {
        "files": ("search.md",),
        "modules": ("src/core/disk_hnsw.cpp", "include/disk_hnsw.h"),
    },
    "Fine rerank / I/O": {
        "files": ("fine-rerank.md", "cqe-peeking.md", "io-modes.md"),
        "modules": ("src/core/disk_hnsw.cpp", "include/io_uring_wrapper.h"),
    },
    "Cache": {
        "files": ("cache.md",),
        "modules": ("src/core/block_cache.cpp", "include/block_cache.h"),
    },
    "Prefetch": {
        "files": ("prefetch.md",),
        "modules": ("src/core/graph_prefetcher.cpp", "include/graph_prefetcher.h"),
    },
    "Physical layout": {
        "files": ("cluster-vecblock-layout.md",),
        "modules": ("src/pipeline/cluster_reorder.cpp",),
    },
    "Metrics / honesty": {
        "files": ("metrics.md",),
        "modules": ("src/benchmark/", "scripts/run_sustained.sh"),
    },
    "Test infrastructure": {
        "files": ("test-infra.md",),
        "modules": ("src/test/", "spec/50-verification/"),
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def run_tool(*args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(TOOLS / args[0]), *args[1:]],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": "python3 spec/meta/tools/" + " ".join(args),
        "exit_code": proc.returncode,
        "state": "passed" if proc.returncode == 0 else "failed",
        "output": proc.stdout.strip(),
    }


def public_check(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": check["command"],
        "exit_code": check["exit_code"],
        "state": check["state"],
        "summary": clean_markdown(check.get("output") or "", 360),
    }


def skipped_check(reason: str) -> dict[str, Any]:
    return {
        "command": "",
        "exit_code": 0,
        "state": "not_applicable",
        "output": reason,
    }


def finding(
    *,
    scope: str,
    space: str,
    kind: str,
    severity: str,
    evidence: str,
    repair_owner: str,
    repair_task: str,
    allowed_write_root: str | None,
    human_gate: str | None = None,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "space": space,
        "kind": kind,
        "severity": severity,
        "evidence": evidence,
        "repair_owner": repair_owner,
        "repair_task": repair_task,
        "allowed_write_root": allowed_write_root,
        "human_gate": human_gate,
    }


def finding_action(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": "repair",
        "space": item["space"],
        "owner": item["repair_owner"],
        "task": item["repair_task"],
        "allowed_write_root": item["allowed_write_root"],
        "human_gate": item["human_gate"],
        "kind": item["kind"],
    }


def unique_actions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in findings:
        action = finding_action(item)
        key = (
            action["owner"],
            action["task"],
            action["space"],
            action["allowed_write_root"],
            action["human_gate"],
        )
        if key not in seen:
            seen.add(key)
            actions.append(action)
    return actions


def header(text: str, key: str) -> str | None:
    match = re.search(rf"(?im)^>\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def section(text: str, title: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)", text
    )
    return match.group(1).strip() if match else ""


def first_token(value: str | None, default: str = "unknown") -> str:
    if not value:
        return default
    match = re.match(r"\s*([A-Za-z0-9_-]+)", value)
    return match.group(1).lower() if match else default


def git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def git_head() -> str | None:
    code, output = git("rev-parse", "HEAD")
    return output if code == 0 else None


def file_sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def source_generation_sha() -> str:
    """Hash local workflow evidence without making Canvas a SoT."""
    digest = hashlib.sha256()
    head = git_head() or "no-git-head"
    digest.update(head.encode())
    digest.update(b"\0")
    candidates = [ROOT / "AGENTS.md"]
    for base in (SPEC, POC, ROOT / ".cursor" / "skills" / "ndf-workflow-canvas"):
        if not base.is_dir():
            continue
        candidates.extend(
            path
            for path in base.rglob("*")
            if path.is_file() and path.suffix in {".md", ".json", ".py", ".tsx"}
        )
    for path in sorted(set(candidates), key=str):
        if not path.is_file():
            continue
        digest.update(rel(path).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def context_binding(
    *,
    topic: str | None,
    role: str,
    task: str,
    track: str,
) -> dict[str, Any]:
    """Compile one shared manifest and its role-specific verified task plan."""
    try:
        manifest = ndf_context.create_manifest(
            root=ROOT,
            topic=topic,
            task=task,
            track=track,
            depth=8,
            node_budget=240,
            byte_budget=1_048_576,
        )
        task_roots: list[str] | None = None
        if role == "openclaw":
            if task in {"legacy_gate_audit", "gate_sha_audit"}:
                task_roots = []
            elif task in {"gate_receipt_draft", "binder_amend"}:
                task_roots = [f"poc/{topic}/ndf/"] if topic else []
            elif task == "control_proposal":
                task_roots = ["spec/open/", "spec/meta/open/"]
        elif role == "project-control":
            task_roots = ["spec/meta/open/"]
        elif role == "claude-code" and task == "project_genesis":
            task_roots = ["src/", "include/", "tests/", "spec/50-verification/"]
        if task_roots is not None:
            manifest["role_policies"][role]["allowed_write_roots"] = task_roots
            manifest["manifest_sha"] = canonical_json_sha(
                {key: value for key, value in manifest.items() if key != "manifest_sha"}
            )
        plan = ndf_context.role_plan(manifest, role=role)
        verification = ndf_context.verify_plan(
            plan,
            root=ROOT,
            manifest=manifest,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        return {
            "context_plan": None,
            "context_verify": {
                "schema": "ndf-context-verification/v1",
                "valid": False,
                "errors": [{"kind": "context_compile_failed", "message": str(exc)}],
                "warnings": [],
            },
            "plan_sha": None,
            "manifest_sha": None,
            "task_manifest": None,
        }
    return {
        "task_manifest": manifest,
        "manifest_sha": manifest.get("manifest_sha"),
        "context_plan": plan,
        "context_verify": verification,
        "plan_sha": plan.get("plan_sha"),
    }


def bind_pack_to_episode(
    payload: dict[str, Any],
    *,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """Explicitly record a generated pack and its preflight in Replay."""
    identifier = episode_id or os.environ.get("NDF_REPLAY_EPISODE")
    allowed_roots = (
        payload.get("context_plan", {})
        .get("privileges", {})
        .get("allowed_write_roots", [])
    )
    if payload.get("allowed_write_root"):
        allowed_roots = [payload.get("allowed_write_root")]
    writable = bool(allowed_roots) and bool(
        payload.get("safe_to_dispatch")
        or (
            payload.get("safe_to_delegate")
            and payload.get("runtime_dispatch_ready") is not False
        )
    )
    if not identifier:
        if writable:
            raise ValueError("writable pack requires explicit Replay Episode")
        return payload
    if writable and (
        not isinstance(payload.get("task_manifest"), Mapping)
        or not payload.get("manifest_sha")
        or not isinstance(payload.get("context_plan"), Mapping)
        or not payload.get("plan_sha")
        or not all(isinstance(root, str) and root for root in allowed_roots)
    ):
        raise ValueError(
            "writable pack requires manifest, role plan, and exact write root"
        )
    store = ndf_replay.ReplayStore(ROOT)
    manifest = payload.get("task_manifest")
    if store.read_ref(f"episodes/{identifier}/HEAD") is None:
        store.init_episode(
            topic=payload.get("topic"),
            task=str(payload.get("task") or payload.get("next_action") or "dispatch"),
            role=str(payload.get("provider") or "tool"),
            track=str(payload.get("track") or "process"),
            manifest=manifest if isinstance(manifest, Mapping) else None,
            episode_id=identifier,
        )
    existing_manifest_shas = {
        event.get("manifest_sha")
        for events in store.read_all_events(identifier).values()
        for event in events
        if event.get("manifest_sha")
    }
    if payload.get("manifest_sha") and existing_manifest_shas not in (
        set(),
        {payload.get("manifest_sha")},
    ):
        raise ValueError("episode manifest does not match generated pack")
    if isinstance(manifest, Mapping):
        manifest_blob = store.put_blob(dict(manifest))
        if not any(
            event.get("kind") == "manifest.created"
            and event.get("payload_sha") == manifest_blob
            for events in store.read_all_events(identifier).values()
            for event in events
        ):
            store.append_event(
                identifier,
                kind="manifest.created",
                actor="context-compiler",
                payload_sha=manifest_blob,
                topic=payload.get("topic"),
                task=str(payload.get("task") or "dispatch"),
                track=str(payload.get("track") or "process"),
                repo_head=payload.get("base_sha"),
                manifest_sha=payload.get("manifest_sha"),
                context_plan_sha=None,
            )
    context_plan = payload.get("context_plan")
    branch = (
        "implementation"
        if payload.get("provider") == "claude-code-acp"
        else "control"
    )
    if isinstance(context_plan, Mapping):
        plan_blob = store.put_blob(dict(context_plan))
        store.append_event(
            identifier,
            kind="context.compiled",
            actor="context-compiler",
            payload_sha=plan_blob,
            topic=payload.get("topic"),
            task=str(payload.get("task") or "dispatch"),
            track=str(payload.get("track") or "process"),
            repo_head=payload.get("base_sha"),
            manifest_sha=payload.get("manifest_sha"),
            context_plan_sha=payload.get("plan_sha"),
            branch=branch,
        )
    recorded = dict(payload)
    recorded.pop("replay", None)
    blob_sha = store.put_blob(recorded)
    event = store.append_event(
        identifier,
        kind=(
            "dispatch.preflight"
            if payload.get("safe_to_dispatch") or payload.get("safe_to_delegate")
            else "dispatch.blocked"
        ),
        actor=str(payload.get("provider") or "tool"),
        payload_sha=blob_sha,
        topic=payload.get("topic"),
        task=str(payload.get("task") or payload.get("next_action") or "dispatch"),
        track=str(payload.get("track") or "process"),
        repo_head=payload.get("base_sha"),
        manifest_sha=payload.get("manifest_sha"),
        context_plan_sha=payload.get("plan_sha"),
        branch=branch,
    )
    payload["replay"] = {
        "episode_id": identifier,
        "pack_blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "coverage": "preflight",
    }
    return payload


def replay_pack_binding(
    episode_id: str,
    *,
    task: str,
    manifest_sha: str | None,
    context_plan_sha: str | None,
) -> tuple[str, dict[str, Any]]:
    """Return the latest verified writable pack in an Episode."""
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    branch_events = store.read_all_events(episode_id)
    for event in reversed(
        [
            item
            for events in branch_events.values()
            for item in events
        ]
    ):
        if (
            event.get("kind") != "dispatch.preflight"
            or event.get("task") != task
            or event.get("manifest_sha") != manifest_sha
            or event.get("context_plan_sha") != context_plan_sha
        ):
            continue
        pack_sha = str(event.get("payload_sha") or "")
        obj = store.get_object(pack_sha, "blob")["data"]
        pack = obj.get("value")
        if not isinstance(pack, dict):
            continue
        if (
            pack.get("safe_to_dispatch") is not True
            or pack.get("task") != task
            or pack.get("manifest_sha") != manifest_sha
            or pack.get("plan_sha") != context_plan_sha
        ):
            continue
        return pack_sha, pack
    raise ValueError("no verified dispatch pack matches lease context")


def active_runtime_leases() -> list[dict[str, Any]]:
    """Return latest active lease per run, ignoring malformed legacy records."""
    latest: dict[str, dict[str, Any]] = {}
    try:
        records = read_leases(LEASE_LOG, root=ROOT, strict=False)
    except ValueError:
        records = []
    for record in records:
        run_id = record.get("run_id")
        if not run_id:
            continue
        context = context_binding(
            topic=record.get("topic"),
            role="claude-code",
            task=str(record.get("task") or "implement"),
            track=str(record.get("mode") or "poc"),
        )
        try:
            pack_sha, pack = replay_pack_binding(
                str(record.get("episode_id") or ""),
                task=str(record.get("task") or "implement"),
                manifest_sha=context.get("manifest_sha"),
                context_plan_sha=context.get("plan_sha"),
            )
        except (FileNotFoundError, ValueError):
            continue
        semantic = validate_runtime_lease_binding(
            record,
            root=ROOT,
            expected={
                "topic": record.get("topic"),
                "task": record.get("task"),
                "repo_head": git_head(),
                "base_sha": pack.get("base_sha"),
                "plan_sha": context.get("plan_sha"),
                "manifest_sha": context.get("manifest_sha"),
                "allowed_write_root": pack.get("allowed_write_root"),
                "pack_sha": pack_sha,
                "episode_id": record.get("episode_id"),
                "branch": record.get("branch"),
                "repo_root": str(ROOT),
            },
        )
        if semantic["valid"]:
            latest[str(run_id)] = record
    return [record for record in latest.values() if record.get("result") == "active"]


def topic_active_lease(topic: str | None) -> dict[str, Any] | None:
    return next(
        (lease for lease in active_runtime_leases() if lease.get("topic") == topic),
        None,
    )


def read_action_receipts() -> list[dict[str, Any]]:
    if not ACTION_LOG.is_file():
        return []
    receipts: list[dict[str, Any]] = []
    for line in read_text(ACTION_LOG).splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("action_id"):
            receipts.append(value)
    return receipts


def action_chain_status(receipts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate the v2 action chain; legacy rows are never chain evidence."""
    records = receipts if receipts is not None else read_action_receipts()
    chained = [
        item
        for item in records
        if item.get("schema") == "ndf-workflow-action/v2"
    ]
    chain = validate_event_chain(chained)
    receipt_errors = [
        f"receipt:{index}:{error}"
        for index, item in enumerate(chained, 1)
        for error in validate_receipt(item)["errors"]
    ]
    return {
        **chain,
        "valid": chain["valid"] and not receipt_errors,
        "errors": [*chain["errors"], *receipt_errors],
        "legacy_count": len(records) - len(chained),
    }


def append_action_receipt(receipt: dict[str, Any]) -> None:
    chained = [
        item
        for item in read_action_receipts()
        if item.get("schema") == "ndf-workflow-action/v2" and item.get("event_sha")
    ]
    chain = action_chain_status(chained)
    if not chain["valid"]:
        raise ValueError(f"cannot append to invalid action chain: {chain['errors']}")
    receipt = chained_event(
        {
            **receipt,
            "schema": "ndf-workflow-action/v2",
            "seq": int(chained[-1]["seq"]) + 1 if chained else 1,
        },
        previous_sha=chained[-1]["event_sha"] if chained else None,
    )
    validation = validate_receipt(receipt)
    if not validation["valid"]:
        raise ValueError(f"invalid action receipt: {validation['errors']}")
    ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACTION_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def projection_freshness(generation_sha: str) -> dict[str, Any]:
    receipts = read_action_receipts()
    if not receipts:
        return {
            "state": "verified_at_generation",
            "snapshot_sha": generation_sha,
            "latest_action": None,
            "receipt_path": rel(ACTION_LOG),
        }
    chain = action_chain_status(receipts)
    if not chain["valid"]:
        return {
            "state": "unknown",
            "snapshot_sha": generation_sha,
            "latest_action": None,
            "receipt_path": rel(ACTION_LOG),
            "chain": chain,
        }
    latest_by_id: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        latest_by_id[str(receipt["action_id"])] = receipt
    in_progress = [
        receipt for receipt in latest_by_id.values() if receipt.get("status") == "started"
    ]
    latest = receipts[-1]
    if in_progress:
        state = "refresh_in_progress"
    else:
        # A newly generated payload is verified against the evidence generation
        # it contains. It makes no claim about future out-of-band changes; Canvas
        # local dispatch overlays pending_refresh until another payload is embedded.
        state = "verified_at_generation"
    return {
        "state": state,
        "snapshot_sha": generation_sha,
        "latest_action": latest,
        "in_progress": sorted(
            (receipt["action_id"] for receipt in in_progress),
        ),
        "receipt_path": rel(ACTION_LOG),
        "chain": chain,
    }


def action_begin(
    operation: str,
    topic: str | None,
    action_id: str | None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    if episode_id and ndf_replay.ReplayStore(ROOT).read_ref(
        f"episodes/{episode_id}/HEAD"
    ) is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    identifier = action_id or str(uuid.uuid4())
    started_at = now_iso()
    repo_head = git_head()
    generation = source_generation_sha()
    input_sha = canonical_json_sha(
        {"action_id": identifier, "operation": operation, "topic": topic}
    )
    receipt = {
        "schema": "ndf-workflow-action/v2",
        "task": operation,
        "action_id": identifier,
        "topic": topic,
        "mode": "process",
        "step": "begin",
        "repo_head": repo_head,
        "source_generation_sha": generation,
        "manifest_sha": None,
        "context_plan_sha": None,
        "command": operation,
        "input_sha": input_sha,
        "output_sha": None,
        "evidence_paths": [],
        "operation": operation,
        "status": "started",
        "started_at": started_at,
        "finished_at": None,
        "result": "started",
        "blockers": [],
        "repo_head_before": repo_head,
        "snapshot_sha_before": generation,
    }
    append_action_receipt(receipt)
    if episode_id:
        store = ndf_replay.ReplayStore(ROOT)
        blob_sha = store.put_blob(receipt)
        event = store.append_event(
            episode_id,
            kind="action.begin",
            actor="canvas",
            payload_sha=blob_sha,
            topic=topic,
            task=operation,
            track="process",
            repo_head=receipt.get("repo_head_before"),
            manifest_sha=None,
            context_plan_sha=None,
        )
        receipt["replay"] = {
            "episode_id": episode_id,
            "blob_sha": blob_sha,
            "event_sha": event["event_sha"],
        }
    return receipt


def action_finish(
    action_id: str,
    result: str,
    blockers: list[str],
    episode_id: str | None = None,
) -> dict[str, Any]:
    receipts = read_action_receipts()
    start = next(
        (
            receipt
            for receipt in reversed(receipts)
            if receipt.get("action_id") == action_id and receipt.get("status") == "started"
        ),
        None,
    )
    if start is None:
        raise ValueError(f"unknown started action: {action_id}")
    if episode_id and ndf_replay.ReplayStore(ROOT).read_ref(
        f"episodes/{episode_id}/HEAD"
    ) is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    finished_at = now_iso()
    repo_head = git_head()
    generation = source_generation_sha()
    outcome = {
        "action_id": action_id,
        "result": result,
        "blockers": blockers,
        "repo_head": repo_head,
        "source_generation_sha": generation,
    }
    receipt = {
        "schema": "ndf-workflow-action/v2",
        "task": start.get("operation"),
        "action_id": action_id,
        "topic": start.get("topic"),
        "mode": "process",
        "step": "finish",
        "repo_head": repo_head,
        "source_generation_sha": generation,
        "manifest_sha": start.get("manifest_sha"),
        "context_plan_sha": start.get("context_plan_sha"),
        "command": start.get("command") or start.get("operation"),
        "input_sha": start.get("input_sha"),
        "output_sha": canonical_json_sha(outcome),
        "evidence_paths": [],
        "operation": start.get("operation"),
        "status": "finished",
        "started_at": start.get("started_at"),
        "finished_at": finished_at,
        "result": result,
        "repo_head_before": start.get("repo_head_before"),
        "repo_head_after": repo_head,
        # Finishing an action changes evidence generation; it does not prove
        # that a Canvas has embedded a subsequently generated projection.
        "snapshot_sha_after": None,
        "evidence_generation": generation,
        "blockers": blockers,
    }
    append_action_receipt(receipt)
    if episode_id:
        store = ndf_replay.ReplayStore(ROOT)
        blob_sha = store.put_blob(receipt)
        event = store.append_event(
            episode_id,
            kind="action.finish",
            actor="canvas",
            payload_sha=blob_sha,
            topic=receipt.get("topic"),
            task=str(receipt.get("operation") or "action"),
            track="process",
            repo_head=receipt.get("repo_head_after"),
            manifest_sha=None,
            context_plan_sha=None,
        )
        receipt["replay"] = {
            "episode_id": episode_id,
            "blob_sha": blob_sha,
            "event_sha": event["event_sha"],
        }
    return receipt


def bundle_sha(paths: list[Path]) -> str | None:
    existing = sorted({p.resolve() for p in paths if p.is_file()}, key=str)
    if not existing:
        return None
    digest = hashlib.sha256()
    for path in existing:
        digest.update(rel(path).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    clean = value.strip().strip("[]")
    return [part.strip().strip("`\"'") for part in re.split(r"[,;]", clean) if part.strip()]


def normalize_lifecycle(raw: str | None) -> str:
    value = (raw or "").lower()
    if "reject" in value:
        return "rejected"
    if "promot" in value:
        return "promoted"
    if "closed" in value:
        return "closed"
    if "block" in value:
        return "blocked"
    if "explor" in value or "active" in value:
        return "exploring"
    return "unknown"


def clean_markdown(text: str, limit: int = 280) -> str:
    value = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    value = re.sub(r"\[\[([A-Z0-9-]+)(?:\|[^\]]+)?\]\]", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[`*#>]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" :")
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def clause_chunk(text: str, clause_id: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+.*?\{{#{re.escape(clause_id)}\}}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def clause_summary(text: str, clause_id: str) -> str:
    chunk = clause_chunk(text, clause_id)
    chunk = re.sub(r"(?m)^<!--\s*ndf:.*?-->\s*$", "", chunk)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", chunk) if part.strip()]
    for paragraph in paragraphs:
        if paragraph.startswith(("```", "|")):
            continue
        summary = clean_markdown(paragraph)
        if summary:
            return summary
    return ""


def clause_status_counts(paths: list[Path]) -> dict[str, int]:
    counts = {"stable": 0, "draft": 0, "deprecated": 0, "other": 0}
    for path in paths:
        text = read_text(path)
        matches = list(re.finditer(r"(?m)^##\s+.*?\{#[A-Z][A-Z0-9-]+\}\s*$", text))
        anchored_ids: set[str] = set()
        for index, match in enumerate(matches):
            id_match = re.search(r"\{#([A-Z][A-Z0-9-]+)\}", match.group(0))
            if id_match:
                anchored_ids.add(id_match.group(1))
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chunk = text[match.end() : end]
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", chunk[:600])
            status = status_match.group(1).lower() if status_match else "other"
            counts[status if status in counts else "other"] += 1
        for metadata in re.finditer(r"<!--\s*ndf:\s*([^>]+)-->", text):
            id_match = re.search(r"\bid=([A-Z][A-Z0-9-]+)", metadata.group(1))
            if not id_match or id_match.group(1) in anchored_ids:
                continue
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", metadata.group(1))
            status = status_match.group(1).lower() if status_match else "other"
            counts[status if status in counts else "other"] += 1
    return counts


def markdown_rows(section_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [clean_markdown(cell, 160) for cell in line.strip().strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows


def markdown_table(path: Path) -> list[dict[str, str]]:
    lines = read_text(path).splitlines()
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        normalized = [re.sub(r"[^a-z_]", "", cell.lower().replace(" ", "_")) for cell in cols]
        if not all(name in normalized for name in GATE_COLUMNS):
            continue
        if index + 1 >= len(lines):
            return []
        rows: list[dict[str, str]] = []
        for row_line in lines[index + 2 :]:
            if not row_line.lstrip().startswith("|"):
                break
            values = [cell.strip().strip("`") for cell in row_line.strip().strip("|").split("|")]
            if len(values) < len(cols):
                values.extend([""] * (len(cols) - len(values)))
            row = dict(zip(normalized, values))
            if row.get("gate") and set(row["gate"]) - {"-", ":"}:
                rows.append(row)
        return rows
    return []


def latest_gate_rows(path: Path) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in markdown_table(path):
        latest[row["gate"]] = row
    return latest


def proposal_paths(topic_text: str) -> list[Path]:
    found: list[Path] = []
    for raw in re.findall(r"(?:spec/open|ndf/proposals)/[A-Za-z0-9_.-]+\.md", topic_text):
        path = ROOT / raw if raw.startswith("spec/") else None
        if path is not None and path.is_file():
            found.append(path)
    return found


def poc_gate_bundles(topic_dir: Path) -> dict[str, list[Path]]:
    ndf = topic_dir / "ndf"
    topic = ndf / "TOPIC.md"
    proposals = proposal_paths(read_text(topic))
    return {
        "topic_review": [topic, *proposals],
        "design_review": [topic, ndf / "DESIGN.md"],
        "implementation_approval": [
            topic,
            ndf / "DESIGN.md",
            ndf / "PERF_BASELINE.md",
            ndf / "DELTA.md",
            ndf / "INTERFACE.md",
        ],
    }


def gate_view(gates_path: Path, bundles: dict[str, list[Path]]) -> dict[str, Any]:
    rows = latest_gate_rows(gates_path)
    result: dict[str, Any] = {}
    for gate, paths in bundles.items():
        expected = bundle_sha(paths)
        row = rows.get(gate)
        if not row:
            result[gate] = {
                "state": "legacy_unknown" if not gates_path.is_file() else "missing",
                "source": "none",
                "expected_content_sha": expected,
            }
            continue
        recorded = row.get("approved_content_sha", "")
        status = first_token(row.get("status"), "unknown")
        approved = status in {"valid", "approved"}
        semantic_complete = bool(
            row.get("phrase") == GATE_PHRASES.get(gate)
            and row.get("approved_by")
            and row.get("approved_at")
            and row.get("source_ref")
        )
        exact = bool(
            semantic_complete
            and
            expected
            and re.fullmatch(r"[0-9a-f]{64}", recorded or "")
            and expected == recorded
        )
        legacy_weak = bool(
            approved
            and expected
            and recorded
            and len(recorded) < 64
            and expected.startswith(recorded)
        )
        state = (
            "valid"
            if approved and exact
            else "legacy_weak"
            if legacy_weak
            else "invalidated"
            if approved
            else status
        )
        result[gate] = {
            "state": state,
            "source": "receipt",
            "phrase": row.get("phrase"),
            "approved_by": row.get("approved_by"),
            "approved_at": row.get("approved_at"),
            "approved_content_sha": recorded or None,
            "expected_content_sha": expected,
            "sha_aligned": exact,
            "source_ref": row.get("source_ref") or None,
            "semantic_complete": semantic_complete,
        }
    return result


def parse_surface(text: str) -> list[str]:
    raw = header(text, "explore_surface") or section(text, "explore_surface")
    if not raw:
        return []
    items = re.split(r"[,;\n]", raw)
    return sorted(
        {
            re.sub(r"^[-*]\s*", "", item).strip().strip("`")
            for item in items
            if re.sub(r"^[-*]\s*", "", item).strip().strip("`")
        }
    )


def binder_files(topic_dir: Path) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    output: dict[str, Any] = {}
    for name in (*POC_FILES, "GATES.md", "COMMITS.md"):
        path = ndf / name
        output[name] = {
            "path": rel(path),
            "exists": path.is_file(),
            "sha256": file_sha(path),
        }
    evidence = ndf / "evidence"
    output["evidence"] = {
        "path": rel(evidence),
        "exists": evidence.is_dir(),
        "count": len([path for path in evidence.rglob("*") if path.is_file()])
        if evidence.is_dir()
        else 0,
    }
    return output


def implementation_files(topic_dir: Path) -> list[str]:
    files: list[str] = []
    for path in topic_dir.rglob("*"):
        if not path.is_file() or "ndf" in path.relative_to(topic_dir).parts:
            continue
        if path.name == "NOTES.md" or path.suffix.lower() not in CODE_SUFFIXES:
            continue
        files.append(rel(path))
    return sorted(files)


def perf_view(topic: str, topic_dir: Path) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    topic_text = read_text(ndf / "TOPIC.md")
    card_value = header(topic_text, "perf_baseline")
    card = ndf / "PERF_BASELINE.md"
    if card_value:
        raw = card_value.strip().strip("`")
        candidate = topic_dir / raw if not raw.startswith("poc/") else ROOT / raw
        if candidate.is_file():
            card = candidate
    text = read_text(card)
    bind = {
        "vs": header(text, "vs") or header(text, "baseline"),
        "config_id": header(text, "config_id") or header(text, "baseline_id"),
        "measure_script": header(text, "measure_script"),
        "measure_binary": header(text, "measure_binary"),
    }
    numbers = section(text, "Numbers")
    pending = not numbers or bool(re.search(r"(?i)\bpending\b|\bTBD\b", numbers))
    errors = [f"missing_{key}" for key in ("vs", "config_id", "measure_script") if not bind[key]]
    if not card.is_file():
        errors.insert(0, "missing_perf_baseline")
    return {
        "path": rel(card),
        "exists": card.is_file(),
        "bind": bind,
        "numbers": "pending" if pending else "filled",
        "delta_exists": (ndf / "DELTA.md").is_file(),
        "errors": errors,
    }


def topic_external_checks(topic: str) -> dict[str, dict[str, Any]]:
    return {
        "perf_baseline": run_tool(
            "ndf_perf_baseline.py",
            "check",
            "--topic",
            topic,
        ),
        "isolation": run_tool(
            "ndf_poc_isolation.py",
            "check",
            "--topic",
            topic,
            "--workspace",
            "--report",
            "-",
        ),
        "bindcheck": run_tool(
            "ndf_bindcheck.py",
            "check",
            "--topic",
            topic,
            "--report",
            "-",
        ),
    }


def parsed_tool_issues(name: str, check: dict[str, Any]) -> list[tuple[str, str, str]]:
    output = check.get("output") or ""
    issues: list[tuple[str, str, str]] = []
    if name == "perf_baseline":
        for severity, kind, message in re.findall(
            r"(?m)^\s*\[(error|warning)\]\s+([a-z0-9_-]+):\s*(.+)$",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    elif name == "isolation":
        for severity, kind, message in re.findall(
            r"(?m)^-\s+\[(error|warning)\]\s+`([^`]+)`\s+\([^)]*\)\s*(.+)$",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    elif name == "bindcheck":
        for severity, kind, message in re.findall(
            r"(?m)^\|\s*\d+\s*\|\s*(error|warning)\s*\|\s*`([^`]+)`\s*\|[^|]*\|\s*([^|]+)\|",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    if check.get("exit_code") and not any(severity == "error" for severity, _, _ in issues):
        issues.append(("error", f"{name}_failed", clean_markdown(output, 260) or "tool failed"))
    return issues


def external_check_findings(
    topic: str,
    checks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name, check in checks.items():
        for severity, kind, message in parsed_tool_issues(name, check):
            if name == "isolation":
                findings.append(
                    finding(
                        scope="topic",
                        space="Implementation",
                        kind=kind,
                        severity=severity,
                        evidence=message,
                        repair_owner="claude-code",
                        repair_task="poc_isolation_repair",
                        allowed_write_root=f"poc/{topic}/",
                        human_gate="人工确认 destructive git disposition"
                        if severity == "error"
                        else None,
                    )
                )
            elif name == "perf_baseline":
                findings.append(
                    finding(
                        scope="topic",
                        space="Test",
                        kind=kind,
                        severity=severity,
                        evidence=message,
                        repair_owner="openclaw",
                        repair_task="binder_amend",
                        allowed_write_root=f"poc/{topic}/ndf/",
                    )
                )
            else:
                findings.append(
                    finding(
                        scope="topic",
                        space="Design",
                        kind=kind,
                        severity=severity,
                        evidence=message,
                        repair_owner="openclaw",
                        repair_task="binder_amend",
                        allowed_write_root=f"poc/{topic}/ndf/",
                    )
                )
    return findings


def gate_findings(topic: str, gates: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name, value in gates.items():
        state = value["state"]
        if state == "valid":
            continue
        if state == "legacy_unknown":
            task = "legacy_gate_audit"
        elif state == "invalidated":
            task = "gate_sha_audit"
        else:
            task = "gate_receipt_draft"
        findings.append(
            finding(
                scope="topic",
                space="Design",
                kind=f"gate_{name}_{state}",
                severity="error",
                evidence=f"{name} receipt state is {state}",
                repair_owner="openclaw",
                repair_task=task,
                allowed_write_root=f"poc/{topic}/ndf/",
                human_gate=GATE_PHRASES.get(name),
            )
        )
    return findings


def topic_health_artifact(topic: str) -> Path:
    return HEALTH_DIR / f"topic-{topic}.json"


def latest_topic_health(topic: str, generation_sha: str) -> dict[str, Any] | None:
    payload = read_json_artifact(topic_health_artifact(topic))
    if payload is None:
        return None
    payload = dict(payload)
    payload["state"] = (
        "current" if payload.get("snapshot_sha") == generation_sha else "stale"
    )
    return payload


def readiness(topic_dir: Path, gates: dict[str, Any], perf: dict[str, Any]) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    design_gaps = [name for name in ("DESIGN.md", "INTERFACE.md") if not (ndf / name).is_file()]
    for gate in ("topic_review", "design_review"):
        if gates[gate]["state"] != "valid":
            design_gaps.append(f"gate:{gate}:{gates[gate]['state']}")
    impl_files = implementation_files(topic_dir)
    impl_gaps: list[str] = []
    if gates["implementation_approval"]["state"] != "valid":
        impl_gaps.append(f"gate:implementation_approval:{gates['implementation_approval']['state']}")
    if not impl_files:
        impl_gaps.append("no_topic_code")
    test_gaps = list(perf["errors"])
    if not perf["delta_exists"]:
        test_gaps.append("missing_delta")
    if perf["numbers"] == "pending":
        test_gaps.append("numbers_pending")
    return {
        "design": {"ready": not design_gaps, "gaps": design_gaps},
        "implementation": {"ready": not impl_gaps, "gaps": impl_gaps, "code_files": impl_files},
        "test": {"ready": not test_gaps, "gaps": test_gaps},
    }


def phase_hint(lifecycle: str, gates: dict[str, Any], spaces: dict[str, Any]) -> str:
    if lifecycle in {"promoted", "rejected", "closed"}:
        return "closed"
    if all(gates[name]["state"] == "legacy_unknown" for name in gates):
        return "legacy_gate_audit"
    if gates["topic_review"]["state"] != "valid":
        return "await_topic_review"
    if gates["design_review"]["state"] != "valid":
        return "await_design_review"
    if gates["implementation_approval"]["state"] != "valid":
        return "await_implementation_approval"
    if not spaces["implementation"]["ready"]:
        return "implementing"
    if not spaces["test"]["ready"]:
        return "measuring"
    return "close_ready"


def topic_view(topic_dir: Path) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    text = read_text(ndf / "TOPIC.md")
    topic_id = header(text, "topic_id") or header(text, "ndf_topic") or topic_dir.name
    lifecycle = normalize_lifecycle(header(text, "status"))
    active = lifecycle in {"exploring", "blocked"}
    baseline_status = first_token(header(text, "baseline_status"), "unknown")
    bundles = poc_gate_bundles(topic_dir)
    gates = gate_view(ndf / "GATES.md", bundles)
    perf = perf_view(topic_id, topic_dir)
    checks = (
        topic_external_checks(topic_id)
        if active
        else {
            name: skipped_check("topic lifecycle is closed")
            for name in ("perf_baseline", "isolation", "bindcheck")
        }
    )
    findings = (
        gate_findings(topic_id, gates) + external_check_findings(topic_id, checks)
        if active
        else []
    )
    if active and perf["numbers"] == "pending":
        findings.append(
            finding(
                scope="topic",
                space="Test",
                kind="numbers_pending",
                severity="info",
                evidence="PERF_BASELINE Numbers are pending measurement evidence",
                repair_owner="claude-code",
                repair_task="poc_measurement",
                allowed_write_root=f"poc/{topic_id}/",
            )
        )
    spaces = readiness(topic_dir, gates, perf)
    for item in findings:
        if item["severity"] != "error":
            continue
        target = {
            "Design": spaces["design"],
            "Implementation": spaces["implementation"],
            "Test": spaces["test"],
        }[item["space"]]
        gap = f"{item['kind']}"
        if gap not in target["gaps"]:
            target["gaps"].append(gap)
        target["ready"] = False
    binder = binder_files(topic_dir)
    delta_text = read_text(ndf / "DELTA.md")
    delta = {
        "exists": bool(delta_text),
        "path": rel(ndf / "DELTA.md"),
        "feature": clean_markdown(section(delta_text, "Feature"), 180) or None,
        "hotspot": clean_markdown(section(delta_text, "Hotspot"), 180) or None,
        "latest_round": clean_markdown(
            section(delta_text, "Rounds") or section(delta_text, "Latest Round"),
            220,
        )
        or None,
    }
    hypothesis = (
        header(text, "active_hypothesis")
        or section(text, "Active hypothesis")
        or section(text, "Hypothesis")
    )
    expected_impact = (
        section(text, "Success criteria")
        or section(text, "Expected impact")
        or section(text, "Goal")
    )
    blockers: list[str] = []
    if baseline_status == "stale":
        blockers.append("baseline_stale")
    for name, value in gates.items():
        if value["state"] == "invalidated":
            blockers.append(f"gate_invalidated:{name}")
    blockers.extend(f"perf:{error}" for error in perf["errors"])
    blockers.extend(
        f"{item['space'].lower()}:{item['kind']}"
        for item in findings
        if item["severity"] == "error"
    )
    perf_passed = checks["perf_baseline"]["exit_code"] == 0
    isolation_passed = checks["isolation"]["exit_code"] == 0
    context = context_binding(
        topic=topic_id,
        role="claude-code",
        task="poc_implementation",
        track="poc",
    )
    context_valid = bool(context["context_verify"].get("valid"))
    static_preflight_passed = (
        active
        and
        gates["implementation_approval"]["state"] == "valid"
        and baseline_status != "stale"
        and perf_passed
        and isolation_passed
        and context_valid
    )
    lease = topic_active_lease(topic_id)
    runtime = runtime_status(False)["implementation"]
    runtime_dispatch_ready = bool(runtime["pipeline_reachable"] and not lease)
    safe_to_dispatch = static_preflight_passed and runtime_dispatch_ready
    dispatch_blockers = [
        reason
        for reason in (
            None if active else "topic_lifecycle_closed",
            None
            if gates["implementation_approval"]["state"] == "valid"
            else f"implementation_gate:{gates['implementation_approval']['state']}",
            None if baseline_status != "stale" else "baseline_stale",
            None if perf_passed else "perf_check_failed",
            None if isolation_passed else "isolation_check_failed",
            None if context_valid else "context_verify_failed",
            "runtime_unavailable" if not runtime["pipeline_reachable"] else None,
            "topic_active_lease" if lease else None,
        )
        if reason
    ]
    return {
        "topic_id": topic_id,
        "path": rel(topic_dir),
        "raw_status": header(text, "status"),
        "lifecycle": lifecycle,
        "phase_hint": phase_hint(lifecycle, gates, spaces),
        "gates": gates,
        "spaces": spaces,
        "perf": perf,
        "delta": delta,
        "binder": binder,
        "business": {
            "hypothesis": clean_markdown(hypothesis or "", 260) or "Not explicitly recorded",
            "expected_impact": clean_markdown(expected_impact or "", 220) or "Not explicitly recorded",
            "current_evidence": {
                "evidence_files": binder["evidence"]["count"],
                "numbers": perf["numbers"],
                "latest_result": clean_markdown(section(text, "Results") or section(text, "Conclusion"), 220)
                or "No summarized result",
            },
            "next_gate": header(text, "next_gate"),
        },
        "explore_surface": parse_surface(text),
        "depends_on_topics": split_list(header(text, "depends_on_topics")),
        "conflicts_with_topics": split_list(header(text, "conflicts_with_topics")),
        "baseline_status": baseline_status,
        "baseline_trunk_sha": header(text, "baseline_trunk_sha"),
        "agent_run": {
            "provider": "claude-code-acp",
            "status": "active" if lease else "unavailable",
            "state_source": "runtime-lease",
            "run_id": lease.get("run_id") if lease else None,
            "session_id": lease.get("session_id") if lease else None,
            "base_sha": lease.get("base_sha") if lease else None,
            "worktree": lease.get("worktree") if lease else None,
            "lease": lease,
        },
        "delegation": {
            "safe_to_dispatch": safe_to_dispatch,
            "static_preflight_passed": static_preflight_passed,
            "runtime_dispatch_ready": runtime_dispatch_ready,
            "safe_to_delegate_control": not any(
                value["state"] == "invalidated" for value in gates.values()
            ),
            "perf_check_passed": perf_passed,
            "isolation_passed": isolation_passed,
            **context,
            "dispatch_blockers": dispatch_blockers,
            "evaluated_at": now_iso(),
        },
        "traceability": [
            {
                "goal_or_clause": surface,
                "design": "DESIGN+INTERFACE"
                if binder["DESIGN.md"]["exists"] and binder["INTERFACE.md"]["exists"]
                else "design gaps",
                "code_or_commit": ", ".join(spaces["implementation"]["code_files"][:3])
                or "no topic code",
                "verification": (
                    "Numbers filled" if perf["numbers"] == "filled" else "Numbers pending"
                ),
            }
            for surface in parse_surface(text)
        ],
        "health": {
            "blockers": sorted(set(blockers)),
            "conflicts": [],
            "stale": baseline_status == "stale",
            "checks": {name: public_check(check) for name, check in checks.items()},
            "findings": findings,
            "next_actions": unique_actions(findings),
        },
    }


def list_topic_views() -> list[dict[str, Any]]:
    if not POC.is_dir():
        return []
    views = []
    for topic_dir in sorted(POC.iterdir()):
        if topic_dir.is_dir() and (topic_dir / "ndf" / "TOPIC.md").is_file():
            views.append(topic_view(topic_dir))
    attach_surface_conflicts(views)
    return views


def attach_surface_conflicts(views: list[dict[str, Any]]) -> None:
    active = [v for v in views if v["lifecycle"] in {"exploring", "blocked"}]
    for index, left in enumerate(active):
        left_surface = set(left["explore_surface"])
        for right in active[index + 1 :]:
            overlap = sorted(left_surface & set(right["explore_surface"]))
            if not overlap:
                continue
            finding = {"topic": right["topic_id"], "surface": overlap}
            reverse = {"topic": left["topic_id"], "surface": overlap}
            left["health"]["conflicts"].append(finding)
            right["health"]["conflicts"].append(reverse)


def iter_open_proposal_paths() -> list[Path]:
    return list((SPEC / "open").glob("*.md")) + list((META / "open").glob("proposal-meta-*.md"))


def proposal_plane_for_path(path: Path) -> str:
    return "process" if path.is_relative_to(META) else "product"


def proposal_record(path: Path) -> dict[str, Any]:
    text = read_text(path)
    track = header(text, "track")
    status = header(text, "Status") or header(text, "status") or "unknown"
    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")),
        path.name,
    )
    return {
        "path": rel(path),
        "title": title,
        "track": track,
        "status": status,
        "plane": proposal_plane_for_path(path),
    }


def proposal_plane_warnings() -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for path in sorted(iter_open_proposal_paths()):
        record = proposal_record(path)
        token = first_token(record["track"])
        plane = record["plane"]
        if plane == "product" and token == "process":
            warnings.append(
                {
                    "kind": "proposal_plane_misfile",
                    "severity": "warning",
                    "path": record["path"],
                    "plane": plane,
                    "track": record["track"],
                    "message": (
                        f"{record['path']} is under spec/open/ but track={record['track']!r}; "
                        "classified as product"
                    ),
                }
            )
        elif plane == "process" and record["track"] and token != "process":
            warnings.append(
                {
                    "kind": "proposal_plane_misfile",
                    "severity": "warning",
                    "path": record["path"],
                    "plane": plane,
                    "track": record["track"],
                    "message": (
                        f"{record['path']} is under spec/meta/open/ but track={record['track']!r}; "
                        "classified as process"
                    ),
                }
            )
    return warnings


def scan_proposals() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    product: list[dict[str, Any]] = []
    process: list[dict[str, Any]] = []
    for path in sorted(iter_open_proposal_paths()):
        record = proposal_record(path)
        normalized = (record["status"] or "").lower()
        if "implemented" in normalized or "rejected" in normalized or "superseded" in normalized:
            continue
        if not record["track"] and "proposal" not in path.name:
            continue
        if record["plane"] == "process":
            process.append(record)
        else:
            product.append(record)
    return product, process


def scan_product_proposals() -> list[dict[str, Any]]:
    return scan_proposals()[0]


def scan_process_proposals() -> list[dict[str, Any]]:
    return scan_proposals()[1]


def close_proposal_records(topic_id: str, topic_path: str) -> list[dict[str, Any]]:
    paths = (
        list((SPEC / "open").glob("*.md"))
        + list((SPEC / "archive").glob("**/*.md"))
        + list((ROOT / topic_path / "ndf" / "proposals").glob("*.md"))
    )
    records: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        text = read_text(path)
        explicit = " ".join(
            value
            for value in (
                path.name,
                header(text, "Topic"),
                header(text, "Subject"),
                header(text, "Rejects"),
                header(text, "Promotes"),
                header(text, "source"),
                "\n".join(text.splitlines()[:12]),
            )
            if value
        )
        if topic_id not in explicit:
            continue
        track = first_token(header(text, "track"))
        rejects = header(text, "Rejects")
        if track not in {"promote", "partial", "rollback", "poc", "bug", "unknown"} and rejects != topic_id:
            continue
        status = header(text, "Status") or header(text, "status") or "unknown"
        reviewed_header = header(text, "reviewed")
        reviewed = bool(
            re.fullmatch(r"(?i)\s*(reviewed|approved|已审核)\s*", status)
            or re.fullmatch(r"(?i)\s*(true|yes|reviewed|approved|已审核)\s*", reviewed_header or "")
        )
        records.append(
            {
                "path": rel(path),
                "track": track,
                "mode": "reject" if rejects == topic_id else ("partial" if track == "partial" else "promote"),
                "status": status,
                "implemented": "implemented" in status.lower(),
                "reviewed": reviewed,
            }
        )
    return records


def _legacy_close_projection(views: list[dict[str, Any]]) -> dict[str, Any]:
    """Permanently quarantined pre-receipt projection.

    Kept only as an explicit tripwire for downstream imports. No caller may
    recover green state from NOTES or bare tmp report existence.
    """
    del views
    raise RuntimeError(
        "legacy close projection is quarantined; use evidence-bound close_projection"
    )

    # Unreachable historical implementation retained temporarily for forensic
    # source review. The tripwire above is covered by a regression test.
    topics: list[dict[str, Any]] = []
    for view in views:
        topic_id = view["topic_id"]
        topic_path = view["path"]
        topic_dir = ROOT / topic_path
        notes_text = read_text(topic_dir / "NOTES.md")
        notes_evidence = bool(
            section(notes_text, "Results")
            or section(notes_text, "Conclusion")
            or re.search(r"(?im)^##\s+R\d+\s+结果", notes_text)
        )
        evidence_ready = bool(
            view["business"]["current_evidence"]["evidence_files"]
            or view["perf"]["numbers"] == "filled"
            or notes_evidence
        )
        proposals = close_proposal_records(topic_id, topic_path)
        proposal_ready = any(record["reviewed"] for record in proposals)
        lifecycle = view["lifecycle"]
        finalized = lifecycle in {"promoted", "rejected", "closed"}
        close_plan_reports = sorted(
            (ROOT / "tmp").glob(f"close-plan-{topic_id}-*.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        close_plan_report = close_plan_reports[0] if close_plan_reports else None
        close_plan_ready = bool(close_plan_report and read_text(close_plan_report).strip())
        graph_report = ROOT / "tmp" / f"graphcheck-after-close-{topic_id}.md"
        graph_text = read_text(graph_report)
        graph_green = bool(
            graph_report.is_file()
            and re.search(r"(?i)summary:\s*0\s+error", graph_text)
        )
        verification_report = ROOT / "tmp" / f"verification-after-close-{topic_id}.json"
        verification_data: dict[str, Any] = {}
        if verification_report.is_file():
            try:
                verification_data = json.loads(read_text(verification_report))
            except json.JSONDecodeError:
                verification_data = {}
        verification_green = verification_data.get("state") == "green"

        blockers = list(view["health"]["blockers"])
        if not evidence_ready:
            blockers.append("close:evidence_missing")
        if not proposal_ready and not finalized:
            blockers.append("close:reviewed_proposal_missing")

        steps = [
            {
                "id": "evidence",
                "plane": "Business",
                "label": "POC evidence ready",
                "status": "completed" if evidence_ready else "pending",
                "source": "binder/evidence/NOTES",
            },
            {
                "id": "proposal",
                "plane": "Control",
                "label": "Promote/reject proposal reviewed",
                "status": "completed" if proposal_ready or finalized else "pending",
                "source": proposals[0]["path"] if proposals else None,
            },
            {
                "id": "plan",
                "plane": "Control",
                "label": "Read-only close plan generated",
                "status": "completed" if close_plan_ready else "pending",
                "source": rel(close_plan_report) if close_plan_report else None,
            },
            {
                "id": "integrate",
                "plane": "Runtime",
                "label": "Integration/reject code disposition completed",
                "status": "completed" if finalized else "pending",
                "source": None,
            },
            {
                "id": "graph",
                "plane": "Control",
                "label": "Index and graphcheck green",
                "status": "completed" if graph_green else "pending",
                "source": rel(graph_report) if graph_report.is_file() else None,
            },
            {
                "id": "verify",
                "plane": "Business",
                "label": "Build, performance and golden verified",
                "status": "completed" if verification_green else "pending",
                "source": rel(verification_report) if verification_report.is_file() else None,
            },
            {
                "id": "finalize",
                "plane": "Control",
                "label": "Binder and archive finalized",
                "status": "completed" if finalized else "pending",
                "source": topic_path,
            },
        ]

        branches: dict[str, Any] = {}
        for mode in ("promote", "partial", "reject"):
            mode_proposals = [
                record
                for record in proposals
                if record["mode"] == mode
                or (mode == "partial" and record["mode"] == "promote")
            ]
            mode_proposal_ready = any(record["reviewed"] for record in mode_proposals)
            plan_report = ROOT / "tmp" / f"close-plan-{topic_id}-{mode}.md"
            plan_ready = plan_report.is_file() and bool(read_text(plan_report).strip())
            branch_finalized = (
                lifecycle == "rejected" if mode == "reject" else lifecycle == "promoted"
            )
            branch_steps = [
                {
                    "id": "evidence",
                    "plane": "Business",
                    "label": "POC evidence ready",
                    "status": "completed" if evidence_ready else "pending",
                    "source": "binder/evidence/NOTES",
                },
                {
                    "id": "proposal",
                    "plane": "Control",
                    "label": f"{mode} proposal reviewed",
                    "status": "completed"
                    if mode_proposal_ready or branch_finalized
                    else "pending",
                    "source": mode_proposals[0]["path"] if mode_proposals else None,
                },
                {
                    "id": "plan",
                    "plane": "Control",
                    "label": f"Read-only {mode} close plan",
                    "status": "completed" if plan_ready or branch_finalized else "pending",
                    "source": rel(plan_report) if plan_report.is_file() else None,
                },
                {
                    "id": "integrate",
                    "plane": "Runtime",
                    "label": "Code integration"
                    if mode != "reject"
                    else "Reject code disposition",
                    "status": "completed" if branch_finalized else "pending",
                    "source": None,
                },
                {
                    "id": "graph",
                    "plane": "Control",
                    "label": "Index and graphcheck green",
                    "status": "completed" if graph_green or branch_finalized else "pending",
                    "source": rel(graph_report) if graph_report.is_file() else None,
                },
            ]
            if mode != "reject":
                branch_steps.append(
                    {
                        "id": "verify",
                        "plane": "Business",
                        "label": "Build, performance and golden verified",
                        "status": "completed"
                        if verification_green or branch_finalized
                        else "pending",
                        "source": rel(verification_report)
                        if verification_report.is_file()
                        else None,
                    }
                )
            pre_finalize_green = all(
                item["status"] == "completed" for item in branch_steps
            )
            branch_steps.append(
                {
                    "id": "finalize",
                    "plane": "Control",
                    "label": "Binder and archive finalized",
                    "status": "completed" if branch_finalized else "pending",
                    "source": topic_path,
                }
            )
            branches[mode] = {
                "mode": mode,
                "proposal_ready": mode_proposal_ready,
                "close_plan_ready": plan_ready,
                "verification_required": mode != "reject",
                "finalization_ready": pre_finalize_green and not branch_finalized,
                "finalized": branch_finalized,
                "steps": branch_steps,
                "next_step": next(
                    (
                        item["id"]
                        for item in branch_steps
                        if item["status"] != "completed"
                    ),
                    "closed",
                ),
            }

        next_step = next(
            (step["id"] for step in steps if step["status"] != "completed"),
            "closed",
        )
        topics.append(
            {
                "topic_id": topic_id,
                "lifecycle": lifecycle,
                "evidence_ready": evidence_ready,
                "proposal_ready": proposal_ready,
                "proposals": proposals,
                "close_plan": {
                    "state": "generated" if close_plan_ready else "unknown",
                    "ready": close_plan_ready or finalized,
                    "source": rel(close_plan_report) if close_plan_report else None,
                },
                "graphcheck": {
                    "state": "green" if graph_green else "unknown",
                    "source": rel(graph_report) if graph_report.is_file() else None,
                },
                "verification": {
                    "state": "green" if verification_green else "unknown",
                    "source": rel(verification_report)
                    if verification_report.is_file()
                    else None,
                },
                "finalization_ready": any(
                    branch["finalization_ready"] for branch in branches.values()
                ),
                "branches": branches,
                "steps": steps,
                "next_step": next_step,
                "blockers": sorted(set(blockers)),
            }
        )
    return {
        "state_source": "tree/git/tool-evidence",
        "topics": topics,
    }


def _close_receipt_path(topic: str, mode: str, step: str) -> Path:
    return CLOSE_EVIDENCE_DIR / topic / mode / f"{step}.json"


def close_command_allowed(step: str, command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or any(any(char in token for char in ";&|><") for token in tokens):
        return False
    executable = Path(tokens[0]).name
    arguments = tokens[1:]
    script = executable
    script_token = tokens[0]
    if executable in {"python", "python3", "bash", "sh"}:
        if not arguments or arguments[0].startswith("-"):
            return False
        script_token = arguments[0]
        script = Path(script_token).name
        arguments = arguments[1:]
    candidate = Path(script_token)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve(strict=False)
    registered = {
        "ndf_close.py": (ROOT / "spec/meta/tools/ndf_close.py").resolve(),
        "ndf_graphcheck.py": (ROOT / "spec/meta/tools/ndf_graphcheck.py").resolve(),
        "ndf_index.py": (ROOT / "spec/meta/tools/ndf_index.py").resolve(),
        "ndf_perf_baseline.py": (
            ROOT / "spec/meta/tools/ndf_perf_baseline.py"
        ).resolve(),
        "ndf_workflow_status.py": (
            ROOT / "spec/meta/tools/ndf_workflow_status.py"
        ).resolve(),
        "run_sustained.sh": (ROOT / "scripts/run_sustained.sh").resolve(),
    }
    if registered.get(script) != candidate:
        return False
    if step == "plan":
        return script == "ndf_close.py" and arguments[:1] == ["plan"]
    if step == "integrate":
        return (
            script == "ndf_workflow_status.py"
            and arguments[:1] == ["completion-record"]
        )
    if step == "graph":
        return script in {"ndf_graphcheck.py", "ndf_index.py"}
    if step == "verify":
        return script in {
            "run_sustained.sh",
            "ndf_perf_baseline.py",
        }
    if step == "finalize":
        return (
            script == "ndf_workflow_status.py"
            and arguments[:1] == ["topic-health"]
        )
    return False


def verify_close_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_topic: str | None = None,
    expected_mode: str | None = None,
    expected_step: str | None = None,
) -> dict[str, Any]:
    validation = validate_receipt(receipt)
    errors = list(validation["errors"])
    topic = expected_topic or receipt.get("topic")
    mode = expected_mode or receipt.get("mode")
    step = expected_step or receipt.get("step")
    for field, expected in (("topic", topic), ("mode", mode), ("step", step)):
        if expected is not None and receipt.get(field) != expected:
            errors.append(f"mismatch:{field}")
    accepted_tasks = {"close", str(step), f"close_{step}", f"close-{step}"}
    if receipt.get("task") not in accepted_tasks:
        errors.append("mismatch:task")
    command = str(receipt.get("command") or "")
    if not close_command_allowed(str(step), command):
        errors.append("command_not_allowed")
    if receipt.get("repo_head") != git_head():
        errors.append("stale:repo_head")
    generation = source_generation_sha()
    if receipt.get("source_generation_sha") != generation:
        errors.append("stale:source_generation_sha")
    plan_sha = receipt.get("context_plan_sha")
    current_plan_sha = None
    current_manifest_sha = None
    if plan_sha:
        context = context_binding(
            topic=str(topic) if topic else None,
            role="openclaw",
            task=str(mode or "close"),
            track=str(mode or "poc"),
        )
        current_plan_sha = context["plan_sha"]
        current_manifest_sha = context.get("manifest_sha")
        if not context["context_verify"].get("valid") or plan_sha != current_plan_sha:
            errors.append("stale:context_plan_sha")
        if receipt.get("manifest_sha") != current_manifest_sha:
            errors.append("stale:manifest_sha")
    if receipt.get("result") not in {"passed", "success", "completed"}:
        errors.append("result_not_green")
    missing_paths = [
        path
        for path in receipt.get("evidence_paths", [])
        if not isinstance(path, str) or not (ROOT / path).is_file()
    ]
    if missing_paths:
        errors.append("missing:evidence_paths")
    evidence_validation = validate_evidence_bundle(receipt, root=ROOT)
    errors.extend(evidence_validation["errors"])
    return {
        "schema": "ndf-close-receipt-verification/v1",
        "valid": not errors,
        "errors": sorted(set(errors)),
        "topic": topic,
        "mode": mode,
        "step": step,
        "repo_head": git_head(),
        "source_generation_sha": generation,
        "context_plan_sha": current_plan_sha,
        "manifest_sha": current_manifest_sha,
        "evidence_bundle": evidence_validation,
    }


def close_receipt_view(topic: str, mode: str, step: str) -> dict[str, Any]:
    path = _close_receipt_path(topic, mode, step)
    if path.is_file():
        data = read_json_artifact(path)
        verification = (
            verify_close_receipt(
                data or {},
                expected_topic=topic,
                expected_mode=mode,
                expected_step=step,
            )
        )
        return {
            "state": "verified" if verification["valid"] else "invalid",
            "ready": verification["valid"],
            "source": rel(path),
            "verification": verification,
        }
    legacy_patterns = {
        "plan": f"close-plan-{topic}-{mode}.md",
        "graph": f"graphcheck-after-close-{topic}.md",
        "verify": f"verification-after-close-{topic}.json",
    }
    legacy = ROOT / "tmp" / legacy_patterns[step] if step in legacy_patterns else None
    return {
        "state": "legacy_unbound" if legacy and legacy.is_file() else "missing",
        "ready": False,
        "source": rel(legacy) if legacy and legacy.is_file() else None,
        "verification": None,
    }


def close_projection(views: list[dict[str, Any]]) -> dict[str, Any]:
    """Project Close conservatively from binder truth and bound receipts."""
    topics: list[dict[str, Any]] = []
    for view in views:
        topic_id = view["topic_id"]
        lifecycle = view["lifecycle"]
        proposals = close_proposal_records(topic_id, view["path"])
        binder = view["binder"]
        binder_minimum = all(
            binder[name]["exists"]
            for name in ("TOPIC.md", "DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md")
        )
        perf_full = (
            view["health"]["checks"]["perf_baseline"]["state"] == "passed"
            and view["perf"]["numbers"] == "filled"
            and view["perf"]["delta_exists"]
            and binder["evidence"]["count"] > 0
            and binder_minimum
        )
        notes_only = bool(read_text(ROOT / view["path"] / "NOTES.md"))
        branches: dict[str, Any] = {}
        for mode in ("promote", "partial", "reject"):
            mode_proposals = [record for record in proposals if record["mode"] == mode]
            proposal_ready = any(record["reviewed"] for record in mode_proposals)
            rejected_proposal = any(record["mode"] == "reject" for record in mode_proposals)
            evidence_ready = (
                (lifecycle == "rejected" or rejected_proposal)
                if mode == "reject"
                else perf_full
            )
            receipts = {
                step: close_receipt_view(topic_id, mode, step)
                for step in ("plan", "integrate", "graph", "verify", "finalize")
            }
            ordered = ["evidence", "proposal", "plan", "integrate", "graph"]
            if mode != "reject":
                ordered.append("verify")
            ordered.append("finalize")
            direct = {"evidence": evidence_ready, "proposal": proposal_ready}
            steps = []
            for step in ordered:
                ready = direct.get(step, receipts.get(step, {}).get("ready", False))
                source = (
                    mode_proposals[0]["path"]
                    if step == "proposal" and mode_proposals
                    else "binder/evidence"
                    if step == "evidence" and evidence_ready
                    else receipts.get(step, {}).get("source")
                )
                steps.append(
                    {
                        "id": step,
                        "status": "completed" if ready else "pending",
                        "source": source,
                        "evidence_state": receipts.get(step, {}).get("state"),
                    }
                )
            pre_finalize = all(item["status"] == "completed" for item in steps[:-1])
            finalized = steps[-1]["status"] == "completed"
            branches[mode] = {
                "mode": mode,
                "evidence_ready": evidence_ready,
                "proposal_ready": proposal_ready,
                "close_plan_ready": receipts["plan"]["ready"],
                "verification_required": mode != "reject",
                "finalization_ready": pre_finalize and not finalized,
                "finalized": finalized,
                "receipts": receipts,
                "steps": steps,
                "next_step": next(
                    (item["id"] for item in steps if item["status"] != "completed"),
                    "closed",
                ),
            }
        aggregate_evidence = any(branch["evidence_ready"] for branch in branches.values())
        aggregate_proposal = any(branch["proposal_ready"] for branch in branches.values())
        blockers = list(view["health"]["blockers"])
        if not aggregate_evidence:
            blockers.append("close:evidence_missing")
        if notes_only and not aggregate_evidence:
            blockers.append("close:notes_only_untrusted")
        topics.append(
            {
                "topic_id": topic_id,
                "lifecycle": lifecycle,
                "evidence_ready": aggregate_evidence,
                "proposal_ready": aggregate_proposal,
                "proposals": proposals,
                "close_plan": {
                    "state": "verified"
                    if any(branch["close_plan_ready"] for branch in branches.values())
                    else "unknown",
                    "ready": any(branch["close_plan_ready"] for branch in branches.values()),
                    "source": None,
                },
                "graphcheck": {
                    "state": "green"
                    if any(branch["receipts"]["graph"]["ready"] for branch in branches.values())
                    else "legacy_unbound"
                    if any(
                        branch["receipts"]["graph"]["state"] == "legacy_unbound"
                        for branch in branches.values()
                    )
                    else "unknown",
                    "source": None,
                },
                "verification": {
                    "state": "green"
                    if any(branch["receipts"]["verify"]["ready"] for branch in branches.values())
                    else "legacy_unbound"
                    if any(
                        branch["receipts"]["verify"]["state"] == "legacy_unbound"
                        for branch in branches.values()
                    )
                    else "unknown",
                    "source": None,
                },
                "finalization_ready": any(branch["finalization_ready"] for branch in branches.values()),
                "branches": branches,
                "steps": branches["promote"]["steps"],
                "next_step": branches["promote"]["next_step"],
                "blockers": sorted(set(blockers)),
            }
        )
    return {"state_source": "tree/git/bound-receipts", "topics": topics}


def business_identity() -> dict[str, Any]:
    charter_path = SPEC / "00-charter" / "charter.md"
    text = read_text(charter_path)
    goal = clause_summary(text, "CHR-001")
    project_match = re.search(r"\b([A-Za-z][A-Za-z0-9_-]+)\s+MUST\b", goal)
    phase = "P3 active" if re.search(r"(?i)P3[（(].*?进行中", text) else "unknown"
    return {
        "name": project_match.group(1) if project_match else ROOT.name,
        "charter_path": rel(charter_path),
        "goal_summary": goal,
        "phase": phase,
        "scale_coverage": [
            {"scale": "SIFT1M", "status": "validated"},
            {"scale": "DEEP10M", "status": "validated" if "DEEP10M" in text else "unknown"},
            {"scale": "100M", "status": "planned" if "100M" in text else "unknown"},
        ],
    }


def business_goals() -> list[dict[str, Any]]:
    text = read_text(SPEC / "00-charter" / "charter.md")
    goals = []
    for clause_id, label in (
        ("CHR-001", "Primary goal"),
        ("CHR-006", "Performance commitment"),
        ("CHR-004", "Evolution roadmap"),
    ):
        summary = clause_summary(text, clause_id)
        if summary:
            chunk = clause_chunk(text, clause_id)
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", chunk[:400])
            goals.append(
                {
                    "id": clause_id,
                    "label": label,
                    "summary": summary,
                    "status": status_match.group(1) if status_match else "unknown",
                }
            )
    return goals


def capability_portfolio() -> list[dict[str, Any]]:
    behavior = SPEC / "20-behavior"
    capabilities = []
    for name, config in CAPABILITY_MAP.items():
        paths = [behavior / filename for filename in config["files"] if (behavior / filename).is_file()]
        counts = clause_status_counts(paths)
        capabilities.append(
            {
                "name": name,
                "spec_paths": [rel(path) for path in paths],
                "modules": list(config["modules"]),
                "clauses": counts,
            }
        )
    return capabilities


def performance_summary() -> dict[str, Any]:
    index_path = SPEC / "50-verification" / "golden-baseline.md"
    text = read_text(index_path)
    baseline_match = re.search(r"现行 Trunk 金标:\s*\*\*([^*]+)\*\*", text)
    trunk_match = re.search(r"(?m)^\|\s*代码\s*\|\s*`([0-9a-f]{7,64})`", text)
    config_match = re.search(r"(?m)^\|\s*配置 A/B/C\s*\|\s*`([^`]+)`\s*/\s*`([^`]+)`\s*/\s*`([^`]+)`", text)
    best_match = re.search(r"(?ms)^##\s+最佳性能速览.*?$\n(.*?)(?=^##\s+|\Z)", text)
    best_rows = markdown_rows(best_match.group(1)) if best_match else []
    if best_rows and best_rows[0] and "场景" in best_rows[0][0]:
        best_rows = best_rows[1:]
    warnings = [clean_markdown(line, 220) for line in text.splitlines() if "⚠" in line or "CV=" in line]
    baseline_id = baseline_match.group(1).strip() if baseline_match else None
    baseline_path = (
        SPEC / "50-verification" / "baselines" / f"{baseline_id}.md" if baseline_id else None
    )
    repo_head = git_head()
    golden_raw = trunk_match.group(1) if trunk_match else None
    golden_full = None
    if golden_raw:
        code, resolved = git("rev-parse", "--verify", f"{golden_raw}^{{commit}}")
        if code == 0 and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", resolved):
            golden_full = resolved
    if not golden_raw:
        golden_head_status = "missing"
    elif not golden_full:
        golden_head_status = "golden_unresolvable"
    elif golden_full == repo_head:
        golden_head_status = "aligned"
    else:
        golden_head_status = "head_ahead_of_golden"
    return {
        "protocol": "sustained",
        "golden_index_path": rel(index_path),
        "baseline_id": baseline_id,
        "baseline_path": rel(baseline_path) if baseline_path else None,
        "status": golden_head_status
        if baseline_path and baseline_path.is_file()
        else "missing",
        "baseline_file_exists": bool(baseline_path and baseline_path.is_file()),
        "trunk_sha": golden_raw,
        "golden_sha_full": golden_full,
        "golden_head_status": golden_head_status,
        "repo_head_full": repo_head,
        "configs": list(config_match.groups()) if config_match else [],
        "best_config": "cfg-m24-ef60" if "cfg-m24-ef60" in text else None,
        "best_scenes": best_rows,
        "warnings": warnings,
        "sla_summary": clause_summary(read_text(SPEC / "40-constraints" / "sla.md"), "CON-SLA-020"),
    }


def roadmap_summary() -> list[dict[str, Any]]:
    path = SPEC / "open" / "optimization-roadmap.md"
    text = read_text(path)
    match = re.search(r"(?ms)^##\s+P3 路线图.*?$\n(.*?)(?=^##\s+|\Z)", text)
    rows = markdown_rows(match.group(1)) if match else []
    items = []
    for row in rows:
        if not row or row[0] in {"#", "---"} or not row[0].startswith("P3-"):
            continue
        items.append(
            {
                "id": row[0],
                "item": row[1] if len(row) > 1 else "",
                "goal": row[2] if len(row) > 2 else "",
                "complexity": row[3] if len(row) > 3 else "",
                "priority": row[4] if len(row) > 4 else "",
                "reference": row[5] if len(row) > 5 else "",
                "path": rel(path),
            }
        )
    return items


def business_risks(views: list[dict[str, Any]], performance: dict[str, Any]) -> list[dict[str, Any]]:
    active = [view for view in views if view["lifecycle"] in {"exploring", "blocked"}]
    stale = [view["topic_id"] for view in views if view["baseline_status"] == "stale"]
    conflicts = []
    for view in active:
        for conflict in view["health"]["conflicts"]:
            pair = sorted((view["topic_id"], conflict["topic"]))
            if pair not in [entry["topics"] for entry in conflicts]:
                conflicts.append({"topics": pair, "surface": conflict["surface"]})
    risks: list[dict[str, Any]] = []
    if stale:
        risks.append({"kind": "stale_baselines", "severity": "warning", "topics": stale})
    if conflicts:
        risks.append({"kind": "surface_conflicts", "severity": "warning", "items": conflicts})
    for warning in performance["warnings"]:
        risks.append({"kind": "golden_variance", "severity": "warning", "message": warning})
    risks.extend(
        [
            {
                "kind": "architecture_debt",
                "severity": "info",
                "message": "God class, friend coupling, and runtime knob sprawl remain recorded debt",
                "path": "spec/10-architecture/modules.md#ARCH-007",
            },
            {
                "kind": "measurement_trap",
                "severity": "info",
                "message": "Cache-warmed/short-query results must not replace sustained evidence",
                "path": "spec/open/optimization-roadmap.md",
            },
        ]
    )
    return risks


def probe_openclaw() -> dict[str, Any]:
    executable = shutil.which("openclaw")
    if not executable:
        return {"reachable": False, "error": "openclaw_cli_missing", "probed_at": now_iso()}
    proc = subprocess.run(
        [executable, "health", "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=10,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "reachable": False,
            "error": "invalid_health_json",
            "exit_code": proc.returncode,
            "probed_at": now_iso(),
        }
    sessions = payload.get("sessions", {}).get("recent", [])
    return {
        "reachable": bool(payload.get("ok")) and proc.returncode == 0,
        "degraded": bool(payload.get("eventLoop", {}).get("degraded")),
        "sessions": sessions,
        "channels": {
            name: {
                "enabled": value.get("enabled"),
                "running": value.get("running"),
                "health_state": value.get("healthState"),
            }
            for name, value in payload.get("channels", {}).items()
        },
        "probed_at": now_iso(),
    }


def runtime_status(probe: bool = False) -> dict[str, Any]:
    agents_text = read_text(ROOT / "AGENTS.md")
    session_match = re.search(r"ACP 长连接会话 ID：`([^`]+)`", agents_text)
    openclaw_match = re.search(r"OpenClaw 指挥会话 session_key：`([^`]+)`", agents_text)
    openclaw_probe = probe_openclaw() if probe else None
    configured_key = openclaw_match.group(1) if openclaw_match else "agent:main:main"
    recent_keys = {
        item.get("key")
        for item in (openclaw_probe or {}).get("sessions", [])
        if isinstance(item, dict)
    }
    leases = active_runtime_leases()
    return {
        "implementation": {
            "provider": "claude-code-acp",
            "status": "active" if leases else "unavailable",
            "pipeline_reachable": False,
            "active_runs": leases,
            "default_session": session_match.group(1) if session_match else None,
            "state_source": "pipeline",
            "cli_available": bool(shutil.which("claude")),
            "probe_note": "Claude CLI presence is not ACP pipeline/run evidence",
            "workspace": project_workspace_view(),
        },
        "control": {
            "provider": "openclaw",
            "default_session_key": configured_key,
            "reachable": openclaw_probe.get("reachable") if openclaw_probe else None,
            "configured_session_visible": configured_key in recent_keys if probe else None,
            "state_source": "gateway",
            "probe": openclaw_probe,
            "workspace": project_workspace_view(),
        },
    }


def openclaw_session_key() -> str:
    agents_text = read_text(ROOT / "AGENTS.md")
    match = re.search(r"OpenClaw 指挥会话 session_key：`([^`]+)`", agents_text)
    return match.group(1) if match else "agent:main:main"


def read_openclaw_workspace() -> dict[str, Any] | None:
    state_path = ROOT / ".openclaw" / "state.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(read_text(state_path))
    except json.JSONDecodeError:
        return None
    workspace = data.get("workspace")
    return workspace if isinstance(workspace, dict) else None


def workspace_binding(topic: str | None) -> dict[str, Any]:
    topic_dir = f"poc/{topic}/" if topic else None
    return {
        "repo_root": str(ROOT),
        "repo_name": ROOT.name,
        "repo_head": git_head(),
        "state_path": ".openclaw/state.json",
        "active_topic": topic,
        "topic_dir": topic_dir,
        "topic_ndf_dir": f"{topic_dir}ndf/" if topic_dir else None,
    }


def project_workspace_view() -> dict[str, Any]:
    binding = workspace_binding(None)
    persisted = read_openclaw_workspace()
    truth = workspace_truth(binding, persisted)
    return {
        "binding": binding,
        "persisted": persisted,
        "match": truth["workspace_bound"],
        "state": truth["state"],
        "truth": truth,
        "state_file": str(ROOT / ".openclaw" / "state.json"),
        "state_exists": (ROOT / ".openclaw" / "state.json").is_file(),
    }


def workspace_truth_view(topic: str | None) -> dict[str, Any]:
    return workspace_truth(workspace_binding(topic), read_openclaw_workspace())


def next_human_phrase(view: dict[str, Any]) -> str | None:
    gates = view["gates"]
    if view["phase_hint"] == "legacy_gate_audit":
        return GATE_PHRASES["topic_review"]
    if gates["topic_review"]["state"] != "valid":
        return GATE_PHRASES["topic_review"]
    if gates["design_review"]["state"] != "valid":
        return GATE_PHRASES["design_review"]
    if gates["implementation_approval"]["state"] != "valid":
        return GATE_PHRASES["implementation_approval"]
    return None


def required_reads_for_task(task: str, topic: str) -> list[str]:
    base_meta = ["META-010", "BEH-025", "META-011"]
    binder = [f"poc/{topic}/ndf/TOPIC.md", f"poc/{topic}/ndf/GATES.md"]
    if task == "legacy_gate_audit":
        return base_meta + binder + [
            f"poc/{topic}/ndf/DESIGN.md",
            f"poc/{topic}/ndf/PERF_BASELINE.md",
            f"poc/{topic}/ndf/INTERFACE.md",
        ]
    if task == "gate_sha_audit":
        return ["META-010"] + binder
    if task == "gate_receipt_draft":
        return ["META-010", "BEH-025"] + binder
    if task == "binder_amend":
        return base_meta + [
            f"poc/{topic}/ndf/TOPIC.md",
            f"poc/{topic}/ndf/DESIGN.md",
            f"poc/{topic}/ndf/INTERFACE.md",
            f"poc/{topic}/ndf/PERF_BASELINE.md",
        ]
    if task == "control_proposal":
        return ["AGENTS.md", "META-011", f"poc/{topic}/ndf/TOPIC.md"]
    return base_meta + binder


def genesis_paths() -> dict[str, Path]:
    return {
        "proposal": SPEC / "open" / "proposal-project-genesis.md",
        "idea": SPEC / "open" / "project-genesis" / "IDEA.md",
        "foundation": SPEC / "open" / "project-genesis" / "FOUNDATION.md",
        "gates": SPEC / "open" / "project-genesis" / "GATES.md",
        "decision": SPEC / "decisions" / "dec-project-genesis.md",
    }


def genesis_status() -> dict[str, Any]:
    paths = genesis_paths()
    decision_text = read_text(paths["decision"])
    accepted = "accepted" in (header(decision_text, "Status") or "").lower()
    bound_sha = header(decision_text, "genesis_trunk_sha")
    resolvable = False
    if bound_sha and not re.search(r"(?i)pending|tbd|unknown", bound_sha):
        code, _ = git("rev-parse", "--verify", f"{bound_sha}^{{commit}}")
        resolvable = code == 0
    has_charter = (SPEC / "00-charter").is_dir() and any((SPEC / "00-charter").glob("*.md"))
    has_src = (ROOT / "src").is_dir() and any((ROOT / "src").rglob("*"))
    clause_count = 0
    for path in SPEC.glob("[0-5][0-9]-*/**/*.md"):
        clause_count += len(re.findall(r"\{#[A-Z][A-Z0-9-]+\}", read_text(path)))
    if accepted and resolvable:
        maturity = "operational"
    elif paths["proposal"].is_file() or paths["idea"].is_file():
        if paths["foundation"].is_file():
            maturity = "ndf_foundation" if not has_src else "trunk_candidate"
        else:
            maturity = "idea_review"
    elif has_charter and has_src and clause_count:
        maturity = "operational_legacy"
    elif has_charter:
        maturity = "ndf_foundation"
    else:
        maturity = "uninitialized"
    if maturity == "operational":
        rail_state = ("completed", "completed", "completed", "completed")
    elif maturity == "operational_legacy":
        rail_state = ("legacy", "legacy", "legacy", "legacy")
    elif maturity == "trunk_candidate":
        rail_state = ("completed", "completed", "in_progress", "pending")
    elif maturity == "ndf_foundation":
        rail_state = ("completed", "in_progress", "pending", "pending")
    elif maturity == "idea_review":
        rail_state = ("in_progress", "pending", "pending", "pending")
    else:
        rail_state = ("pending", "pending", "pending", "pending")
    rail = [
        {
            "id": "G0",
            "label": "IDEA",
            "state": rail_state[0],
            "path": rel(paths["idea"]),
            "content_sha": file_sha(paths["idea"]),
            "next_phrase": "IDEA已审核",
        },
        {
            "id": "G1",
            "label": "Foundation",
            "state": rail_state[1],
            "path": rel(paths["foundation"]),
            "content_sha": file_sha(paths["foundation"]),
            "next_phrase": "VERIFICATION已审核",
        },
        {
            "id": "G2",
            "label": "Trunk Candidate",
            "state": rail_state[2],
            "path": rel(paths["gates"]),
            "content_sha": file_sha(paths["gates"]),
            "next_phrase": "可以建立初始主线",
        },
        {
            "id": "G3",
            "label": "Freeze",
            "state": rail_state[3],
            "path": rel(paths["decision"]),
            "content_sha": file_sha(paths["decision"]),
            "next_phrase": "GENESIS已审核",
        },
    ]
    return {
        "project_maturity": maturity,
        "accepted": accepted,
        "genesis_trunk_sha": bound_sha,
        "genesis_trunk_sha_resolves": resolvable,
        "clause_count": clause_count,
        "paths": {name: {"path": rel(path), "exists": path.is_file()} for name, path in paths.items()},
        "rail": rail,
        "next_step": next(
            (
                {"id": item["id"], "label": item["label"], "phrase": item["next_phrase"]}
                for item in rail
                if item["state"] in {"pending", "in_progress"}
            ),
            None,
        ),
        "warning": "Genesis provenance missing; legacy operational project"
        if maturity == "operational_legacy"
        else None,
    }


def topic_business_summary(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic_id": view["topic_id"],
        "path": view["path"],
        "lifecycle": view["lifecycle"],
        "phase_hint": view["phase_hint"],
        "hypothesis": view["business"]["hypothesis"],
        "expected_impact": view["business"]["expected_impact"],
        "current_evidence": view["business"]["current_evidence"],
        "next_gate": view["business"]["next_gate"],
        "explore_surface": view["explore_surface"],
        "baseline_status": view["baseline_status"],
        "control_blockers": view["health"]["blockers"],
        "surface_conflicts": view["health"]["conflicts"],
        "gates": {
            name: {
                "state": gate["state"],
                "phrase": GATE_PHRASES.get(name),
                "expected_content_sha": gate.get("expected_content_sha"),
            }
            for name, gate in view["gates"].items()
        },
        "next_human_phrase": next_human_phrase(view),
    }


def topic_health(topic: str, persist: bool = True) -> tuple[dict[str, Any], int]:
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    generation_sha = source_generation_sha()
    view = topic_view(topic_dir)
    findings = view["health"]["findings"]
    previous = read_json_artifact(topic_health_artifact(topic)) or {}
    previous_kinds = {
        str(item.get("kind"))
        for item in previous.get("findings", [])
        if isinstance(item, dict) and item.get("kind")
    }
    current_kinds = {
        str(item.get("kind"))
        for item in findings
        if isinstance(item, dict) and item.get("kind")
    }
    payload = {
        "schema": "ndf-topic-health/v1",
        "generated_at": now_iso(),
        "snapshot_sha": generation_sha,
        "repo_head": git_head(),
        "topic": view["topic_id"],
        "lifecycle": view["lifecycle"],
        "phase_hint": view["phase_hint"],
        "spaces": view["spaces"],
        "checks": view["health"]["checks"],
        "findings": findings,
        "findings_hash": canonical_json_sha(findings),
        "finding_diff": {
            "resolved": sorted(previous_kinds - current_kinds),
            "remaining": sorted(previous_kinds & current_kinds),
            "new": sorted(current_kinds - previous_kinds),
            "previous_findings_hash": previous.get("findings_hash"),
        },
        "next_actions": view["health"]["next_actions"],
        "delegation": view["delegation"],
        "state": "current",
    }
    if persist:
        write_json_artifact(topic_health_artifact(topic), payload)
    hard_errors = sum(1 for item in findings if item["severity"] == "error")
    return payload, 1 if hard_errors else 0


def project_check_findings(checks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name, check in checks.items():
        if check["exit_code"] == 0:
            continue
        is_bind = name == "binder_health"
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=f"{name}_failed",
                severity="error",
                evidence=clean_markdown(check["output"], 360) or "check failed",
                repair_owner="openclaw",
                repair_task="binder_amend" if is_bind else "control_proposal",
                allowed_write_root="poc/*/ndf/" if is_bind else "spec/meta/open/",
                human_gate=None if is_bind else "已确认 → 已审核",
            )
        )
    for warning in proposal_plane_warnings():
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=warning["kind"],
                severity=warning["severity"],
                evidence=warning["message"],
                repair_owner="openclaw",
                repair_task="control_proposal",
                allowed_write_root="spec/meta/open/",
                human_gate="已确认 → 已审核",
            )
        )
    return findings


def spec_health(persist: bool = True) -> tuple[dict[str, Any], int]:
    checks = {
        "meta_graph": run_tool(
            "ndf_graphcheck.py",
            "--meta",
            "--format",
            "text",
            "--report",
            "-",
        ),
        "product_graph": run_tool(
            "ndf_graphcheck.py",
            "--product",
            "--format",
            "text",
            "--report",
            "-",
        ),
        "index_consistency": run_tool("ndf_index.py", "validate"),
        "binder_health": run_tool(
            "ndf_bindcheck.py",
            "check",
            "--all-topics",
            "--report",
            "-",
        ),
    }
    findings = project_check_findings(checks)
    generation_sha = source_generation_sha()
    payload = {
        "schema": "ndf-spec-health/v1",
        "generated_at": now_iso(),
        "snapshot_sha": generation_sha,
        "repo_head": git_head(),
        "state": "current",
        "checks": {name: public_check(check) for name, check in checks.items()},
        "findings": findings,
        "next_actions": unique_actions(findings),
        "advisor": {
            "graph": "python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit",
            "bind": "python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit",
            "read_only": True,
        },
    }
    if persist:
        write_json_artifact(HEALTH_DIR / "spec.json", payload)
    hard_errors = sum(1 for item in findings if item["severity"] == "error")
    return payload, 1 if hard_errors else 0


def latest_spec_health(generation_sha: str) -> dict[str, Any] | None:
    payload = read_json_artifact(HEALTH_DIR / "spec.json")
    if payload is None:
        return None
    payload = dict(payload)
    payload["state"] = (
        "current" if payload.get("snapshot_sha") == generation_sha else "stale"
    )
    return payload


def replay_summary() -> dict[str, Any]:
    """Project local Replay evidence without creating or changing the store."""
    store = ndf_replay.ReplayStore(ROOT)
    if not store.root.is_dir():
        return {
            "schema": "ndf-replay-summary/v1",
            "state": "not_initialized",
            "fsck": None,
            "episodes": [],
        }
    fsck = store.fsck()
    episodes: list[dict[str, Any]] = []
    episode_refs = store.refs / "episodes"
    head_paths = sorted(episode_refs.glob("*/HEAD")) if episode_refs.is_dir() else []
    for head_path in head_paths:
        episode_id = head_path.parent.name
        try:
            head = head_path.read_text(encoding="utf-8").strip()
            commit = store.get_object(head, "commit")["data"]
            branch_events = store.read_all_events(episode_id)
            chains = {
                branch: validate_event_chain(events)
                for branch, events in branch_events.items()
            }
            events = sorted(
                [item for values in branch_events.values() for item in values],
                key=lambda item: (
                    str(item.get("timestamp") or ""),
                    str(item.get("branch") or ""),
                    int(item.get("seq") or 0),
                ),
            )
            chain_valid = bool(chains) and all(
                item["valid"] for item in chains.values()
            )
            audit = store.audit(head, strict=True)
        except (FileNotFoundError, ValueError, KeyError) as exc:
            episodes.append(
                {
                    "id": episode_id,
                    "state": "invalid",
                    "error": str(exc),
                    "levels": {"R0": False, "R1": False, "R2": False, "R3": True},
                }
            )
            continue
        kinds = {event.get("kind") for event in events}
        coverage = commit.get("coverage", {})
        bound_manifest_sha = commit.get("manifest_sha")
        bound_plan_sha = commit.get("context_plan_sha")
        for _, historical in store.walk_commits(head):
            bound_manifest_sha = bound_manifest_sha or historical.get("manifest_sha")
            bound_plan_sha = bound_plan_sha or historical.get("context_plan_sha")
            if bound_manifest_sha and bound_plan_sha:
                break
        manifest_summary: dict[str, Any] | None = None
        context_summary: dict[str, Any] | None = None
        if bound_manifest_sha:
            try:
                _, recorded_manifest = store.find_blob(
                    schema="ndf-task-manifest/v1",
                    semantic_field="manifest_sha",
                    semantic_sha=str(bound_manifest_sha),
                )
                manifest_summary = {
                    "intent": recorded_manifest.get("intent"),
                    "businessGoal": recorded_manifest.get("business_goal"),
                    "seeds": recorded_manifest.get("clause_seeds", []),
                    "graphNodes": len(
                        recorded_manifest.get("shared_graph_closure", {}).get(
                            "nodes", []
                        )
                    ),
                    "gates": recorded_manifest.get("human_gates"),
                    "baseline": recorded_manifest.get("baseline"),
                }
            except ValueError:
                pass
        recorded_plan: dict[str, Any] | None = None
        if bound_plan_sha:
            try:
                _, recorded_plan = store.find_blob(
                    schema=None,
                    schema_prefix="ndf-context-plan",
                    semantic_field="plan_sha",
                    semantic_sha=str(bound_plan_sha),
                )
                context_summary = {
                    "role": recorded_plan.get("role"),
                    "task": recorded_plan.get("task"),
                    "orderedReads": [
                        item.get("path")
                        for item in recorded_plan.get("ordered_reads", [])
                    ],
                    "writeRoots": recorded_plan.get("privileges", {}).get(
                        "allowed_write_roots", []
                    ),
                    "humanPhrase": recorded_plan.get("human_phrase"),
                }
            except ValueError:
                pass
        observations: list[dict[str, Any]] = []
        sandbox_commands: list[list[str]] = []
        changed_files: set[str] = set()
        gate_events: list[dict[str, Any]] = []
        r2_outcome = "not_run"
        recorded_r2_profile: dict[str, Any] | None = None
        for replay_event in events:
            try:
                obj = store.get_object(str(replay_event.get("payload_sha") or ""))
            except (FileNotFoundError, ValueError):
                continue
            data = obj.get("data", {})
            if obj.get("type") == "tool-cassette":
                if data.get("replay_policy") == "sandbox":
                    sandbox_commands.append(list(data.get("argv", [])))
                observations.append(
                    {
                        "kind": "tool",
                        "name": data.get("name"),
                        "policy": data.get("replay_policy"),
                        "sha": replay_event.get("payload_sha"),
                    }
                )
            elif obj.get("type") == "model-turn":
                observations.append(
                    {
                        "kind": "model",
                        "name": data.get("model_id"),
                        "policy": "recorded-response",
                        "sha": replay_event.get("payload_sha"),
                    }
                )
            elif obj.get("type") == "blob" and isinstance(data.get("value"), dict):
                value = data["value"]
                changed_files.update(
                    str(item) for item in value.get("changed_files", [])
                )
                if replay_event.get("kind") == "gate.approved":
                    gate_events.append(
                        {
                            "gate": value.get("gate") or value.get("step"),
                            "approvedBy": value.get("approved_by"),
                            "sourceRef": value.get("source_ref"),
                            "payloadSha": replay_event.get("payload_sha"),
                        }
                    )
                if (
                    replay_event.get("kind") == "verification.completed"
                    and value.get("schema") == "ndf-replay-sandbox/v1"
                ):
                    r2_outcome = str(value.get("state") or "unknown")
                    if isinstance(value.get("profile"), dict):
                        recorded_r2_profile = value["profile"]
        complete_observations = bool(
            {"tool.result", "model.response"} & kinds
            or coverage.get("runtime_stream") == "full_stream"
        )
        has_sandbox_cassette = any(
            item.get("kind") == "tool" and item.get("policy") == "sandbox"
            for item in observations
        )
        episodes.append(
            {
                "id": episode_id,
                "state": "verified" if audit["valid"] else "invalid",
                "head": head,
                "topic": commit.get("topic"),
                "task": commit.get("task"),
                "track": commit.get("track"),
                "actor": commit.get("actor"),
                "manifestSha": bound_manifest_sha,
                "planSha": bound_plan_sha,
                "coverage": coverage,
                "coverageGaps": audit.get("coverage_gaps", []),
                "joinGaps": audit.get("join_gaps", []),
                "semanticGaps": audit.get("semantic_gaps", []),
                "historicalIntegrity": audit.get("historical_integrity"),
                "historicalSemantics": audit.get("historical_semantics"),
                "currentRestoreReady": audit.get("current_restore_ready"),
                "currentDispatchReady": audit.get("current_dispatch_ready"),
                "currentReadinessErrors": audit.get(
                    "current_readiness_errors", []
                ),
                "manifestSummary": manifest_summary,
                "contextSummary": context_summary,
                "branches": {
                    name: {
                        "eventCount": value["count"],
                        "eventTip": value["tip_sha"],
                        "valid": value["valid"],
                    }
                    for name, value in chains.items()
                },
                "eventCount": len(events),
                "eventTip": canonical_json_sha(
                    {
                        name: value["tip_sha"]
                        for name, value in sorted(chains.items())
                    }
                ),
                "levels": {
                    "R0": bool(audit["valid"]),
                    "R1": bool(chain_valid and complete_observations),
                    "R2": bool(
                        chain_valid
                        and commit.get("repo_head")
                        and audit["valid"]
                        and audit.get("current_restore_ready") is True
                        and bound_manifest_sha
                        and bound_plan_sha
                        and has_sandbox_cassette
                    ),
                    "R3": True,
                },
                "observations": observations[-100:],
                "r2Outcome": r2_outcome,
                "r2Profile": {
                    "adapter": (
                        (recorded_r2_profile or {}).get("adapter", ["bwrap"])[0]
                        if (recorded_r2_profile or {}).get("adapter", ["bwrap"])
                        else "bwrap"
                    ),
                    "network": (recorded_r2_profile or {}).get(
                        "network", "none"
                    ),
                    "commands": (recorded_r2_profile or {}).get(
                        "commands", sandbox_commands
                    ),
                    "allowedWriteRoots": (recorded_r2_profile or {}).get(
                        "allowed_write_roots",
                        (
                            recorded_plan.get("privileges", {}).get(
                                "allowed_write_roots", []
                            )
                            if recorded_plan
                            else []
                        ),
                    ),
                    "confirmCost": (recorded_r2_profile or {}).get(
                        "confirm_cost", False
                    ),
                    "confirmSideEffects": (recorded_r2_profile or {}).get(
                        "confirm_side_effects", False
                    ),
                },
                "changedFiles": sorted(changed_files),
                "gateEvents": gate_events[-50:],
                "timeline": [
                    {
                        "seq": event.get("seq"),
                        "timestamp": event.get("timestamp"),
                        "kind": event.get("kind"),
                        "actor": event.get("actor"),
                        "payloadSha": event.get("payload_sha"),
                        "branch": event.get("branch"),
                    }
                    for event in events[-100:]
                ],
            }
        )
    return {
        "schema": "ndf-replay-summary/v1",
        "state": "verified" if fsck["valid"] else "invalid",
        "fsck": fsck,
        "episodes": episodes,
    }


def snapshot(topic: str | None, probe_runtime: bool = False) -> dict[str, Any]:
    views = list_topic_views()
    selected = None
    if topic:
        selected = next((view for view in views if view["topic_id"] == topic or Path(view["path"]).name == topic), None)
        if selected is None:
            raise FileNotFoundError(f"unknown topic: {topic}")
    active = [view for view in views if view["lifecycle"] in {"exploring", "blocked"}]
    product_proposals, process_proposals = scan_proposals()
    performance = performance_summary()
    blockers = sum(len(view["health"]["blockers"]) for view in active)
    legacy_gates = sum(
        1
        for view in active
        if any(gate["state"] == "legacy_unknown" for gate in view["gates"].values())
    )
    invalidated = sum(
        1
        for view in active
        for gate in view["gates"].values()
        if gate["state"] == "invalidated"
    )
    meta_graph = META / "graph.json"
    meta_graph_data: dict[str, Any] = {}
    if meta_graph.is_file():
        try:
            meta_graph_data = json.loads(read_text(meta_graph))
        except json.JSONDecodeError:
            meta_graph_data = {}
    identity = business_identity()
    active_summaries = [topic_business_summary(view) for view in active]
    primary = active_summaries[0] if active_summaries else None
    details = list(active)
    if selected and selected not in details:
        details.append(selected)
    generation_sha = source_generation_sha()
    for detail in details:
        detail["health"]["latest_diagnosis"] = latest_topic_health(
            detail["topic_id"],
            generation_sha,
        )
    spec_health_view = latest_spec_health(generation_sha)
    payload = {
        "schema": "ndf-workflow-snapshot/v2",
        "generated_at": now_iso(),
        "repo_head": git_head(),
        "snapshot_sha": generation_sha,
        "evidence_generation": generation_sha,
        "embedded_projection": {
            "status": "unknown",
            "verified_path": None,
        },
        "payload_binding": {
            "repo_head": git_head(),
            "source_generation_sha": generation_sha,
        },
        "projection_freshness": projection_freshness(generation_sha),
        "business": {
            "identity": identity,
            "goals": business_goals(),
            "capabilities": capability_portfolio(),
            "performance": performance,
            "roadmap": roadmap_summary(),
            "product_proposals": product_proposals,
            "topics": active_summaries,
            "risks": business_risks(views, performance),
            "now_next_blocked": {
                "now": primary["topic_id"] if primary else f"{identity['name']} Trunk",
                "next": (
                    primary["next_gate"]
                    or primary["phase_hint"]
                    if primary
                    else "Review product roadmap"
                ),
                "blocked": blockers,
            },
        },
        "control": {
            "genesis": genesis_status(),
            "process_proposals": process_proposals,
            "close": close_projection(active),
            "spec_health": {
                "meta_clause_count": meta_graph_data.get("clause_count"),
                "meta_graph_index_generated_at": meta_graph_data.get("generated_at"),
                "meta_graphcheck": (
                    (spec_health_view or {}).get("checks", {})
                    .get("meta_graph", {})
                    .get("state", "not_run")
                ),
                "state": (spec_health_view or {}).get("state", "not_run"),
                "checks": (spec_health_view or {}).get("checks", {}),
                "findings": (spec_health_view or {}).get("findings", []),
                "next_actions": (spec_health_view or {}).get("next_actions", []),
                "advisor": (spec_health_view or {}).get(
                    "advisor",
                    {"read_only": True},
                ),
                "proposal_plane_warnings": proposal_plane_warnings(),
            },
            "gate_summary": {
                "legacy_unknown_topics": legacy_gates,
                "invalidated_receipts": invalidated,
            },
        },
        "runtime": runtime_status(probe_runtime),
        "replay": replay_summary(),
        "topics_detail": details,
        "selected_topic": selected,
    }
    return payload


def canvas_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the stable, camelCase payload embedded by the Cursor Canvas."""
    business = payload["business"]
    performance = business["performance"]
    detail_by_id = {
        item["topic_id"]: item for item in payload.get("topics_detail", [])
    }
    topics = []
    for item in business["topics"]:
        detail = detail_by_id.get(item["topic_id"], {})
        spaces = detail.get("spaces", {})
        topics.append(
            {
                "id": item["topic_id"],
                "path": item["path"],
                "lifecycle": item["lifecycle"],
                "hypothesis": item["hypothesis"],
                "expectedImpact": item["expected_impact"],
                "surface": [
                    value.rsplit("/", 1)[-1] for value in item["explore_surface"]
                ],
                "evidenceFiles": item["current_evidence"]["evidence_files"],
                "numbers": item["current_evidence"]["numbers"],
                "baseline": item["baseline_status"],
                "phase": item["phase_hint"].replace("_", " "),
                "spaces": spaces,
                "blockers": item["control_blockers"],
                "conflicts": item["surface_conflicts"],
                "gates": {
                    name: {
                        "state": gate["state"],
                        "phrase": gate["phrase"],
                        "expectedContentSha": gate.get("expected_content_sha"),
                        "approvedContentSha": detail.get("gates", {})
                        .get(name, {})
                        .get("approved_content_sha"),
                        "shaAligned": detail.get("gates", {})
                        .get(name, {})
                        .get("sha_aligned", False),
                    }
                    for name, gate in item["gates"].items()
                },
                "nextHumanPhrase": item["next_human_phrase"],
                "delta": detail.get("delta", {}),
                "traceability": detail.get("traceability", []),
                "delegation": detail.get("delegation", {}),
                "health": detail.get("health", {}),
            }
        )
    scenes = performance.get("best_scenes", [])
    capabilities = []
    for capability in business["capabilities"]:
        clauses = capability["clauses"]
        capabilities.append(
            [
                capability["name"],
                clauses["stable"],
                clauses["draft"],
                clauses["deprecated"],
                " + ".join(capability["modules"][:2]),
            ]
        )
    close_topics = []
    for item in payload["control"]["close"]["topics"]:
        close_topics.append(
            {
                "topicId": item["topic_id"],
                "lifecycle": item["lifecycle"],
                "evidenceReady": item["evidence_ready"],
                "proposalReady": item["proposal_ready"],
                "closePlanReady": item["close_plan"]["ready"],
                "finalizationReady": item["finalization_ready"],
                "steps": item["steps"],
                "branches": {
                    mode: {
                        "mode": branch["mode"],
                        "proposalReady": branch["proposal_ready"],
                        "closePlanReady": branch["close_plan_ready"],
                        "verificationRequired": branch["verification_required"],
                        "finalizationReady": branch["finalization_ready"],
                        "finalized": branch["finalized"],
                        "steps": branch["steps"],
                        "nextStep": branch["next_step"],
                    }
                    for mode, branch in item.get("branches", {}).items()
                },
                "nextStep": item["next_step"],
                "blockers": item["blockers"],
            }
        )
    implementation = payload["runtime"]["implementation"]
    control_runtime = payload["runtime"]["control"]
    result = {
        "schema": "ndf-workflow-canvas-snapshot/v1",
        "generatedAt": payload["generated_at"],
        "repoHead": (payload["repo_head"] or "")[:12],
        "snapshotSha": payload["snapshot_sha"],
        "evidenceGeneration": payload.get("evidence_generation"),
        "embeddedProjection": payload.get("embedded_projection"),
        "payloadBinding": payload.get("payload_binding"),
        "projectionFreshness": payload["projection_freshness"],
        "absorbedActionId": (
            (payload.get("projection_freshness", {}).get("latest_action") or {}).get("action_id")
            if (payload.get("projection_freshness", {}).get("latest_action") or {}).get("status")
            == "finished"
            else None
        ),
        "business": {
            "identity": {
                "name": business["identity"]["name"],
                "phase": business["identity"]["phase"],
                "goal": business["identity"]["goal_summary"],
                "charterPath": business["identity"]["charter_path"],
                "scales": [
                    [entry["scale"], entry["status"]]
                    for entry in business["identity"]["scale_coverage"]
                ],
            },
            "performance": {
                "protocol": performance["protocol"],
                "baselineId": performance["baseline_id"],
                "goldenSha": (performance.get("trunk_sha") or "")[:12],
                "goldenHeadStatus": performance.get("golden_head_status"),
                "repoHeadFull": performance.get("repo_head_full"),
                "status": performance["status"],
                "configs": performance["configs"],
                "scenes": [row[0] for row in scenes],
                "aggQps": [int(row[1].replace(",", "")) for row in scenes],
                "steadyQps": [int(row[2].replace(",", "")) for row in scenes],
                "recall": [row[3] for row in scenes],
                "warning": performance["warnings"][0]
                if performance["warnings"]
                else None,
            },
            "capabilities": capabilities,
            "topics": topics,
            "proposals": [
                [
                    proposal["title"],
                    proposal["track"] or "unknown",
                    proposal["status"],
                ]
                for proposal in business["product_proposals"]
            ],
            "roadmap": [
                [
                    item["id"],
                    item["item"],
                    item["goal"],
                    item["priority"],
                    item["reference"],
                ]
                for item in business["roadmap"]
            ],
            "risks": business["risks"],
            "nowNextBlocked": business["now_next_blocked"],
        },
        "control": {
            "maturity": payload["control"]["genesis"]["project_maturity"],
            "genesis": payload["control"]["genesis"],
            "metaClauses": payload["control"]["spec_health"]["meta_clause_count"],
            "metaGraph": payload["control"]["spec_health"],
            "legacyUnknownTopics": payload["control"]["gate_summary"][
                "legacy_unknown_topics"
            ],
            "invalidatedReceipts": payload["control"]["gate_summary"][
                "invalidated_receipts"
            ],
            "processProposals": [
                [proposal["title"], proposal["status"]]
                for proposal in payload["control"]["process_proposals"]
            ],
            "proposalPlaneWarnings": [
                [
                    warning["path"],
                    warning.get("track") or "",
                    warning["message"],
                ]
                for warning in payload["control"]["spec_health"].get(
                    "proposal_plane_warnings", []
                )
            ],
            "close": {
                "stateSource": payload["control"]["close"]["state_source"],
                "topics": close_topics,
            },
        },
        "runtime": {
            "implementation": {
                "provider": implementation["provider"],
                "status": implementation["status"],
                "pipelineReachable": implementation["pipeline_reachable"],
                "defaultSession": implementation["default_session"],
                "activeRuns": implementation["active_runs"],
                "cliAvailable": implementation.get("cli_available"),
                "probeNote": implementation.get("probe_note"),
                "workspace": {
                    "binding": {
                        "repoRoot": implementation["workspace"]["binding"][
                            "repo_root"
                        ],
                        "statePath": implementation["workspace"]["binding"][
                            "state_path"
                        ],
                        "activeTopic": implementation["workspace"]["binding"].get(
                            "active_topic"
                        ),
                    },
                    "stateExists": implementation["workspace"]["state_exists"],
                    "match": implementation["workspace"].get("match"),
                    "state": implementation["workspace"].get("state"),
                },
            },
            "control": {
                "provider": control_runtime["provider"],
                "defaultSessionKey": control_runtime["default_session_key"],
                "reachable": control_runtime["reachable"],
                "configuredSessionVisible": control_runtime.get(
                    "configured_session_visible"
                ),
                "probe": control_runtime.get("probe"),
                "workspace": {
                    "binding": {
                        "repoRoot": control_runtime["workspace"]["binding"][
                            "repo_root"
                        ],
                        "statePath": control_runtime["workspace"]["binding"][
                            "state_path"
                        ],
                        "activeTopic": control_runtime["workspace"]["binding"].get(
                            "active_topic"
                        ),
                    },
                    "stateExists": control_runtime["workspace"]["state_exists"],
                    "match": control_runtime["workspace"].get("match"),
                    "state": control_runtime["workspace"].get("state"),
                },
            },
        },
        "replay": payload.get("replay", {
            "schema": "ndf-replay-summary/v1",
            "state": "not_initialized",
            "fsck": None,
            "episodes": [],
        }),
    }
    result["payloadSha"] = canvas_payload_sha(result)
    return result


def canvas_payload_sha(payload: Mapping[str, Any]) -> str:
    """Hash stable Canvas semantics, excluding volatile observation timestamps."""

    volatile = {
        "payloadSha",
        "generatedAt",
        "generated_at",
        "evaluated_at",
        "probed_at",
        "started_at",
        "finished_at",
        "summary",
        "age",
    }

    def stable(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: stable(item)
                for key, item in sorted(value.items())
                if key not in volatile
            }
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    return canonical_json_sha(stable(dict(payload)))


def verify_embedded_snapshot(path: Path, *, topic: str | None = None) -> dict[str, Any]:
    """Compare a managed TSX ``const SNAPSHOT`` object with a fresh payload."""
    text = read_text(path)
    match = re.search(r"\bconst\s+SNAPSHOT\b[^=]*=", text)
    if not match:
        raise ValueError(f"const SNAPSHOT JSON not found: {path}")
    tail = text[match.end() :].lstrip()
    try:
        embedded, _ = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid embedded SNAPSHOT JSON: {exc}") from exc
    if not isinstance(embedded, dict):
        raise ValueError("embedded SNAPSHOT must be a JSON object")
    probe_runtime = bool(
        embedded.get("runtime", {}).get("control", {}).get("probe")
    )
    fresh = canvas_snapshot(snapshot(topic, probe_runtime))
    embedded_hash = canvas_payload_sha(embedded)
    checks = {
        "snapshotSha": embedded.get("snapshotSha") == fresh.get("snapshotSha"),
        "payloadSha": (
            embedded.get("payloadSha") == embedded_hash
            and embedded.get("payloadSha") == fresh.get("payloadSha")
        ),
        "absorbedActionId": embedded.get("absorbedActionId")
        == fresh.get("absorbedActionId"),
    }
    return {
        "schema": "ndf-embedded-projection-verification/v1",
        "valid": all(checks.values()),
        "path": rel(path),
        "checks": checks,
        "embedded": {
            "snapshotSha": embedded.get("snapshotSha"),
            "payloadSha": embedded.get("payloadSha"),
            "canonicalPayloadSha": embedded_hash,
            "absorbedActionId": embedded.get("absorbedActionId"),
        },
        "fresh": {
            "snapshotSha": fresh.get("snapshotSha"),
            "payloadSha": fresh.get("payloadSha"),
            "absorbedActionId": fresh.get("absorbedActionId"),
        },
    }


def update_embedded_snapshot(path: Path, *, topic: str | None = None) -> dict[str, Any]:
    """Atomically replace the managed Canvas SNAPSHOT with official JSON."""
    text = read_text(path)
    match = re.search(r"\bconst\s+SNAPSHOT\b[^=]*=", text)
    if not match:
        raise ValueError(f"const SNAPSHOT JSON not found: {path}")
    tail = text[match.end() :].lstrip()
    leading = len(text[match.end() :]) - len(tail)
    try:
        _, consumed = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid embedded SNAPSHOT JSON: {exc}") from exc
    payload = canvas_snapshot(snapshot(topic, True))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    start = match.end() + leading
    updated = text[:start] + rendered + tail[consumed:]
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    verification = verify_embedded_snapshot(path, topic=topic)
    return {
        "schema": "ndf-embedded-projection-update/v1",
        "updated": verification["valid"],
        "path": str(path),
        "payloadSha": payload.get("payloadSha"),
        "snapshotSha": payload.get("snapshotSha"),
        "absorbedActionId": payload.get("absorbedActionId"),
        "verification": verification,
    }


def record_projection_verification(
    source_path: Path,
    verification: Mapping[str, Any],
    *,
    topic: str | None,
    episode_id: str | None,
) -> dict[str, Any]:
    """Persist an evidence-bound embedded projection receipt."""
    if episode_id:
        store = ndf_replay.ReplayStore(ROOT)
        if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
            raise ValueError(f"unknown replay episode: {episode_id}")
    timestamp = now_iso()
    evidence = {
        "schema": "ndf-embedded-projection-evidence/v1",
        "source_path": str(source_path.resolve()),
        "source_file_sha": file_sha(source_path),
        "topic": topic,
        "checks": dict(verification.get("checks") or {}),
        "embedded": dict(verification.get("embedded") or {}),
        "fresh": dict(verification.get("fresh") or {}),
    }
    evidence_name = (
        "embedded-"
        f"{str((verification.get('embedded') or {}).get('canonicalPayloadSha') or 'unknown')}.json"
    )
    evidence_path = PROJECTION_EVIDENCE_DIR / evidence_name
    write_json_artifact(evidence_path, evidence)
    evidence_rel = rel(evidence_path)
    output_sha = evidence_bundle_sha([evidence_rel], root=ROOT)
    receipt = {
        "schema": "ndf-projection-receipt/v2",
        "task": "snapshot_embedded",
        "topic": topic,
        "mode": "process",
        "step": "verify-embedded",
        "repo_head": git_head(),
        "source_generation_sha": (verification.get("fresh") or {}).get("snapshotSha"),
        "manifest_sha": None,
        "context_plan_sha": None,
        "command": "ndf_workflow_status.py snapshot --verify-embedded",
        "input_sha": file_sha(source_path),
        "output_sha": output_sha,
        "evidence_paths": [evidence_rel],
        "started_at": timestamp,
        "finished_at": timestamp,
        "result": "passed" if verification.get("valid") else "failed",
        "blockers": [] if verification.get("valid") else ["embedded_projection_mismatch"],
        "projection_sha": (verification.get("embedded") or {}).get(
            "canonicalPayloadSha"
        ),
        "snapshot_sha_after": (verification.get("fresh") or {}).get("snapshotSha"),
        "absorbed_action_id": (verification.get("embedded") or {}).get(
            "absorbedActionId"
        ),
        "episode_id": episode_id,
    }
    validation = validate_receipt(receipt)
    bundle_validation = validate_evidence_bundle(receipt, root=ROOT)
    if not validation["valid"] or not bundle_validation["valid"]:
        raise ValueError(
            f"invalid projection receipt: {validation['errors'] + bundle_validation['errors']}"
        )
    receipt_path = PROJECTION_EVIDENCE_DIR / (
        f"receipt-{str(receipt['projection_sha'] or 'unknown')}.json"
    )
    write_json_artifact(receipt_path, receipt)
    return {**receipt, "receipt_path": rel(receipt_path)}


def pack_topic(topic: str, episode_id: str | None = None) -> tuple[dict[str, Any], int]:
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    view = topic_view(topic_dir)
    bundles = poc_gate_bundles(topic_dir)
    files = []
    for name in POC_FILES:
        path = topic_dir / "ndf" / name
        if path.is_file():
            files.append({"path": rel(path), "sha256": file_sha(path)})
    approval = view["gates"]["implementation_approval"]
    static_ready = view["delegation"]["static_preflight_passed"]
    runtime_ready = view["delegation"]["runtime_dispatch_ready"]
    safe = static_ready and runtime_ready
    blockers = [] if safe else view["delegation"]["dispatch_blockers"]
    payload = {
        "schema": "ndf-workflow-pack/v2",
        "compatibility": {"legacy_schema": "ndf-workflow-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": "poc_implementation",
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": workspace_truth_view(topic),
        "allowed_write_root": f"poc/{topic}/",
        "forbidden": ["src/", "include/", "tests/", "spec/meta/", "stable SLA"],
        "read_order": files,
        "gate_receipt": approval,
        "approved_bundle_sha": bundle_sha(bundles["implementation_approval"]),
        "spaces": view["spaces"],
        "preflight": {
            "perf_baseline": view["health"]["checks"]["perf_baseline"],
            "isolation": view["health"]["checks"]["isolation"],
        },
        "context_plan": view["delegation"]["context_plan"],
        "context_verify": view["delegation"]["context_verify"],
        "plan_sha": view["delegation"]["plan_sha"],
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        "next_action": view["phase_hint"],
        "safe_to_dispatch": safe,
        "blockers": blockers,
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
    }
    return bind_pack_to_episode(payload, episode_id=episode_id), 0 if safe else 1


def repair_pack(
    topic: str,
    task: str,
    episode_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in IMPLEMENTATION_REPAIR_TASKS:
        raise ValueError(f"unknown implementation repair task: {task}")
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    view = topic_view(topic_dir)
    approval_valid = view["gates"]["implementation_approval"]["state"] == "valid"
    perf_passed = view["delegation"]["perf_check_passed"]
    active = view["lifecycle"] in {"exploring", "blocked"}
    context = context_binding(topic=topic, role="claude-code", task=task, track="poc")
    context_valid = bool(context["context_verify"].get("valid"))
    lease = topic_active_lease(topic)
    runtime_ready = bool(runtime_status(False)["implementation"]["pipeline_reachable"] and not lease)
    if task == "poc_measurement":
        static_ready = active and approval_valid and perf_passed and context_valid
        blockers = [
            reason
            for reason in (
                None if approval_valid else "implementation_gate_not_valid",
                None if perf_passed else "perf_binding_not_ready",
                None if active else "topic_lifecycle_closed",
                None if context_valid else "context_verify_failed",
            )
            if reason
        ]
    else:
        isolation_failed = (
            view["health"]["checks"]["isolation"]["state"] == "failed"
            or any(
                item.get("repair_task") == "poc_isolation_repair"
                for item in view["health"].get("findings", [])
            )
        )
        static_ready = active and isolation_failed and context_valid
        blockers = [
            reason
            for reason in (
                None if active else "topic_lifecycle_closed",
                None if isolation_failed else "isolation_finding_missing",
                None if context_valid else "context_verify_failed",
            )
            if reason
        ]
    if lease:
        blockers.append("topic_active_lease")
    if not runtime_ready:
        blockers.append("runtime_unavailable")
    safe = static_ready and runtime_ready
    payload = {
        "schema": "ndf-implementation-repair-pack/v2",
        "compatibility": {"legacy_schema": "ndf-implementation-repair-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": task,
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": workspace_truth_view(topic),
        "allowed_write_root": f"poc/{topic}/",
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/",
            "stable SLA",
            "git history rewrite",
        ],
        "safe_to_delegate": safe,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
        "human_gate": (
            "人工确认 destructive git disposition"
            if task == "poc_isolation_repair"
            else None
        ),
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
        "post_checks": [
            f"python3 spec/meta/tools/ndf_poc_isolation.py check --topic {topic} --workspace --report -",
            f"python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic {topic} --json",
        ],
    }
    return bind_pack_to_episode(payload, episode_id=episode_id), 0 if safe else 1


def control_pack(
    topic: str,
    task: str,
    episode_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in CONTROL_TASKS:
        raise ValueError(f"unknown control task: {task}")
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    view = topic_view(topic_dir)
    bundles = poc_gate_bundles(topic_dir)
    gates_detail: dict[str, Any] = {}
    for gate_name, gate_data in view["gates"].items():
        paths = bundles[gate_name]
        gates_detail[gate_name] = {
            **gate_data,
            "phrase": GATE_PHRASES.get(gate_name),
            "bundle_paths": [rel(path) for path in paths if path.is_file()],
        }
    invalidated = any(gate["state"] == "invalidated" for gate in view["gates"].values())
    audit_tasks = {"legacy_gate_audit", "gate_sha_audit"}
    context = context_binding(topic=topic, role="openclaw", task=task, track="poc")
    context_valid = bool(context["context_verify"].get("valid"))
    static_ready = (task in audit_tasks or not invalidated) and context_valid
    control_runtime = runtime_status(True)["control"]
    runtime_ready = bool(control_runtime.get("reachable"))
    safe = static_ready and runtime_ready
    blockers: list[str] = []
    if not safe:
        if invalidated and task not in audit_tasks:
            blockers.append("gate_invalidated")
        if not context_valid:
            blockers.append("context_verify_failed")
        if not runtime_ready:
            blockers.append("runtime_unavailable")
    allowed_roots = (
        []
        if task in {"legacy_gate_audit", "gate_sha_audit"}
        else [f"poc/{topic}/ndf/"]
        if task in {"gate_receipt_draft", "binder_amend"}
        else ["spec/open/", "spec/meta/open/"]
    )
    payload = {
        "schema": "ndf-control-pack/v2",
        "compatibility": {"legacy_schema": "ndf-control-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": task,
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": workspace_truth_view(topic),
        "phase_hint": view["phase_hint"],
        "gates": gates_detail,
        "spaces": view["spaces"],
        "binder_gaps": {
            "design": view["spaces"]["design"]["gaps"],
            "implementation": view["spaces"]["implementation"]["gaps"],
            "test": view["spaces"]["test"]["gaps"],
        },
        "required_reads": required_reads_for_task(task, topic),
        "allowed_write_roots": allowed_roots,
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            "GATES.md approved_by without human phrase",
        ],
        "next_human_phrase": next_human_phrase(view),
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    return bind_pack_to_episode(payload, episode_id=episode_id), 0 if safe else 1


def project_control_pack(
    task: str,
    episode_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in PROJECT_CONTROL_TASKS:
        raise ValueError(f"unknown project control task: {task}")
    generation_sha = source_generation_sha()
    health = latest_spec_health(generation_sha)
    findings = (health or {}).get("findings", [])
    health_current = bool(health and health.get("state") == "current")
    context = context_binding(
        topic=None,
        role="project-control",
        task=task,
        track="process",
    )
    context_valid = bool(context["context_verify"].get("valid"))
    static_ready = bool(findings) and health_current and context_valid
    runtime_ready = bool(runtime_status(True)["control"].get("reachable"))
    safe = static_ready and runtime_ready
    blockers = []
    if not findings:
        blockers.append("spec_health_findings_missing")
    if not health_current:
        blockers.append("spec_health_stale")
    if not context_valid:
        blockers.append("context_verify_failed")
    if not runtime_ready:
        blockers.append("runtime_unavailable")
    payload = {
        "schema": "ndf-project-control-pack/v2",
        "compatibility": {"legacy_schema": "ndf-project-control-pack/v1"},
        "generated_at": now_iso(),
        "track": "process",
        "task": task,
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "required_reads": [
            "AGENTS.md",
            "spec/meta/README.md",
            "spec/meta/language.md",
            "spec/meta/process.md",
            "spec/meta/tools/GOVERNANCE.md",
        ],
        "spec_health": {
            "state": (health or {}).get("state", "not_run"),
            "findings": findings,
            "advisor": (health or {}).get("advisor", {"read_only": True}),
        },
        "allowed_write_roots": ["spec/meta/open/"],
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            ".openclaw/state.json (except OpenClaw's own workspace binding)",
            "human approval fabrication",
        ],
        "next_human_phrase": "已确认",
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    return bind_pack_to_episode(payload, episode_id=episode_id), 0 if safe else 1


def genesis_pack(mode: str, episode_id: str | None = None) -> tuple[dict[str, Any], int]:
    paths = genesis_paths()
    foundation_files: list[Path] = []
    for directory in ("00-charter", "10-architecture", "20-behavior", "30-interfaces", "40-constraints", "50-verification"):
        foundation_files.extend(sorted((SPEC / directory).rglob("*.md")) if (SPEC / directory).is_dir() else [])
    gates = latest_gate_rows(paths["gates"])
    approval = gates.get("trunk_approval")
    foundation_sha = bundle_sha(foundation_files)
    gate_valid = bool(
        approval
        and first_token(approval.get("status")) in {"valid", "approved"}
        and foundation_sha
        and re.fullmatch(r"[0-9a-f]{64}", approval.get("approved_content_sha", ""))
        and foundation_sha == approval.get("approved_content_sha")
    )
    context = context_binding(
        topic=None,
        role="claude-code",
        task="project_genesis",
        track="bootstrap",
    )
    context_valid = bool(context["context_verify"].get("valid"))
    static_ready = gate_valid and context_valid
    runtime_ready = bool(runtime_status(False)["implementation"]["pipeline_reachable"])
    valid = static_ready and runtime_ready
    payload = {
        "schema": "ndf-genesis-pack/v2",
        "compatibility": {"legacy_schema": "ndf-genesis-pack/v1"},
        "generated_at": now_iso(),
        "track": "bootstrap",
        "task": "project_genesis",
        "bootstrap_mode": mode,
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "foundation_sha": foundation_sha,
        "trunk_approval": approval,
        "safe_to_dispatch": valid,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "allowed_write_roots": ["src/", "include/", "tests/", "spec/50-verification/"],
        "forbidden": [
            "spec/00-charter/",
            "spec/10-architecture/",
            "spec/meta/",
            "spec/decisions/",
            "L0/L1 clauses",
        ],
        "foundation_files": [{"path": rel(path), "sha256": file_sha(path)} for path in foundation_files],
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
    }
    return bind_pack_to_episode(payload, episode_id=episode_id), 0 if valid else 1


def close_plan(topic: str, mode: str, ids: list[str]) -> tuple[dict[str, Any], int]:
    command = [
        sys.executable,
        str(TOOLS / "ndf_close.py"),
        "plan",
        "--topic",
        topic,
        "--mode",
        mode,
    ]
    if ids:
        command.extend(["--ids", *ids])
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "schema": "ndf-close-plan-view/v1",
        "generated_at": now_iso(),
        "topic": topic,
        "mode": mode,
        "read_only": True,
        "exit_code": proc.returncode,
        "plan_markdown": proc.stdout,
    }, proc.returncode


def validate_lease_transition(
    history: list[dict[str, Any]],
    lease: Mapping[str, Any],
) -> list[str]:
    """Validate the append-only state machine for one immutable run id."""
    prior = next(
        (
            item
            for item in reversed(history)
            if item.get("run_id") == lease.get("run_id")
            and item.get("episode_id") == lease.get("episode_id")
        ),
        None,
    )
    if lease.get("result") == "active":
        return (
            ["run_id_already_has_lease_history"]
            if prior is not None
            else []
        )
    if prior is None or prior.get("result") != "active":
        return ["release_without_active_lease"]
    immutable = (
        "session_id",
        "task",
        "topic",
        "base_sha",
        "worktree",
        "branch",
        "allowed_write_root",
        "pack_sha",
        "manifest_sha",
        "context_plan_sha",
    )
    if any(prior.get(field) != lease.get(field) for field in immutable):
        return ["release_binding_mismatch"]
    return []


def record_runtime_lease(args: argparse.Namespace) -> dict[str, Any]:
    requested_episode = getattr(args, "episode", None) or os.environ.get(
        "NDF_REPLAY_EPISODE"
    )
    if args.file:
        lease = json.loads(Path(args.file).read_text(encoding="utf-8"))
        episode_id = lease.get("episode_id") or requested_episode
        if lease.get("episode_id") != episode_id:
            raise ValueError("lease file episode_id does not match --episode")
    else:
        episode_id = requested_episode
        if not episode_id:
            raise ValueError("writable runtime lease requires --episode")
        context = context_binding(
            topic=args.topic,
            role="claude-code",
            task=args.task,
            track=args.mode,
        )
        pack_sha, pack = replay_pack_binding(
            str(episode_id),
            task=args.task,
            manifest_sha=context.get("manifest_sha"),
            context_plan_sha=context.get("plan_sha"),
        )
        if args.allowed_write_root != pack.get("allowed_write_root"):
            raise ValueError("runtime handshake allowed_write_root does not match pack")
        if args.base_sha != pack.get("base_sha"):
            raise ValueError("runtime handshake base_sha does not match pack")
        timestamp = now_iso()
        seed = {
            "run_id": args.run_id,
            "topic": args.topic,
            "result": args.result,
            "repo_head": git_head(),
        }
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": args.task,
            "topic": args.topic,
            "mode": args.mode,
            "step": args.step,
            "repo_head": git_head(),
            "source_generation_sha": source_generation_sha(),
            "context_plan_sha": context["plan_sha"],
            "manifest_sha": context["manifest_sha"],
            "command": args.command_text,
            "input_sha": canonical_json_sha(seed),
            "output_sha": canonical_json_sha({**seed, "state": args.result}),
            "evidence_paths": args.evidence_path,
            "started_at": args.started_at or timestamp,
            "finished_at": None if args.result == "active" else timestamp,
            "result": args.result,
            "blockers": args.blocker,
            "run_id": args.run_id,
            "session_id": args.session_id,
            "base_sha": args.base_sha,
            "worktree": args.worktree,
            "branch": args.branch,
            "repo_root": str(ROOT),
            "allowed_write_root": pack.get("allowed_write_root"),
            "pack_sha": pack_sha,
            "episode_id": episode_id,
        }
    episode_id = str(lease.get("episode_id") or "")
    try:
        lease_history = read_leases(LEASE_LOG, root=ROOT, strict=False)
    except ValueError:
        lease_history = []
    transition_errors = validate_lease_transition(lease_history, lease)
    if transition_errors:
        raise ValueError(f"invalid runtime lease transition: {transition_errors}")
    prior_active = next(
        (
            item
            for item in reversed(lease_history)
            if item.get("run_id") == lease.get("run_id")
            and item.get("episode_id") == lease.get("episode_id")
            and item.get("result") == "active"
        ),
        None,
    )
    if lease.get("result") == "active":
        expected_context = context_binding(
            topic=lease.get("topic"),
            role="claude-code",
            task=str(lease.get("task") or "implement"),
            track=str(lease.get("mode") or "poc"),
        )
        pack_sha, pack = replay_pack_binding(
            episode_id,
            task=str(lease.get("task") or "implement"),
            manifest_sha=expected_context.get("manifest_sha"),
            context_plan_sha=expected_context.get("plan_sha"),
        )
        semantic = validate_runtime_lease_binding(
            lease,
            root=ROOT,
            expected={
                "topic": lease.get("topic"),
                "task": lease.get("task"),
                "repo_head": git_head(),
                "base_sha": pack.get("base_sha"),
                "plan_sha": expected_context.get("plan_sha"),
                "allowed_write_root": pack.get("allowed_write_root"),
                "manifest_sha": expected_context.get("manifest_sha"),
                "pack_sha": pack_sha,
                "episode_id": episode_id,
                "branch": lease.get("branch"),
                "repo_root": str(ROOT),
            },
        )
        if not semantic["valid"]:
            raise ValueError(
                f"invalid runtime lease binding: {semantic['errors']}"
            )
        lease["binding_proof"] = runtime_lease_binding_proof(lease, root=ROOT)
    else:
        if prior_active is None or not prior_active.get("binding_proof"):
            raise ValueError("release requires recorded acquisition binding proof")
        expected_context = {
            "manifest_sha": prior_active.get("manifest_sha"),
            "plan_sha": prior_active.get("context_plan_sha"),
        }
        pack_sha = str(prior_active.get("pack_sha") or "")
        pack_object = ndf_replay.ReplayStore(ROOT).get_object(pack_sha, "blob")[
            "data"
        ]
        pack = pack_object.get("value")
        if not isinstance(pack, dict):
            raise ValueError("recorded runtime pack is not an object")
        lease["binding_proof"] = prior_active["binding_proof"]
    recorded_binding = validate_recorded_runtime_lease_binding(
        lease,
        expected={
            "topic": lease.get("topic"),
            "task": lease.get("task"),
            "base_sha": pack.get("base_sha"),
            "plan_sha": expected_context.get("plan_sha"),
            "manifest_sha": expected_context.get("manifest_sha"),
            "allowed_write_root": pack.get("allowed_write_root"),
            "pack_sha": pack_sha,
            "episode_id": episode_id,
            "branch": lease.get("branch"),
            "repo_root": str(ROOT),
        },
    )
    if not recorded_binding["valid"]:
        raise ValueError(
            f"invalid recorded runtime binding: {recorded_binding['errors']}"
        )
    append_lease(LEASE_LOG, lease, root=ROOT)
    if episode_id:
        store = ndf_replay.ReplayStore(ROOT)
        lease_blob = store.put_blob(dict(lease))
        if lease.get("result") == "active":
            store.append_event(
                episode_id,
                kind="acp.start",
                actor="claude-code",
                payload_sha=lease_blob,
                topic=lease.get("topic"),
                task=str(lease.get("task") or "implement"),
                track=str(lease.get("mode") or "poc"),
                repo_head=lease.get("repo_head"),
                manifest_sha=lease.get("manifest_sha"),
                context_plan_sha=lease.get("context_plan_sha"),
                session_id=lease.get("session_id"),
                run_id=lease.get("run_id"),
                branch="implementation",
            )
        event = store.append_event(
            episode_id,
            kind="lease.acquired" if lease.get("result") == "active" else "lease.released",
            actor="claude-code",
            payload_sha=lease_blob,
            topic=lease.get("topic"),
            task=str(lease.get("task") or "implement"),
            track=str(lease.get("mode") or "poc"),
            repo_head=lease.get("repo_head"),
            manifest_sha=lease.get("manifest_sha"),
            context_plan_sha=lease.get("context_plan_sha"),
            session_id=lease.get("session_id"),
            run_id=lease.get("run_id"),
            branch="implementation",
        )
        run_commit = store.commit_events(
            episode_id,
            message=f"runtime lease {lease.get('result')}",
            actor="claude-code",
            branch="implementation",
            coverage={"runtime_lease": lease_blob},
        )
        store.update_ref(f"runs/{lease.get('run_id')}", run_commit)
        lease = {
            **lease,
            "replay": {
                "episode_id": episode_id,
                "blob_sha": lease_blob,
                "event_sha": event["event_sha"],
            },
        }
    return lease


def record_agent_message(
    path: Path,
    *,
    episode_id: str,
    role: str,
    direction: str,
    coverage: str,
) -> tuple[dict[str, Any], int]:
    """Capture an OpenClaw/Claude visible request or response."""
    message = json.loads(path.read_text(encoding="utf-8"))
    expected_schema = "ndf-agent-message/v1"
    errors: list[str] = []
    if message.get("schema") != expected_schema:
        errors.append("unsupported_schema")
    for field in (
        "task",
        "track",
        "manifest_sha",
        "context_plan_sha",
        "session_id",
        "run_id",
        "message",
    ):
        if field not in message:
            errors.append(f"missing:{field}")
    if direction not in {"request", "response"}:
        errors.append("invalid_direction")
    allowed_coverage = (
        {"full_stream", "messages_only"}
        if role == "openclaw"
        else {"full_stream", "completion_only"}
    )
    if coverage not in allowed_coverage:
        errors.append("invalid_runtime_coverage")
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        errors.append("unknown_episode")
    historical_pack: dict[str, Any] | None = None
    historical_pack_sha: str | None = None
    if not errors:
        try:
            _, historical_pack = replay_pack_binding(
                episode_id,
                task=str(message.get("task")),
                manifest_sha=message.get("manifest_sha"),
                context_plan_sha=message.get("context_plan_sha"),
            )
        except (FileNotFoundError, ValueError):
            errors.append("missing:historical_pack")
    expected_provider = (
        "openclaw" if role == "openclaw" else "claude-code-acp"
    )
    if historical_pack and historical_pack.get("provider") != expected_provider:
        errors.append("provider_mismatch")
    if errors:
        return {
            "schema": "ndf-agent-message-verification/v1",
            "valid": False,
            "errors": sorted(set(errors)),
        }, 1
    payload = dict(message)
    session_key = payload.pop("session_key", None)
    provenance_sha = None
    if session_key is not None:
        provenance_sha = store.put_blob(
            {
                "schema": "ndf-encrypted-session-provenance/v1",
                "session_key": session_key,
                "session_id": message.get("session_id"),
                "run_id": message.get("run_id"),
            },
            sensitivity="secret",
        )
    payload["direction"] = direction
    payload["stream_coverage"] = coverage
    payload["session_provenance_sha"] = provenance_sha
    blob_sha = store.put_blob(payload, sensitivity="sensitive")
    branch = "control" if role == "openclaw" else "implementation"
    kind = (
        f"openclaw.{direction}"
        if role == "openclaw"
        else f"model.{direction}"
    )
    event = store.append_event(
        episode_id,
        kind=kind,
        actor=role,
        payload_sha=blob_sha,
        topic=message.get("topic"),
        task=str(message.get("task")),
        track=str(message.get("track")),
        repo_head=message.get("repo_head"),
        manifest_sha=message.get("manifest_sha"),
        context_plan_sha=message.get("context_plan_sha"),
        session_id=message.get("session_id"),
        run_id=message.get("run_id"),
        branch=branch,
    )
    commit_sha = store.commit_events(
        episode_id,
        message=f"{role} {direction} ({coverage})",
        actor=role,
        branch=branch,
        coverage={"runtime_stream": coverage},
    )
    return {
        "schema": "ndf-agent-message-verification/v1",
        "valid": True,
        "episode_id": episode_id,
        "coverage": coverage,
        "blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "commit_sha": commit_sha,
    }, 0


def record_close_receipt(path: Path) -> tuple[dict[str, Any], int]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verification = verify_close_receipt(receipt)
    if not verification["valid"]:
        return verification, 1
    episode_id = receipt.get("episode_id")
    store = ndf_replay.ReplayStore(ROOT) if episode_id else None
    if store and store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        return {
            **verification,
            "valid": False,
            "errors": [*verification["errors"], "unknown_episode"],
        }, 1
    target = _close_receipt_path(
        str(receipt["topic"]),
        str(receipt["mode"]),
        str(receipt["step"]),
    )
    write_json_artifact(target, dict(receipt))
    result = {
        **verification,
        "written": rel(target),
    }
    if episode_id and store:
        blob_sha = store.put_blob(dict(receipt))
        event = store.append_event(
            str(episode_id),
            kind="close.receipt",
            actor=str(receipt.get("actor") or "tool"),
            payload_sha=blob_sha,
            topic=receipt.get("topic"),
            task=str(receipt.get("task") or "close"),
            track=str(receipt.get("mode") or "process"),
            repo_head=receipt.get("repo_head"),
            manifest_sha=receipt.get("manifest_sha"),
            context_plan_sha=receipt.get("context_plan_sha"),
            branch="control",
        )
        commit_sha = store.commit_events(
            str(episode_id),
            message=f"close receipt {receipt.get('step')}",
            actor=str(receipt.get("actor") or "tool"),
            branch="control",
            coverage={"close_receipt": blob_sha},
        )
        result["replay"] = {
            "episode_id": episode_id,
            "blob_sha": blob_sha,
            "event_sha": event["event_sha"],
            "commit_sha": commit_sha,
        }
        if (
            receipt.get("step") == "finalize"
            and receipt.get("mode") in {"promote", "partial"}
        ):
            control_ref = f"branches/{episode_id}/control"
            implementation_ref = f"branches/{episode_id}/implementation"
            if store.read_ref(control_ref) and store.read_ref(implementation_ref):
                result["replay"]["merge_commit_sha"] = store.merge(
                    str(episode_id),
                    control_ref,
                    implementation_ref,
                    message=f"verified {receipt.get('mode')} episode merge",
                    actor="close",
                )
                result["replay"]["ledger"] = store.ledger_entry(
                    str(episode_id),
                    write=True,
                )
    return result, 0


def record_agent_completion(
    path: Path,
    *,
    episode_id: str,
    role: str,
    coverage: str,
) -> tuple[dict[str, Any], int]:
    """Bind an Agent completion to its manifest/plan and Episode history."""
    completion = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if completion.get("schema") != "ndf-agent-completion/v1":
        errors.append("unsupported_schema")
    for field in (
        "task",
        "track",
        "base_sha",
        "repo_head",
        "manifest_sha",
        "context_plan_sha",
        "changed_files",
        "changed_file_shas",
        "reproduce_commands",
        "evidence_paths",
        "evidence_bundle_sha",
        "git_commit",
        "post_check_receipts",
        "result",
    ):
        if field not in completion:
            errors.append(f"missing:{field}")
    if role == "claude-code":
        for field in ("worktree", "branch", "run_id", "session_id"):
            if field not in completion:
                errors.append(f"missing:{field}")
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        return {
            "schema": "ndf-agent-completion-verification/v1",
            "valid": False,
            "errors": ["unknown_episode"],
        }, 1
    historical_pack: dict[str, Any] | None = None
    for replay_event in reversed(
        [
            item
            for events in store.read_all_events(episode_id).values()
            for item in events
        ]
    ):
        if (
            replay_event.get("kind") != "dispatch.preflight"
            or replay_event.get("task") != completion.get("task")
        ):
            continue
        try:
            blob = store.get_object(str(replay_event["payload_sha"]), "blob")["data"]
        except (FileNotFoundError, ValueError, KeyError):
            continue
        if blob.get("encoding") == "json" and isinstance(blob.get("value"), dict):
            candidate = blob["value"]
            expected_provider = (
                "claude-code-acp" if role == "claude-code" else "openclaw"
            )
            if (
                candidate.get("provider") == expected_provider
                and candidate.get("safe_to_dispatch") is True
            ):
                historical_pack = candidate
                historical_pack_sha = str(replay_event["payload_sha"])
                break
    if historical_pack is None:
        errors.append("missing:historical_pack")
        historical_pack = {}
    if completion.get("manifest_sha") != historical_pack.get("manifest_sha"):
        errors.append("stale:manifest_sha")
    if completion.get("context_plan_sha") != historical_pack.get("plan_sha"):
        errors.append("stale:context_plan_sha")
    if completion.get("base_sha") != historical_pack.get("base_sha"):
        errors.append("stale:base_sha")
    completion_root = ROOT
    matching_lease: dict[str, Any] | None = None
    if role == "claude-code":
        try:
            leases = read_leases(LEASE_LOG, root=ROOT, strict=False)
        except ValueError:
            leases = []
        for lease in reversed(leases):
            if (
                lease.get("run_id") == completion.get("run_id")
                and lease.get("session_id") == completion.get("session_id")
                and lease.get("episode_id") == episode_id
                and lease.get("task") == completion.get("task")
            ):
                matching_lease = lease
                break
        if matching_lease is None or matching_lease.get("result") != "active":
            errors.append("missing:active_runtime_lease")
        else:
            completion_root = Path(str(matching_lease.get("worktree"))).resolve()
            if Path(str(completion.get("worktree") or "")).resolve() != completion_root:
                errors.append("mismatch:worktree")
            if completion.get("branch") != matching_lease.get("branch"):
                errors.append("mismatch:branch")
            lease_check = validate_recorded_runtime_lease_binding(
                matching_lease,
                expected={
                    "topic": completion.get("topic"),
                    "task": completion.get("task"),
                    "repo_head": matching_lease.get("repo_head"),
                    "base_sha": historical_pack.get("base_sha"),
                    "plan_sha": completion.get("context_plan_sha"),
                    "manifest_sha": completion.get("manifest_sha"),
                    "allowed_write_root": historical_pack.get("allowed_write_root"),
                    "pack_sha": historical_pack_sha,
                    "episode_id": episode_id,
                    "branch": matching_lease.get("branch"),
                    "repo_root": str(ROOT),
                },
            )
            if not lease_check["valid"]:
                errors.extend(
                    f"runtime_lease:{item}" for item in lease_check["errors"]
                )
            live_lease_check = validate_runtime_lease_binding(
                matching_lease,
                root=ROOT,
                expected={
                    "topic": completion.get("topic"),
                    "task": completion.get("task"),
                    "base_sha": historical_pack.get("base_sha"),
                    "plan_sha": completion.get("context_plan_sha"),
                    "manifest_sha": completion.get("manifest_sha"),
                    "allowed_write_root": historical_pack.get("allowed_write_root"),
                    "pack_sha": historical_pack_sha,
                    "episode_id": episode_id,
                    "branch": matching_lease.get("branch"),
                    "repo_root": str(ROOT),
                },
            )
            if not live_lease_check["valid"]:
                errors.extend(
                    f"runtime_lease_current:{item}"
                    for item in live_lease_check["errors"]
                )
            current_head = subprocess.run(
                ["git", "-C", str(completion_root), "rev-parse", "HEAD"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if (
                current_head.returncode != 0
                or current_head.stdout.strip() != completion.get("repo_head")
            ):
                errors.append("stale:completion_repo_head")
    for field in ("changed_files", "reproduce_commands", "evidence_paths"):
        if not isinstance(completion.get(field), list):
            errors.append(f"not_list:{field}")
    missing_evidence = [
        item
        for item in completion.get("evidence_paths", [])
        if not isinstance(item, str) or not (completion_root / item).is_file()
    ]
    if missing_evidence:
        errors.append("missing:evidence_paths")
    if not missing_evidence and completion.get("evidence_paths"):
        actual_evidence_sha = evidence_bundle_sha(
            completion["evidence_paths"],
            root=completion_root,
        )
        if completion.get("evidence_bundle_sha") != actual_evidence_sha:
            errors.append("mismatch:evidence_bundle_sha")
    changed_file_shas = completion.get("changed_file_shas")
    if not isinstance(changed_file_shas, dict):
        errors.append("not_object:changed_file_shas")
        changed_file_shas = {}
    for changed_path in completion.get("changed_files", []):
        target = completion_root / str(changed_path)
        if (
            not target.is_file()
            or changed_file_shas.get(changed_path) != file_sha(target)
        ):
            errors.append(f"changed_file_drift:{changed_path}")
    if role == "claude-code" and matching_lease is not None:
        try:
            completion_snapshot = git_mutation_snapshot(completion_root)
            acquisition_snapshot = matching_lease.get("binding_proof", {}).get(
                "acquisition_snapshot", {}
            )
            acquisition_head = str(acquisition_snapshot.get("head") or "")
            committed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(completion_root),
                    "diff",
                    "--name-only",
                    "-z",
                    f"{acquisition_head}..{completion_snapshot['head']}",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if committed.returncode != 0:
                errors.append("mutation_diff_unavailable")
                committed_paths: set[str] = set()
            else:
                committed_paths = {
                    item.decode("utf-8", errors="surrogateescape")
                    for item in committed.stdout.split(b"\0")
                    if item
                }
            before_shas = acquisition_snapshot.get("path_shas", {})
            after_shas = completion_snapshot.get("path_shas", {})
            worktree_paths = {
                path
                for path in set(before_shas) | set(after_shas)
                if before_shas.get(path) != after_shas.get(path)
            }
            actual_mutations = committed_paths | worktree_paths
            declared_mutations = {
                str(path) for path in completion.get("changed_files", [])
            }
            if actual_mutations != declared_mutations:
                errors.append("changed_files_do_not_match_actual_mutations")
            completion["mutation_proof"] = {
                "schema": "ndf-runtime-mutation-proof/v1",
                "acquisition_snapshot_sha": acquisition_snapshot.get(
                    "snapshot_sha"
                ),
                "completion_snapshot": completion_snapshot,
                "committed_paths": sorted(committed_paths),
                "actual_mutations": sorted(actual_mutations),
                "declared_mutations": sorted(declared_mutations),
            }
            completion["mutation_proof"]["proof_sha"] = canonical_json_sha(
                completion["mutation_proof"]
            )
        except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"mutation_proof_failed:{type(exc).__name__}")
    git_commit = str(completion.get("git_commit") or "")
    if git_commit:
        resolved = subprocess.run(
            ["git", "-C", str(completion_root), "rev-parse", f"{git_commit}^{{commit}}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if resolved.returncode != 0:
            errors.append("git_commit_unresolvable")
    expected_coverage = (
        {"full_stream", "completion_only"}
        if role == "claude-code"
        else {"full_stream", "messages_only"}
    )
    if coverage not in expected_coverage:
        errors.append("invalid_runtime_coverage")
    allowed_roots = (
        historical_pack.get("context_plan", {})
        .get("privileges", {})
        .get("allowed_write_roots", [])
    )
    write_violations = [
        item
        for item in completion.get("changed_files", [])
        if not isinstance(item, str)
        or item.startswith("/")
        or ".." in Path(item).parts
        or not any(
            item == root.rstrip("/") or item.startswith(root.rstrip("/") + "/")
            for root in allowed_roots
        )
    ]
    if write_violations:
        errors.append("write_root_violation")
    if completion.get("result") not in {"success", "passed", "completed"}:
        errors.append("result_not_green")
    post_checks = completion.get("post_check_receipts")
    if not isinstance(post_checks, list) or not post_checks:
        errors.append("missing:post_check_receipts")
    else:
        allowed_post_checks = {
            "ndf_poc_isolation.py",
            "ndf_workflow_status.py",
            "ndf_perf_baseline.py",
            "ndf_bindcheck.py",
        }
        for index, receipt in enumerate(post_checks):
            if not isinstance(receipt, Mapping):
                errors.append(f"invalid:post_check:{index}")
                continue
            try:
                tokens = shlex.split(str(receipt.get("command") or ""))
            except ValueError:
                tokens = []
            safe_tokens = bool(tokens) and not any(
                any(char in token for char in ";&|><") for token in tokens
            )
            executable = Path(tokens[0]).name if tokens else ""
            arguments = tokens[1:]
            script = executable
            if executable in {"python", "python3", "bash", "sh"}:
                if not arguments or arguments[0].startswith("-"):
                    safe_tokens = False
                else:
                    script = Path(arguments[0]).name
            if (
                receipt.get("result") not in {"passed", "success", "completed"}
                or not safe_tokens
                or script not in allowed_post_checks
            ):
                errors.append(f"invalid:post_check:{index}")
            verifier = receipt.get("verifier")
            if not isinstance(verifier, Mapping):
                errors.append(f"missing:post_check_verifier:{index}")
            else:
                verifier_path = Path(str(verifier.get("path") or ""))
                if (
                    not verifier_path.is_absolute()
                    or not verifier_path.is_file()
                    or verifier_path.name != script
                    or verifier.get("argv") != tokens
                    or verifier.get("version_sha") != file_sha(verifier_path)
                    or verifier.get("exit_code") != 0
                    or not verifier.get("output_schema")
                ):
                    errors.append(f"invalid:post_check_verifier:{index}")
            post_evidence = validate_evidence_bundle(receipt, root=completion_root)
            if not post_evidence["valid"]:
                errors.append(f"invalid:post_check_evidence:{index}")
    if errors:
        return {
            "schema": "ndf-agent-completion-verification/v1",
            "valid": False,
            "errors": sorted(set(errors)),
            "write_violations": write_violations,
        }, 1
    blob_sha = store.put_blob(completion)
    branch = "implementation" if role == "claude-code" else "control"
    event = store.append_event(
        episode_id,
        kind="acp.complete" if role == "claude-code" else "openclaw.response",
        actor=role,
        payload_sha=blob_sha,
        topic=completion.get("topic"),
        task=str(completion["task"]),
        track=str(completion["track"]),
        repo_head=completion.get("repo_head"),
        manifest_sha=completion.get("manifest_sha"),
        context_plan_sha=completion.get("context_plan_sha"),
        session_id=completion.get("session_id"),
        run_id=completion.get("run_id"),
        branch=branch,
    )
    commit_sha = store.commit_events(
        episode_id,
        message=f"{role} completion ({coverage})",
        actor=role,
        branch=branch,
        coverage={"runtime_stream": coverage},
    )
    return {
        "schema": "ndf-agent-completion-verification/v1",
        "valid": True,
        "episode_id": episode_id,
        "coverage": coverage,
        "blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "commit_sha": commit_sha,
        "write_violations": [],
    }, 0


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    genesis_status_parser = sub.add_parser("genesis-status")
    genesis_status_parser.add_argument("--json", action="store_true")

    genesis_pack_parser = sub.add_parser("genesis-pack")
    genesis_pack_parser.add_argument("--mode", choices=("greenfield", "adopt"), required=True)
    genesis_pack_parser.add_argument("--episode")
    genesis_pack_parser.add_argument("--json", action="store_true")

    snapshot_parser = sub.add_parser("snapshot")
    snapshot_parser.add_argument("--topic")
    snapshot_parser.add_argument("--json", action="store_true")
    snapshot_parser.add_argument(
        "--format",
        choices=("raw", "canvas-json"),
        default="raw",
    )
    snapshot_parser.add_argument("--probe-runtime", action="store_true")
    snapshot_parser.add_argument("--verify-embedded")
    snapshot_parser.add_argument("--update-embedded")
    snapshot_parser.add_argument("--episode")

    topic_health_parser = sub.add_parser("topic-health")
    topic_health_parser.add_argument("--topic", required=True)
    topic_health_parser.add_argument("--json", action="store_true")

    spec_health_parser = sub.add_parser("spec-health")
    spec_health_parser.add_argument("--json", action="store_true")

    action_begin_parser = sub.add_parser("action-begin")
    action_begin_parser.add_argument("--operation", required=True)
    action_begin_parser.add_argument("--topic")
    action_begin_parser.add_argument("--action-id")
    action_begin_parser.add_argument("--episode")
    action_begin_parser.add_argument("--json", action="store_true")

    action_finish_parser = sub.add_parser("action-finish")
    action_finish_parser.add_argument("--action-id", required=True)
    action_finish_parser.add_argument(
        "--result",
        choices=("success", "failed", "cancelled"),
        required=True,
    )
    action_finish_parser.add_argument("--blocker", action="append", default=[])
    action_finish_parser.add_argument("--episode")
    action_finish_parser.add_argument("--json", action="store_true")

    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("--topic", required=True)
    pack_parser.add_argument("--episode")
    pack_parser.add_argument("--json", action="store_true")

    repair_pack_parser = sub.add_parser("repair-pack")
    repair_pack_parser.add_argument("--topic", required=True)
    repair_pack_parser.add_argument(
        "--task",
        choices=sorted(IMPLEMENTATION_REPAIR_TASKS),
        required=True,
    )
    repair_pack_parser.add_argument("--episode")
    repair_pack_parser.add_argument("--json", action="store_true")

    control_pack_parser = sub.add_parser("control-pack")
    control_pack_parser.add_argument("--topic", required=True)
    control_pack_parser.add_argument(
        "--task",
        choices=sorted(CONTROL_TASKS),
        required=True,
    )
    control_pack_parser.add_argument("--episode")
    control_pack_parser.add_argument("--json", action="store_true")

    project_control_parser = sub.add_parser("project-control-pack")
    project_control_parser.add_argument(
        "--task",
        choices=sorted(PROJECT_CONTROL_TASKS),
        required=True,
    )
    project_control_parser.add_argument("--episode")
    project_control_parser.add_argument("--json", action="store_true")

    close_parser = sub.add_parser("close-plan")
    close_parser.add_argument("--topic", required=True)
    close_parser.add_argument("--mode", choices=("promote", "reject", "partial"), required=True)
    close_parser.add_argument("--ids", nargs="*", default=[])
    close_parser.add_argument("--json", action="store_true")

    lease_parser = sub.add_parser("lease-record")
    lease_parser.add_argument("--file")
    lease_parser.add_argument("--task", default="implement")
    lease_parser.add_argument("--topic")
    lease_parser.add_argument("--mode", default="poc")
    lease_parser.add_argument("--step", default="start")
    lease_parser.add_argument("--run-id")
    lease_parser.add_argument("--session-id")
    lease_parser.add_argument("--base-sha")
    lease_parser.add_argument("--worktree")
    lease_parser.add_argument("--branch")
    lease_parser.add_argument("--allowed-write-root")
    lease_parser.add_argument(
        "--result",
        choices=("active", "released", "expired", "failed"),
        default="active",
    )
    lease_parser.add_argument("--command-text", default="runtime lease")
    lease_parser.add_argument("--started-at")
    lease_parser.add_argument("--evidence-path", action="append", default=[])
    lease_parser.add_argument("--blocker", action="append", default=[])
    lease_parser.add_argument("--episode")
    lease_parser.add_argument("--json", action="store_true")

    close_verify_parser = sub.add_parser("close-receipt-verify")
    close_verify_parser.add_argument("--receipt", required=True)
    close_verify_parser.add_argument("--json", action="store_true")
    close_record_parser = sub.add_parser("close-receipt-record")
    close_record_parser.add_argument("--receipt", required=True)
    close_record_parser.add_argument("--json", action="store_true")
    completion_parser = sub.add_parser("completion-record")
    completion_parser.add_argument("--file", required=True)
    completion_parser.add_argument("--episode", required=True)
    completion_parser.add_argument(
        "--role",
        choices=("openclaw", "claude-code"),
        required=True,
    )
    completion_parser.add_argument(
        "--coverage",
        choices=("full_stream", "completion_only", "messages_only"),
        required=True,
    )
    completion_parser.add_argument("--json", action="store_true")

    message_parser = sub.add_parser("message-record")
    message_parser.add_argument("--file", required=True)
    message_parser.add_argument("--episode", required=True)
    message_parser.add_argument(
        "--role",
        choices=("openclaw", "claude-code"),
        required=True,
    )
    message_parser.add_argument(
        "--direction",
        choices=("request", "response"),
        required=True,
    )
    message_parser.add_argument(
        "--coverage",
        choices=("full_stream", "completion_only", "messages_only"),
        required=True,
    )
    message_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "genesis-status":
            emit({"schema": "ndf-genesis-status/v1", "generated_at": now_iso(), **genesis_status()})
            return 0
        if args.command == "genesis-pack":
            payload, code = genesis_pack(args.mode, args.episode)
            emit(payload)
            return code
        if args.command == "snapshot":
            if args.verify_embedded and args.update_embedded:
                raise ValueError(
                    "--verify-embedded and --update-embedded are mutually exclusive"
                )
            if args.update_embedded:
                result = update_embedded_snapshot(
                    Path(args.update_embedded),
                    topic=args.topic,
                )
                receipt = record_projection_verification(
                    Path(args.update_embedded),
                    result["verification"],
                    topic=args.topic,
                    episode_id=args.episode,
                )
                result["receipt"] = receipt
                emit(result)
                return 0 if result["updated"] else 1
            if args.verify_embedded:
                source_path = Path(args.verify_embedded)
                result = verify_embedded_snapshot(source_path, topic=args.topic)
                receipt = record_projection_verification(
                    source_path,
                    result,
                    topic=args.topic,
                    episode_id=args.episode,
                )
                result["receipt"] = receipt
                if result["valid"] and args.episode:
                    store = ndf_replay.ReplayStore(ROOT)
                    blob_sha = store.put_blob(receipt)
                    event = store.append_event(
                        args.episode,
                        kind="snapshot.embedded",
                        actor="canvas",
                        payload_sha=blob_sha,
                        topic=args.topic,
                        task="snapshot_embedded",
                        track="process",
                        repo_head=git_head(),
                        manifest_sha=None,
                        context_plan_sha=None,
                    )
                    result["replay"] = {
                        "episode_id": args.episode,
                        "blob_sha": blob_sha,
                        "event_sha": event["event_sha"],
                    }
                emit(result)
                return 0 if result["valid"] else 1
            payload = snapshot(args.topic, args.probe_runtime)
            emit(canvas_snapshot(payload) if args.format == "canvas-json" else payload)
            return 0
        if args.command == "topic-health":
            payload, code = topic_health(args.topic)
            emit(payload)
            return code
        if args.command == "spec-health":
            payload, code = spec_health()
            emit(payload)
            return code
        if args.command == "action-begin":
            emit(action_begin(args.operation, args.topic, args.action_id, args.episode))
            return 0
        if args.command == "action-finish":
            emit(action_finish(args.action_id, args.result, args.blocker, args.episode))
            return 0
        if args.command == "pack":
            payload, code = pack_topic(args.topic, args.episode)
            emit(payload)
            return code
        if args.command == "repair-pack":
            payload, code = repair_pack(args.topic, args.task, args.episode)
            emit(payload)
            return code
        if args.command == "control-pack":
            payload, code = control_pack(args.topic, args.task, args.episode)
            emit(payload)
            return code
        if args.command == "project-control-pack":
            payload, code = project_control_pack(args.task, args.episode)
            emit(payload)
            return code
        if args.command == "lease-record":
            emit(record_runtime_lease(args))
            return 0
        if args.command == "close-receipt-verify":
            receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
            result = verify_close_receipt(receipt)
            emit(result)
            return 0 if result["valid"] else 1
        if args.command == "close-receipt-record":
            result, code = record_close_receipt(Path(args.receipt))
            emit(result)
            return code
        if args.command == "completion-record":
            result, code = record_agent_completion(
                Path(args.file),
                episode_id=args.episode,
                role=args.role,
                coverage=args.coverage,
            )
            emit(result)
            return code
        if args.command == "message-record":
            result, code = record_agent_message(
                Path(args.file),
                episode_id=args.episode,
                role=args.role,
                direction=args.direction,
                coverage=args.coverage,
            )
            emit(result)
            return code
        payload, code = close_plan(args.topic, args.mode, args.ids)
        emit(payload)
        return code
    except (FileNotFoundError, ValueError) as exc:
        emit({"schema": "ndf-workflow-error/v1", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
