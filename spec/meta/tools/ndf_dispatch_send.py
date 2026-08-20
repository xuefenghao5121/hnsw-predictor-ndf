#!/usr/bin/env python3
"""Trusted pack → OpenClaw / Claude Code ACP dispatch (afterShellExecution).

Command Agent only builds pack JSON. This module:
  1. sends when safe_to_dispatch (or lease-only prepare)
  2. waits for a worker result (or times out)
  3. records completion → action-commit → snapshot

sent / acknowledged alone MUST NOT refresh the commander as success.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
DISPATCH_LAST = ROOT / "tmp" / "ndf-dispatch-last.json"
DEFAULT_TIMEOUT_SEC = 900


def _write_last(payload: Mapping[str, Any]) -> None:
    DISPATCH_LAST.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_LAST.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _pack_sha(pack: Mapping[str, Any]) -> str:
    raw = pack.get("pack_sha") or pack.get("replay", {}).get("pack_sha")
    if isinstance(raw, str) and raw:
        return raw
    # Fallback identity for idempotency when pack was not yet bound.
    import hashlib

    blob = json.dumps(pack, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _safe_to_send(pack: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers = [str(item) for item in (pack.get("blockers") or []) if str(item).strip()]
    if pack.get("safe_to_dispatch") is True:
        return True, blockers
    # Control packs may expose safe_to_delegate + runtime separately.
    if (
        pack.get("safe_to_delegate") is True
        and pack.get("runtime_dispatch_ready") is not False
        and pack.get("provider") == "openclaw"
    ):
        return True, blockers
    return False, blockers or ["not_safe_to_dispatch"]


def _already_sent(pack_sha: str, request_id: str | None) -> dict[str, Any] | None:
    if not DISPATCH_LAST.is_file():
        return None
    try:
        prior = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(prior, dict):
        return None
    if prior.get("pack_sha") == pack_sha and prior.get("state") in {
        "sent",
        "acknowledged",
        "running",
        "waiting_human",
        "succeeded",
        "failed",
        "delivery_unknown",
        "blocked",
    }:
        if request_id and prior.get("request_id") and prior.get("request_id") != request_id:
            return None
        return {**prior, "idempotent": True}
    return None


def _build_worker_message(pack: Mapping[str, Any]) -> str:
    provider = str(pack.get("provider") or "")
    topic = pack.get("topic") or ""
    task = pack.get("task") or ""
    episode = pack.get("episode_id") or ""
    manifest = pack.get("manifest_sha") or ""
    plan = pack.get("plan_sha") or (pack.get("context_plan") or {}).get("plan_sha") or ""
    lines = [
        f"【NDF dispatch-send】provider={provider} task={task} topic={topic}",
        f"episode_id={episode}",
        f"manifest_sha={manifest}",
        f"context_plan_sha={plan}",
        f"allowed_write_root={pack.get('allowed_write_root') or pack.get('allowed_write_roots')}",
        "Follow the pack JSON binding. Return a completion receipt.",
        "BEGIN NDF_PACK_JSON",
        json.dumps(pack, ensure_ascii=False, sort_keys=True, default=str),
        "END NDF_PACK_JSON",
    ]
    return "\n".join(lines)


def _send_openclaw(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
) -> dict[str, Any]:
    session_key = str(pack.get("session_key") or "")
    override = os.environ.get("NDF_OPENCLAW_DISPATCH_CMD")
    executable = shutil.which("openclaw")
    if override:
        cmd = override.split()
    elif executable:
        # Prefer agent turn against the configured control session.
        cmd = [executable, "agent", "--agent", "main", "--message", message]
        if session_key:
            cmd.extend(["--session-id", session_key])
    else:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_cli_missing",
            "response_text": None,
        }
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_sec,
            env={**os.environ, "NDF_PACK_SHA": _pack_sha(pack)},
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_timeout",
            "detail": str(exc),
            "response_text": None,
        }
    except OSError as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_spawn_failed",
            "detail": str(exc),
            "response_text": None,
        }
    text = proc.stdout or ""
    if proc.returncode != 0:
        return {
            "ok": False,
            "state": "failed",
            "error": "openclaw_nonzero_exit",
            "exit_code": proc.returncode,
            "response_text": text[-8000:],
        }
    return {
        "ok": True,
        "state": "succeeded",
        "exit_code": 0,
        "response_text": text[-8000:],
    }


def _send_acp(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
    lease_only: bool,
) -> dict[str, Any]:
    """Resume the configured Claude Code ACP session with the pack."""
    import ndf_workflow_status as workflow

    session_id = workflow.configured_acp_session_id()
    if not session_id:
        return {
            "ok": False,
            "state": "failed",
            "error": "acp_session_unconfigured",
            "response_text": None,
        }
    if lease_only:
        # Lease prepare: do not start implementation; record a dry handshake stub.
        run_id = f"lease-{uuid.uuid4().hex[:12]}"
        return {
            "ok": True,
            "state": "succeeded",
            "lease_only": True,
            "run_id": run_id,
            "session_id": session_id,
            "response_text": "lease_only_no_implementation_start",
        }
    override = os.environ.get("NDF_ACP_DISPATCH_CMD")
    executable = shutil.which("claude")
    if override:
        cmd = override.split()
    elif executable:
        cmd = [
            executable,
            "--resume",
            session_id,
            "-p",
            message,
            "--output-format",
            "text",
        ]
    else:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "claude_cli_missing",
            "response_text": None,
        }
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_sec,
            env={**os.environ, "NDF_PACK_SHA": _pack_sha(pack)},
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "acp_timeout",
            "detail": str(exc),
            "response_text": None,
        }
    except OSError as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "acp_spawn_failed",
            "detail": str(exc),
            "response_text": None,
        }
    text = proc.stdout or ""
    if proc.returncode != 0:
        return {
            "ok": False,
            "state": "failed",
            "error": "acp_nonzero_exit",
            "exit_code": proc.returncode,
            "response_text": text[-8000:],
        }
    return {
        "ok": True,
        "state": "succeeded",
        "run_id": f"acp-{uuid.uuid4().hex[:12]}",
        "session_id": session_id,
        "exit_code": 0,
        "response_text": text[-8000:],
    }


def _closeout(
    *,
    catalog_action_id: str | None,
    action_id: str | None,
    result: str,
    blockers: list[str],
    result_summary: str,
) -> dict[str, Any]:
    """completion-record (best effort) → action-commit → snapshot."""
    import ndf_actions
    import ndf_workflow_status as workflow

    steps: dict[str, Any] = {}
    # Completion file for workers that returned text.
    completion_path = ROOT / "tmp" / "ndf-dispatch-completion.json"
    completion = {
        "schema": "ndf-dispatch-completion/v1",
        "result": result,
        "blockers": blockers,
        "result_summary": result_summary,
        "finished_at": workflow.now_iso(),
    }
    completion_path.write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    steps["completion"] = {"path": "tmp/ndf-dispatch-completion.json", **completion}

    if action_id and catalog_action_id:
        prompt_rel = ndf_actions.action_prompt_relpath(catalog_action_id)
        commit_cmd = [
            "python3",
            "spec/meta/tools/ndf_workflow_status.py",
            "action-commit",
            "--action-id",
            action_id,
            "--catalog-action-id",
            catalog_action_id,
            "--prompt-file",
            prompt_rel,
            "--json",
        ]
        commit = subprocess.run(
            commit_cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        steps["action_commit"] = {
            "exit_code": commit.returncode,
            "stdout": (commit.stdout or "")[-4000:],
            "stderr": (commit.stderr or "")[-2000:],
        }
        finish = subprocess.run(
            [
                "python3",
                "spec/meta/tools/ndf_workflow_status.py",
                "action-finish",
                "--action-id",
                action_id,
                "--result",
                "success" if result == "succeeded" else "failed",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        steps["action_finish"] = {
            "exit_code": finish.returncode,
            "stdout": (finish.stdout or "")[-2000:],
        }
    snap = subprocess.run(
        [
            "python3",
            "spec/meta/tools/ndf_workflow_status.py",
            "snapshot",
            "--out",
            "tmp/ndf-canvas-snapshot.json",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    steps["snapshot"] = {
        "exit_code": snap.returncode,
        "stdout": (snap.stdout or "")[-2000:],
    }
    return steps


def dispatch_send(
    pack: Mapping[str, Any],
    *,
    catalog_action_id: str | None = None,
    action_id: str | None = None,
    timeout_sec: int | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    """Send a verified pack and close out the commander surface."""
    timeout = int(timeout_sec or os.environ.get("NDF_DISPATCH_TIMEOUT_SEC") or DEFAULT_TIMEOUT_SEC)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    provider = str(pack.get("provider") or "")
    task = str(pack.get("task") or "")
    lease_only = task in {"prepare_acp_lease"} or (
        catalog_action_id == "prepare-acp-lease"
    )

    prior = _already_sent(pack_sha, request_id)
    if prior and prior.get("state") in {"succeeded", "failed", "blocked"}:
        return {**prior, "schema": "ndf-dispatch-send/v1"}, 0

    ok_to_send, blockers = _safe_to_send(pack)
    if not ok_to_send and not lease_only:
        payload = {
            "schema": "ndf-dispatch-send/v1",
            "state": "blocked",
            "dispatch_state": "blocked",
            "delegate_to": provider or "unknown",
            "pack_sha": pack_sha,
            "request_id": request_id,
            "blockers": blockers,
            "result_summary": "pack not safe_to_dispatch; not sent",
            "sent": False,
        }
        _write_last(payload)
        # Still snapshot so the panel shows blockers.
        close = _closeout(
            catalog_action_id=catalog_action_id,
            action_id=action_id,
            result="failed",
            blockers=blockers,
            result_summary=payload["result_summary"],
        )
        payload["closeout"] = close
        _write_last(payload)
        return payload, 1

    if dry_run:
        payload = {
            "schema": "ndf-dispatch-send/v1",
            "state": "sent",
            "dispatch_state": "awaiting_result",
            "delegate_to": provider,
            "pack_sha": pack_sha,
            "request_id": request_id,
            "blockers": [],
            "result_summary": "dry_run: would send",
            "sent": False,
            "dry_run": True,
        }
        _write_last(payload)
        return payload, 0

    message = _build_worker_message(pack)
    # Mark sent before waiting — commander may show awaiting_result.
    sent_receipt = {
        "schema": "ndf-dispatch-send/v1",
        "state": "sent",
        "dispatch_state": "awaiting_result",
        "delegate_to": provider,
        "pack_sha": pack_sha,
        "request_id": request_id,
        "blockers": [],
        "result_summary": "已发出，等待结果",
        "sent": True,
        "started_at": time.time(),
    }
    _write_last(sent_receipt)

    if provider == "openclaw":
        send_result = _send_openclaw(pack, message=message, timeout_sec=timeout)
    elif provider == "claude-code-acp":
        send_result = _send_acp(
            pack, message=message, timeout_sec=timeout, lease_only=lease_only
        )
    else:
        send_result = {
            "ok": False,
            "state": "failed",
            "error": f"unknown_provider:{provider}",
            "response_text": None,
        }

    final_state = str(send_result.get("state") or ("succeeded" if send_result.get("ok") else "failed"))
    summary = (
        (send_result.get("response_text") or "")[:240]
        if send_result.get("ok")
        else str(send_result.get("error") or final_state)
    )
    final_blockers = [] if send_result.get("ok") else [str(send_result.get("error") or final_state)]
    payload = {
        **sent_receipt,
        "state": final_state,
        "dispatch_state": final_state,
        "result_summary": summary or final_state,
        "blockers": final_blockers,
        "send": {k: v for k, v in send_result.items() if k != "response_text"},
        "response_excerpt": (send_result.get("response_text") or "")[:2000],
        "finished_at": time.time(),
    }
    # Closeout order is fixed: completion → action-commit → snapshot.
    payload["closeout"] = _closeout(
        catalog_action_id=catalog_action_id,
        action_id=action_id,
        result="succeeded" if send_result.get("ok") else "failed",
        blockers=final_blockers,
        result_summary=payload["result_summary"],
    )
    _write_last(payload)
    code = 0 if send_result.get("ok") else 1
    return payload, code


def load_pack_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pack file must be a JSON object")
    return data


def extract_pack_from_shell_output(stdout: str) -> dict[str, Any] | None:
    """Parse the last JSON object from pack CLI stdout."""
    text = (stdout or "").strip()
    if not text:
        return None
    # Prefer whole stdout as JSON.
    try:
        value = json.loads(text)
        if isinstance(value, dict) and (
            value.get("schema")
            or value.get("safe_to_dispatch") is not None
            or value.get("provider")
        ):
            return value
    except json.JSONDecodeError:
        pass
    # Scan for the last {...} block.
    end = text.rfind("}")
    if end < 0:
        return None
    depth = 0
    start = None
    for idx in range(end, -1, -1):
        ch = text[idx]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = idx
                break
    if start is None:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
