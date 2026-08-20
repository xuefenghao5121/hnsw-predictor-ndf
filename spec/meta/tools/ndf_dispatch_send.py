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
    preflight_blockers = _pack_preflight_blockers(pack)
    for item in preflight_blockers:
        if item not in blockers:
            blockers.append(item)
    if preflight_blockers:
        return False, blockers
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


def _pack_preflight_blockers(pack: Mapping[str, Any]) -> list[str]:
    """Verify pack-side fields that MUST exist before transport (not Worker-minted)."""
    blockers: list[str] = []
    truth = pack.get("workspace_truth")
    if isinstance(truth, Mapping) and truth.get("workspace_bound") is False:
        blockers.append("workspace_unbound")
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    if not str(pack.get("base_sha") or "").strip():
        blockers.append("missing_handshake:base_sha")
    if not str(workspace.get("repo_root") or "").strip():
        blockers.append("missing_handshake:repo_root")
    write_root = pack.get("allowed_write_root") or pack.get("allowed_write_roots")
    if isinstance(write_root, list):
        write_root = write_root[0] if write_root else ""
    if not str(write_root or "").strip():
        blockers.append("missing_handshake:allowed_write_root")
    return blockers


def extract_agent_completion(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract exactly one ndf-agent-completion/v1 object from worker stdout.

    Returns (completion_or_None, parse_blockers). Missing / ambiguous / invalid
    schemas fail closed — transport acknowledgement alone is not task success.
    """
    raw = text or ""
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []

    def _consider(blob: str) -> None:
        try:
            value = json.loads(blob)
        except json.JSONDecodeError:
            return
        if isinstance(value, dict) and value.get("schema") == "ndf-agent-completion/v1":
            candidates.append(value)

    # Fenced ```json ... ``` blocks first.
    fence = "```"
    parts = raw.split(fence)
    for idx in range(1, len(parts), 2):
        body = parts[idx]
        if body.lstrip().startswith("json"):
            body = body.lstrip()[4:]
        _consider(body.strip())

    # Whole stdout / last balanced object fallback when no fence hit.
    if not candidates:
        try:
            value = json.loads(raw.strip())
            if isinstance(value, dict) and value.get("schema") == "ndf-agent-completion/v1":
                candidates.append(value)
        except json.JSONDecodeError:
            end = raw.rfind("}")
            if end >= 0:
                depth = 0
                start = None
                for idx in range(end, -1, -1):
                    ch = raw[idx]
                    if ch == "}":
                        depth += 1
                    elif ch == "{":
                        depth -= 1
                        if depth == 0:
                            start = idx
                            break
                if start is not None:
                    _consider(raw[start : end + 1])

    if not candidates:
        return None, ["missing_agent_completion"]
    if len(candidates) > 1:
        # Prefer the last occurrence (final worker judgment).
        completion = candidates[-1]
        errors.append("multiple_agent_completions")
    else:
        completion = candidates[0]
    result = str(completion.get("result") or completion.get("status") or "").lower()
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        errors.append("invalid_agent_completion_result")
    return completion, errors


def _task_outcome_from_transport(
    send_result: Mapping[str, Any],
    *,
    lease_only: bool,
) -> tuple[str, list[str], str, dict[str, Any] | None]:
    """Map transport + optional completion receipt → task result.

    Returns (result, blockers, summary, completion_or_None).
    result is succeeded|failed|delivery_unknown.
    """
    transport_ok = bool(send_result.get("transport_ok") or send_result.get("ok"))
    text = send_result.get("response_text")
    if not transport_ok:
        err = str(send_result.get("error") or send_result.get("state") or "transport_failed")
        return "failed", [err], err, None
    if lease_only:
        return (
            "succeeded",
            [],
            str(text or "lease_only_no_implementation_start")[:240],
            None,
        )
    completion, parse_errors = extract_agent_completion(
        text if isinstance(text, str) else None
    )
    if completion is None:
        blockers = parse_errors or ["missing_agent_completion"]
        return (
            "failed",
            blockers,
            "transport_acknowledged but no ndf-agent-completion/v1",
            None,
        )
    result_raw = str(completion.get("result") or completion.get("status") or "").lower()
    worker_blockers = [
        str(item) for item in (completion.get("blockers") or []) if str(item).strip()
    ]
    summary = str(
        completion.get("summary")
        or completion.get("result_summary")
        or (text or "")[:240]
    )
    if result_raw in {"success", "succeeded"} and not worker_blockers and not parse_errors:
        return "succeeded", [], summary[:800], completion
    blockers = list(worker_blockers)
    for item in parse_errors:
        if item not in blockers:
            blockers.append(item)
    if result_raw not in {"success", "succeeded"} and "agent_completion_failed" not in blockers:
        blockers.insert(0, "agent_completion_failed")
    if not blockers:
        blockers = ["agent_completion_failed"]
    return "failed", blockers, summary[:800], completion


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
            "transport_ok": False,
            "state": "failed",
            "error": "openclaw_nonzero_exit",
            "exit_code": proc.returncode,
            "response_text": text[-8000:],
        }
    return {
        "ok": True,
        "transport_ok": True,
        "state": "transport_acknowledged",
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
    """Resume the configured Claude Code ACP session with the pack.

    Exit 0 means transport acknowledgement only. Task success requires a
    validated ``ndf-agent-completion/v1`` (see ``dispatch_send``).
    """
    import ndf_workflow_status as workflow

    session_id = workflow.configured_acp_session_id()
    if not session_id:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": "acp_session_unconfigured",
            "response_text": None,
        }
    if lease_only:
        # Lease prepare: do not start implementation; record a dry handshake stub.
        return {
            "ok": True,
            "transport_ok": True,
            "state": "succeeded",
            "lease_only": True,
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
            "transport_ok": False,
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
            "transport_ok": False,
            "state": "delivery_unknown",
            "error": "acp_timeout",
            "detail": str(exc),
            "response_text": None,
        }
    except OSError as exc:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "delivery_unknown",
            "error": "acp_spawn_failed",
            "detail": str(exc),
            "response_text": None,
        }
    text = proc.stdout or ""
    if proc.returncode != 0:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": "acp_nonzero_exit",
            "exit_code": proc.returncode,
            "session_id": session_id,
            "response_text": text[-8000:],
        }
    return {
        "ok": True,
        "transport_ok": True,
        "state": "transport_acknowledged",
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
    agent_completion: Mapping[str, Any] | None = None,
    pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist dispatch receipt → action-commit → snapshot.

    Task success MUST NOT be inferred from transport alone. When a Worker
    ``ndf-agent-completion/v1`` is present it is written beside the thin
    dispatch receipt; ``action-finish`` uses the validated task ``result``.
    """
    import ndf_actions
    import ndf_workflow_status as workflow

    steps: dict[str, Any] = {}
    completion_path = ROOT / "tmp" / "ndf-dispatch-completion.json"
    completion = {
        "schema": "ndf-dispatch-completion/v1",
        "result": result,
        "blockers": blockers,
        "result_summary": result_summary,
        "finished_at": workflow.now_iso(),
        "transport_only": agent_completion is None and result != "succeeded",
    }
    if agent_completion is not None:
        completion["agent_completion"] = dict(agent_completion)
        agent_path = ROOT / "tmp" / "ndf-agent-completion.json"
        agent_path.write_text(
            json.dumps(dict(agent_completion), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        steps["agent_completion_path"] = "tmp/ndf-agent-completion.json"
        # Best-effort Episode bind when replay episode + role are known.
        episode_id = None
        if isinstance(pack, Mapping):
            episode_id = (
                pack.get("episode_id")
                or (pack.get("replay") or {}).get("episode_id")
            )
        if episode_id and result == "succeeded":
            try:
                verify, verify_code = workflow.record_agent_completion(
                    agent_path,
                    episode_id=str(episode_id),
                    role="claude-code"
                    if str((pack or {}).get("provider") or "").startswith("claude")
                    else "openclaw",
                    coverage="completion_only",
                )
                steps["completion_record"] = {
                    "exit_code": verify_code,
                    "valid": bool(verify.get("valid")),
                    "errors": verify.get("errors") or [],
                }
                if verify_code != 0 or not verify.get("valid"):
                    # Fail closed: do not keep a false succeeded closeout.
                    result = "failed"
                    for err in verify.get("errors") or ["completion_record_failed"]:
                        if str(err) not in blockers:
                            blockers.append(str(err))
                    completion["result"] = result
                    completion["blockers"] = blockers
            except Exception as exc:  # noqa: BLE001 — closeout must not crash dispatch
                steps["completion_record"] = {
                    "exit_code": 1,
                    "valid": False,
                    "errors": [f"completion_record_exception:{type(exc).__name__}"],
                }
                result = "failed"
                blockers.append(f"completion_record_exception:{type(exc).__name__}")
                completion["result"] = result
                completion["blockers"] = blockers
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
        finish_result = "success" if result == "succeeded" else "failed"
        finish_cmd = [
            "python3",
            "spec/meta/tools/ndf_workflow_status.py",
            "action-finish",
            "--action-id",
            action_id,
            "--result",
            finish_result,
            "--json",
        ]
        for blocker in blockers:
            finish_cmd.extend(["--blocker", str(blocker)[:200]])
        finish = subprocess.run(
            finish_cmd,
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
    steps["final_result"] = result
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
        return {**prior, "schema": "ndf-dispatch-send/v1"}, 0 if prior.get("state") == "succeeded" else 1

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
            pack=pack,
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
            "transport_ok": False,
            "state": "failed",
            "error": f"unknown_provider:{provider}",
            "response_text": None,
        }

    task_result, final_blockers, summary, agent_completion = _task_outcome_from_transport(
        send_result, lease_only=lease_only
    )
    # Prefer Worker-minted run_id; never invent one for a failed/missing receipt.
    run_id = None
    if isinstance(agent_completion, Mapping):
        run_id = agent_completion.get("run_id")
    if run_id is None and lease_only:
        run_id = send_result.get("run_id")
    payload = {
        **sent_receipt,
        "state": task_result,
        "dispatch_state": task_result,
        "result_summary": summary or task_result,
        "blockers": final_blockers,
        "transport_ok": bool(send_result.get("transport_ok") or send_result.get("ok")),
        "send": {k: v for k, v in send_result.items() if k != "response_text"},
        "response_excerpt": (send_result.get("response_text") or "")[:2000],
        "agent_completion": agent_completion,
        "finished_at": time.time(),
    }
    if run_id:
        payload["run_id"] = run_id
    if send_result.get("session_id"):
        payload["session_id"] = send_result.get("session_id")
    # Closeout order is fixed: completion → action-commit → snapshot.
    payload["closeout"] = _closeout(
        catalog_action_id=catalog_action_id,
        action_id=action_id,
        result=task_result,
        blockers=final_blockers,
        result_summary=payload["result_summary"],
        agent_completion=agent_completion,
        pack=pack,
    )
    # completion_record may have downgraded success → failed inside _closeout.
    close_final = (payload["closeout"] or {}).get("final_result")
    if close_final in {"succeeded", "failed"} and close_final != task_result:
        payload["state"] = close_final
        payload["dispatch_state"] = close_final
        payload["blockers"] = list(
            (payload["closeout"].get("completion") or {}).get("blockers") or final_blockers
        )
        task_result = close_final
    _write_last(payload)
    code = 0 if task_result == "succeeded" else 1
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
