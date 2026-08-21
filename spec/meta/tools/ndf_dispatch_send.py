#!/usr/bin/env python3
"""Trusted pack → OpenClaw / Claude Code ACP dispatch.

Command Agent builds pack JSON, waits for human 「派发」, then runs this module:
  1. sends when safe_to_dispatch (or lease-only prepare)
  2. waits for worker stdout notify (ndf-dispatch-notify/v1)
  3. reads pack.completion_receipt_path from disk
  4. records that disk completion → action-commit → action-finish → snapshot

stdout completion JSON and transport acknowledgement MUST NOT count as
validated success. Must not rely on Cursor afterShellExecution to auto-send.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
DISPATCH_LAST = ROOT / "tmp" / "ndf-dispatch-last.json"
DEFAULT_TIMEOUT_SEC = 900
DEFAULT_OPENCLAW_PING_SEC = 60
DEFAULT_OPENCLAW_STALL_SEC = 900
DEFAULT_OPENCLAW_MAX_SEC = 14400


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
    # Capability readiness: fail closed unless lease-only prepare.
    if pack.get("execution_capabilities_ready") is False:
        for item in (pack.get("blockers") or []):
            text = str(item)
            if text.startswith("capability_missing:") or text == "waiting_human":
                if text not in blockers:
                    blockers.append(text)
        if "waiting_human" not in blockers and not any(
            str(b).startswith("capability_missing:") for b in blockers
        ):
            blockers.append("execution_capabilities_not_ready")
    return blockers


def _command_flag(command: str, name: str) -> str:
    match = re.search(rf"--{re.escape(name)}(?:\s+|=)(\S+)", command or "")
    return match.group(1).strip() if match else ""


def correlate_started_action(
    pack: Mapping[str, Any],
    *,
    command: str = "",
    receipts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Match a started action receipt to a pack or pack CLI. Never 'latest started' alone."""
    import ndf_actions
    import ndf_workflow_status as workflow

    if receipts is None:
        try:
            receipts = workflow.read_action_receipts()
        except Exception:
            receipts = []
    action_id = str(pack.get("action_id") or pack.get("attempt_id") or "").strip()
    catalog = str(pack.get("catalog_action_id") or "").strip()
    episode = _pack_episode_id(pack)
    task = str(pack.get("task") or "").strip()
    if command:
        action_id = action_id or _command_flag(command, "action-id")
        episode = episode or _command_flag(command, "episode")
        task = task or _command_flag(command, "task")
    if not catalog and task:
        for item in ndf_actions.registry_actions():
            if item.get("task") == task or item.get("packTask") == task:
                catalog = str(item.get("id") or "")
                break
    started = [
        receipt
        for receipt in receipts
        if receipt.get("status") == "started" and receipt.get("action_id")
    ]
    if action_id:
        match = next(
            (
                receipt
                for receipt in reversed(started)
                if str(receipt.get("action_id") or "") == action_id
            ),
            None,
        )
        if match:
            return dict(match)
    for receipt in reversed(started):
        rec_catalog = str(receipt.get("catalog_action_id") or "")
        rec_episode = str(
            receipt.get("episode_id")
            or (receipt.get("replay") or {}).get("episode_id")
            or ""
        )
        rec_task = str(receipt.get("operation") or receipt.get("task") or "")
        if catalog and rec_catalog and rec_catalog != catalog:
            continue
        if episode and rec_episode and rec_episode != episode:
            continue
        if catalog and rec_catalog == catalog:
            return dict(receipt)
        if task and rec_task in {task, catalog}:
            return dict(receipt)
    return None


def _finish_result(result: str, blockers: list[str]) -> str:
    if result == "succeeded":
        return "success"
    if result in {"cancelled", "blocked"} or "waiting_human" in blockers:
        return "cancelled"
    return "failed"


def _pack_episode_id(pack: Mapping[str, Any]) -> str:
    episode = pack.get("episode_id")
    if isinstance(episode, str) and episode.strip():
        return episode.strip()
    replay = pack.get("replay") if isinstance(pack.get("replay"), Mapping) else {}
    nested = replay.get("episode_id") if isinstance(replay, Mapping) else None
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return ""


def _build_worker_message(pack: Mapping[str, Any]) -> str:
    provider = str(pack.get("provider") or "")
    topic = pack.get("topic") or ""
    task = pack.get("task") or ""
    episode = _pack_episode_id(pack)
    attempt = (
        pack.get("attempt_id")
        or pack.get("action_id")
        or (pack.get("replay") or {}).get("attempt_id")
        or ""
    )
    catalog = pack.get("catalog_action_id") or ""
    manifest = pack.get("manifest_sha") or ""
    plan = pack.get("plan_sha") or (pack.get("context_plan") or {}).get("plan_sha") or ""
    lines = [
        f"【NDF dispatch-send】provider={provider} task={task} topic={topic}",
        f"episode_id={episode}",
        f"attempt_id={attempt}",
        f"catalog_action_id={catalog}",
        f"action_id={pack.get('action_id') or ''}",
        f"manifest_sha={manifest}",
        f"context_plan_sha={plan}",
        f"allowed_write_root={pack.get('allowed_write_root') or pack.get('allowed_write_roots')}",
        f"completion_receipt_path={pack.get('completion_receipt_path') or ''}",
        "Follow the pack JSON binding.",
        "Write the full ndf-agent-completion/v1 to pack.completion_receipt_path "
        "(changed_files, changed_file_shas, evidence_paths, evidence_bundle_sha, "
        "reproduce_commands — not 'reproduce', git_commit, post_check_receipts).",
        "Stdout MUST be exactly one ndf-dispatch-notify/v1 object "
        "(result, receipt_path, topic, task, episode_id, attempt_id). "
        "MUST NOT treat a thin stdout ndf-agent-completion/v1 as the validated receipt.",
        "Commander (Cursor) is the only human capability surface. This pack is already "
        "capability-approved; run the bound measure/write. MUST NOT wait for a Claude Code "
        "Bash permission prompt. MUST NOT treat execution_binding_stale as a blocker. "
        "Host sudo is passwordless.",
    ]
    if provider == "claude-code-acp":
        lines.append(
            "ACP: first lease-record (or continue the active lease for this attempt). "
            "Disk receipt MUST include worktree, branch, run_id, session_id "
            "(session_id MUST equal this resume id). Dispatcher will not invent them."
        )
    lines.extend([
        "BEGIN NDF_PACK_JSON",
        json.dumps(pack, ensure_ascii=False, sort_keys=True, default=str),
        "END NDF_PACK_JSON",
    ])
    return "\n".join(lines)


def _extract_schema_objects(text: str | None, schema: str) -> list[dict[str, Any]]:
    raw = text or ""
    candidates: list[dict[str, Any]] = []

    def _consider(blob: str) -> None:
        try:
            value = json.loads(blob)
        except json.JSONDecodeError:
            return
        if isinstance(value, dict) and value.get("schema") == schema:
            candidates.append(value)

    fence = "```"
    parts = raw.split(fence)
    for idx in range(1, len(parts), 2):
        body = parts[idx]
        if body.lstrip().startswith("json"):
            body = body.lstrip()[4:]
        _consider(body.strip())

    if not candidates:
        try:
            value = json.loads(raw.strip())
            if isinstance(value, dict) and value.get("schema") == schema:
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
    return candidates


def extract_agent_completion(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract ndf-agent-completion/v1 from text (tests / leftover stdout).

    dispatch-send MUST NOT use this for completion-record. Validated receipts
    come from disk via extract_dispatch_notify + load_disk_agent_completion.
    """
    candidates = _extract_schema_objects(text, "ndf-agent-completion/v1")
    errors: list[str] = []
    if not candidates:
        return None, ["missing_agent_completion"]
    if len(candidates) > 1:
        completion = candidates[-1]
        errors.append("multiple_agent_completions")
    else:
        completion = candidates[0]
    result = str(completion.get("result") or completion.get("status") or "").lower()
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        errors.append("invalid_agent_completion_result")
    return completion, errors


def extract_dispatch_notify(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract exactly one ndf-dispatch-notify/v1 from worker stdout."""
    candidates = _extract_schema_objects(text, "ndf-dispatch-notify/v1")
    errors: list[str] = []
    if not candidates:
        return None, ["missing_dispatch_notify"]
    if len(candidates) > 1:
        notify = candidates[-1]
        errors.append("multiple_dispatch_notifies")
    else:
        notify = candidates[0]
    for field in ("result", "receipt_path", "topic", "task", "episode_id", "attempt_id"):
        if field not in notify:
            errors.append(f"missing_notify:{field}")
        elif field != "topic" and not str(notify.get(field) or "").strip():
            errors.append(f"missing_notify:{field}")
        elif field == "topic" and notify.get("topic") is None:
            errors.append("missing_notify:topic")
    result = str(notify.get("result") or "").lower()
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        errors.append("invalid_dispatch_notify_result")
    return notify, errors


def _normalize_relpath(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    return text


def _is_safe_relpath(path: str) -> bool:
    text = _normalize_relpath(path)
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    try:
        parts = Path(text).parts
    except (ValueError, OSError):
        return False
    if not parts or parts[0] in {"/", ".."}:
        return False
    return all(part not in {"..", ""} for part in parts)


def _first_write_root(pack: Mapping[str, Any]) -> str:
    write_root = pack.get("allowed_write_root") or pack.get("allowed_write_roots")
    if write_root is None:
        write_root = pack.get("allowed_write_paths")
    if isinstance(write_root, list):
        write_root = write_root[0] if write_root else ""
    return _normalize_relpath(str(write_root or ""))


def _under_write_root(path: str, write_root: str) -> bool:
    rel = _normalize_relpath(path).rstrip("/")
    root = _normalize_relpath(write_root).rstrip("/")
    if not root:
        return False
    return rel == root or rel.startswith(root + "/")


def _pack_repo_root(pack: Mapping[str, Any]) -> Path:
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    raw = str(workspace.get("repo_root") or ROOT)
    return Path(raw)


def completion_receipt_path_for_pack(pack: Mapping[str, Any]) -> str:
    """Pack-pinned relative path for the disk ndf-agent-completion/v1."""
    declared = _normalize_relpath(str(pack.get("completion_receipt_path") or ""))
    if declared:
        return declared
    topic = str(pack.get("topic") or "").strip()
    task = str(pack.get("task") or "task").strip().replace(" ", "_") or "task"
    attempt = str(
        pack.get("attempt_id")
        or pack.get("action_id")
        or (pack.get("replay") or {}).get("attempt_id")
        or "attempt"
    ).strip() or "attempt"
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    topic_ndf = _normalize_relpath(str(workspace.get("topic_ndf_dir") or ""))
    if not topic_ndf and topic:
        topic_ndf = f"poc/{topic}/ndf"
    write_root = _first_write_root(pack)
    if topic_ndf:
        candidate = _normalize_relpath(f"{topic_ndf.rstrip('/')}/evidence/{task}-completion.json")
        if not write_root or _under_write_root(candidate, write_root):
            return candidate
    tmp_candidate = _normalize_relpath(f"tmp/ndf-completion/{attempt}.json")
    if write_root and _under_write_root(tmp_candidate, write_root):
        return tmp_candidate
    if write_root:
        return _normalize_relpath(
            f"{write_root.rstrip('/')}/.ndf-completion/{task}-{attempt}.json"
        )
    return tmp_candidate


def _resolve_disk_receipt_path(
    pack: Mapping[str, Any],
    receipt_path: str,
) -> tuple[Path | None, list[str]]:
    expected = completion_receipt_path_for_pack(pack)
    rel = _normalize_relpath(receipt_path)
    if not _is_safe_relpath(rel):
        return None, ["illegal_receipt_path"]
    if _normalize_relpath(expected) != rel:
        return None, ["receipt_path_mismatch"]
    write_root = _first_write_root(pack)
    if write_root and not _under_write_root(rel, write_root):
        return None, ["receipt_path_outside_write_root"]
    root = _pack_repo_root(pack)
    full = (root / rel)
    try:
        full.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None, ["receipt_path_outside_repo"]
    return full, []


def load_disk_agent_completion(
    pack: Mapping[str, Any],
    notify: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read ndf-agent-completion/v1 from notify.receipt_path under the write root."""
    receipt_path = str(notify.get("receipt_path") or "")
    path, errors = _resolve_disk_receipt_path(pack, receipt_path)
    if path is None:
        return None, errors or ["illegal_receipt_path"]
    if not path.is_file():
        return None, ["missing_disk_receipt"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ["invalid_disk_receipt_json"]
    if not isinstance(data, dict) or data.get("schema") != "ndf-agent-completion/v1":
        return None, ["invalid_disk_receipt_schema"]
    result = str(data.get("result") or data.get("status") or "").lower()
    extra: list[str] = []
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        extra.append("invalid_agent_completion_result")
    return data, extra


def _notify_identity_errors(pack: Mapping[str, Any], notify: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    pack_topic = str(pack.get("topic") or "")
    notify_topic = str(notify.get("topic") or "")
    if pack_topic != notify_topic:
        errors.append("notify_topic_mismatch")
    pack_task = str(pack.get("task") or "")
    notify_task = str(notify.get("task") or "")
    if pack_task and notify_task and pack_task != notify_task:
        errors.append("notify_task_mismatch")
    pack_episode = _pack_episode_id(pack)
    notify_episode = str(notify.get("episode_id") or "")
    if pack_episode and notify_episode and pack_episode != notify_episode:
        errors.append("notify_episode_mismatch")
    pack_attempt = str(
        pack.get("attempt_id") or pack.get("action_id") or ""
    ).strip()
    notify_attempt = str(notify.get("attempt_id") or "").strip()
    if pack_attempt and notify_attempt and pack_attempt != notify_attempt:
        errors.append("notify_attempt_mismatch")
    return errors


def _task_outcome_from_transport(
    send_result: Mapping[str, Any],
    *,
    pack: Mapping[str, Any],
    lease_only: bool,
) -> tuple[str, list[str], str, dict[str, Any] | None]:
    """Map transport notify + disk receipt → task result.

    stdout ndf-agent-completion/v1 is ignored. Returns
    (result, blockers, summary, completion_or_None).
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
    notify, parse_errors = extract_dispatch_notify(
        text if isinstance(text, str) else None
    )
    if notify is None:
        blockers = parse_errors or ["missing_dispatch_notify"]
        return (
            "failed",
            blockers,
            "transport_acknowledged but no ndf-dispatch-notify/v1",
            None,
        )
    identity_errors = _notify_identity_errors(pack, notify)
    path_ok = not any(
        item.startswith("missing_notify:") or item == "illegal_receipt_path"
        for item in parse_errors
    )
    completion = None
    disk_errors: list[str] = []
    if path_ok and "missing_notify:receipt_path" not in parse_errors:
        completion, disk_errors = load_disk_agent_completion(pack, notify)
    all_errors = list(parse_errors)
    for item in identity_errors + disk_errors:
        if item not in all_errors:
            all_errors.append(item)
    if completion is None:
        blockers = all_errors or ["missing_disk_receipt"]
        return (
            "failed",
            blockers,
            "notify present but disk ndf-agent-completion/v1 unusable",
            None,
        )
    provider = str(pack.get("provider") or "")
    if provider == "claude-code-acp":
        resume_id = str(send_result.get("session_id") or "").strip()
        receipt_sid = str(completion.get("session_id") or "").strip()
        if resume_id and receipt_sid and resume_id != receipt_sid:
            all_errors.append("session_id_mismatch")
    notify_result = str(notify.get("result") or "").lower()
    result_raw = str(completion.get("result") or completion.get("status") or "").lower()
    if (
        notify_result
        and result_raw
        and notify_result not in {result_raw, "success" if result_raw == "succeeded" else result_raw}
        and not (
            {notify_result, result_raw} <= {"success", "succeeded"}
            or {notify_result, result_raw} <= {"failed", "cancelled", "blocked"}
        )
    ):
        all_errors.append("notify_result_mismatch")
    worker_blockers = [
        str(item) for item in (completion.get("blockers") or []) if str(item).strip()
    ]
    summary = str(
        completion.get("summary")
        or completion.get("result_summary")
        or notify.get("summary")
        or (text or "")[:240]
    )
    if result_raw in {"success", "succeeded"} and not worker_blockers and not all_errors:
        return "succeeded", [], summary[:800], completion
    blockers = list(worker_blockers)
    for item in all_errors:
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


_OPENCLAW_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_openclaw_uuid(value: str) -> bool:
    return bool(_OPENCLAW_UUID_RE.fullmatch(str(value or "").strip()))


def _openclaw_wait_budgets(
    timeout_sec: int | None = None,
) -> tuple[float, float, float]:
    """Return (ping_sec, stall_sec, max_sec) for OpenClaw heartbeat wait."""
    ping = float(
        os.environ.get("NDF_OPENCLAW_PING_SEC") or DEFAULT_OPENCLAW_PING_SEC
    )
    stall = float(
        os.environ.get("NDF_OPENCLAW_STALL_SEC") or DEFAULT_OPENCLAW_STALL_SEC
    )
    # Absolute ceiling: explicit MAX, else at least legacy timeout, else default max.
    legacy = float(timeout_sec or DEFAULT_TIMEOUT_SEC)
    max_sec = float(
        os.environ.get("NDF_OPENCLAW_MAX_SEC")
        or max(DEFAULT_OPENCLAW_MAX_SEC, legacy)
    )
    ping = max(5.0, ping)
    stall = max(ping, stall)
    max_sec = max(stall, max_sec)
    return ping, stall, max_sec


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text or ""
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def _openclaw_session_progress(
    session_key: str,
    *,
    executable: str | None = None,
) -> dict[str, Any] | None:
    """Read sessions store row for configured key; used as heartbeat progress."""
    key = str(session_key or "").strip()
    if not key:
        return None
    exe = executable or shutil.which("openclaw")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "sessions", "--json", "--all-agents", "--limit", "100"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    payload = _extract_json_object(proc.stdout or "")
    if not payload:
        return None
    for item in payload.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "") == key or str(item.get("sessionId") or "") == key:
            return {
                "key": item.get("key"),
                "sessionId": item.get("sessionId"),
                "updatedAt": item.get("updatedAt"),
                "totalTokens": item.get("totalTokens"),
                "abortedLastRun": item.get("abortedLastRun"),
                "model": item.get("model"),
            }
    return None


def _progress_signature(row: Mapping[str, Any] | None) -> tuple[Any, Any]:
    if not row:
        return (None, None)
    return (row.get("updatedAt"), row.get("totalTokens"))


def _disk_completion_present(pack: Mapping[str, Any]) -> bool:
    rel = str(pack.get("completion_receipt_path") or "").strip()
    if not rel:
        return False
    path = _pack_repo_root(pack) / rel
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("schema") == "ndf-agent-completion/v1"


def _write_openclaw_heartbeat(
    *,
    pack_sha: str,
    request_id: str,
    provider: str,
    started_at: float,
    heartbeat: Mapping[str, Any],
) -> None:
    prior: dict[str, Any] = {}
    if DISPATCH_LAST.is_file():
        try:
            loaded = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prior = loaded
        except json.JSONDecodeError:
            prior = {}
    payload = {
        **prior,
        "schema": "ndf-dispatch-send/v1",
        "state": "sent",
        "dispatch_state": "awaiting_result",
        "delegate_to": provider or prior.get("delegate_to") or "openclaw",
        "pack_sha": pack_sha or prior.get("pack_sha"),
        "request_id": request_id or prior.get("request_id"),
        "sent": True,
        "started_at": started_at or prior.get("started_at"),
        "result_summary": "已发出，心跳等待 OpenClaw",
        "openclaw_heartbeat": dict(heartbeat),
        "heartbeat_at": time.time(),
    }
    _write_last(payload)


def _send_openclaw(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
) -> dict[str, Any]:
    session_key = str(pack.get("session_key") or "").strip()
    resolved = str(pack.get("resolved_session_id") or "").strip()
    transport = str(pack.get("session_transport") or "").strip()
    if not transport and not resolved and session_key:
        try:
            import ndf_workflow_status as workflow

            resolution = workflow.resolve_openclaw_dispatch_session(session_key)
            resolved = str(resolution.get("resolved_session_id") or "").strip()
            transport = str(resolution.get("transport") or "").strip()
        except Exception:
            resolved = ""
            transport = ""
    if not transport:
        if resolved and _looks_like_openclaw_uuid(resolved):
            transport = "session_id"
        elif session_key and ":" in session_key and not _looks_like_openclaw_uuid(
            session_key
        ):
            transport = "session_key"
        elif session_key and _looks_like_openclaw_uuid(session_key):
            transport = "session_id"
            resolved = session_key
        else:
            transport = "session_key" if session_key else "session_id"
    override = os.environ.get("NDF_OPENCLAW_DISPATCH_CMD")
    executable = shutil.which("openclaw")
    if override:
        cmd = override.split()
        use_heartbeat = False
    elif not executable:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_cli_missing",
            "response_text": None,
        }
    elif transport == "session_id":
        session_id = resolved or session_key
        cmd = [executable, "agent", "--agent", "main", "--message", message]
        if session_id:
            cmd.extend(["--session-id", session_id])
        use_heartbeat = True
    else:
        import uuid as _uuid

        ping_sec, stall_sec, max_sec = _openclaw_wait_budgets(timeout_sec)
        timeout_ms = int(max_sec * 1000) + 60_000
        params = {
            "message": message,
            "agentId": "main",
            "sessionKey": session_key,
            "timeout": int(max_sec),
            "idempotencyKey": str(_uuid.uuid4()),
        }
        cmd = [
            executable,
            "gateway",
            "call",
            "agent",
            "--expect-final",
            "--json",
            "--timeout",
            str(timeout_ms),
            "--params",
            json.dumps(params, ensure_ascii=False),
        ]
        use_heartbeat = True

    if not use_heartbeat:
        # Test / override path: single blocking run with legacy timeout.
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=float(timeout_sec),
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

    return _wait_openclaw_with_heartbeat(
        pack,
        cmd=cmd,
        session_key=session_key,
        executable=executable,
        timeout_sec=timeout_sec,
    )


def _wait_openclaw_with_heartbeat(
    pack: Mapping[str, Any],
    *,
    cmd: list[str],
    session_key: str,
    executable: str | None,
    timeout_sec: int,
) -> dict[str, Any]:
    ping_sec, stall_sec, max_sec = _openclaw_wait_budgets(timeout_sec)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    provider = str(pack.get("provider") or "openclaw")
    started = time.time()
    hard_deadline = started + max_sec
    last_progress_at = started
    last_sig = _progress_signature(
        _openclaw_session_progress(session_key, executable=executable)
    )
    ping_count = 0
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "NDF_PACK_SHA": pack_sha},
        )
    except OSError as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_spawn_failed",
            "detail": str(exc),
            "response_text": None,
        }

    chunks: list[str] = []
    assert proc.stdout is not None
    last_ping_at = 0.0
    try:
        while True:
            # Non-blocking read of available stdout.
            ready, _, _ = select.select([proc.stdout], [], [], min(ping_sec, 1.0))
            if ready:
                line = proc.stdout.readline()
                if line:
                    chunks.append(line)
            rc = proc.poll()
            now = time.time()
            if rc is not None:
                # Drain remainder.
                rest = proc.stdout.read() or ""
                if rest:
                    chunks.append(rest)
                text = "".join(chunks)
                if rc != 0:
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_nonzero_exit",
                        "exit_code": rc,
                        "response_text": text[-8000:],
                        "openclaw_heartbeat": {
                            "pings": ping_count,
                            "elapsed_sec": round(now - started, 1),
                            "stall_sec": stall_sec,
                            "max_sec": max_sec,
                        },
                    }
                return {
                    "ok": True,
                    "transport_ok": True,
                    "state": "transport_acknowledged",
                    "exit_code": 0,
                    "response_text": text[-8000:],
                    "openclaw_heartbeat": {
                        "pings": ping_count,
                        "elapsed_sec": round(now - started, 1),
                        "stall_sec": stall_sec,
                        "max_sec": max_sec,
                        "finished": "gateway_final",
                    },
                }

            if now - last_ping_at >= ping_sec:
                last_ping_at = now
                ping_count += 1
                row = _openclaw_session_progress(session_key, executable=executable)
                sig = _progress_signature(row)
                progressed = sig != last_sig and sig != (None, None)
                disk_done = _disk_completion_present(pack)
                if progressed:
                    last_sig = sig
                    last_progress_at = now
                if disk_done:
                    last_progress_at = now
                heartbeat = {
                    "pings": ping_count,
                    "elapsed_sec": round(now - started, 1),
                    "seconds_since_progress": round(now - last_progress_at, 1),
                    "stall_sec": stall_sec,
                    "max_sec": max_sec,
                    "session": row,
                    "progressed": progressed,
                    "disk_completion_present": disk_done,
                }
                _write_openclaw_heartbeat(
                    pack_sha=pack_sha,
                    request_id=request_id,
                    provider=provider,
                    started_at=started,
                    heartbeat=heartbeat,
                )
                if now - last_progress_at >= stall_sec:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_stalled",
                        "detail": (
                            f"no session/disk progress for {stall_sec:.0f}s "
                            f"(pings={ping_count})"
                        ),
                        "response_text": "".join(chunks)[-8000:],
                        "openclaw_heartbeat": heartbeat,
                    }
                if now >= hard_deadline:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_timeout",
                        "detail": f"absolute max_sec={max_sec:.0f} exceeded",
                        "response_text": "".join(chunks)[-8000:],
                        "openclaw_heartbeat": heartbeat,
                    }
    except Exception as exc:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_heartbeat_error",
            "detail": str(exc),
            "response_text": "".join(chunks)[-8000:],
        }


def _acp_inherit_commander_permissions(pack: Mapping[str, Any]) -> bool:
    """True when the commander already approved capabilities / 派发."""
    if pack.get("execution_capabilities_ready") is True:
        return True
    caps = pack.get("capabilities")
    if isinstance(caps, Mapping) and caps.get("execution_capabilities_ready") is True:
        return True
    return pack.get("safe_to_dispatch") is True


def _acp_argv(
    pack: Mapping[str, Any],
    *,
    session_id: str,
    message: str,
    executable: str | None = None,
) -> list[str] | None:
    """Build ``claude --resume`` argv. None means the CLI is missing.

    Commander-approved packs inherit permission bypass so the ACP session is
    not a second human gate. ``NDF_ACP_DISPATCH_CMD`` replaces the argv as-is.
    """
    override = os.environ.get("NDF_ACP_DISPATCH_CMD")
    if override:
        return override.split()
    exe = executable if executable is not None else shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "--resume", session_id]
    if _acp_inherit_commander_permissions(pack):
        cmd.extend(
            [
                "--permission-mode",
                "bypassPermissions",
                "--dangerously-skip-permissions",
            ]
        )
    cmd.extend(["-p", message, "--output-format", "text"])
    return cmd


def _send_acp(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
    lease_only: bool,
) -> dict[str, Any]:
    """Resume the configured Claude Code ACP session with the pack.

    Exit 0 means transport acknowledgement only. Task success requires a
    disk ``ndf-agent-completion/v1`` at ``pack.completion_receipt_path``
    after stdout ``ndf-dispatch-notify/v1`` (see ``dispatch_send``).
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
    cmd = _acp_argv(pack, session_id=session_id, message=message)
    if not cmd:
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
            "response_text": text[-8000:],  # notify-sized; disk receipt is authoritative
        }
    return {
        "ok": True,
        "transport_ok": True,
        "state": "transport_acknowledged",
        "session_id": session_id,
        "exit_code": 0,
        "response_text": text[-8000:],  # notify-sized; disk receipt is authoritative
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
        # Bind Episode for both success and failure completions.
        episode_id = None
        if isinstance(pack, Mapping):
            episode_id = _pack_episode_id(pack)
        if episode_id and agent_completion is not None:
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
                if result == "succeeded" and (
                    verify_code != 0 or not verify.get("valid")
                ):
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
                if result == "succeeded":
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
    if action_id:
        finish_result = _finish_result(result, blockers)
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
        episode_id = _pack_episode_id(pack) if isinstance(pack, Mapping) else ""
        if episode_id:
            finish_cmd.extend(["--episode", episode_id])
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
    snap_cmd = [
        "python3",
        "spec/meta/tools/ndf_workflow_status.py",
        "snapshot",
        "--out",
        "tmp/ndf-canvas-snapshot.json",
        "--json",
    ]
    topic = ""
    if isinstance(pack, Mapping):
        topic = str(pack.get("topic") or "").strip()
    if topic:
        snap_cmd.extend(["--topic", topic])
    snap = subprocess.run(
        snap_cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    steps["snapshot"] = {
        "exit_code": snap.returncode,
        "stdout": (snap.stdout or "")[-2000:],
        "stderr": (snap.stderr or "")[-1000:],
    }
    # Task success + projection failure → distinct state; do not wipe task result.
    if result == "succeeded" and snap.returncode != 0:
        result = "succeeded_projection_stale"
        blockers.append("projection_publish_failed")
        completion["result"] = result
        completion["blockers"] = blockers
        completion_path.write_text(
            json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        steps["completion"] = {"path": "tmp/ndf-dispatch-completion.json", **completion}
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
        # waiting_human / blocked still MUST finish the started attempt and
        # snapshot --out so requireFresh CTAs are not stuck in refresh_in_progress.
        close_result = (
            "cancelled"
            if "waiting_human" in blockers or pack.get("dispatch_state") == "waiting_human"
            else "failed"
        )
        close = _closeout(
            catalog_action_id=catalog_action_id,
            action_id=action_id,
            result=close_result,
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

    working = dict(pack)
    if action_id:
        working.setdefault("action_id", action_id)
        working.setdefault("attempt_id", action_id)
    working["completion_receipt_path"] = completion_receipt_path_for_pack(working)
    pack = working

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
        send_result, pack=pack, lease_only=lease_only
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
    # completion_record may have downgraded success → failed / projection_stale.
    close_final = (payload["closeout"] or {}).get("final_result")
    if close_final in {"succeeded", "failed", "succeeded_projection_stale"} and close_final != task_result:
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
