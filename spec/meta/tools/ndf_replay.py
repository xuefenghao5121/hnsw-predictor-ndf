#!/usr/bin/env python3
"""Content-addressed Agent Episode recording and bounded replay.

The default store is ``<repo>/.ndf/replay`` and is not an NDF source of truth.
All mutation is explicit through this CLI or the ``ReplayStore`` API.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - deployment guard
    AESGCM = None  # type: ignore[assignment]

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ndf_workflow_evidence import (  # noqa: E402
    canonical_json_bytes,
    canonical_json_sha,
    chained_event,
    validate_evidence_bundle,
    validate_event_chain,
    validate_receipt,
    validate_recorded_runtime_lease_binding,
    validate_runtime_lease_binding,
)

ROOT = Path(__file__).resolve().parents[3]
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
EVENT_KINDS = frozenset(
    {
        "intent.received",
        "manifest.created",
        "context.compiled",
        "context.expanded",
        "context.verified",
        "proposal.confirmed",
        "proposal.reviewed",
        "gate.approved",
        "gate.audit",
        "gate.draft",
        "gate.confirmed",
        "binder.audit",
        "binder.amend",
        "binder.recheck",
        "control.handoff",
        "decision.selected",
        "control.dispatch",
        "dispatch.preflight",
        "dispatch.blocked",
        "openclaw.request",
        "openclaw.response",
        "acp.start",
        "lease.acquired",
        "model.request",
        "model.response",
        "tool.invoke",
        "tool.result",
        "filesystem.acquired",
        "filesystem.changed",
        "git.commit",
        "acp.complete",
        "lease.released",
        "verification.completed",
        "close.receipt",
        "action.begin",
        "action.finish",
        "snapshot.embedded",
        "compaction.checkpoint",
        "legacy.import",
    }
)
REPLAY_LEVELS = ("R0", "R1", "R2", "R3")
SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|session[_-]?key|authorization|cookie)",
    re.I,
)
_UNSET = object()
ENCRYPTED_MAGIC = b"NDFE1\0"
AGENT_ACTORS = {
    "agent",
    "openclaw",
    "claude-code",
    "canvas",
    "tool",
    "context-compiler",
    "project-control",
    "model",
    "sandbox",
    "close",
}
CONTROL_STAGES = frozenset({"draft", "confirm_land", "review"})
CONTROL_STAGE_ORDER = ("draft", "confirm_land", "review")

# Replay projection helpers (Canvas-facing; do not change object schema).
HUMAN_SPACE_KINDS = frozenset(
    {
        "intent.received",
        "proposal.confirmed",
        "proposal.reviewed",
        "gate.approved",
        "gate.confirmed",
        "decision.selected",
    }
)
NDF_SPACE_KINDS = frozenset(
    {
        "manifest.created",
        "context.compiled",
        "context.expanded",
        "context.verified",
        "gate.audit",
        "gate.draft",
        "binder.audit",
        "binder.amend",
        "binder.recheck",
        "control.handoff",
        "control.dispatch",
        "dispatch.preflight",
        "dispatch.blocked",
        "openclaw.request",
        "openclaw.response",
        "acp.start",
        "lease.acquired",
        "lease.released",
        "compaction.checkpoint",
        "snapshot.embedded",
        "action.begin",
        "action.finish",
    }
)
RESULT_SPACE_KINDS = frozenset(
    {
        "model.request",
        "model.response",
        "tool.invoke",
        "tool.result",
        "filesystem.acquired",
        "filesystem.changed",
        "git.commit",
        "acp.complete",
        "verification.completed",
        "close.receipt",
        "legacy.import",
    }
)
META_PLANE_KINDS = frozenset(
    {
        "proposal.confirmed",
        "proposal.reviewed",
        "gate.approved",
        "gate.audit",
        "gate.draft",
        "gate.confirmed",
        "binder.audit",
        "binder.amend",
        "binder.recheck",
        "control.handoff",
        "control.dispatch",
        "dispatch.preflight",
        "dispatch.blocked",
        "openclaw.request",
        "openclaw.response",
        "snapshot.embedded",
        "compaction.checkpoint",
        "action.begin",
        "action.finish",
    }
)
PROJECT_PLANE_KINDS = frozenset(
    {
        "model.request",
        "model.response",
        "tool.invoke",
        "tool.result",
        "filesystem.acquired",
        "filesystem.changed",
        "git.commit",
        "acp.start",
        "acp.complete",
        "lease.acquired",
        "lease.released",
        "verification.completed",
        "close.receipt",
    }
)
DISPATCH_KINDS = frozenset(
    {
        "openclaw.request",
        "acp.start",
        "control.dispatch",
        "dispatch.preflight",
    }
)
KNOWN_GATE_PHRASES = frozenset(
    {
        "已确认",
        "已审核",
        "TOPIC已审核",
        "DESIGN已审核",
        "可以开始实现",
        "IDEA已审核",
        "CHARTER已审核",
        "ARCHITECTURE已审核",
        "VERIFICATION已审核",
        "可以建立初始主线",
        "GENESIS已审核",
    }
)
EVENT_TITLE_ZH = {
    "intent.received": "收到意图",
    "manifest.created": "创建任务清单",
    "context.compiled": "拼装规范上下文",
    "context.expanded": "展开图闭包",
    "context.verified": "校验规范上下文",
    "proposal.confirmed": "提案已确认",
    "proposal.reviewed": "提案已审核",
    "gate.approved": "门禁通过",
    "gate.audit": "门禁审计",
    "gate.draft": "门禁草稿",
    "gate.confirmed": "人工门禁确认",
    "binder.audit": "装订器审计",
    "binder.amend": "装订器修订",
    "binder.recheck": "装订器复核",
    "control.handoff": "控制面交接",
    "decision.selected": "选定决策",
    "control.dispatch": "控制面派发",
    "dispatch.preflight": "派发预检",
    "dispatch.blocked": "派发阻塞",
    "openclaw.request": "下达 OpenClaw",
    "openclaw.response": "OpenClaw 回执",
    "acp.start": "下达 Claude Code",
    "lease.acquired": "获得运行租约",
    "model.request": "模型请求",
    "model.response": "模型回复",
    "tool.invoke": "调用工具",
    "tool.result": "工具结果",
    "filesystem.acquired": "获取文件系统快照",
    "filesystem.changed": "文件变更",
    "git.commit": "Git 提交",
    "acp.complete": "Claude Code 完成",
    "lease.released": "释放运行租约",
    "verification.completed": "验证完成",
    "close.receipt": "关闭回执",
    "action.begin": "投影动作开始",
    "action.finish": "投影动作结束",
    "snapshot.embedded": "嵌入快照",
    "compaction.checkpoint": "压缩检查点",
    "legacy.import": "遗产导入",
}
STAGE_TITLE_ZH = {
    "draft": "起草",
    "confirm_land": "确认落地",
    "review": "审核",
}


def event_space(kind: str) -> str:
    """Classify an event into human | ndf | result description space."""
    if kind in HUMAN_SPACE_KINDS:
        return "human"
    if kind in RESULT_SPACE_KINDS:
        return "result"
    if kind in NDF_SPACE_KINDS:
        return "ndf"
    return "ndf"


def event_plane(kind: str, *, track: str | None = None, actor: str | None = None) -> str:
    """Classify an event into meta (NDF workflow) or project plane."""
    if kind in META_PLANE_KINDS:
        return "meta"
    if kind in PROJECT_PLANE_KINDS:
        return "project"
    if track == "process" or (actor or "") in {
        "openclaw",
        "canvas",
        "project-control",
        "context-compiler",
    }:
        return "meta"
    if (actor or "") in {"claude-code", "model", "sandbox"}:
        return "project"
    return "meta" if track == "process" else "project"


def episode_plane(
    *,
    episode_id: str,
    track: str | None,
    task: str | None,
    kinds: Iterable[str],
) -> str:
    """Primary plane for an Episode (control child → meta; POC/ACP → project)."""
    identity = str(episode_id or "")
    if (
        identity.startswith("flow-")
        or "--" in identity
        or str(task or "") in {
            "project_control",
            "binder_amend",
            "gate_pipeline",
            "binder_pipeline",
        }
        or track == "process"
    ):
        return "meta"
    kind_list = list(kinds)
    meta_hits = sum(1 for kind in kind_list if kind in META_PLANE_KINDS)
    project_hits = sum(1 for kind in kind_list if kind in PROJECT_PLANE_KINDS)
    if project_hits > meta_hits:
        return "project"
    return "meta"


def event_title(kind: str) -> str:
    return EVENT_TITLE_ZH.get(kind, kind)


def episode_title(
    *,
    episode_id: str,
    proposal_id: str | None = None,
    stage: str | None = None,
    topic: str | None = None,
    task: str | None = None,
    happened_at: str | None = None,
) -> str:
    """Human-facing Episode label without SHA walls."""
    date_part = ""
    if happened_at:
        date_part = str(happened_at)[:10]
    if proposal_id or stage:
        stage_label = STAGE_TITLE_ZH.get(str(stage or ""), str(stage or "阶段"))
        parts = [str(proposal_id or episode_id), stage_label]
        if date_part:
            parts.append(date_part)
        return " · ".join(parts)
    if topic:
        parts = [str(topic), str(task or "任务")]
        if date_part:
            parts.append(date_part)
        return " · ".join(parts)
    parts = [str(episode_id)]
    if task:
        parts.append(str(task))
    if date_part:
        parts.append(date_part)
    return " · ".join(parts)


def _safe_text(value: Any, *, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if SECRET_KEY_RE.search(text):
        return "[redacted]"
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _payload_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    if payload.get("schema") == "ndf-replay-blob/v1" and isinstance(
        payload.get("value"), Mapping
    ):
        value = payload["value"]
        return dict(value) if isinstance(value, Mapping) else {}
    if isinstance(payload.get("value"), Mapping) and "schema" in payload.get(
        "value", {}
    ):
        return dict(payload["value"])
    return dict(payload)


def extract_human_utterance(payload: Any, *, kind: str | None = None) -> str | None:
    """Pull the Cursor-side human phrase from a recorded payload when present."""
    data = _payload_mapping(payload)
    for key in (
        "human_phrase",
        "human_intent",
        "phrase",
        "approved_phrase",
        "gate_phrase",
        "utterance",
    ):
        text = _safe_text(data.get(key))
        if text:
            return text
    if kind in {"proposal.confirmed", "proposal.reviewed", "gate.confirmed", "gate.approved"}:
        for key in ("message", "intent", "text"):
            text = _safe_text(data.get(key))
            if text and (text in KNOWN_GATE_PHRASES or len(text) <= 40):
                return text
    return None


def episode_matches_agent(
    *,
    needle: str,
    agent: str | None = None,
    actor: str | None = None,
    participants: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
) -> bool:
    """True when a hop involved this agent, not only when it is the primary actor."""
    text = str(needle or "").strip().lower()
    if not text or text == "all":
        return True
    pool = [agent, actor, *(participants or [])]
    normalized_pool = {str(item).strip().lower() for item in pool if item}
    normalized_kinds = {str(item) for item in (kinds or [])}
    if text in {"command-agent", "commander", "cursor"}:
        return bool(
            normalized_pool
            & {"canvas", "human", "cursor", "commander", "composer", "cursor-agent"}
        ) or bool({"intent.received", "human.utterance"} & normalized_kinds)
    if any(text in str(item).lower() for item in pool if item):
        return True
    if "context-compiler" in text or text in {"compiler", "context_compiler"}:
        return bool(
            {"context.compiled", "context.verified", "manifest.created"}
            & normalized_kinds
        )
    return False


def replay_agent_lenses(
    *,
    agent: str | None = None,
    actor: str | None = None,
    participants: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
) -> list[str]:
    """Canonical commander identity lenses for a hop or timeline event."""
    return [
        lens
        for lens in ("command-agent", "openclaw", "claude-code", "context-compiler")
        if episode_matches_agent(
            needle=lens,
            agent=agent,
            actor=actor,
            participants=participants,
            kinds=kinds,
        )
    ]


def payload_looks_like_manifest(mapped: Mapping[str, Any]) -> bool:
    schema = str(mapped.get("schema") or "")
    if schema == "ndf-task-manifest/v1":
        return True
    if schema.startswith("ndf-context-plan"):
        return False
    return bool(
        mapped.get("clause_seeds") or mapped.get("shared_graph_closure")
    ) and not bool(mapped.get("ordered_reads"))


def payload_looks_like_plan(mapped: Mapping[str, Any]) -> bool:
    schema = str(mapped.get("schema") or "")
    if schema.startswith("ndf-context-plan"):
        return True
    if mapped.get("ordered_reads"):
        return True
    return bool(mapped.get("plan_sha")) and bool(
        mapped.get("role") or mapped.get("privileges") or mapped.get("ordered_reads") is not None
    )


def classify_compile_payload(
    kind: str,
    payload: Any,
) -> dict[str, Mapping[str, Any] | None]:
    """Split a compile-related event payload into Manifest vs Plan.

    ``manifest.created`` often arrives before ``context.compiled``. Callers MUST
    accumulate them separately; the first hit must not win for both.
    """
    mapped = _payload_mapping(payload)
    if not mapped:
        return {"manifest": None, "plan": None}
    manifest: Mapping[str, Any] | None = None
    plan: Mapping[str, Any] | None = None
    if kind == "manifest.created" and payload_looks_like_manifest(mapped):
        manifest = mapped
    if kind in {"context.compiled", "context.verified"} and payload_looks_like_plan(
        mapped
    ):
        plan = mapped
    # Some older recordings put plan fields on context.compiled without schema.
    if kind in {"context.compiled", "context.verified"} and plan is None:
        if mapped.get("ordered_reads") or mapped.get("plan_sha"):
            plan = mapped
    if kind == "manifest.created" and manifest is None and payload_looks_like_plan(
        mapped
    ):
        # Rare: plan blob mis-tagged as manifest.created — still expose as plan.
        plan = mapped
    return {"manifest": manifest, "plan": plan}


def read_why_missing(
    *,
    ordered_reads: list[str] | None,
    plan: Mapping[str, Any] | None,
    plan_sha: str | None,
    plan_blob_found: bool,
    manifest: Mapping[str, Any] | None = None,
) -> str | None:
    """Human-readable reason when ordered reads cannot be listed."""
    if ordered_reads:
        return None
    if plan is not None:
        raw = plan.get("ordered_reads")
        if isinstance(raw, list) and not raw:
            return "Plan 已记录但 ordered_reads 为空"
        if raw is None:
            return "Plan 已记录但没有 ordered_reads 字段"
        return "Plan 无法解析 ordered_reads"
    if plan_sha and not plan_blob_found:
        return "有 planSha 但找不到 Plan 对象"
    if not plan_sha:
        if manifest is not None:
            return "缺 planSha（这次 hop 只装了 Manifest，尚未写入 Context Plan）"
        return "缺 planSha（未绑定 Context Plan）"
    return "Plan 不可用"


def assembled_context_summary(
    *,
    manifest: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
    plan_sha: str | None = None,
    plan_blob_found: bool | None = None,
) -> dict[str, Any] | None:
    """Projection of NDF-assembled context (not SHA walls)."""
    if not manifest and not plan:
        return None
    seeds = []
    if isinstance(manifest, Mapping):
        seeds = list(manifest.get("clause_seeds") or [])
    ordered_reads: list[str] = []
    write_roots: list[str] = []
    role = None
    task = None
    human_phrase = None
    if isinstance(plan, Mapping):
        role = plan.get("role")
        task = plan.get("task")
        human_phrase = plan.get("human_phrase")
        ordered_reads = [
            str(item.get("path"))
            for item in plan.get("ordered_reads", [])
            if isinstance(item, Mapping) and item.get("path")
        ]
        privileges = plan.get("privileges") if isinstance(plan.get("privileges"), Mapping) else {}
        write_roots = [str(item) for item in privileges.get("allowed_write_roots", [])]
    found = (
        bool(plan_blob_found)
        if plan_blob_found is not None
        else plan is not None
    )
    why = read_why_missing(
        ordered_reads=ordered_reads,
        plan=plan if isinstance(plan, Mapping) else None,
        plan_sha=plan_sha,
        plan_blob_found=found,
        manifest=manifest if isinstance(manifest, Mapping) else None,
    )
    return {
        "role": role,
        "task": task or (manifest.get("task") if isinstance(manifest, Mapping) else None),
        "intent": manifest.get("intent") if isinstance(manifest, Mapping) else None,
        "seeds": seeds,
        "orderedReads": ordered_reads,
        "writeRoots": write_roots,
        "humanPhrase": human_phrase,
        "graphNodes": len(
            (manifest or {}).get("shared_graph_closure", {}).get("nodes", [])
            if isinstance(manifest, Mapping)
            else []
        ),
        "readWhyMissing": why,
    }


PROMPT_TEXT_LIMIT = 4000
CANVAS_PROMPT_LIMIT = 900


def _prompt_text(value: Any, *, limit: int = PROMPT_TEXT_LIMIT) -> str | None:
    """Longer than timeline preview; redact secret-shaped spans, keep the rest."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = SECRET_KEY_RE.sub("[redacted]", text)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def assembled_prompt_view(
    *,
    manifest: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
    plan_sha: str | None = None,
    plan_blob_found: bool | None = None,
) -> dict[str, Any]:
    """Reconstruct the normative NDF prompt from recorded Manifest + Plan.

    Does not re-read the live tree. Missing Plan cannot be faked from graphNodes.
    """
    summary = assembled_context_summary(
        manifest=manifest,
        plan=plan,
        plan_sha=plan_sha,
        plan_blob_found=plan_blob_found,
    )
    if plan is None:
        if manifest is None:
            return {
                "text": None,
                "whyMissing": "这次 hop 没有 Manifest / Context Plan，无法拼装规范 Prompt",
                "source": None,
            }
        return {
            "text": None,
            "whyMissing": "缺 Context Plan，只有 Manifest，不能拼出完整下达 Prompt（图节点数不是 Prompt）",
            "source": "manifest-only",
        }
    role = (summary or {}).get("role") or "unknown"
    task = (summary or {}).get("task") or "unknown"
    intent = (summary or {}).get("intent") or "未记录"
    phrase = (summary or {}).get("humanPhrase") or "无"
    seeds = [str(item) for item in ((summary or {}).get("seeds") or []) if item]
    reads = [str(item) for item in ((summary or {}).get("orderedReads") or []) if item]
    roots = [str(item) for item in ((summary or {}).get("writeRoots") or []) if item]
    lines = [
        "NDF 规范组装 Prompt（当时 Manifest + Context Plan，不是现仓重读）",
        "",
        f"角色: {role}",
        f"任务: {task}",
        f"意图: {intent}",
        f"人口令（记录，不是主指令）: {phrase}",
        f"条款种子: {', '.join(seeds) if seeds else '无'}",
        "有序读取（必须按序读）:",
    ]
    if reads:
        lines.extend(f"  {index}. {path}" for index, path in enumerate(reads, start=1))
    else:
        lines.append("  （无）")
    lines.extend(
        [
            f"可写根: {', '.join(roots) if roots else '只读 / 未声明'}",
            "",
            "执行约定:",
            "- 先按有序读取打开文件，再执行绑定任务。",
            "- 不得把人口令当成主任务正文。",
            "- 只写可写根。",
        ]
    )
    return {
        "text": "\n".join(lines),
        "whyMissing": (summary or {}).get("readWhyMissing"),
        "source": "context-plan",
    }


def _format_agent_message(mapped: Mapping[str, Any]) -> str | None:
    message = _prompt_text(mapped.get("message"))
    if not message:
        return None
    header = [
        "实发 OpenClaw message（ndf-agent-message/v1）",
        "",
        f"task: {mapped.get('task') or 'unknown'}",
        f"topic: {mapped.get('topic') or 'none'}",
        f"pipeline: {mapped.get('pipeline') or 'none'}",
        "",
        message,
    ]
    return "\n".join(header)


def _format_lease_dispatch(mapped: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "实发 ACP handshake（ndf-runtime-lease/v1，不是 Composer userPrompt 全文）",
            "",
            f"task: {mapped.get('task') or 'unknown'}",
            f"command: {mapped.get('command') or 'unknown'}",
            f"topic: {mapped.get('topic') or 'none'}",
            f"allowed_write_root: {mapped.get('allowed_write_root') or 'none'}",
            f"worktree: {mapped.get('worktree') or 'none'}",
        ]
    )


def dispatched_prompt_view(dispatch_payloads: Iterable[Any]) -> dict[str, Any]:
    """Actual text sent to OpenClaw / Claude Code, from recorded dispatch blobs."""
    messages: list[str] = []
    leases: list[str] = []
    fallbacks: list[str] = []
    seen: set[str] = set()

    def _add(bucket: list[str], text: str | None) -> None:
        if not text or text in seen:
            return
        seen.add(text)
        bucket.append(text)

    for payload in dispatch_payloads:
        mapped = _payload_mapping(payload)
        if not mapped:
            continue
        schema = str(mapped.get("schema") or "")
        if schema == "ndf-agent-message/v1" or (
            mapped.get("message") and mapped.get("manifest_sha")
        ):
            _add(messages, _format_agent_message(mapped))
            continue
        if schema == "ndf-runtime-lease/v1" or (
            mapped.get("pack_sha") and mapped.get("session_id")
        ):
            _add(leases, _format_lease_dispatch(mapped))
            continue
        added = len(fallbacks)
        for key in ("user_prompt", "prompt", "message", "primary_task", "instruction"):
            _add(fallbacks, _prompt_text(mapped.get(key)))
            if len(fallbacks) > added:
                break
    if messages:
        return {
            "text": "\n\n---\n\n".join(messages),
            "whyMissing": None,
            "source": "openclaw.request",
        }
    if leases:
        return {
            "text": "\n\n---\n\n".join(leases),
            "whyMissing": "ACP 记录是 lease/handshake，没有存 Composer userPrompt 全文；下面是握手摘要",
            "source": "acp.start",
        }
    if fallbacks:
        return {
            "text": "\n\n---\n\n".join(fallbacks),
            "whyMissing": None,
            "source": "dispatch",
        }
    return {
        "text": None,
        "whyMissing": "这次 hop 没有 openclaw.request / acp.start 正文",
        "source": None,
    }


def prompt_drift_view(
    *,
    assembled: Mapping[str, Any] | None,
    dispatched: Mapping[str, Any] | None,
    dispatch_leak: bool,
    dispatch_payloads: Iterable[Any],
) -> dict[str, Any]:
    """Semantic mismatch between normative assembled prompt and actual dispatch."""
    reasons: list[str] = []
    assembled_text = str((assembled or {}).get("text") or "").strip()
    dispatched_text = str((dispatched or {}).get("text") or "").strip()
    if dispatch_leak:
        reasons.append("dispatch_human_leak")
    if dispatched_text and not assembled_text:
        reasons.append("assembled_missing")
    if assembled_text and not dispatched_text:
        reasons.append("dispatched_missing")
    if assembled_text and dispatched_text:
        bound = any(dispatch_has_assembled_binding(item) for item in dispatch_payloads)
        if not bound and not dispatch_leak:
            reasons.append("dispatch_unbound")
    return {"mismatch": bool(reasons), "reasons": reasons}


CANVAS_INDEX_CACHE = "canvas-index.json"
CANVAS_LEDGER_CACHE_DIR = "canvas-ledger"
CANVAS_SNAPSHOT_BYTE_LIMIT = 120 * 1024
CANVAS_TIMELINE_PREVIEW_LIMIT = 160
CANVAS_BUCKET_LIMITS = {
    "topics_directory": 24 * 1024,
    "focused_topic": 24 * 1024,
    "control": 20 * 1024,
    "replay_directory": 16 * 1024,
    "focused_ledger": 16 * 1024,
    "other": 20 * 1024,
}
CANVAS_REPLAY_DIRECTORY_LIMIT = CANVAS_BUCKET_LIMITS["replay_directory"]


def list_episode_ids(store: "ReplayStore") -> list[str]:
    refs = store.refs / "episodes"
    if not refs.is_dir():
        return []
    return sorted(path.parent.name for path in refs.glob("*/HEAD"))


def episode_head_map(store: "ReplayStore") -> dict[str, str]:
    refs = store.refs / "episodes"
    if not refs.is_dir():
        return {}
    heads: dict[str, str] = {}
    for path in sorted(refs.glob("*/HEAD")):
        heads[path.parent.name] = path.read_text(encoding="utf-8").strip()
    return heads


def pick_canvas_focused_id(
    episodes: Iterable[Mapping[str, Any]],
    requested_id: str | None = None,
    active_topic: str | None = None,
) -> str | None:
    cards = [item for item in episodes if isinstance(item, Mapping) and item.get("id")]
    ids = {str(item["id"]) for item in cards}
    if requested_id and requested_id in ids:
        return requested_id

    def newest(rows: list[Mapping[str, Any]]) -> str | None:
        if not rows:
            return None
        rows = sorted(
            rows,
            key=lambda item: str(item.get("happenedAt") or ""),
            reverse=True,
        )
        return str(rows[0]["id"])

    if active_topic:
        topic_rows = [
            item for item in cards if str(item.get("topic") or "") == active_topic
        ]
        chosen = newest(topic_rows)
        if chosen:
            return chosen
    return newest(cards)


def _episode_event_bundle(store: "ReplayStore", episode_id: str) -> dict[str, Any]:
    head = store.read_ref(f"episodes/{episode_id}/HEAD")
    if head is None:
        raise FileNotFoundError(f"unknown replay episode: {episode_id}")
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
    chain_valid = bool(chains) and all(item["valid"] for item in chains.values())
    return {
        "head": head,
        "commit": commit,
        "branch_events": branch_events,
        "chains": chains,
        "events": events,
        "chain_valid": chain_valid,
    }


def _clip_prompt_view(
    prompt: Any,
    *,
    limit: int = CANVAS_PROMPT_LIMIT,
) -> Any:
    if not isinstance(prompt, Mapping):
        return prompt
    clipped = dict(prompt)
    text = clipped.get("text")
    if not isinstance(text, str) or len(text) <= limit:
        return clipped
    clipped["text"] = text[: limit - 1] + "…"
    why = clipped.get("whyMissing")
    note = f"Canvas 只嵌入前 {limit} 字；全文在 .ndf/replay"
    clipped["whyMissing"] = f"{why} · {note}" if why else note
    return clipped


def slim_canvas_timeline_event(event: Mapping[str, Any]) -> dict[str, Any]:
    preview = event.get("preview") if isinstance(event.get("preview"), Mapping) else {}
    payload = event.get("payloadPreview")
    if isinstance(payload, str) and len(payload) > CANVAS_TIMELINE_PREVIEW_LIMIT:
        payload = payload[: CANVAS_TIMELINE_PREVIEW_LIMIT - 1] + "…"
    slim_preview = {
        key: preview[key]
        for key in ("orderedReads", "humanUtterance", "changedFiles")
        if preview.get(key)
    }
    kind = str(event.get("kind") or "")
    return {
        "seq": event.get("seq"),
        "timestamp": event.get("timestamp"),
        "kind": event.get("kind"),
        "actor": event.get("actor"),
        "agent": event.get("agent"),
        "title": event.get("title"),
        "plane": event.get("plane"),
        "space": event.get("space"),
        "payloadPreview": payload,
        "preview": slim_preview or None,
        "lenses": replay_agent_lenses(
            agent=str(event.get("agent") or "") or None,
            actor=str(event.get("actor") or "") or None,
            kinds=[kind] if kind else [],
        ),
    }


def as_canvas_index_card(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Directory row: no Prompt text, no timeline."""
    if episode.get("state") == "invalid" and episode.get("error"):
        return {
            "id": episode.get("id"),
            "state": "invalid",
            "error": str(episode.get("error"))[:200],
            "canRestoreRecord": False,
        }
    return {
        "id": episode.get("id"),
        "title": episode.get("title"),
        "plane": episode.get("plane"),
        "agent": episode.get("agent"),
        "happenedAt": episode.get("happenedAt"),
        "resultLine": episode.get("resultLine"),
        "topic": episode.get("topic"),
        "task": episode.get("task"),
        "lenses": list(episode.get("lenses") or []),
        "canRestoreRecord": bool(episode.get("canRestoreRecord")),
        "state": episode.get("state") or "indexed",
    }


def slim_canvas_ledger(episode: Mapping[str, Any]) -> dict[str, Any]:
    """One hop for Canvas: clipped prompts, slim timeline, no r2/semantic walls."""
    item = dict(episode)
    item["assembledPrompt"] = _clip_prompt_view(item.get("assembledPrompt"))
    item["dispatchedPrompt"] = _clip_prompt_view(item.get("dispatchedPrompt"))
    item["timeline"] = [
        slim_canvas_timeline_event(event)
        for event in item.get("timeline") or []
        if isinstance(event, Mapping)
    ]
    summary = item.get("manifestSummary")
    if isinstance(summary, Mapping):
        item["manifestSummary"] = {
            "intent": summary.get("intent"),
            "seeds": summary.get("seeds"),
            "graphNodes": summary.get("graphNodes"),
        }
    errors = item.get("currentReadinessErrors")
    if isinstance(errors, list):
        slim_errors = []
        for error in errors[:5]:
            if isinstance(error, Mapping):
                slim_errors.append(
                    {
                        "kind": error.get("kind"),
                        **({"path": error.get("path")} if error.get("path") else {}),
                    }
                )
            else:
                slim_errors.append({"kind": str(error)[:120]})
        item["currentReadinessErrors"] = slim_errors
    item.pop("r2Profile", None)
    item.pop("semanticGaps", None)
    item.pop("observations", None)
    return item


def project_canvas_index_card(store: "ReplayStore", episode_id: str) -> dict[str, Any]:
    """Cheap directory card: event metadata only, no Prompt blobs."""
    try:
        bundle = _episode_event_bundle(store, episode_id)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return {
            "id": episode_id,
            "state": "invalid",
            "error": str(exc)[:200],
            "canRestoreRecord": False,
        }
    commit = bundle["commit"]
    events = bundle["events"]
    kinds = [str(event.get("kind")) for event in events if event.get("kind")]
    kinds_set = set(kinds)
    participants = sorted(
        {
            str(event.get("actor"))
            for event in events
            if event.get("actor")
        }
    )
    happened_at = None
    for event in events:
        if event.get("timestamp"):
            happened_at = str(event.get("timestamp"))
    plane = episode_plane(
        episode_id=episode_id,
        track=str(commit.get("track") or "") or None,
        task=str(commit.get("task") or "") or None,
        kinds=kinds,
    )
    title = episode_title(
        episode_id=episode_id,
        topic=commit.get("topic"),
        task=commit.get("task"),
        happened_at=happened_at,
    )
    result_bits: list[str] = []
    if {"gate.approved", "gate.confirmed"} & kinds_set:
        result_bits.append("门禁")
    if "filesystem.changed" in kinds_set:
        result_bits.append("改文件")
    if kinds_set & DISPATCH_KINDS:
        result_bits.append("下达")
    return {
        "id": episode_id,
        "title": title,
        "plane": plane,
        "agent": commit.get("actor") or "unknown",
        "participants": participants,
        "happenedAt": happened_at,
        "resultLine": " · ".join(result_bits) if result_bits else None,
        "topic": commit.get("topic"),
        "task": commit.get("task"),
        "track": commit.get("track"),
        "actor": commit.get("actor"),
        "kinds": sorted(kinds_set),
        "lenses": replay_agent_lenses(
            agent=str(commit.get("actor") or "") or None,
            actor=str(commit.get("actor") or "") or None,
            participants=participants,
            kinds=kinds_set,
        ),
        "dispatchLeak": None,
        "promptDrift": None,
        "canRestoreRecord": bool(bundle["chain_valid"] and bundle["head"]),
        "state": "indexed" if bundle["chain_valid"] else "invalid",
        "eventCount": len(events),
    }


def project_episode_ledger(store: "ReplayStore", episode_id: str) -> dict[str, Any]:
    """Rebuild one hop ledger from the object store. Does not change HEAD."""
    try:
        bundle = _episode_event_bundle(store, episode_id)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return {
            "id": episode_id,
            "state": "invalid",
            "error": str(exc),
            "levels": {"R0": False, "R1": False, "R2": False, "R3": True},
        }
    head = bundle["head"]
    commit = bundle["commit"]
    chains = bundle["chains"]
    events = bundle["events"]
    chain_valid = bundle["chain_valid"]
    audit = store.audit(head, strict=True)
    kinds = {event.get("kind") for event in events}
    coverage = commit.get("coverage", {})
    bound_manifest_sha = commit.get("manifest_sha")
    bound_plan_sha = commit.get("context_plan_sha")
    for _, historical in store.walk_commits(head):
        bound_manifest_sha = bound_manifest_sha or historical.get("manifest_sha")
        bound_plan_sha = bound_plan_sha or historical.get("context_plan_sha")
        if bound_manifest_sha and bound_plan_sha:
            break
    recorded_manifest: dict[str, Any] | None = None
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
                    recorded_manifest.get("shared_graph_closure", {}).get("nodes", [])
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
    sandbox_targets: list[dict[str, Any]] = []
    changed_files: set[str] = set()
    gate_events: list[dict[str, Any]] = []
    r2_outcome = "not_run"
    recorded_r2_profile: dict[str, Any] | None = None
    human_utterance: str | None = None
    dispatch_payloads: list[Any] = []
    timeline_rows: list[dict[str, Any]] = []
    happened_at: str | None = None
    participants: set[str] = set()
    event_manifest: dict[str, Any] | None = None
    event_plan: dict[str, Any] | None = None
    for replay_event in events:
        if replay_event.get("timestamp"):
            happened_at = str(replay_event.get("timestamp"))
        kind = str(replay_event.get("kind") or "")
        actor = str(replay_event.get("actor") or "")
        if actor:
            participants.add(actor)
        payload_obj: dict[str, Any] | None = None
        payload_data: Any = None
        try:
            payload_obj = store.get_object(str(replay_event.get("payload_sha") or ""))
            payload_data = payload_obj.get("data", {})
        except (FileNotFoundError, ValueError):
            payload_obj = None
            payload_data = None
        if human_utterance is None and payload_data is not None:
            human_utterance = extract_human_utterance(payload_data, kind=kind)
        if kind in DISPATCH_KINDS and payload_data is not None:
            dispatch_payloads.append(payload_data)
        if (
            kind in {"context.compiled", "context.verified", "manifest.created"}
            and payload_data is not None
        ):
            classified = classify_compile_payload(kind, payload_data)
            if classified["manifest"] is not None:
                event_manifest = dict(classified["manifest"])
            if classified["plan"] is not None:
                event_plan = dict(classified["plan"])
        preview = payload_preview(
            kind=kind,
            payload=payload_data or {},
            actor=actor,
        )
        timeline_rows.append(
            {
                "seq": replay_event.get("seq"),
                "timestamp": replay_event.get("timestamp"),
                "kind": kind,
                "actor": actor,
                "agent": actor,
                "payloadSha": replay_event.get("payload_sha"),
                "branch": replay_event.get("branch"),
                "title": preview.get("title") or event_title(kind),
                "plane": event_plane(
                    kind,
                    track=str(commit.get("track") or "") or None,
                    actor=actor,
                ),
                "space": preview.get("space") or event_space(kind),
                "payloadPreview": preview.get("summary"),
                "preview": preview,
            }
        )
        if payload_obj is None:
            continue
        data = payload_obj.get("data", {})
        if payload_obj.get("type") == "tool-cassette":
            if data.get("replay_policy") == "sandbox":
                sandbox_commands.append(list(data.get("argv", [])))
                sandbox_targets.append(
                    {
                        "run_id": data.get("run_id"),
                        "role": "claude-code",
                        "manifest_sha": data.get("manifest_sha"),
                        "plan_sha": data.get("plan_sha"),
                        "env_allowlist_fingerprint": data.get(
                            "env_allowlist_fingerprint"
                        ),
                        "cwd": data.get("cwd"),
                        "tool_runtime_version": data.get("external_resource_version"),
                    }
                )
            observations.append(
                {
                    "kind": "tool",
                    "name": data.get("name"),
                    "policy": data.get("replay_policy"),
                    "sha": replay_event.get("payload_sha"),
                }
            )
        elif payload_obj.get("type") == "model-turn":
            observations.append(
                {
                    "kind": "model",
                    "name": data.get("model_id"),
                    "policy": "recorded-response",
                    "sha": replay_event.get("payload_sha"),
                }
            )
        elif payload_obj.get("type") == "blob" and isinstance(data.get("value"), dict):
            value = data["value"]
            changed_files.update(str(item) for item in value.get("changed_files", []))
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
            if human_utterance is None:
                human_utterance = extract_human_utterance(value, kind=kind)
    if human_utterance is None and context_summary:
        human_utterance = context_summary.get("humanPhrase")
    plan_for_summary = recorded_plan if recorded_plan is not None else event_plan
    manifest_for_summary = (
        recorded_manifest if recorded_manifest is not None else event_manifest
    )
    plan_blob_found = recorded_plan is not None or event_plan is not None
    assembled = assembled_context_summary(
        manifest=manifest_for_summary,
        plan=plan_for_summary,
        plan_sha=str(bound_plan_sha) if bound_plan_sha else None,
        plan_blob_found=plan_blob_found,
    )
    dispatch_leak = detect_dispatch_leak(
        human_utterance=human_utterance,
        dispatch_payloads=dispatch_payloads,
    )
    assembled_prompt = assembled_prompt_view(
        manifest=manifest_for_summary,
        plan=plan_for_summary,
        plan_sha=str(bound_plan_sha) if bound_plan_sha else None,
        plan_blob_found=plan_blob_found,
    )
    dispatched_prompt = dispatched_prompt_view(dispatch_payloads)
    prompt_drift = prompt_drift_view(
        assembled=assembled_prompt,
        dispatched=dispatched_prompt,
        dispatch_leak=dispatch_leak,
        dispatch_payloads=dispatch_payloads,
    )
    identity = store.episode_identity(episode_id) or {}
    plane = episode_plane(
        episode_id=episode_id,
        track=str(commit.get("track") or "") or None,
        task=str(commit.get("task") or "") or None,
        kinds=[str(item) for item in kinds if item],
    )
    primary_agent = (
        (assembled or {}).get("role")
        or commit.get("actor")
        or identity.get("role")
        or "unknown"
    )
    title = episode_title(
        episode_id=episode_id,
        proposal_id=identity.get("proposal_id"),
        stage=identity.get("stage"),
        topic=commit.get("topic"),
        task=commit.get("task"),
        happened_at=happened_at,
    )
    result_bits: list[str] = []
    if gate_events:
        result_bits.append(f"门禁 {len(gate_events)}")
    if changed_files:
        result_bits.append(f"改文件 {len(changed_files)}")
    if observations:
        result_bits.append(f"观察 {len(observations)}")
    if dispatch_leak:
        result_bits.append("下达泄漏")
    elif prompt_drift.get("mismatch"):
        result_bits.append("Prompt 漂移")
    complete_observations = bool(
        {"tool.result", "model.response"} & kinds
        or coverage.get("runtime_stream") == "full_stream"
    )
    has_sandbox_cassette = any(
        item.get("kind") == "tool" and item.get("policy") == "sandbox"
        for item in observations
    )
    historical_integrity = bool(audit.get("historical_integrity"))
    can_restore_record = bool(historical_integrity and head and chain_valid)
    read_why = (assembled or {}).get("readWhyMissing")
    return {
        "id": episode_id,
        "title": title,
        "plane": plane,
        "agent": primary_agent,
        "participants": sorted(participants),
        "happenedAt": happened_at,
        "resultLine": " · ".join(result_bits) if result_bits else None,
        "humanUtterance": human_utterance,
        "assembledContext": assembled,
        "assembledPrompt": assembled_prompt,
        "dispatchedPrompt": dispatched_prompt,
        "promptDrift": prompt_drift,
        "readWhyMissing": read_why,
        "canRestoreRecord": can_restore_record,
        "dispatchLeak": dispatch_leak,
        "state": "verified" if audit["valid"] and not dispatch_leak else "invalid",
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
        "semanticGaps": list(audit.get("semantic_gaps", []))
        + (["dispatch_human_leak"] if dispatch_leak else []),
        "historicalIntegrity": historical_integrity,
        "historicalSemantics": bool(audit.get("historical_semantics"))
        and not dispatch_leak,
        "currentRestoreReady": audit.get("current_restore_ready"),
        "currentDispatchReady": audit.get("current_dispatch_ready"),
        "currentReadinessErrors": audit.get("current_readiness_errors", []),
        "manifestSummary": manifest_summary,
        "contextSummary": context_summary,
        "kinds": sorted(str(item) for item in kinds if item),
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
            {name: value["tip_sha"] for name, value in sorted(chains.items())}
        ),
        "levels": {
            "R0": can_restore_record and not dispatch_leak,
            "R1": bool(chain_valid and complete_observations),
            "R2": bool(
                chain_valid
                and commit.get("repo_head")
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
            "network": (recorded_r2_profile or {}).get("network", "none"),
            "commands": (recorded_r2_profile or {}).get("commands", sandbox_commands),
            "allowedWriteRoots": (recorded_r2_profile or {}).get(
                "allowed_write_roots",
                (
                    recorded_plan.get("privileges", {}).get("allowed_write_roots", [])
                    if recorded_plan
                    else []
                ),
            ),
            "confirmCost": (recorded_r2_profile or {}).get("confirm_cost", False),
            "confirmSideEffects": (recorded_r2_profile or {}).get(
                "confirm_side_effects", False
            ),
            "target": (
                (recorded_r2_profile or {}).get("target")
                or (
                    sandbox_targets[0]
                    if sandbox_targets
                    and all(target == sandbox_targets[0] for target in sandbox_targets)
                    else None
                )
            ),
        },
        "changedFiles": sorted(changed_files),
        "gateEvents": gate_events[-50:],
        "timeline": timeline_rows[-100:],
    }


def project_canvas_index(
    store: "ReplayStore",
    *,
    write_cache: bool = False,
) -> dict[str, Any]:
    heads = episode_head_map(store)
    cache_path = store.root / CANVAS_INDEX_CACHE
    cached: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cached = loaded
        except (OSError, json.JSONDecodeError):
            cached = {}
    cached_heads = cached.get("heads") if isinstance(cached.get("heads"), dict) else {}
    cards_by_id = {
        str(item["id"]): item
        for item in cached.get("episodes") or []
        if isinstance(item, Mapping) and item.get("id")
    }
    episodes = []
    for episode_id, head in heads.items():
        previous = cards_by_id.get(episode_id)
        if previous and cached_heads.get(episode_id) == head:
            if "participants" in previous and "kinds" in previous:
                cached_card = dict(previous)
                cached_card["lenses"] = replay_agent_lenses(
                    agent=str(cached_card.get("agent") or "") or None,
                    actor=str(cached_card.get("actor") or "") or None,
                    participants=cached_card.get("participants") or [],
                    kinds=cached_card.get("kinds") or [],
                )
                episodes.append(cached_card)
                continue
        episodes.append(project_canvas_index_card(store, episode_id))
    episodes.sort(key=lambda item: str(item.get("happenedAt") or ""), reverse=True)
    payload = {
        "schema": "ndf-replay-canvas-index/v1",
        "storeRoot": ".ndf/replay",
        "heads": heads,
        "episodes": episodes,
    }
    if write_cache:
        store.initialize()
        store._atomic_write(
            cache_path,
            canonical_json_bytes(payload) + b"\n",
        )
    return payload


def project_canvas_ledger(
    store: "ReplayStore",
    episode_id: str,
    *,
    write_cache: bool = False,
) -> dict[str, Any]:
    ledger = slim_canvas_ledger(project_episode_ledger(store, episode_id))
    ledger["schema"] = "ndf-replay-canvas-ledger/v1"
    ledger["storeRoot"] = ".ndf/replay"
    if write_cache:
        store.initialize()
        path = store.root / CANVAS_LEDGER_CACHE_DIR / f"{episode_id}.json"
        if ledger.get("state") == "invalid" and path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("state") != "invalid":
                    return cached
            except (OSError, json.JSONDecodeError):
                pass
        store._atomic_write(path, canonical_json_bytes(ledger) + b"\n")
    return ledger


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def trim_canvas_replay_directory(
    episodes: list[Mapping[str, Any]],
    *,
    byte_limit: int = CANVAS_REPLAY_DIRECTORY_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """Keep newest directory rows under the Replay directory byte budget."""
    cards = [as_canvas_index_card(item) for item in episodes if isinstance(item, Mapping)]
    # Reserve the newest row from each semantic plane. A purely newest-first
    # trim can hide all Product-project history when recent NDF workflow hops
    # dominate the ledger, making the plane filter misleading.
    anchors: dict[str, dict[str, Any]] = {}
    for card in cards:
        plane = str(card.get("plane") or "")
        if plane in {"meta", "project"} and plane not in anchors:
            anchors[plane] = card
    kept_by_id = {
        str(card.get("id")): card
        for card in anchors.values()
        if card.get("id")
    }
    used = _json_bytes(list(kept_by_id.values()))
    for card in cards:
        card_id = str(card.get("id") or "")
        if card_id in kept_by_id:
            continue
        size = _json_bytes(card) + (1 if kept_by_id else 0)
        if kept_by_id and used + size > byte_limit:
            continue
        kept_by_id[card_id] = card
        used += size
    kept = [
        card
        for card in cards
        if str(card.get("id") or "") in kept_by_id
    ]
    omitted = len(cards) - len(kept)
    return kept, omitted


def project_canvas_replay(
    replay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Counter stock: slim directory + at most one focused ledger page."""
    data = dict(replay or {})
    focused = data.get("focused")
    if isinstance(focused, Mapping):
        data["focused"] = slim_canvas_ledger(focused)
    elif not focused:
        data["focused"] = None
    episodes, omitted = trim_canvas_replay_directory(
        [item for item in data.get("episodes") or [] if isinstance(item, Mapping)]
    )
    data["episodes"] = episodes
    if omitted:
        data["omittedCount"] = omitted
    else:
        data.pop("omittedCount", None)
    data.pop("canvasOmittedEpisodes", None)
    data["storeRoot"] = data.get("storeRoot") or ".ndf/replay"
    return data


def dispatch_task_text(payload: Any) -> str | None:
    """Primary free-text task carried by a dispatch/request payload."""
    data = _payload_mapping(payload)
    request = data.get("request") if isinstance(data.get("request"), Mapping) else {}
    for source in (data, request):
        if not isinstance(source, Mapping):
            continue
        for key in (
            "primary_task",
            "user_prompt",
            "prompt",
            "message",
            "human_intent",
            "human_phrase",
            "task_text",
            "instruction",
        ):
            text = _safe_text(source.get(key), limit=400)
            if text:
                return text
    return None


def dispatch_has_assembled_binding(payload: Any) -> bool:
    data = _payload_mapping(payload)
    request = data.get("request") if isinstance(data.get("request"), Mapping) else {}
    for source in (data, request):
        if not isinstance(source, Mapping):
            continue
        if source.get("manifest_sha") and source.get("plan_sha"):
            return True
        if source.get("context_plan_sha") and source.get("manifest_sha"):
            return True
        ordered = source.get("ordered_reads") or source.get("orderedReads")
        if isinstance(ordered, list) and ordered:
            return True
        seeds = source.get("clause_seeds") or source.get("seeds")
        if isinstance(seeds, list) and seeds:
            return True
    return False


def detect_dispatch_leak(
    *,
    human_utterance: str | None,
    dispatch_payloads: Iterable[Any],
) -> bool:
    """True when a dispatch primary task is still raw human speech (short-circuit)."""
    utterance = (human_utterance or "").strip()
    for payload in dispatch_payloads:
        text = dispatch_task_text(payload)
        if not text:
            if not dispatch_has_assembled_binding(payload):
                # Request present but neither bound plan nor structured task.
                data = _payload_mapping(payload)
                if data:
                    return True
            continue
        normalized = text.strip()
        if utterance and normalized == utterance:
            return True
        if normalized in KNOWN_GATE_PHRASES and not dispatch_has_assembled_binding(
            payload
        ):
            return True
        if (
            not dispatch_has_assembled_binding(payload)
            and len(normalized) <= 80
            and ("\n" not in normalized)
            and (
                normalized in KNOWN_GATE_PHRASES
                or (utterance and utterance in normalized)
            )
        ):
            return True
    return False


def payload_preview(
    *,
    kind: str,
    payload: Any,
    actor: str | None = None,
) -> dict[str, Any]:
    """Safe one-glance preview for timeline rows (no secrets, no SHA walls)."""
    data = _payload_mapping(payload)
    preview: dict[str, Any] = {
        "space": event_space(kind),
        "title": event_title(kind),
        "agent": actor,
        "summary": None,
    }
    human = extract_human_utterance(data, kind=kind)
    if human:
        preview["summary"] = human
        preview["humanUtterance"] = human
        return preview
    if kind in {"context.compiled", "context.verified", "manifest.created"}:
        reads = [
            str(item.get("path"))
            for item in data.get("ordered_reads", [])
            if isinstance(item, Mapping) and item.get("path")
        ]
        seeds = data.get("clause_seeds") or data.get("seeds") or []
        role = data.get("role")
        bits = []
        if role:
            bits.append(f"角色 {role}")
        if seeds:
            bits.append(f"种子 {len(seeds)}")
        if reads:
            bits.append(" → ".join(reads[:3]))
        preview["summary"] = " · ".join(bits) or event_title(kind)
        preview["orderedReads"] = reads[:8]
        return preview
    if kind in DISPATCH_KINDS:
        task_text = dispatch_task_text(data)
        bound = dispatch_has_assembled_binding(data)
        preview["summary"] = (
            f"{'已绑定 Plan' if bound else '未绑定 Plan'}"
            + (f" · {_safe_text(task_text, limit=80)}" if task_text else "")
        )
        preview["bound"] = bound
        return preview
    if kind in {"tool.invoke", "tool.result"}:
        name = data.get("name") or data.get("tool") or "tool"
        argv = data.get("argv") or data.get("args")
        argv_text = None
        if isinstance(argv, list):
            argv_text = _safe_text(" ".join(str(item) for item in argv[:6]), limit=100)
        preview["summary"] = f"{name}" + (f" · {argv_text}" if argv_text else "")
        preview["policy"] = data.get("replay_policy")
        return preview
    if kind in {"model.request", "model.response"}:
        preview["summary"] = _safe_text(
            data.get("model_id") or data.get("model") or "model"
        )
        return preview
    if kind in {"filesystem.changed", "filesystem.acquired"}:
        files = data.get("changed_files") or data.get("paths") or []
        if isinstance(files, list) and files:
            preview["summary"] = f"{len(files)} 个文件 · {files[0]}"
            preview["changedFiles"] = [str(item) for item in files[:12]]
            return preview
    if kind == "gate.audit" or kind.startswith("gate."):
        gate = data.get("gate") or data.get("step") or data.get("id")
        preview["summary"] = _safe_text(gate) or event_title(kind)
        return preview
    if kind == "verification.completed":
        preview["summary"] = _safe_text(
            data.get("state") or data.get("result") or "verification"
        )
        return preview
    # Generic: pick a short non-secret field.
    for key in ("intent", "task", "role", "state", "result", "status", "message"):
        text = _safe_text(data.get(key), limit=100)
        if text and text not in KNOWN_GATE_PHRASES:
            # Prefer structured fields; gate phrases already handled above.
            if key == "message" and text in KNOWN_GATE_PHRASES:
                continue
            preview["summary"] = text
            break
    if preview["summary"] is None:
        preview["summary"] = event_title(kind)
    return preview


def control_parent_id(flow_id: str) -> str:
    return f"flow-{flow_id}"


def control_child_id(flow_id: str, stage: str) -> str:
    return f"{flow_id}--{stage.replace('_', '-')}"


def control_parent_ref(flow_id: str) -> str:
    return f"flows/{flow_id}/parent"


def control_child_ref(flow_id: str, stage: str) -> str:
    return f"flows/{flow_id}/children/{stage}"


def classify_gate_bundle_changes(
    left_specs: Mapping[str, Any] | None,
    right_specs: Mapping[str, Any] | None,
) -> dict[str, list[str]]:
    """Classify gate identity drift between two recorded bundle_specs maps.

    ``contract_slice_changed`` uses expected_content_sha + bundle_mode + slice
    content_sha. ``slice_manifest_sha`` inequality alone is
    ``manifest_formula_changed`` (line-number / formula migration, not contract).
    """
    import ndf_gate_slices

    left = left_specs if isinstance(left_specs, Mapping) else {}
    right = right_specs if isinstance(right_specs, Mapping) else {}
    contract_slice_changed: list[str] = []
    manifest_formula_changed: list[str] = []
    for gate in sorted(set(left) | set(right)):
        left_spec = left.get(gate) if isinstance(left.get(gate), Mapping) else {}
        right_spec = right.get(gate) if isinstance(right.get(gate), Mapping) else {}
        if ndf_gate_slices.gate_spec_content_identity(
            left_spec
        ) != ndf_gate_slices.gate_spec_content_identity(right_spec):
            contract_slice_changed.append(gate)
        elif left_spec.get("slice_manifest_sha") != right_spec.get(
            "slice_manifest_sha"
        ):
            manifest_formula_changed.append(gate)
    return {
        "contract_slice_changed": contract_slice_changed,
        "manifest_formula_changed": manifest_formula_changed,
    }


def dispatch_pack_lease_eligible(pack: Mapping[str, Any] | None) -> bool:
    """True when a recorded dispatch pack may bind a runtime lease.

    Write dispatch still requires ``safe_to_dispatch``. Lease-prep may bind a
    pack that only passed static preflight while the ACP pipeline is down.
    """
    if not isinstance(pack, Mapping):
        return False
    if pack.get("safe_to_dispatch") is True:
        return True
    return (
        pack.get("static_preflight_passed") is True
        or pack.get("safe_to_delegate") is True
    )


def event_actor_valid(kind: str, actor: str) -> bool:
    if kind in {
        "proposal.confirmed",
        "proposal.reviewed",
        "gate.approved",
        "gate.confirmed",
        "decision.selected",
    }:
        return bool(actor) and actor.lower() not in AGENT_ACTORS
    if kind in {
        "gate.audit",
        "gate.draft",
        "binder.audit",
        "binder.amend",
        "binder.recheck",
        "control.handoff",
    }:
        return actor in {"openclaw", "tool"}
    if kind == "control.dispatch":
        return actor in {"tool", "canvas"}
    if kind in {"acp.start", "lease.acquired", "lease.released", "acp.complete"}:
        return actor == "claude-code"
    if kind.startswith("openclaw."):
        return actor == "openclaw"
    if kind in {"manifest.created", "context.compiled", "context.expanded", "context.verified"}:
        return actor in {"context-compiler", "canvas", "openclaw", "claude-code", "project-control"}
    if kind in {"snapshot.embedded", "compaction.checkpoint"}:
        return actor in {"tool", "canvas"}
    return bool(actor)


def validate_project_control_flow(
    records: list[tuple[Mapping[str, Any], Any]],
) -> list[str]:
    """Validate one META-014 child Episode's identity, order, and write set."""
    errors: list[str] = []
    identity_fields = (
        "proposal_id",
        "flow_id",
        "hop",
        "manifest_sha",
        "context_plan_sha",
    )
    expected: dict[str, Any] | None = None
    compiled = False
    verified = False
    preflight = False
    confirmed = False
    reviewed = False
    requests: dict[str, tuple[Any, ...]] = {}
    for event, payload in records:
        value = payload if isinstance(payload, Mapping) else {}
        nested_identity = (
            value.get("control")
            if isinstance(value.get("control"), Mapping)
            else value.get("proposal")
            if isinstance(value.get("proposal"), Mapping)
            else {}
        )
        identity = {
            field: event.get(
                field,
                value.get(field, nested_identity.get(field)),
            )
            for field in identity_fields
        }
        if expected is None:
            expected = identity
        elif identity != expected:
            errors.append("project_control_identity_mismatch")
        kind = str(event.get("kind") or "")
        actor = str(event.get("actor") or "")
        if not event_actor_valid(kind, actor):
            errors.append("project_control_invalid_actor")
        if kind == "proposal.confirmed":
            confirmed = True
        elif kind == "proposal.reviewed":
            reviewed = True
        elif kind == "context.compiled":
            compiled = True
        elif kind == "context.verified":
            if not compiled:
                errors.append("context_verified_without_compile")
            verified = True
        elif kind == "dispatch.preflight":
            if not verified:
                errors.append("dispatch_without_context_verify")
            if identity.get("hop") == "confirm_land" and not confirmed:
                errors.append("confirm_land_without_human_confirmation")
            if identity.get("hop") == "review" and not reviewed:
                errors.append("review_without_human_receipt")
            preflight = True
        elif kind == "openclaw.request":
            if not preflight:
                errors.append("request_without_dispatch_preflight")
            request_id = str(value.get("request_id") or "")
            attempt = value.get("attempt")
            if not request_id or not isinstance(attempt, int) or attempt < 1:
                errors.append("project_control_request_identity_invalid")
            else:
                request_identity = tuple(identity[field] for field in identity_fields)
                previous = requests.setdefault(request_id, request_identity)
                if previous != request_identity:
                    errors.append("project_control_request_identity_conflict")
        elif kind == "openclaw.response":
            request_id = str(value.get("request_id") or "")
            if request_id not in requests:
                errors.append("project_control_response_without_request")
        if kind == "filesystem.changed":
            errors.extend(validate_project_control_mutation(value))
    return list(dict.fromkeys(errors))


def validate_project_control_mutation(payload: Mapping[str, Any]) -> list[str]:
    """Require declared and actual project-control writes to match exactly."""
    changed = payload.get("changed_files")
    declared = payload.get("declared_files")
    allowed = payload.get("allowed_write_roots")
    if not isinstance(changed, list):
        return ["project_control_stage_write_violation"]
    expected = declared if isinstance(declared, list) else allowed
    if not isinstance(expected, list):
        return ["project_control_stage_write_violation"]
    actual = {str(path).rstrip("/") for path in changed}
    wanted = {str(path).rstrip("/") for path in expected}
    if actual != wanted:
        return ["project_control_mutation_mismatch"]
    return []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _assert_no_plaintext_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            secret_marker = child is None or child is False or child is True
            if isinstance(child, str):
                secret_marker = child in {"[REDACTED]", "present", "absent"}
            telemetry_key = str(key).lower() in {
                "token_usage",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            }
            if (
                SECRET_KEY_RE.search(str(key))
                and not telemetry_key
                and not secret_marker
            ):
                raise ValueError(f"plaintext secret-like field is forbidden: {child_path}")
            _assert_no_plaintext_secrets(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_plaintext_secrets(child, f"{path}[{index}]")


def probe_vm_hypervisor() -> dict[str, Any]:
    """Detect KVM + qemu/firecracker. Absence is fail-closed for Lvm."""
    kvm = Path("/dev/kvm").exists()
    qemu = shutil.which("qemu-system-x86_64")
    firecracker = shutil.which("firecracker")
    available = bool(kvm and (qemu or firecracker))
    blocker = None
    if not kvm:
        blocker = "no_/dev/kvm"
    elif not (qemu or firecracker):
        blocker = "no_qemu_or_firecracker"
    return {
        "kvm": kvm,
        "qemu": qemu,
        "firecracker": firecracker,
        "available": available,
        "blocker": blocker,
    }


def probe_cube_api(
    *,
    api_url: str | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Detect CubeSandbox / E2B-compatible API. Unreachable → fail closed."""
    url = (
        api_url
        or os.environ.get("NDF_CUBE_API_URL")
        or os.environ.get("E2B_API_URL")
        or ""
    ).rstrip("/")
    template = (
        os.environ.get("NDF_CUBE_TEMPLATE_ID")
        or os.environ.get("CUBE_TEMPLATE_ID")
        or ""
    )
    result: dict[str, Any] = {
        "kind": "cube",
        "api_url": url or None,
        "template_id": template or None,
        "available": False,
        "blocker": None,
    }
    if not url:
        result["blocker"] = "no_NDF_CUBE_API_URL_or_E2B_API_URL"
        return result
    if not template:
        result["blocker"] = "no_CUBE_TEMPLATE_ID"
        return result
    # Optional live probe; failures stay environment_blocked.
    try:
        import urllib.request

        req = urllib.request.Request(
            f"{url}/health",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            result["http_status"] = getattr(resp, "status", None) or resp.getcode()
            result["available"] = 200 <= int(result["http_status"]) < 500
            if not result["available"]:
                result["blocker"] = f"cube_api_http_{result['http_status']}"
    except Exception as exc:  # noqa: BLE001 — probe must never raise to callers
        result["blocker"] = f"cube_api_unreachable:{type(exc).__name__}"
        result["available"] = False
    return result


DEFAULT_VM_IMAGE_REL = Path("tmp") / "ndf-replay-images" / "alpine-ndf-replay"

GUEST_INIT_SCRIPT = """#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mount -o remount,rw / 2>/dev/null || true
mkdir -p /guest /tmp /dev/pts
mount -t tmpfs tmpfs /tmp 2>/dev/null || true
modprobe virtio_pci 2>/dev/null || true
modprobe virtio_blk 2>/dev/null || true
modprobe 9p 2>/dev/null || true
modprobe 9pnet_virtio 2>/dev/null || true
modprobe virtio_console 2>/dev/null || true
COMMIT=""
LEVEL="R0"
EPISODE=""
for tok in $(cat /proc/cmdline 2>/dev/null); do
  case "$tok" in
    ndf.commit=*) COMMIT="${tok#ndf.commit=}" ;;
    ndf.level=*) LEVEL="${tok#ndf.level=}" ;;
    ndf.episode=*) EPISODE="${tok#ndf.episode=}" ;;
  esac
done
PROOF=""
i=0
while [ -z "$PROOF" ] && [ "$i" -lt 50 ]; do
  if [ -e /dev/virtio-ports/org.ndf.proof ]; then
    PROOF=/dev/virtio-ports/org.ndf.proof
  fi
  i=$((i + 1))
  [ -n "$PROOF" ] || sleep 0.1
done
[ -n "$PROOF" ] || PROOF=/tmp/ndf-guest-proof.json
i=0
while [ "$i" -lt 50 ]; do
  if mount -t 9p -o trans=virtio,version=9p2000.L,ro ndfguest /guest 2>/tmp/ndf-9p.err; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done
if [ ! -d /guest/spec/meta/tools ]; then
  echo "ndf-9p-failed: $(cat /tmp/ndf-9p.err 2>/dev/null)"
fi
RECON=/tmp/ndf-reconstruct.json
STATUS=1
if [ -d /guest/spec/meta/tools ]; then
  cd /guest || true
  if [ -f /guest/.ndf/replay-key ]; then
    export NDF_REPLAY_KEY_FILE=/guest/.ndf/replay-key
  fi
  if python3 spec/meta/tools/ndf_replay.py reconstruct --commit "$COMMIT" --level "$LEVEL" > "$RECON"; then
    STATUS=0
  else
    STATUS=$?
  fi
else
  echo '{"error":"guest_snapshot_missing"}' > "$RECON"
fi
python3 - "$PROOF" "$RECON" "$STATUS" "$COMMIT" "$LEVEL" "$EPISODE" <<'PY'
import json, sys
proof_path, recon_path, status, commit, level, episode = sys.argv[1:7]
try:
    recon = json.loads(open(recon_path, encoding="utf-8").read())
except Exception as exc:
    recon = {"error": type(exc).__name__, "path": recon_path}
payload = {
    "guest_id": "qemu-guest",
    "guest_toplevel": "/guest",
    "episode_id": episode,
    "init_status": int(status),
    "reconstruct": {
        "level": recon.get("level") or level,
        "side_effects": recon.get("side_effects", False) if isinstance(recon, dict) else False,
        "commit_sha": recon.get("commit_sha") or commit,
        "timeline_events": len((recon or {}).get("timeline") or []),
        "error": recon.get("error") if isinstance(recon, dict) else None,
    },
}
open(proof_path, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False) + "\\n")
PY
sync
exec reboot -f
"""


def resolve_vm_image(
    image: str | None,
    repo_root: Path,
) -> dict[str, Path] | None:
    """Resolve kernel + rootfs for adapter=vm. Missing image is fail-closed."""
    raw = (image or os.environ.get("NDF_REPLAY_VM_IMAGE") or "").strip()
    candidate = Path(raw).expanduser() if raw else (repo_root / DEFAULT_VM_IMAGE_REL)
    if not candidate.exists():
        return None
    if candidate.is_dir():
        kernel = candidate / "vmlinuz"
        rootfs = candidate / "rootfs.ext4"
        initrd = candidate / "initramfs"
    else:
        kernel = candidate.parent / "vmlinuz"
        rootfs = candidate
        initrd = candidate.parent / "initramfs"
    if kernel.is_file() and rootfs.is_file():
        resolved = {"kernel": kernel.resolve(), "rootfs": rootfs.resolve()}
        if initrd.is_file():
            resolved["initrd"] = initrd.resolve()
        return resolved
    return None


def guest_environment_probe(repo_root: Path) -> dict[str, Any]:
    """Host readiness for Lvm guest-run. Does not install or start a guest."""
    hypervisor = probe_vm_hypervisor()
    kvm_path = Path("/dev/kvm")
    kvm_usable = kvm_path.exists() and os.access(kvm_path, os.R_OK | os.W_OK)
    resolved = resolve_vm_image(None, repo_root)
    docker = shutil.which("docker")
    image_blockers: list[str] = []
    image_meta: dict[str, str] | None = None
    if resolved is None:
        image_blockers.append("missing_guest_image")
    else:
        image_meta = {key: str(path) for key, path in resolved.items()}
        for key in ("kernel", "rootfs"):
            if not os.access(resolved[key], os.R_OK):
                image_blockers.append(f"unreadable:{key}")
        if "initrd" not in resolved:
            image_blockers.append("missing_initramfs")
        elif not os.access(resolved["initrd"], os.R_OK):
            image_blockers.append("unreadable:initrd")
    next_actions: list[str] = []
    if not hypervisor.get("kvm") or not kvm_usable:
        next_actions.append("enable_kvm")
    if not hypervisor.get("qemu"):
        next_actions.append("install_qemu")
    if resolved is None:
        if not docker:
            next_actions.append("install_docker")
        next_actions.append("guest_image")
    elif image_blockers:
        next_actions.append("chmod_image")
    ready = bool(hypervisor.get("available") and kvm_usable and not image_blockers)
    if ready:
        next_actions.append("smoke_guest_run")
    return {
        "schema": "ndf-replay-guest-probe/v1",
        "ready": ready,
        "default_adapter": "vm",
        "hypervisor": hypervisor,
        "kvm_usable": kvm_usable,
        "docker": docker,
        "image": image_meta,
        "image_ready": not image_blockers,
        "image_blockers": image_blockers,
        "default_image": str((repo_root / DEFAULT_VM_IMAGE_REL).resolve()),
        "next_actions": next_actions,
    }


def provision_replay_guest_image(
    dest: Path,
    *,
    alpine_ref: str = "alpine:3.21",
) -> dict[str, Any]:
    """Build a local Lvm rootfs (Alpine + python3 + git + virt kernel) via Docker."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    kernel = dest / "vmlinuz"
    rootfs = dest / "rootfs.ext4"
    init_host = dest / "ndf-replay-init"
    if kernel.is_file() and rootfs.is_file() and rootfs.stat().st_size > 0:
        return {
            "ready": True,
            "reused": True,
            "kernel": str(kernel),
            "rootfs": str(rootfs),
            "image_sha": hashlib.sha256(kernel.read_bytes() + rootfs.read_bytes()).hexdigest(),
        }
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker_required_to_provision_guest_image")
    init_host.write_text(GUEST_INIT_SCRIPT, encoding="utf-8")
    init_host.chmod(0o755)
    script = """
set -eu
apk add --no-cache python3 py3-cryptography git linux-virt e2fsprogs
cp /boot/vmlinuz-virt /out/vmlinuz
cp /boot/initramfs-virt /out/initramfs
cp /init-src/ndf-replay-init /ndf-replay-init
chmod 0755 /ndf-replay-init
dd if=/dev/zero of=/out/rootfs.ext4 bs=1M count=768
mkfs.ext4 -F -q /out/rootfs.ext4
mkdir -p /mnt
mount -o loop /out/rootfs.ext4 /mnt
tar -C / --exclude=out --exclude=proc --exclude=sys --exclude=dev --exclude=mnt --exclude=init-src -cf - . \\
  | tar -C /mnt -xf -
mkdir -p /mnt/proc /mnt/sys /mnt/dev /mnt/guest /mnt/tmp
cp /ndf-replay-init /mnt/ndf-replay-init
chmod 0755 /mnt/ndf-replay-init
umount /mnt
chmod 0644 /out/vmlinuz /out/rootfs.ext4 /out/initramfs
"""
    subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--privileged",
            "-v",
            f"{dest}:/out",
            "-v",
            f"{init_host}:/init-src/ndf-replay-init:ro",
            alpine_ref,
            "sh",
            "-c",
            script,
        ],
        check=True,
    )
    if not kernel.is_file() or not rootfs.is_file():
        raise RuntimeError("guest_image_provision_incomplete")
    return {
        "ready": True,
        "reused": False,
        "kernel": str(kernel),
        "rootfs": str(rootfs),
        "image_sha": hashlib.sha256(kernel.read_bytes() + rootfs.read_bytes()).hexdigest(),
    }


def assert_no_live_host_mount(
    host_mount: str | None,
    live_toplevel: str,
) -> str | None:
    """Return blocker reason if host_mount would expose the live checkout."""
    if not host_mount:
        return None
    try:
        mount = Path(host_mount).expanduser().resolve()
        live = Path(live_toplevel).resolve()
    except OSError:
        return "host_mount_unresolvable"
    if mount == live or live in mount.parents or mount in live.parents:
        return "host_mount_forbidden_for_replay"
    # Any host-mount is forbidden on the replay path (contract: snapshot inject only).
    return "host_mount_forbidden_for_replay"


def validate_guest_proof(proof: Mapping[str, Any]) -> list[str]:
    """Return proof_errors; empty list means the hop may be marked replayed."""
    errors: list[str] = []
    if proof.get("schema") != "ndf-replay-guest-proof/v1":
        errors.append("schema")
    isolation = proof.get("isolation")
    if not isinstance(isolation, Mapping):
        errors.append("isolation")
        return errors
    for field in (
        "guest_id",
        "image_sha",
        "guest_toplevel",
        "host_toplevel",
        "adapter",
    ):
        if not isolation.get(field):
            errors.append(f"missing:{field}")
    if isolation.get("same_checkout") is not False:
        errors.append("same_checkout")
    if isolation.get("host_tracked_unchanged") is not True:
        errors.append("host_tracked_changed")
    if isolation.get("host_head_unchanged") is not True:
        errors.append("host_head_changed")
    if isolation.get("sandbox_marker_absent_from_live_root") is not True:
        errors.append("guest_marker_on_live_root")
    # Contract level is always Lvm ``vm``; fake-vm is tests-only observe.
    if isolation.get("adapter") not in {"vm", "fake-vm"}:
        errors.append("adapter")
    if isolation.get("bwrap_used") is True:
        errors.append("bwrap_not_lvm")
    if isolation.get("host_mount_used") is True:
        errors.append("host_mount_used")
    reconstruct = proof.get("reconstruct")
    if not isinstance(reconstruct, Mapping):
        errors.append("reconstruct")
    elif reconstruct.get("side_effects") is not False:
        errors.append("reconstruct_side_effects")
    if proof.get("state") == "environment_blocked":
        errors.append("environment_blocked")
    return sorted(set(errors))


class MockCubeSandboxClient:
    """In-process Cube stand-in for tests: separate tree, never host-mounts live root."""

    def __init__(self, host_repo: Path) -> None:
        self.host_repo = host_repo.resolve()
        self.sandboxes: dict[str, Path] = {}

    def create(
        self,
        *,
        template_id: str,
        airgap: bool = True,
        host_mount: str | None = None,
    ) -> dict[str, Any]:
        if host_mount:
            raise ValueError("host_mount_forbidden_for_replay")
        if not airgap:
            raise ValueError("cube_replay_requires_airgap")
        sandbox_id = f"cube-mock-{uuid.uuid4()}"
        root = self.host_repo / "tmp" / "ndf-replay-guests" / sandbox_id / "root"
        root.mkdir(parents=True, exist_ok=True)
        self.sandboxes[sandbox_id] = root
        return {
            "sandbox_id": sandbox_id,
            "template_id": template_id,
            "guest_toplevel": str(root.resolve()),
        }

    def materialize_snapshot(self, sandbox_id: str, archive_tar: bytes) -> None:
        root = self.sandboxes[sandbox_id]
        subprocess.run(
            ["tar", "-xf", "-"],
            cwd=root,
            input=archive_tar,
            check=True,
        )

    def write_tree(self, sandbox_id: str, relative: str, src: Path) -> None:
        root = self.sandboxes[sandbox_id]
        dst = root / relative
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("*.lock", ".*.tmp"),
            )
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def kill(self, sandbox_id: str) -> None:
        root = self.sandboxes.pop(sandbox_id, None)
        if root is not None:
            shutil.rmtree(root.parent, ignore_errors=True)


class ReplayStore:
    """Small Git-like object store with atomic refs and append-only events."""

    def __init__(self, repo_root: Path = ROOT, store_root: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.root = (store_root or self.repo_root / ".ndf" / "replay").resolve()
        if not _inside(self.root, self.repo_root):
            raise ValueError("replay store must remain inside repository")
        self.objects = self.root / "objects"
        self.refs = self.root / "refs"
        self.events = self.root / "events"

    def initialize(self) -> None:
        for path in (self.objects, self.refs, self.events):
            path.mkdir(parents=True, exist_ok=True)
        config = self.root / "config.json"
        if not config.exists():
            self._atomic_write(
                config,
                canonical_json_bytes(
                    {
                        "schema": "ndf-replay-config/v1",
                        "created_at": now_iso(),
                        "object_hash": "sha256-canonical-json",
                        "default_replay_level": "R0",
                        "storage_security": "encrypted-local",
                        "cipher": "AES-256-GCM",
                        "key_id": self._key_id(),
                        "retention": {
                            "large_tool_blob_hot_days": 90,
                            "sensitive_model_turn_hot_days": 30,
                            "core_evidence": "topic-close-plus-one-archive-cycle",
                            "cold_objects_keep_sha_and_location": True,
                        },
                    }
                )
                + b"\n",
            )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _key_path(self) -> Path:
        override = os.environ.get("NDF_REPLAY_KEY_FILE")
        if override:
            return Path(override).expanduser().resolve()
        repo_id = hashlib.sha256(str(self.repo_root).encode("utf-8")).hexdigest()
        return (
            Path.home()
            / ".local"
            / "share"
            / "ndf-replay"
            / "keys"
            / f"{repo_id}.key"
        )

    def _key(self) -> bytes:
        if AESGCM is None:
            raise RuntimeError("cryptography is required for encrypted Replay objects")
        path = self._key_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._atomic_write(path, os.urandom(32))
            path.chmod(0o600)
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError(f"invalid Replay encryption key: {path}")
        return key

    def _key_id(self) -> str:
        return hashlib.sha256(self._key()).hexdigest()

    def _encrypt_object(self, sha: str, content: bytes) -> bytes:
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key()).encrypt(
            nonce,
            content,
            sha.encode("ascii"),
        )
        return ENCRYPTED_MAGIC + nonce + encrypted

    def _decrypt_object(self, sha: str, content: bytes) -> tuple[bytes, bool]:
        if not content.startswith(ENCRYPTED_MAGIC):
            return content, False
        nonce_start = len(ENCRYPTED_MAGIC)
        nonce = content[nonce_start : nonce_start + 12]
        ciphertext = content[nonce_start + 12 :]
        try:
            plain = AESGCM(self._key()).decrypt(
                nonce,
                ciphertext,
                sha.encode("ascii"),
            )
        except Exception as exc:
            raise ValueError(f"object decryption failed: {sha}") from exc
        return plain, True

    def _object_path(self, sha: str) -> Path:
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid object sha: {sha}")
        return self.objects / sha[:2] / sha[2:]

    def put_object(self, kind: str, data: Mapping[str, Any]) -> str:
        self.initialize()
        envelope = {"type": kind, "data": _json_copy(data)}
        content = canonical_json_bytes(envelope)
        sha = canonical_json_sha(envelope)
        path = self._object_path(sha)
        if path.exists():
            existing, _ = self._decrypt_object(sha, path.read_bytes())
            if existing != content:
                raise ValueError(f"object collision: {sha}")
            return sha
        self._atomic_write(path, self._encrypt_object(sha, content))
        return sha

    def get_object(self, sha: str, expected_type: str | None = None) -> dict[str, Any]:
        path = self._object_path(sha)
        if not path.is_file():
            raise FileNotFoundError(f"missing replay object: {sha}")
        raw, _ = self._decrypt_object(sha, path.read_bytes())
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid replay object: {sha}") from exc
        if canonical_json_sha(value) != sha:
            raise ValueError(f"object hash mismatch: {sha}")
        if expected_type and value.get("type") != expected_type:
            raise ValueError(f"expected {expected_type}, got {value.get('type')}")
        return value

    def find_blob(
        self,
        *,
        schema: str | None,
        schema_prefix: str | None = None,
        semantic_field: str,
        semantic_sha: str,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve one semantic SHA to its content-addressed blob."""
        matches: list[tuple[str, dict[str, Any]]] = []
        if self.objects.is_dir():
            for path in sorted(
                item
                for item in self.objects.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                sha = path.parent.name + path.name
                try:
                    obj = self.get_object(sha, "blob")
                except (FileNotFoundError, ValueError):
                    continue
                value = obj.get("data", {}).get("value")
                if (
                    isinstance(value, dict)
                    and (
                        value.get("schema") == schema
                        if schema is not None
                        else True
                    )
                    and (
                        str(value.get("schema") or "").startswith(schema_prefix)
                        if schema_prefix is not None
                        else True
                    )
                    and value.get(semantic_field) == semantic_sha
                ):
                    matches.append((sha, value))
        if not matches:
            raise ValueError(f"missing {schema or 'semantic'} blob for {semantic_sha}")
        first_sha, first = matches[0]
        if any(value != first for _, value in matches[1:]):
            raise ValueError(f"ambiguous semantic object: {semantic_sha}")
        return first_sha, first

    def put_blob(
        self,
        value: Any,
        *,
        media_type: str = "application/json",
        sensitivity: str = "internal",
    ) -> str:
        if isinstance(value, bytes):
            encoding = "base64"
            payload: Any = base64.b64encode(value).decode("ascii")
        elif isinstance(value, str):
            encoding = "utf-8"
            payload = value
        else:
            encoding = "json"
            payload = _json_copy(value)
        return self.put_object(
            "blob",
            {
                "schema": "ndf-replay-blob/v1",
                "media_type": media_type,
                "encoding": encoding,
                "sensitivity": sensitivity,
                "value": payload,
            },
        )

    def put_tree(self, entries: Mapping[str, str]) -> str:
        normalized: dict[str, str] = {}
        for name, sha in sorted(entries.items()):
            if not name or name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"invalid tree name: {name}")
            self.get_object(sha)
            normalized[name] = sha
        return self.put_object(
            "tree",
            {"schema": "ndf-replay-tree/v1", "entries": normalized},
        )

    def put_commit(
        self,
        tree: str,
        *,
        parents: Iterable[str] = (),
        actor: str,
        topic: str | None,
        task: str,
        track: str,
        repo_head: str | None,
        manifest_sha: str | None,
        context_plan_sha: str | None,
        message: str,
        coverage: Mapping[str, Any] | None = None,
    ) -> str:
        self.get_object(tree, "tree")
        parent_list = list(parents)
        for parent in parent_list:
            self.get_object(parent, "commit")
        return self.put_object(
            "commit",
            {
                "schema": "ndf-replay-commit/v1",
                "tree": tree,
                "parents": parent_list,
                "actor": actor,
                "topic": topic,
                "task": task,
                "track": track,
                "repo_head": repo_head,
                "manifest_sha": manifest_sha,
                "context_plan_sha": context_plan_sha,
                "message": message,
                "coverage": dict(coverage or {}),
                "created_at": now_iso(),
            },
        )

    @staticmethod
    def _validate_ref_name(name: str) -> str:
        clean = name.strip("/")
        if (
            not REF_RE.fullmatch(clean)
            or ".." in Path(clean).parts
            or any(part in {"", ".", ".."} for part in Path(clean).parts)
        ):
            raise ValueError(f"invalid ref name: {name}")
        return clean

    def ref_path(self, name: str) -> Path:
        clean = self._validate_ref_name(name)
        path = (self.refs / clean).resolve(strict=False)
        if not _inside(path, self.refs.resolve(strict=False)):
            raise ValueError(f"ref escapes store: {name}")
        return path

    def read_ref(self, name: str) -> str | None:
        path = self.ref_path(name)
        if not path.is_file():
            return None
        sha = path.read_text(encoding="utf-8").strip()
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid ref target: {name}")
        return sha

    def update_ref(
        self,
        name: str,
        sha: str,
        *,
        expected_old: str | None | object = _UNSET,
        immutable: bool = False,
    ) -> None:
        self.get_object(sha)
        path = self.ref_path(name)
        lock_path = self.root / "locks" / (
            hashlib.sha256(f"ref:{name}".encode("utf-8")).hexdigest() + ".lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            current = self.read_ref(name)
            if immutable and current is not None and current != sha:
                raise ValueError(f"immutable ref already exists: {name}")
            if expected_old is not _UNSET and current != expected_old:
                raise ValueError(
                    f"ref changed: {name}: expected {expected_old}, got {current}"
                )
            self._atomic_write(path, f"{sha}\n".encode())

    def create_gate_tag(
        self,
        name: str,
        target: str,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create an immutable approval tag only from a human-bound receipt."""
        errors = list(validate_receipt(receipt)["errors"])
        evidence = validate_evidence_bundle(receipt, root=self.repo_root)
        errors.extend(evidence["errors"])
        if receipt.get("status") not in {"approved", "valid"}:
            errors.append("gate_not_approved")
        if not receipt.get("phrase"):
            errors.append("missing:phrase")
        actor = str(receipt.get("approved_by") or "")
        if not actor or actor.lower() in {"agent", "openclaw", "claude-code", "canvas", "tool"}:
            errors.append("approval_actor_not_human")
        for field in (
            "approved_at",
            "source_ref",
            "approved_content_sha",
            "manifest_sha",
            "context_plan_sha",
        ):
            if not receipt.get(field):
                errors.append(f"missing:{field}")
        if not SHA_RE.fullmatch(str(receipt.get("approved_content_sha") or "")):
            errors.append("invalid:approved_content_sha")
        if receipt.get("approved_content_sha") != evidence.get(
            "expected_output_sha"
        ):
            errors.append("approved_content_sha_not_evidence_bundle")
        if errors:
            raise ValueError(f"invalid gate tag receipt: {errors}")
        target_sha = self.read_ref(target) or target
        target_commit = self.get_object(target_sha, "commit")["data"]
        receipt_sha = self.put_blob(dict(receipt))
        tree = self.put_tree(
            {
                "parent-tree": target_commit["tree"],
                "gate-receipt": receipt_sha,
            }
        )
        commit = self.put_commit(
            tree,
            parents=[target_sha],
            actor=actor,
            topic=target_commit.get("topic"),
            task="human_gate",
            track=target_commit.get("track") or "process",
            repo_head=target_commit.get("repo_head"),
            manifest_sha=receipt.get("manifest_sha"),
            context_plan_sha=receipt.get("context_plan_sha"),
            message=f"human gate tag: {name}",
            coverage={"gate_receipt": receipt_sha},
        )
        self.update_ref(f"tags/gates/{name}", commit, immutable=True)
        return {
            "schema": "ndf-replay-gate-tag/v1",
            "tag": f"gates/{name}",
            "commit_sha": commit,
            "receipt_sha": receipt_sha,
        }

    def event_path(self, episode_id: str, branch: str = "main") -> Path:
        clean = self._validate_ref_name(episode_id)
        if "/" in clean:
            raise ValueError("episode id must be a single path segment")
        if branch == "main":
            return self.events / f"{clean}.jsonl"
        branch_name = self._validate_ref_name(branch)
        path = (self.events / clean / f"{branch_name}.jsonl").resolve(strict=False)
        episode_root = (self.events / clean).resolve(strict=False)
        if not _inside(path, episode_root):
            raise ValueError("event branch escapes episode")
        return path

    def read_events(self, episode_id: str, branch: str = "main") -> list[dict[str, Any]]:
        path = self.event_path(episode_id, branch)
        if not path.is_file():
            return []
        events = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event JSON at line {number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"event is not object at line {number}")
            events.append(value)
        return events

    def event_branches(self, episode_id: str) -> list[str]:
        branches: list[str] = []
        if self.event_path(episode_id).is_file():
            branches.append("main")
        branch_root = self.events / self._validate_ref_name(episode_id)
        if branch_root.is_dir():
            branches.extend(
                path.relative_to(branch_root).with_suffix("").as_posix()
                for path in sorted(branch_root.rglob("*.jsonl"))
            )
        return branches

    def read_all_events(self, episode_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            branch: self.read_events(episode_id, branch)
            for branch in self.event_branches(episode_id)
        }

    def list_episode_ids(self) -> list[str]:
        return list_episode_ids(self)

    def episode_head_map(self) -> dict[str, str]:
        return episode_head_map(self)

    def canvas_index(self, *, write_cache: bool = False) -> dict[str, Any]:
        return project_canvas_index(self, write_cache=write_cache)

    def canvas_ledger(
        self,
        episode_id: str,
        *,
        write_cache: bool = False,
    ) -> dict[str, Any]:
        return project_canvas_ledger(self, episode_id, write_cache=write_cache)

    def append_event(
        self,
        episode_id: str,
        *,
        kind: str,
        actor: str,
        payload_sha: str,
        topic: str | None,
        task: str,
        track: str,
        repo_head: str | None,
        manifest_sha: str | None,
        context_plan_sha: str | None,
        session_id: str | None = None,
        run_id: str | None = None,
        branch: str = "main",
        verified: bool = True,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown replay event kind: {kind}")
        self.get_object(payload_sha)
        self.initialize()
        path = self.event_path(episode_id, branch)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / "locks" / (
            hashlib.sha256(
                f"event:{episode_id}:{branch}".encode("utf-8")
            ).hexdigest()
            + ".lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            events = self.read_events(episode_id, branch)
            chain = validate_event_chain(events)
            if not chain["valid"]:
                raise ValueError(
                    f"cannot append to invalid event chain: {chain['errors']}"
                )
            event = chained_event(
                {
                    "schema": "ndf-replay-event/v1",
                    "seq": len(events) + 1,
                    "episode_id": episode_id,
                    "branch": branch,
                    "timestamp": now_iso(),
                    "kind": kind,
                    "actor": actor,
                    "session_id": session_id,
                    "run_id": run_id,
                    "topic": topic,
                    "task": task,
                    "track": track,
                    "payload_sha": payload_sha,
                    "repo_head": repo_head,
                    "manifest_sha": manifest_sha,
                    "context_plan_sha": context_plan_sha,
                    "semantic_status": (
                        "verified"
                        if verified and event_actor_valid(kind, actor)
                        else "unverified"
                    ),
                },
                previous_sha=chain["tip_sha"],
            )
            existing = path.read_bytes() if path.is_file() else b""
            self._atomic_write(
                path,
                existing + canonical_json_bytes(event) + b"\n",
            )
        return event

    def init_episode(
        self,
        *,
        topic: str | None,
        task: str,
        role: str,
        track: str,
        manifest: Mapping[str, Any] | None = None,
        episode_id: str | None = None,
        flow_id: str | None = None,
        stage: str | None = None,
        parent_episode_id: str | None = None,
        proposal_id: str | None = None,
        proposal_sha: str | None = None,
    ) -> dict[str, Any]:
        identifier = episode_id or f"ep-{uuid.uuid4()}"
        if stage:
            if stage not in CONTROL_STAGES:
                raise ValueError(f"unknown control stage: {stage}")
            if not flow_id:
                raise ValueError("control child requires flow_id")
            if not parent_episode_id:
                raise ValueError("control child requires parent_episode_id")
        if manifest:
            import ndf_context

            manifest_check = ndf_context.verify_manifest(
                manifest,
                root=self.repo_root,
            )
            if not manifest_check["valid"]:
                raise ValueError(
                    f"episode requires a verified manifest: {manifest_check['errors']}"
                )
            expected_identity = {
                "topic": manifest.get("topic"),
                "task": manifest.get("task"),
                "track": manifest.get("track"),
            }
            actual_identity = {"topic": topic, "task": task, "track": track}
            if actual_identity != expected_identity:
                raise ValueError(
                    "episode identity does not match manifest: "
                    f"expected={expected_identity} actual={actual_identity}"
                )
        payload = {
            "schema": "ndf-replay-episode/v1",
            "episode_id": identifier,
            "topic": topic,
            "task": task,
            "role": role,
            "track": track,
            "flow_id": flow_id,
            "stage": stage,
            "parent_episode_id": parent_episode_id,
            "proposal_id": proposal_id,
            "proposal_sha": proposal_sha,
            "manifest_sha": (manifest or {}).get("manifest_sha"),
            "created_at": now_iso(),
        }
        entries = {"episode": self.put_blob(payload)}
        if manifest:
            entries["manifest"] = self.put_blob(dict(manifest))
        tree = self.put_tree(entries)
        commit = self.put_commit(
            tree,
            actor=role,
            topic=topic,
            task=task,
            track=track,
            repo_head=(manifest or {}).get("workspace", {}).get("repo_head"),
            manifest_sha=(manifest or {}).get("manifest_sha"),
            context_plan_sha=None,
            message="episode init",
            coverage={"events": "initialized"},
        )
        self.update_ref(f"episodes/{identifier}/HEAD", commit)
        self.update_ref(f"episodes/{identifier}/BASE", commit, immutable=True)
        self.update_ref(f"branches/{identifier}/main", commit)
        if topic:
            self.update_ref(f"topics/{topic}/current", commit)
        event = self.append_event(
            identifier,
            kind="intent.received",
            actor=role,
            payload_sha=entries["episode"],
            topic=topic,
            task=task,
            track=track,
            repo_head=(manifest or {}).get("workspace", {}).get("repo_head"),
            manifest_sha=(manifest or {}).get("manifest_sha"),
            context_plan_sha=None,
        )
        return {
            "schema": "ndf-replay-episode-init/v1",
            "episode_id": identifier,
            "commit_sha": commit,
            "event_sha": event["event_sha"],
            "flow_id": flow_id,
            "stage": stage,
            "parent_episode_id": parent_episode_id,
        }

    def _flow_pointer(self, name: str) -> dict[str, Any] | None:
        sha = self.read_ref(name)
        if sha is None:
            return None
        value = self.get_object(sha, "blob")["data"].get("value")
        return value if isinstance(value, dict) else None

    def _write_flow_pointer(self, name: str, payload: Mapping[str, Any]) -> str:
        sha = self.put_blob(dict(payload))
        self.update_ref(name, sha, immutable=True)
        return sha

    def episode_identity(self, episode_id: str) -> dict[str, Any] | None:
        if self.read_ref(f"episodes/{episode_id}/HEAD") is None:
            return None
        for events in self.read_all_events(episode_id).values():
            for event in events:
                if event.get("kind") != "intent.received":
                    continue
                try:
                    blob = self.get_object(str(event.get("payload_sha")), "blob")
                except (FileNotFoundError, ValueError):
                    continue
                value = blob.get("data", {}).get("value")
                if isinstance(value, dict) and value.get("schema") == "ndf-replay-episode/v1":
                    return value
        return {"episode_id": episode_id}

    def ensure_control_parent(
        self,
        *,
        flow_id: str,
        proposal_id: str | None,
        role: str,
        track: str,
    ) -> str:
        parent_id = control_parent_id(flow_id)
        pointer = self._flow_pointer(control_parent_ref(flow_id))
        if pointer:
            return str(pointer.get("episode_id") or parent_id)
        if self.read_ref(f"episodes/{parent_id}/HEAD") is None:
            self.init_episode(
                topic=None,
                task="ndf_control_flow",
                role=role,
                track=track,
                manifest=None,
                episode_id=parent_id,
                flow_id=flow_id,
                proposal_id=proposal_id,
            )
        self._write_flow_pointer(
            control_parent_ref(flow_id),
            {
                "schema": "ndf-control-flow-pointer/v1",
                "flow_id": flow_id,
                "stage": None,
                "episode_id": parent_id,
                "proposal_id": proposal_id,
            },
        )
        return parent_id

    def ensure_control_child(
        self,
        *,
        flow_id: str,
        stage: str,
        requested_episode_id: str | None,
        manifest: Mapping[str, Any] | None,
        topic: str | None,
        task: str,
        role: str,
        track: str,
        proposal_id: str | None = None,
        proposal_sha: str | None = None,
    ) -> dict[str, Any]:
        if stage not in CONTROL_STAGES:
            raise ValueError(f"unknown control stage: {stage}")
        parent_id = self.ensure_control_parent(
            flow_id=flow_id,
            proposal_id=proposal_id,
            role=role,
            track=track,
        )
        pointer = self._flow_pointer(control_child_ref(flow_id, stage))
        if pointer:
            bound_id = str(pointer.get("episode_id") or "")
            if requested_episode_id and requested_episode_id != bound_id:
                raise ValueError("control child already bound for stage")
            if pointer.get("manifest_sha") and manifest:
                if pointer.get("manifest_sha") != manifest.get("manifest_sha"):
                    raise ValueError("control child refuses manifest rebind")
            if pointer.get("proposal_sha") and proposal_sha:
                if pointer.get("proposal_sha") != proposal_sha:
                    raise ValueError("control child refuses proposal rebind")
            identity = self.episode_identity(bound_id) or {}
            if identity.get("stage") not in {None, stage}:
                raise ValueError("episode already bound to another control stage")
            return {
                "episode_id": bound_id,
                "parent_episode_id": parent_id,
                "flow_id": flow_id,
                "stage": stage,
                "created": False,
            }
        child_id = requested_episode_id or control_child_id(flow_id, stage)
        existing = self.episode_identity(child_id)
        if existing and existing.get("stage") not in {None, stage}:
            raise ValueError("episode already bound to another control stage")
        if existing and existing.get("flow_id") not in {None, flow_id}:
            raise ValueError("episode already bound to another control flow")
        if self.read_ref(f"episodes/{child_id}/HEAD") is None:
            self.init_episode(
                topic=topic,
                task=task,
                role=role,
                track=track,
                manifest=manifest,
                episode_id=child_id,
                flow_id=flow_id,
                stage=stage,
                parent_episode_id=parent_id,
                proposal_id=proposal_id,
                proposal_sha=proposal_sha,
            )
        elif existing and existing.get("stage") is None:
            raise ValueError("cannot adopt unbound episode as control child")
        self._write_flow_pointer(
            control_child_ref(flow_id, stage),
            {
                "schema": "ndf-control-flow-pointer/v1",
                "flow_id": flow_id,
                "stage": stage,
                "episode_id": child_id,
                "parent_episode_id": parent_id,
                "proposal_id": proposal_id,
                "proposal_sha": proposal_sha,
                "manifest_sha": (manifest or {}).get("manifest_sha"),
            },
        )
        return {
            "episode_id": child_id,
            "parent_episode_id": parent_id,
            "flow_id": flow_id,
            "stage": stage,
            "created": True,
        }

    def commit_events(
        self,
        episode_id: str,
        *,
        message: str,
        actor: str = "tool",
        branch: str = "main",
        coverage: Mapping[str, Any] | None = None,
    ) -> str:
        events = self.read_events(episode_id, branch)
        validation = validate_event_chain(events)
        if not validation["valid"]:
            raise ValueError(f"invalid event chain: {validation['errors']}")
        head_ref = f"episodes/{episode_id}/HEAD"
        branch_ref = f"branches/{episode_id}/{branch}"
        parent = self.read_ref(branch_ref)
        if parent is None:
            parent = self.read_ref(f"episodes/{episode_id}/BASE")
        if parent is None:
            raise ValueError(f"unknown episode: {episode_id}")
        entries: dict[str, str] = {}
        for event in events:
            sequence = int(event["seq"])
            entries[f"event-{sequence:08d}"] = self.put_blob(event)
            entries[f"payload-{sequence:08d}"] = str(event["payload_sha"])
        entries["event-chain"] = self.put_blob(
            {
                "schema": "ndf-replay-event-chain/v1",
                "episode_id": episode_id,
                "branch": branch,
                "count": validation["count"],
                "tip_sha": validation["tip_sha"],
            }
        )
        tree = self.put_tree(entries)
        last = events[-1] if events else {}
        commit = self.put_commit(
            tree,
            parents=[parent],
            actor=actor,
            topic=last.get("topic"),
            task=str(last.get("task") or "unknown"),
            track=str(last.get("track") or "unknown"),
            repo_head=last.get("repo_head"),
            manifest_sha=last.get("manifest_sha"),
            context_plan_sha=last.get("context_plan_sha"),
            message=message,
            coverage={
                "event_count": len(events),
                "event_tip": validation["tip_sha"],
                **dict(coverage or {}),
            },
        )
        self.update_ref(branch_ref, commit, expected_old=self.read_ref(branch_ref))
        if branch == "main":
            self.update_ref(head_ref, commit, expected_old=self.read_ref(head_ref))
        return commit

    def checkpoint(
        self,
        episode_id: str,
        *,
        summary: str,
        manifest_sha: str | None,
        plan_sha: str | None,
        open_decisions: Iterable[str] = (),
        resolved_decisions: Iterable[str] = (),
        summary_provenance: Mapping[str, Any] | None = None,
        branch: str = "main",
    ) -> str:
        if not manifest_sha or not plan_sha:
            raise ValueError("checkpoint requires manifest_sha and plan_sha")
        manifest_blob, manifest = self.find_blob(
            schema="ndf-task-manifest/v1",
            semantic_field="manifest_sha",
            semantic_sha=manifest_sha,
        )
        plan_blob, plan = self.find_blob(
            schema=None,
            schema_prefix="ndf-context-plan",
            semantic_field="plan_sha",
            semantic_sha=plan_sha,
        )
        # Role plan schemas vary, so fall back to a type-neutral scan.
        if (
            plan.get("plan_sha") != plan_sha
            or not str(plan.get("schema") or "").startswith("ndf-context-plan")
        ):
            raise ValueError("checkpoint plan SHA mismatch")
        import ndf_context

        policy = manifest.get("compiler_policy") or {}
        recompiled_manifest = ndf_context.create_manifest(
            root=self.repo_root,
            topic=manifest.get("topic"),
            task=str(manifest.get("task")),
            track=str(manifest.get("track")),
            business_goal=str(manifest.get("business_goal") or ""),
            seed_ids=policy.get("requested_seed_ids", []),
            depth=int(policy.get("depth", 2)),
            node_budget=int(policy.get("node_budget", 80)),
            byte_budget=int(policy.get("byte_budget", 256_000)),
        )
        if recompiled_manifest.get("manifest_sha") != manifest_sha:
            raise ValueError("checkpoint manifest drift; recompile context first")
        recompiled_plan = ndf_context.role_plan(
            recompiled_manifest,
            role=str(plan.get("role")),
        )
        if recompiled_plan.get("plan_sha") != plan_sha:
            raise ValueError("checkpoint role plan drift; recompile context first")
        verification = ndf_context.verify_plan(
            plan,
            root=self.repo_root,
            manifest=manifest,
            require_manifest=True,
        )
        if not verification["valid"]:
            raise ValueError(f"checkpoint context verification failed: {verification['errors']}")
        events = self.read_events(episode_id, branch)
        validation = validate_event_chain(events)
        if not validation["valid"]:
            raise ValueError(f"invalid event chain: {validation['errors']}")
        all_branch_events = self.read_all_events(episode_id)
        branch_coverage = {
            name: validate_event_chain(values)
            for name, values in all_branch_events.items()
        }
        if not branch_coverage or any(
            not value["valid"] for value in branch_coverage.values()
        ):
            raise ValueError("checkpoint requires all Episode branch chains valid")
        retained_branch_heads = [
            value
            for name in all_branch_events
            if (value := self.read_ref(f"branches/{episode_id}/{name}"))
        ]
        summary_blob = self.put_blob(
            summary,
            media_type="text/plain",
            sensitivity="sensitive",
        )
        provenance = {
            "schema": "ndf-summary-provenance/v1",
            "producer": "human-or-tool",
            "model": None,
            **dict(summary_provenance or {}),
        }
        provenance_blob = self.put_blob(provenance)
        previous_checkpoint = next(
            (
                event.get("payload_sha")
                for event in reversed(events)
                if event.get("kind") == "compaction.checkpoint"
            ),
            None,
        )
        checkpoint = {
            "schema": "ndf-replay-checkpoint/v1",
            "episode_id": episode_id,
            "covered_seq": [1, len(events)],
            "covered_branches": {
                name: {
                    "count": value["count"],
                    "tip_sha": value["tip_sha"],
                }
                for name, value in sorted(branch_coverage.items())
            },
            "raw_events_digest": canonical_json_sha(all_branch_events),
            "event_tip_sha": validation["tip_sha"],
            "parent_checkpoint": previous_checkpoint,
            "manifest_sha": manifest_sha,
            "context_plan_sha": plan_sha,
            "recompiled_manifest_sha": recompiled_manifest["manifest_sha"],
            "recompiled_context_plan_sha": recompiled_plan["plan_sha"],
            "retained_object_refs": [
                manifest_blob,
                plan_blob,
                *sorted(set(retained_branch_heads)),
            ],
            "summary_blob": summary_blob,
            "summary_provenance_blob": provenance_blob,
            "summary_navigation_only": True,
            "resolved_decisions": list(resolved_decisions),
            "open_decisions": list(open_decisions),
            "gate_states": manifest.get("human_gates"),
            "context_verification": verification,
            "created_at": now_iso(),
        }
        payload_sha = self.put_blob(checkpoint)
        last = events[-1] if events else {}
        self.append_event(
            episode_id,
            kind="compaction.checkpoint",
            actor="tool",
            payload_sha=payload_sha,
            topic=last.get("topic"),
            task=str(last.get("task") or "checkpoint"),
            track=str(last.get("track") or "process"),
            repo_head=last.get("repo_head"),
            manifest_sha=manifest_sha,
            context_plan_sha=plan_sha,
            branch=branch,
        )
        return self.commit_events(
            episode_id,
            message="compaction checkpoint",
            branch=branch,
            coverage={"checkpoint_context_reverified": True},
        )

    def merge(
        self,
        episode_id: str,
        left: str,
        right: str,
        *,
        message: str,
        actor: str = "tool",
    ) -> str:
        left_sha = self.read_ref(left) or left
        right_sha = self.read_ref(right) or right
        left_commit = self.get_object(left_sha, "commit")["data"]
        right_commit = self.get_object(right_sha, "commit")["data"]
        left_audit = self.audit(left_sha, strict=True)
        right_audit = self.audit(right_sha, strict=True)
        if not left_audit["valid"] or not right_audit["valid"]:
            raise ValueError(
                "merge requires semantically verified parent histories: "
                f"left={left_audit['join_gaps'] + left_audit.get('semantic_gaps', [])}; "
                f"right={right_audit['join_gaps'] + right_audit.get('semantic_gaps', [])}"
            )
        if (
            not left_commit.get("manifest_sha")
            or left_commit.get("manifest_sha") != right_commit.get("manifest_sha")
        ):
            raise ValueError("merge parents must share one manifest_sha")
        tree = self.put_tree(
            {
                "left": left_commit["tree"],
                "right": right_commit["tree"],
                "merge-metadata": self.put_blob(
                    {
                        "schema": "ndf-replay-merge/v1",
                        "left": left_sha,
                        "right": right_sha,
                        "verified_objects_only": True,
                        "left_audit": left_audit["valid"],
                        "right_audit": right_audit["valid"],
                    }
                ),
            }
        )
        commit = self.put_commit(
            tree,
            parents=[left_sha, right_sha],
            actor=actor,
            topic=left_commit.get("topic") or right_commit.get("topic"),
            task="merge",
            track=left_commit.get("track") or right_commit.get("track") or "process",
            repo_head=right_commit.get("repo_head") or left_commit.get("repo_head"),
            manifest_sha=left_commit.get("manifest_sha") or right_commit.get("manifest_sha"),
            context_plan_sha=None,
            message=message,
            coverage={
                "left": left_commit.get("coverage", {}),
                "right": right_commit.get("coverage", {}),
            },
        )
        head_ref = f"episodes/{episode_id}/HEAD"
        self.update_ref(head_ref, commit, expected_old=self.read_ref(head_ref))
        main_ref = f"branches/{episode_id}/main"
        self.update_ref(main_ref, commit, expected_old=self.read_ref(main_ref))
        topic = left_commit.get("topic") or right_commit.get("topic")
        if topic:
            self.update_ref(f"topics/{topic}/current", commit)
        return commit

    def walk_commits(self, start: str) -> list[tuple[str, dict[str, Any]]]:
        sha = self.read_ref(start) or start
        output: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def visit(current: str) -> None:
            if current in seen:
                return
            if current in visiting:
                raise ValueError(f"commit parent cycle: {current}")
            visiting.add(current)
            commit = self.get_object(current, "commit")["data"]
            for parent in commit.get("parents", []):
                visit(str(parent))
            visiting.remove(current)
            seen.add(current)
            output.append((current, commit))

        visit(sha)
        return output

    def diff(self, left: str, right: str) -> dict[str, Any]:
        left_sha = self.read_ref(left) or left
        right_sha = self.read_ref(right) or right
        left_commit = self.get_object(left_sha, "commit")["data"]
        right_commit = self.get_object(right_sha, "commit")["data"]
        left_tree = self.get_object(left_commit["tree"], "tree")["data"]["entries"]
        right_tree = self.get_object(right_commit["tree"], "tree")["data"]["entries"]
        names = sorted(set(left_tree) | set(right_tree))
        facet_names = (
            "manifest",
            "context",
            "events",
            "observations",
            "results",
            "verification",
        )

        def semantic_objects(commit_sha: str) -> dict[str, dict[str, str]]:
            facets: dict[str, dict[str, str]] = {
                name: {} for name in facet_names
            }
            reconstruction = self.reconstruct(commit_sha, "R0")
            for item in reconstruction.get("recorded_objects", []):
                obj = item.get("object", {})
                data = obj.get("data", {})
                value = data.get("value") if obj.get("type") == "blob" else data
                schema = (
                    str(value.get("schema") or "")
                    if isinstance(value, Mapping)
                    else str(data.get("schema") or "")
                )
                facet = None
                semantic_key = item["sha"]
                if schema == "ndf-task-manifest/v1":
                    facet = "manifest"
                    semantic_key = str(value.get("manifest_sha") or item["sha"])
                elif schema.startswith("ndf-context-plan"):
                    facet = "context"
                    semantic_key = str(value.get("plan_sha") or item["sha"])
                elif schema == "ndf-replay-event/v1":
                    facet = "events"
                    semantic_key = str(value.get("event_sha") or item["sha"])
                elif obj.get("type") in {"tool-cassette", "model-turn"}:
                    facet = "observations"
                    semantic_key = str(
                        data.get("invocation_id")
                        or data.get("turn_id")
                        or item["sha"]
                    )
                elif schema in {
                    "ndf-agent-completion/v1",
                    "ndf-runtime-mutation-proof/v1",
                    "ndf-replay-r2-expectations/v1",
                }:
                    facet = "results"
                    semantic_key = str(
                        value.get("run_id") or value.get("proof_sha") or item["sha"]
                    )
                elif schema in {
                    "ndf-replay-sandbox/v1",
                    "ndf-close-evidence/v1",
                    "ndf-projection-receipt/v2",
                    "ndf-context-verification/v1",
                }:
                    facet = "verification"
                    semantic_key = str(
                        value.get("profile_sha")
                        or value.get("output_sha")
                        or value.get("plan_sha")
                        or item["sha"]
                    )
                if facet:
                    facets[facet][semantic_key] = str(item["sha"])
            return facets

        def recorded_manifest(commit_sha: str) -> dict[str, Any]:
            found: dict[str, Any] = {}
            reconstruction = self.reconstruct(commit_sha, "R0")
            for item in reconstruction.get("recorded_objects", []):
                obj = item.get("object", {})
                data = obj.get("data", {})
                value = data.get("value") if obj.get("type") == "blob" else data
                if (
                    isinstance(value, Mapping)
                    and value.get("schema") == "ndf-task-manifest/v1"
                ):
                    found = dict(value)
            return found

        left_facets = semantic_objects(left_sha)
        right_facets = semantic_objects(right_sha)
        left_manifest = recorded_manifest(left_sha)
        right_manifest = recorded_manifest(right_sha)
        left_specs = (
            left_manifest.get("human_gates", {}).get("bundle_specs", {})
            if isinstance(left_manifest.get("human_gates"), Mapping)
            else {}
        )
        right_specs = (
            right_manifest.get("human_gates", {}).get("bundle_specs", {})
            if isinstance(right_manifest.get("human_gates"), Mapping)
            else {}
        )
        classified = classify_gate_bundle_changes(left_specs, right_specs)
        contract_slice_changed = classified["contract_slice_changed"]
        manifest_formula_changed = classified["manifest_formula_changed"]
        mutable_evidence_changed = bool(
            left_manifest.get("baseline") != right_manifest.get("baseline")
            or left_manifest.get("evidence_refs")
            != right_manifest.get("evidence_refs")
        )
        facet_diff = {}
        for facet in facet_names:
            left_values = left_facets[facet]
            right_values = right_facets[facet]
            keys = sorted(set(left_values) | set(right_values))
            facet_diff[facet] = {
                "added": [
                    key for key in keys if key not in left_values
                ],
                "removed": [
                    key for key in keys if key not in right_values
                ],
                "changed": [
                    key
                    for key in keys
                    if key in left_values
                    and key in right_values
                    and left_values[key] != right_values[key]
                ],
                "left_shas": left_values,
                "right_shas": right_values,
            }
        return {
            "schema": "ndf-replay-diff/v1",
            "left": left_sha,
            "right": right_sha,
            "added": [name for name in names if name not in left_tree],
            "removed": [name for name in names if name not in right_tree],
            "changed": [
                name
                for name in names
                if name in left_tree
                and name in right_tree
                and left_tree[name] != right_tree[name]
            ],
            "facets": facet_diff,
            "change_classification": {
                "contract_slice_changed": contract_slice_changed,
                "manifest_formula_changed": manifest_formula_changed,
                "mutable_evidence_changed": mutable_evidence_changed,
                "bundle_mode_changed": (
                    (
                        left_manifest.get("human_gates", {}).get("bundle_mode")
                        if isinstance(left_manifest.get("human_gates"), Mapping)
                        else None
                    )
                    != (
                        right_manifest.get("human_gates", {}).get("bundle_mode")
                        if isinstance(right_manifest.get("human_gates"), Mapping)
                        else None
                    )
                ),
            },
        }

    def audit(self, commit_or_ref: str, *, strict: bool = True) -> dict[str, Any]:
        fsck = self.fsck()
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        coverage_gaps: list[str] = []
        join_gaps: list[str] = []
        semantic_gaps: list[str] = []
        seen_events: set[str] = set()
        observed_events: list[
            tuple[str, str, dict[str, Any], dict[str, Any], Any]
        ] = []
        if strict:
            import ndf_context
        for commit_sha, historical in self.walk_commits(sha):
            for key, value in historical.get("coverage", {}).items():
                if value is None or (
                    isinstance(value, str)
                    and value in {"unknown", "completion_only", "messages_only"}
                ):
                    coverage_gaps.append(f"{commit_sha}:{key}:{value}")
            manifest_sha = historical.get("manifest_sha")
            plan_sha = historical.get("context_plan_sha")
            manifest: dict[str, Any] | None = None
            plan: dict[str, Any] | None = None
            if manifest_sha:
                try:
                    _, manifest = self.find_blob(
                        schema="ndf-task-manifest/v1",
                        semantic_field="manifest_sha",
                        semantic_sha=str(manifest_sha),
                    )
                    if strict:
                        manifest_check = ndf_context.verify_manifest_recorded(manifest)
                        if not manifest_check["valid"]:
                            semantic_gaps.append(
                                f"{commit_sha}:manifest_invalid:"
                                f"{canonical_json_sha(manifest_check['errors'])}"
                            )
                except ValueError:
                    join_gaps.append(f"{commit_sha}:manifest:{manifest_sha}")
            if plan_sha:
                try:
                    _, plan = self.find_blob(
                        schema=None,
                        schema_prefix="ndf-context-plan",
                        semantic_field="plan_sha",
                        semantic_sha=str(plan_sha),
                    )
                    if not str(plan.get("schema") or "").startswith(
                        "ndf-context-plan"
                    ):
                        raise ValueError("semantic plan object has wrong schema")
                    if manifest_sha and plan.get("manifest_sha") != manifest_sha:
                        join_gaps.append(f"{commit_sha}:plan_manifest_mismatch")
                    if strict and manifest is not None:
                        plan_check = ndf_context.verify_plan_recorded(
                            plan,
                            manifest=manifest,
                        )
                        if not plan_check["valid"]:
                            semantic_gaps.append(
                                f"{commit_sha}:plan_invalid:"
                                f"{canonical_json_sha(plan_check['errors'])}"
                            )
                except ValueError:
                    join_gaps.append(f"{commit_sha}:plan:{plan_sha}")
            if plan_sha and manifest is None:
                join_gaps.append(f"{commit_sha}:plan_without_manifest")
            tree_entries = self.get_object(
                str(historical["tree"]),
                "tree",
            )["data"].get("entries", {})
            for name, event_blob_sha in tree_entries.items():
                if (
                    not re.fullmatch(r"event-\d{8}", str(name))
                    or event_blob_sha in seen_events
                ):
                    continue
                seen_events.add(str(event_blob_sha))
                event_blob = self.get_object(str(event_blob_sha), "blob")["data"]
                replay_event = event_blob.get("value")
                if not isinstance(replay_event, dict):
                    semantic_gaps.append(f"{commit_sha}:{name}:event_not_json")
                    continue
                payload = self.get_object(str(replay_event.get("payload_sha") or ""))
                payload_value = payload.get("data", {}).get("value")
                kind = replay_event.get("kind")
                observed_events.append(
                    (commit_sha, str(name), replay_event, payload, payload_value)
                )
                if not event_actor_valid(str(kind or ""), str(replay_event.get("actor") or "")):
                    semantic_gaps.append(f"{commit_sha}:{name}:invalid_event_actor")
                if replay_event.get("semantic_status") != "verified":
                    semantic_gaps.append(f"{commit_sha}:{name}:unverified_event")
                if kind == "gate.approved":
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-gate-receipt/v1"
                        or not validate_receipt(payload_value)["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_gate_receipt")
                elif kind == "dispatch.preflight":
                    invalid_dispatch = (
                        not isinstance(payload_value, Mapping)
                        or not dispatch_pack_lease_eligible(payload_value)
                        or payload_value.get("manifest_sha")
                        != replay_event.get("manifest_sha")
                        or payload_value.get("plan_sha")
                        != replay_event.get("context_plan_sha")
                        or payload_value.get("task") != replay_event.get("task")
                        or payload_value.get("track") != replay_event.get("track")
                    )
                    if not invalid_dispatch and replay_event.get(
                        "context_plan_sha"
                    ):
                        try:
                            _, dispatch_plan = self.find_blob(
                                schema=None,
                                schema_prefix="ndf-context-plan",
                                semantic_field="plan_sha",
                                semantic_sha=str(
                                    replay_event["context_plan_sha"]
                                ),
                            )
                            write_root = str(
                                payload_value.get("allowed_write_root") or ""
                            ).strip("/")
                            planned_roots = [
                                str(root).strip("/")
                                for root in dispatch_plan.get(
                                    "privileges", {}
                                ).get("allowed_write_roots", [])
                            ]
                            if write_root and not any(
                                write_root == root
                                or write_root.startswith(f"{root}/")
                                for root in planned_roots
                            ):
                                invalid_dispatch = True
                        except ValueError:
                            invalid_dispatch = True
                    if invalid_dispatch:
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_dispatch_pack")
                elif kind in {"acp.start", "lease.acquired", "lease.released"}:
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-runtime-lease/v1"
                        or not validate_receipt(payload_value)["valid"]
                        or payload_value.get("manifest_sha")
                        != replay_event.get("manifest_sha")
                        or payload_value.get("context_plan_sha")
                        != replay_event.get("context_plan_sha")
                        or not validate_recorded_runtime_lease_binding(
                            payload_value
                        )["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_runtime_lease")
                elif kind == "close.receipt":
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-close-evidence/v1"
                        or not validate_receipt(payload_value)["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_close_receipt")
                elif kind in {"acp.complete", "openclaw.response"}:
                    if not isinstance(payload_value, Mapping):
                        semantic_gaps.append(f"{commit_sha}:{name}:completion_not_json")
                        continue
                    schema = payload_value.get("schema")
                    if schema == "ndf-agent-message/v1":
                        if any(
                            field not in payload_value
                            for field in (
                                "task",
                                "track",
                                "manifest_sha",
                                "context_plan_sha",
                                "session_id",
                                "run_id",
                                "message",
                            )
                        ):
                            semantic_gaps.append(
                                f"{commit_sha}:{name}:invalid_agent_message"
                            )
                    elif schema == "ndf-agent-completion/v1":
                        required_completion = (
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
                            "run_id",
                            "session_id",
                        )
                        changed_files = payload_value.get("changed_files")
                        changed_shas = payload_value.get("changed_file_shas")
                        valid_changed = bool(
                            isinstance(changed_files, list)
                            and isinstance(changed_shas, Mapping)
                            and set(changed_files) == set(changed_shas)
                            and all(
                                SHA_RE.fullmatch(str(value or ""))
                                for value in changed_shas.values()
                            )
                        )
                        event_bound = all(
                            payload_value.get(field) == replay_event.get(event_field)
                            for field, event_field in (
                                ("task", "task"),
                                ("track", "track"),
                                ("manifest_sha", "manifest_sha"),
                                ("context_plan_sha", "context_plan_sha"),
                                ("run_id", "run_id"),
                                ("session_id", "session_id"),
                            )
                        )
                        evidence_valid = bool(
                            SHA_RE.fullmatch(
                                str(payload_value.get("evidence_bundle_sha") or "")
                            )
                            and isinstance(payload_value.get("evidence_paths"), list)
                        )
                        post_checks_valid = bool(
                            isinstance(
                                payload_value.get("post_check_receipts"), list
                            )
                            and payload_value.get("post_check_receipts")
                            and all(
                                isinstance(receipt, Mapping)
                                and receipt.get("result")
                                in {"success", "passed", "completed"}
                                and isinstance(receipt.get("verifier"), Mapping)
                                and Path(
                                    str(receipt["verifier"].get("path") or "")
                                ).is_absolute()
                                and isinstance(
                                    receipt["verifier"].get("argv"), list
                                )
                                and SHA_RE.fullmatch(
                                    str(
                                        receipt["verifier"].get("version_sha")
                                        or ""
                                    )
                                )
                                is not None
                                and receipt["verifier"].get("exit_code") == 0
                                and bool(
                                    receipt["verifier"].get("output_schema")
                                )
                                for receipt in payload_value.get(
                                    "post_check_receipts", []
                                )
                            )
                        )
                        mutation_proof = payload_value.get("mutation_proof")
                        mutation_valid = bool(
                            isinstance(mutation_proof, Mapping)
                            and mutation_proof.get("schema")
                            == "ndf-runtime-mutation-proof/v1"
                            and mutation_proof.get("proof_sha")
                            == canonical_json_sha(
                                {
                                    key: value
                                    for key, value in mutation_proof.items()
                                    if key != "proof_sha"
                                }
                            )
                            and set(mutation_proof.get("actual_mutations", []))
                            == set(payload_value.get("changed_files", []))
                        )
                        if (
                            any(field not in payload_value for field in required_completion)
                            or payload_value.get("result")
                            not in {"success", "passed", "completed"}
                            or not valid_changed
                            or not evidence_valid
                            or not post_checks_valid
                            or not mutation_valid
                            or not event_bound
                        ):
                            semantic_gaps.append(
                                f"{commit_sha}:{name}:invalid_agent_completion"
                            )
                    else:
                        semantic_gaps.append(
                            f"{commit_sha}:{name}:unsupported_agent_response"
                        )
                elif kind == "verification.completed":
                    if (
                        isinstance(payload_value, Mapping)
                        and payload_value.get("schema") == "ndf-replay-sandbox/v1"
                        and payload_value.get("state") == "equivalent"
                        and (
                            payload_value.get("executed") is not True
                            or not payload_value.get("output_checks")
                            or not all(
                                check.get("matches") is True
                                for check in payload_value.get("output_checks", [])
                            )
                            or payload_value.get("write_violations")
                        )
                    ):
                        semantic_gaps.append(
                            f"{commit_sha}:{name}:invalid_r2_equivalence"
                        )
        branch_state: dict[str, dict[str, bool]] = {}
        for commit_sha, name, event, _, _ in sorted(
            observed_events,
            key=lambda item: (
                str(item[2].get("branch") or "main"),
                int(item[2].get("seq") or 0),
            ),
        ):
            branch = str(event.get("branch") or "main")
            state = branch_state.setdefault(
                branch,
                {
                    "compiled": False,
                    "verified": False,
                    "dispatch": False,
                    "lease": False,
                    "completion": False,
                },
            )
            kind = event.get("kind")
            if kind == "context.compiled":
                state["compiled"] = True
            elif kind == "context.verified":
                if not state["compiled"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:context_verified_without_compile"
                    )
                state["verified"] = True
            elif kind in {"dispatch.preflight", "dispatch.blocked"}:
                if kind == "dispatch.preflight" and not state["verified"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:dispatch_without_context_verify"
                    )
                if kind == "dispatch.preflight":
                    state["dispatch"] = True
            elif kind == "lease.acquired":
                if not state["dispatch"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:lease_without_dispatch"
                    )
                state["lease"] = True
            elif kind in {"acp.complete", "openclaw.response"}:
                if kind == "acp.complete" and not state["lease"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:completion_without_acquired_lease"
                    )
                if kind == "acp.complete":
                    state["completion"] = True
            elif kind == "lease.released":
                if not state["completion"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:release_without_completion"
                    )
        for branch, state in branch_state.items():
            if state["compiled"] and not state["verified"]:
                semantic_gaps.append(f"{branch}:compiled_context_not_verified")

        project_control_groups: dict[
            tuple[Any, ...], list[tuple[Mapping[str, Any], Any]]
        ] = {}
        for _, _, event, _, value in observed_events:
            if event.get("task") not in {
                "ndf_improvement_proposal",
                "ndf_improvement_land",
            }:
                continue
            payload = value if isinstance(value, Mapping) else {}
            key = (
                payload.get("flow_id"),
                payload.get("hop"),
                event.get("manifest_sha"),
                event.get("context_plan_sha"),
            )
            project_control_groups.setdefault(key, []).append((event, value))
        for key, records in project_control_groups.items():
            for error in validate_project_control_flow(records):
                semantic_gaps.append(
                    f"project-control:{canonical_json_sha(key)}:{error}"
                )

        dispatches = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "dispatch.preflight"
            and dispatch_pack_lease_eligible(value)
        ]
        leases = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "lease.acquired"
            and isinstance(value, Mapping)
            and value.get("result") == "active"
        ]
        releases = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "lease.released"
            and isinstance(value, Mapping)
            and value.get("result") in {"released", "expired", "failed"}
        ]
        for event, lease in leases:
            joined_pack = next(
                (
                    (dispatch_event, pack)
                    for dispatch_event, pack in dispatches
                    if dispatch_event.get("task") == event.get("task")
                    and dispatch_event.get("manifest_sha")
                    == event.get("manifest_sha")
                    and dispatch_event.get("context_plan_sha")
                    == event.get("context_plan_sha")
                    and lease.get("pack_sha")
                    == dispatch_event.get("payload_sha")
                ),
                None,
            )
            if joined_pack is None:
                semantic_gaps.append(
                    f"{event.get('run_id')}:lease_without_dispatch_pack"
                )
                continue
            dispatch_event, pack = joined_pack
            lease_check = validate_recorded_runtime_lease_binding(
                lease,
                expected={
                    "topic": event.get("topic"),
                    "task": event.get("task"),
                    "repo_head": event.get("repo_head"),
                    "base_sha": pack.get("base_sha"),
                    "plan_sha": event.get("context_plan_sha"),
                    "manifest_sha": event.get("manifest_sha"),
                    "allowed_write_root": pack.get("allowed_write_root"),
                    "pack_sha": dispatch_event.get("payload_sha"),
                    "episode_id": event.get("episode_id"),
                    "branch": lease.get("branch"),
                    "repo_root": str(self.repo_root),
                },
            )
            if not lease_check["valid"]:
                semantic_gaps.extend(
                    f"{event.get('run_id')}:lease:{error}"
                    for error in lease_check["errors"]
                )
        for event, released in releases:
            active_pair = next(
                (
                    (active_event, active)
                    for active_event, active in leases
                    if active_event.get("run_id") == event.get("run_id")
                    and active_event.get("session_id") == event.get("session_id")
                    and active_event.get("branch") == event.get("branch")
                    and int(active_event.get("seq") or 0)
                    < int(event.get("seq") or 0)
                ),
                None,
            )
            if active_pair is None or any(
                active_pair[1].get(field) != released.get(field)
                for field in (
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
            ):
                semantic_gaps.append(
                    f"{event.get('run_id')}:invalid_lease_release_transition"
                )
        for commit_sha, name, event, _, value in observed_events:
            if event.get("kind") != "acp.complete" or not isinstance(value, Mapping):
                continue
            joined_dispatch = any(
                candidate.get("task") == event.get("task")
                and candidate.get("manifest_sha") == event.get("manifest_sha")
                and candidate.get("context_plan_sha")
                == event.get("context_plan_sha")
                for candidate, _ in dispatches
            )
            joined_lease = any(
                candidate.get("run_id") == event.get("run_id")
                and candidate.get("session_id") == event.get("session_id")
                and candidate.get("task") == event.get("task")
                and candidate.get("manifest_sha") == event.get("manifest_sha")
                and candidate.get("context_plan_sha")
                == event.get("context_plan_sha")
                for candidate, _ in leases
            )
            joined_release = any(
                candidate.get("run_id") == event.get("run_id")
                and candidate.get("session_id") == event.get("session_id")
                and candidate.get("task") == event.get("task")
                for candidate, _ in releases
            )
            if not joined_dispatch:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_dispatch")
            if not joined_lease:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_lease")
            if not joined_release:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_lease_release")
        valid = fsck["valid"] and (
            not strict or (not join_gaps and not semantic_gaps)
        )
        current_errors: list[Any] = []
        current_manifest: dict[str, Any] | None = None
        current_plan: dict[str, Any] | None = None
        if strict:
            for _, candidate_commit in reversed(self.walk_commits(sha)):
                candidate_manifest_sha = candidate_commit.get("manifest_sha")
                candidate_plan_sha = candidate_commit.get("context_plan_sha")
                if candidate_manifest_sha and current_manifest is None:
                    try:
                        _, current_manifest = self.find_blob(
                            schema="ndf-task-manifest/v1",
                            semantic_field="manifest_sha",
                            semantic_sha=str(candidate_manifest_sha),
                        )
                    except ValueError:
                        pass
                if candidate_plan_sha and current_plan is None:
                    try:
                        _, current_plan = self.find_blob(
                            schema=None,
                            schema_prefix="ndf-context-plan",
                            semantic_field="plan_sha",
                            semantic_sha=str(candidate_plan_sha),
                        )
                    except ValueError:
                        pass
                if current_manifest is not None and current_plan is not None:
                    break
            if current_manifest is None:
                current_errors.append({"kind": "current_manifest_unavailable"})
            else:
                current_errors.extend(
                    ndf_context.verify_manifest_current(
                        current_manifest,
                        root=self.repo_root,
                    )["errors"]
                )
            if current_plan is None:
                current_errors.append({"kind": "current_plan_unavailable"})
            elif current_manifest is not None:
                current_errors.extend(
                    ndf_context.verify_plan(
                        current_plan,
                        root=self.repo_root,
                        manifest=current_manifest,
                        require_manifest=True,
                    )["errors"]
                )
        return {
            "schema": "ndf-replay-audit/v1",
            "level": "R0",
            "valid": valid,
            "historical_integrity": fsck["valid"],
            "historical_semantics": not join_gaps and not semantic_gaps,
            "current_restore_ready": not current_errors if strict else None,
            "current_dispatch_ready": not current_errors if strict else None,
            "current_readiness_errors": current_errors,
            "commit_sha": sha,
            "commit": commit,
            "coverage_gaps": sorted(set(coverage_gaps)),
            "join_gaps": sorted(set(join_gaps)),
            "semantic_gaps": sorted(set(semantic_gaps)),
            "fsck": fsck,
        }

    def reconstruct(self, commit_or_ref: str, level: str = "R1") -> dict[str, Any]:
        if level not in {"R0", "R1"}:
            raise ValueError("reconstruct supports R0 or R1")
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        recorded: list[dict[str, Any]] = []
        by_object: dict[str, dict[str, Any]] = {}
        commit_dag: list[dict[str, Any]] = []

        def visit_tree(
            tree_sha: str,
            *,
            commit_sha: str,
            parents: list[str],
            prefix: str = "",
            seen_trees: set[str] | None = None,
        ) -> None:
            local_seen = seen_trees if seen_trees is not None else set()
            if tree_sha in local_seen:
                return
            local_seen.add(tree_sha)
            entries = self.get_object(tree_sha, "tree")["data"]["entries"]
            for name, object_sha in sorted(entries.items()):
                obj = self.get_object(object_sha)
                qualified = f"{prefix}/{name}".strip("/")
                provenance = {
                    "commit_sha": commit_sha,
                    "parents": list(parents),
                    "path": qualified,
                }
                if object_sha not in by_object:
                    item = {
                        "name": qualified,
                        "sha": object_sha,
                        "object": obj,
                        "provenance": [provenance],
                    }
                    by_object[object_sha] = item
                    recorded.append(item)
                else:
                    by_object[object_sha]["provenance"].append(provenance)
                if obj.get("type") == "tree":
                    visit_tree(
                        object_sha,
                        commit_sha=commit_sha,
                        parents=parents,
                        prefix=qualified,
                        seen_trees=local_seen,
                    )

        for historical_sha, historical in self.walk_commits(sha):
            parents = [str(parent) for parent in historical.get("parents", [])]
            commit_dag.append(
                {
                    "commit_sha": historical_sha,
                    "parents": parents,
                    "tree": historical.get("tree"),
                    "actor": historical.get("actor"),
                    "task": historical.get("task"),
                    "manifest_sha": historical.get("manifest_sha"),
                    "context_plan_sha": historical.get("context_plan_sha"),
                }
            )
            visit_tree(
                str(historical["tree"]),
                commit_sha=historical_sha,
                parents=parents,
            )
        observations: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        observation_gaps: list[str] = []
        seen_observations: set[str] = set()
        seen_event_shas: set[str] = set()
        for item in recorded:
            obj = item["object"]
            data = obj.get("data", {})
            if obj.get("type") == "tool-cassette":
                if item["sha"] in seen_observations:
                    continue
                seen_observations.add(item["sha"])
                observations.append(
                    {
                        "kind": "tool",
                        "sha": item["sha"],
                        "cassette": data,
                        "stdout": self.get_object(data["stdout_blob"], "blob")[
                            "data"
                        ].get("value"),
                        "stderr": self.get_object(data["stderr_blob"], "blob")[
                            "data"
                        ].get("value"),
                    }
                )
                if data.get("replay_policy") not in {
                    "recorded-only",
                    "sandbox",
                    "live-readonly",
                }:
                    observation_gaps.append(
                        f"{item['sha']}:invalid_tool_replay_policy"
                    )
                if (
                    data.get("replay_policy") == "live-readonly"
                    and not data.get("external_resource_version")
                ):
                    observation_gaps.append(
                        f"{item['sha']}:unversioned_live_observation"
                    )
            elif obj.get("type") == "model-turn":
                if item["sha"] in seen_observations:
                    continue
                seen_observations.add(item["sha"])
                observations.append(
                    {
                        "kind": "model",
                        "sha": item["sha"],
                        "turn": data,
                        "user_message": self.get_object(
                            data["user_message_blob"], "blob"
                        )["data"].get("value"),
                        "assistant_response": self.get_object(
                            data["assistant_response_blob"], "blob"
                        )["data"].get("value"),
                    }
                )
                if not data.get("visible_system_surface_sha"):
                    observation_gaps.append(
                        f"{item['sha']}:missing_visible_prompt_surface"
                    )
            elif (
                obj.get("type") == "blob"
                and isinstance(data.get("value"), dict)
                and data["value"].get("schema") == "ndf-replay-event/v1"
            ):
                event = data["value"]
                event_sha = str(event.get("event_sha") or "")
                if event_sha and event_sha not in seen_event_shas:
                    seen_event_shas.add(event_sha)
                    timeline.append(event)
        return {
            "schema": "ndf-replay-reconstruction/v1",
            "level": level,
            "commit_sha": sha,
            "side_effects": False,
            "recorded_objects": recorded,
            "commit_dag": commit_dag,
            "merge_parents": [
                item for item in commit_dag if len(item.get("parents", [])) > 1
            ],
            "timeline": sorted(
                timeline,
                key=lambda item: (
                    str(item.get("branch") or ""),
                    int(item.get("seq") or 0),
                    str(item.get("event_sha") or ""),
                ),
            ),
            "observations": observations,
            "observation_replay_valid": (
                not observation_gaps
                and (level == "R0" or bool(observations))
            ),
            "observation_gaps": (
                observation_gaps
                if observations
                else (["recorded_observation_surface_missing"] if level == "R1" else [])
            ),
            "coverage": commit.get("coverage", {}),
        }

    def sandbox_replay(
        self,
        commit_or_ref: str,
        profile: Mapping[str, Any],
        *,
        execute: bool = False,
    ) -> dict[str, Any]:
        """Validate or execute an R2 profile in a disposable git worktree."""
        if not profile.get("sandbox") or profile.get("network") not in {False, "none"}:
            raise ValueError("R2 requires sandbox=true and network=false|none")
        commands = profile.get("commands", [])
        if not isinstance(commands, list) or not all(
            isinstance(command, list)
            and command
            and all(isinstance(part, str) for part in command)
            for command in commands
        ):
            raise ValueError("R2 profile commands must be non-empty argv arrays")
        adapter = profile.get("adapter", [])
        if not isinstance(adapter, list) or not all(isinstance(part, str) for part in adapter):
            raise ValueError("R2 profile adapter must be an argv array")
        if execute and not adapter:
            raise ValueError("R2 execution with network disabled requires an isolation adapter")
        if execute:
            if not profile.get("confirm_cost") or not profile.get(
                "confirm_side_effects"
            ):
                raise ValueError("R2 execution requires explicit cost and side-effect confirmation")
            adapter_name = Path(adapter[0]).name
            if len(adapter) != 1 or adapter_name not in {
                "bwrap",
                "bubblewrap",
                "vm",
            }:
                raise ValueError(
                    "R2 execution requires managed adapter bwrap|bubblewrap|vm"
                )
            if adapter_name == "vm":
                probe = probe_vm_hypervisor()
                if not probe.get("available"):
                    raise ValueError(
                        "R2 vm adapter unavailable: "
                        f"{probe.get('blocker') or 'no_kvm_or_hypervisor'}"
                    )
            elif not (
                Path(adapter[0]).is_file()
                or shutil.which(adapter[0])
            ):
                raise ValueError("R2 isolation adapter is unavailable")
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        audit = self.audit(sha, strict=execute)
        if execute and not audit["valid"]:
            raise ValueError(
                f"R2 requires a strict verified episode: "
                f"{audit['join_gaps'] + audit.get('semantic_gaps', [])}"
            )
        if execute and audit.get("current_restore_ready") is not True:
            raise ValueError(
                "R2 current restore is not ready: "
                f"{audit.get('current_readiness_errors', [])}"
            )
        commit = self.get_object(sha, "commit")["data"]
        repo_head = commit.get("repo_head")
        if not repo_head:
            raise ValueError("R2 commit has no bound repo_head")
        target = profile.get("target")
        manifest_sha: str | None = None
        plan_sha: str | None = None
        run_id: str | None = None
        role: str | None = None
        manifest: dict[str, Any] | None = None
        plan: dict[str, Any] | None = None
        if execute or target is not None:
            if not isinstance(target, Mapping):
                raise ValueError("R2 profile requires exact target binding")
            required_target = (
                "run_id",
                "role",
                "manifest_sha",
                "plan_sha",
                "env_allowlist_fingerprint",
                "cwd",
                "tool_runtime_version",
            )
            missing_target = [
                field for field in required_target if not target.get(field)
            ]
            if missing_target:
                raise ValueError(f"R2 target missing fields: {missing_target}")
            run_id = str(target["run_id"])
            role = str(target["role"])
            manifest_sha = str(target["manifest_sha"])
            plan_sha = str(target["plan_sha"])
            _, manifest = self.find_blob(
                schema="ndf-task-manifest/v1",
                semantic_field="manifest_sha",
                semantic_sha=manifest_sha,
            )
            _, plan = self.find_blob(
                schema=None,
                schema_prefix="ndf-context-plan",
                semantic_field="plan_sha",
                semantic_sha=plan_sha,
            )
            if plan.get("role") != role:
                raise ValueError("R2 target role does not match recorded plan")
            if plan.get("manifest_sha") != manifest_sha:
                raise ValueError("R2 target manifest does not match recorded plan")
        result: dict[str, Any] = {
            "schema": "ndf-replay-sandbox/v1",
            "level": "R2",
            "commit_sha": sha,
            "repo_head": repo_head,
            "audit": audit,
            "profile_sha": canonical_json_sha(profile),
            "profile": _json_copy(profile),
            "executed": False,
            "state": "validated_profile",
            "commands": [],
            "changed_paths": [],
            "output_checks": [],
        }
        if not execute:
            return result
        adapter_name = Path(adapter[0]).name
        if adapter_name == "vm":
            guest = self.guest_run(
                sha,
                episode_id=str(
                    (target or {}).get("run_id")
                    or profile.get("episode_id")
                    or f"r2-{sha[:12]}"
                ),
                level="R0",
                adapter="vm",
                image=str(profile.get("image") or "") or None,
            )
            result.update(
                {
                    "executed": False,
                    "state": guest.get("state") or "environment_blocked",
                    "environment_blocker": guest.get("environment_blocker"),
                    "guest_proof": guest,
                    "adapter": "vm",
                }
            )
            return result
        adapter_probe = subprocess.run(
            [
                adapter[0],
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/",
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--",
                "/bin/true",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        result["adapter_probe"] = {
            "exit_code": adapter_probe.returncode,
            "stdout_sha": canonical_json_sha(adapter_probe.stdout),
            "stderr_sha": canonical_json_sha(adapter_probe.stderr),
        }
        if adapter_probe.returncode != 0:
            result["state"] = "environment_blocked"
            result["environment_blocker"] = adapter_probe.stderr.strip()
            return result
        if not commands:
            raise ValueError("R2 execution requires at least one recorded command")
        expected_outputs = profile.get("expected_outputs", [])
        if not isinstance(expected_outputs, list) or not expected_outputs:
            raise ValueError("R2 equivalence requires at least one expected output")
        assert target is not None
        assert run_id is not None
        assert manifest_sha is not None
        assert plan_sha is not None
        assert manifest is not None
        assert plan is not None
        allowed_roots = [
            str(value).strip("/")
            for value in profile.get("allowed_write_roots", [])
            if str(value).strip("/")
        ]
        planned_roots = [
            str(value).strip("/")
            for value in plan.get("privileges", {}).get("allowed_write_roots", [])
            if str(value).strip("/")
        ]
        if any(
            not any(
                root == planned or root.startswith(f"{planned}/")
                for planned in planned_roots
            )
            for root in allowed_roots
        ):
            raise ValueError("R2 write roots exceed recorded context privileges")
        reconstruction = self.reconstruct(sha, "R1")
        recorded_completions = [
            item["object"]["data"]["value"]
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(item.get("object", {}).get("data", {}).get("value"), dict)
            and item["object"]["data"]["value"].get("schema")
            == "ndf-agent-completion/v1"
        ]
        exact_expectations = {
            str(expected.get("path") or ""): str(expected.get("sha256") or "")
            for expected in expected_outputs
            if expected.get("comparison") != "epsilon"
        }
        matching_completions = [
            completion
            for completion in recorded_completions
            if str(completion.get("run_id") or "") == run_id
            and completion.get("manifest_sha") == manifest_sha
            and completion.get("context_plan_sha") == plan_sha
            and {
                str(path): str(file_sha)
                for path, file_sha in completion.get(
                    "changed_file_shas", {}
                ).items()
            }
            == exact_expectations
        ]
        matching_run_ids = {
            str(completion.get("run_id"))
            for completion in matching_completions
            if completion.get("run_id")
        }
        if matching_run_ids != {run_id}:
            raise ValueError(
                "R2 expected outputs are not the complete output set of one "
                "recorded completion"
            )
        recorded_expectations = [
            (str(value.get("run_id") or ""), expectation)
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(
                item.get("object", {}).get("data", {}).get("value"), dict
            )
            and (
                value := item["object"]["data"]["value"]
            ).get("schema")
            == "ndf-replay-r2-expectations/v1"
            for expectation in value.get("outputs", [])
        ]
        for expected in expected_outputs:
            relative = str(expected.get("path") or "")
            if expected.get("comparison") == "epsilon":
                if not any(
                    run_id in matching_run_ids and expectation == expected
                    for run_id, expectation in recorded_expectations
                ):
                    raise ValueError(
                        f"R2 epsilon expectation is not recorded evidence: {relative}"
                    )
        recorded_leases = [
            value
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(
                item.get("object", {}).get("data", {}).get("value"), dict
            )
            and (
                value := item["object"]["data"]["value"]
            ).get("schema")
            == "ndf-runtime-lease/v1"
            and str(value.get("run_id") or "") in matching_run_ids
        ]
        if not recorded_leases:
            raise ValueError("R2 completion has no joined recorded runtime lease")
        for root in allowed_roots:
            if not any(
                root == str(lease.get("allowed_write_root") or "").strip("/")
                or root.startswith(
                    f"{str(lease.get('allowed_write_root') or '').strip('/')}/"
                )
                for lease in recorded_leases
            ):
                raise ValueError("R2 write roots exceed recorded runtime lease")
        if any(
            not any(
                path == root or path.startswith(f"{root}/")
                for root in allowed_roots
            )
            for path in exact_expectations
        ):
            raise ValueError(
                "R2 recorded changed outputs are outside the replay write roots"
            )
        recorded_commands = {
            tuple(item["cassette"].get("argv", []))
            for item in reconstruction.get("observations", [])
            if item.get("kind") == "tool"
            and item.get("cassette", {}).get("replay_policy") == "sandbox"
            and item.get("cassette", {}).get("manifest_sha") == manifest_sha
            and item.get("cassette", {}).get("plan_sha") == plan_sha
            and item.get("cassette", {}).get("repo_head") == repo_head
            and str(item.get("cassette", {}).get("run_id")) in matching_run_ids
            and item.get("cassette", {}).get("env_allowlist_fingerprint")
            == target.get("env_allowlist_fingerprint")
            and item.get("cassette", {}).get("cwd") == target.get("cwd")
            and item.get("cassette", {}).get("external_resource_version")
            == target.get("tool_runtime_version")
        }
        unrecorded = [argv for argv in commands if tuple(argv) not in recorded_commands]
        if unrecorded:
            raise ValueError(f"R2 commands lack sandbox replay cassettes: {unrecorded}")
        sandbox_root = self.repo_root / "tmp" / "ndf-replay-sandboxes"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        worktree = sandbox_root / f"r2-{uuid.uuid4()}"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), str(repo_head)],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            import ndf_context

            context_check = ndf_context.verify_plan(
                plan,
                root=worktree,
                manifest=manifest,
                require_manifest=True,
            )
            if not context_check["valid"]:
                raise ValueError(
                    f"R2 context/gate drift: {context_check['errors']}"
                )
            result["context_verification"] = context_check
            managed_adapter = [
                adapter[0],
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/",
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--chdir",
                str(worktree),
            ]
            for relative in allowed_roots:
                if relative.startswith("/") or ".." in Path(relative).parts:
                    raise ValueError(f"R2 write root escapes sandbox: {relative}")
                writable = worktree / relative
                writable.mkdir(parents=True, exist_ok=True)
                managed_adapter.extend(["--bind", str(writable), str(writable)])
            managed_adapter.append("--")
            command_results = []
            for argv in commands:
                proc = subprocess.run(
                    [*managed_adapter, *argv],
                    cwd=worktree,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=int(profile.get("timeout_seconds", 600)),
                    check=False,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "HOME": "/tmp",
                        "NDF_REPLAY_LEVEL": "R2",
                    },
                )
                command_results.append(
                    {
                        "argv": argv,
                        "exit_code": proc.returncode,
                        "stdout_sha": canonical_json_sha(proc.stdout),
                        "stderr_sha": canonical_json_sha(proc.stderr),
                    }
                )
                if proc.returncode != 0:
                    result["state"] = "command_failed"
                    result["commands"] = command_results
                    return result
            changed = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=worktree,
                text=True,
            ).splitlines()
            changed_paths = [line[3:].strip() for line in changed if len(line) > 3]
            violations = [
                path
                for path in changed_paths
                if not any(path == root or path.startswith(f"{root}/") for root in allowed_roots)
            ]
            checks = []
            for expected in expected_outputs:
                relative = str(expected["path"])
                if relative.startswith("/") or ".." in Path(relative).parts:
                    raise ValueError(f"R2 expected output escapes sandbox: {relative}")
                output = worktree / relative
                if expected.get("comparison") == "epsilon":
                    if not output.is_file():
                        actual_metric = None
                    else:
                        observed = json.loads(output.read_text(encoding="utf-8"))
                        actual_metric = observed.get(str(expected.get("metric")))
                    target = expected.get("expected")
                    epsilon = expected.get("epsilon")
                    matches = bool(
                        isinstance(actual_metric, (int, float))
                        and isinstance(target, (int, float))
                        and isinstance(epsilon, (int, float))
                        and abs(float(actual_metric) - float(target))
                        <= float(epsilon)
                    )
                    checks.append(
                        {
                            "path": relative,
                            "comparison": "epsilon",
                            "metric": expected.get("metric"),
                            "expected": target,
                            "actual": actual_metric,
                            "epsilon": epsilon,
                            "matches": matches,
                        }
                    )
                else:
                    actual = (
                        hashlib.sha256(output.read_bytes()).hexdigest()
                        if output.is_file()
                        else None
                    )
                    checks.append(
                        {
                            "path": relative,
                            "comparison": "sha256",
                            "expected_sha256": expected.get("sha256"),
                            "actual_sha256": actual,
                            "matches": actual == expected.get("sha256"),
                        }
                    )
            result.update(
                {
                    "executed": True,
                    "state": (
                        "equivalent"
                        if checks
                        and not violations
                        and all(item["matches"] for item in checks)
                        else "different"
                    ),
                    "commands": command_results,
                    "changed_paths": changed_paths,
                    "write_violations": violations,
                    "output_checks": checks,
                }
            )
            return result
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=self.repo_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            shutil.rmtree(worktree, ignore_errors=True)

    def isolate_observe(
        self,
        commit_or_ref: str,
        *,
        episode_id: str,
        keep_worktree: bool = False,
        write_proof: Path | None = None,
    ) -> dict[str, Any]:
        """Rebuild a hop in a disposable worktree and prove the live checkout was not used.

        This is git-worktree isolation, not bwrap. R2 ``sandbox --execute`` is a
        separate, cassette-gated path. Composer cwd is never this worktree.
        """
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        recorded_head = str(commit.get("repo_head") or "").strip() or None
        live_toplevel = self._git_toplevel(self.repo_root)
        live_head_before = self._git_head(self.repo_root)
        target_head = recorded_head or live_head_before
        porcelain_before = self._live_porcelain()
        sandbox_root = self.repo_root / "tmp" / "ndf-replay-sandboxes"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        worktree = sandbox_root / f"observe-{uuid.uuid4()}"
        added = False
        try:
            try:
                subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree), target_head],
                    cwd=self.repo_root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise ValueError(
                    "isolate worktree failed: "
                    + ((exc.stderr or exc.stdout or "").strip() or str(exc))
                ) from exc
            added = True
            sandbox_toplevel = self._git_toplevel(worktree)
            sandbox_head = self._git_head(worktree)
            marker = worktree / "NDF_ISOLATE_PROOF"
            marker.write_text(
                json.dumps(
                    {
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "sandbox_toplevel": sandbox_toplevel,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            reconstruction = self.reconstruct(sha, "R0")
            live_head_after = self._git_head(self.repo_root)
            porcelain_after = self._live_porcelain()
            live_marker = self.repo_root / "NDF_ISOLATE_PROOF"
            same_checkout = Path(sandbox_toplevel).resolve() == Path(live_toplevel).resolve()
            isolation = {
                "kind": "disposable_git_worktree",
                "bwrap_used": False,
                "live_toplevel": live_toplevel,
                "sandbox_toplevel": sandbox_toplevel,
                "same_checkout": same_checkout,
                "sandbox_head": sandbox_head,
                "recorded_repo_head": recorded_head,
                "used_fallback_head": recorded_head is None,
                "head_matches_record": (
                    sandbox_head == recorded_head if recorded_head else None
                ),
                "live_head_before": live_head_before,
                "live_head_after": live_head_after,
                "live_head_unchanged": live_head_after == live_head_before,
                "live_porcelain_before": porcelain_before,
                "live_porcelain_after": porcelain_after,
                "live_tracked_unchanged": porcelain_after == porcelain_before,
                "sandbox_marker": "NDF_ISOLATE_PROOF",
                "sandbox_marker_absent_from_live_root": not live_marker.exists(),
            }
            valid = (
                not same_checkout
                and isolation["live_head_unchanged"]
                and isolation["live_tracked_unchanged"]
                and isolation["sandbox_marker_absent_from_live_root"]
                and reconstruction.get("side_effects") is False
            )
            result = {
                "schema": "ndf-replay-isolate-proof/v1",
                "valid": valid,
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": isolation,
                "reconstruct": {
                    "level": reconstruction.get("level"),
                    "side_effects": reconstruction.get("side_effects"),
                    "commit_sha": reconstruction.get("commit_sha"),
                    "timeline_events": len(reconstruction.get("timeline") or []),
                },
                "execute": {
                    "attempted": False,
                    "reason": "isolate_is_observe_only",
                },
            }
            proof_path = write_proof or (
                sandbox_root / f"proof-{episode_id}.json"
            )
            proof_path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(
                proof_path,
                canonical_json_bytes(result) + b"\n",
            )
            result["proof_path"] = proof_path.as_posix()
            return result
        finally:
            if added and not keep_worktree:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=self.repo_root,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                shutil.rmtree(worktree, ignore_errors=True)

    def _git_toplevel(self, cwd: Path) -> str:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            text=True,
        ).strip()

    def _git_head(self, cwd: Path) -> str:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
        ).strip()

    def _live_porcelain(self) -> list[str]:
        lines = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=self.repo_root,
            text=True,
        ).splitlines()
        ignored = ("tmp", ".ndf")
        kept: list[str] = []
        for line in lines:
            path = line[3:].strip() if len(line) > 3 else ""
            if any(path == prefix or path.startswith(f"{prefix}/") for prefix in ignored):
                continue
            kept.append(line)
        return kept

    def _reconstruct_copied_store(
        self,
        guest_root: Path,
        sha: str,
        level: str,
        *,
        store_root: Path | None = None,
    ) -> dict[str, Any]:
        """Reconstruct from a copied store using the host encryption key."""
        guest_store = ReplayStore(
            guest_root,
            store_root or (guest_root / ".ndf" / "replay"),
        )
        host_key = str(self._key_path())
        previous = os.environ.get("NDF_REPLAY_KEY_FILE")
        os.environ["NDF_REPLAY_KEY_FILE"] = host_key
        try:
            return guest_store.reconstruct(sha, level)
        finally:
            if previous is None:
                os.environ.pop("NDF_REPLAY_KEY_FILE", None)
            else:
                os.environ["NDF_REPLAY_KEY_FILE"] = previous

    def guest_run(
        self,
        commit_or_ref: str,
        *,
        episode_id: str,
        level: str = "R0",
        adapter: str | None = None,
        image: str | None = None,
        keep_guest: bool = False,
        write_proof: Path | None = None,
        host_mount: str | None = None,
        cube_client: Any | None = None,
        cube_api_url: str | None = None,
        cube_template_id: str | None = None,
    ) -> dict[str, Any]:
        """Host launcher: snapshot + guest executor; never run replay body in live cwd.

        Production adapters:
        - ``vm`` — local KVM + qemu/firecracker image (fail closed if missing)
        - ``cube`` — CubeSandbox / E2B API (Lvm); proof still uses adapter=vm +
          hypervisor_backend=cube. host-mount of the live checkout is forbidden.
        ``fake-vm`` is tests-only.
        """
        if level not in {"R0", "R1"}:
            raise ValueError("guest-run supports R0 or R1 observe levels")
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        recorded_head = str(commit.get("repo_head") or "").strip() or None
        live_toplevel = self._git_toplevel(self.repo_root)
        live_head_before = self._git_head(self.repo_root)
        target_head = recorded_head or live_head_before
        porcelain_before = self._live_porcelain()
        guest_id = str(uuid.uuid4())
        staging = self.repo_root / "tmp" / "ndf-replay-guests" / guest_id
        staging.mkdir(parents=True, exist_ok=True)
        guest_root = staging / "root"
        proof_path = write_proof or (
            self.repo_root / "tmp" / "ndf-replay-guests" / f"proof-{episode_id}.json"
        )
        chosen = (adapter or "vm").strip().lower()
        probe = probe_vm_hypervisor()
        cube_probe = probe_cube_api(api_url=cube_api_url)
        if cube_template_id:
            cube_probe = {**cube_probe, "template_id": cube_template_id}
        image_sha = (
            hashlib.sha256(Path(image).read_bytes()).hexdigest()
            if image and Path(image).is_file()
            else hashlib.sha256(
                f"snapshot:{target_head}:{guest_id}".encode("utf-8")
            ).hexdigest()
        )

        def _blocked(
            reason: str,
            *,
            proof_adapter: str | None = None,
            extra_isolation: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            isolation: dict[str, Any] = {
                "adapter": proof_adapter or chosen,
                "kind": "guest_vm",
                "guest_id": guest_id,
                "image_sha": image_sha,
                "recorded_repo_head": recorded_head,
                "guest_toplevel": None,
                "host_toplevel": live_toplevel,
                "same_checkout": None,
                "host_tracked_unchanged": True,
                "host_head_unchanged": True,
                "sandbox_marker_absent_from_live_root": True,
                "bwrap_used": False,
                "host_mount_used": bool(host_mount),
                "hypervisor": probe,
                "cube": cube_probe,
            }
            if extra_isolation:
                isolation.update(dict(extra_isolation))
            result = {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "environment_blocked",
                "environment_blocker": reason,
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": isolation,
                "reconstruct": None,
                "execute": {"attempted": False, "level": level},
            }
            result["proof_errors"] = validate_guest_proof(result)
            self._atomic_write(proof_path, canonical_json_bytes(result) + b"\n")
            result["proof_path"] = proof_path.as_posix()
            return result

        mount_blocker = assert_no_live_host_mount(host_mount, live_toplevel)
        if mount_blocker:
            return _blocked(
                mount_blocker,
                proof_adapter="vm" if chosen == "cube" else chosen,
                extra_isolation={"hypervisor_backend": "cube" if chosen == "cube" else None},
            )

        if chosen == "vm":
            if not probe.get("available"):
                return _blocked(str(probe.get("blocker") or "no_kvm_or_hypervisor"))
            resolved = resolve_vm_image(image, self.repo_root)
            if resolved is None:
                return _blocked("vm_adapter_requires_guest_image")
            return self._guest_run_vm(
                sha=sha,
                episode_id=episode_id,
                level=level,
                target_head=target_head,
                recorded_head=recorded_head,
                live_toplevel=live_toplevel,
                live_head_before=live_head_before,
                porcelain_before=porcelain_before,
                proof_path=proof_path,
                probe=probe,
                guest_id=guest_id,
                staging=staging,
                guest_root=guest_root,
                resolved=resolved,
                keep_guest=keep_guest,
                image_sha=hashlib.sha256(
                    resolved["kernel"].read_bytes() + resolved["rootfs"].read_bytes()
                ).hexdigest(),
            )

        if chosen == "cube":
            return self._guest_run_cube(
                sha=sha,
                episode_id=episode_id,
                level=level,
                target_head=target_head,
                recorded_head=recorded_head,
                live_toplevel=live_toplevel,
                live_head_before=live_head_before,
                porcelain_before=porcelain_before,
                proof_path=proof_path,
                cube_probe=cube_probe,
                probe=probe,
                cube_client=cube_client,
                keep_guest=keep_guest,
                host_mount=host_mount,
            )

        if chosen != "fake-vm":
            return _blocked(f"unsupported_guest_adapter:{chosen}")

        # Tests-only fake guest: separate tree, not the live checkout.
        try:
            self._materialize_guest_snapshot(guest_root, target_head)
            guest_store_src = self.root
            guest_store_dst = guest_root / ".ndf" / "replay"
            if guest_store_src.is_dir():
                shutil.copytree(
                    guest_store_src,
                    guest_store_dst,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.lock", ".*.tmp"),
                )
            marker = guest_root / "NDF_GUEST_MARKER"
            marker.write_text(
                json.dumps(
                    {
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "guest_id": guest_id,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            reconstruction = self._reconstruct_copied_store(
                guest_root,
                sha,
                level,
                store_root=guest_store_dst,
            )
            live_head_after = self._git_head(self.repo_root)
            porcelain_after = self._live_porcelain()
            live_marker = self.repo_root / "NDF_GUEST_MARKER"
            guest_toplevel = str(guest_root.resolve())
            same_checkout = Path(guest_toplevel).resolve() == Path(live_toplevel).resolve()
            isolation = {
                "adapter": "fake-vm",
                "kind": "guest_vm",
                "guest_id": guest_id,
                "image_sha": image_sha,
                "recorded_repo_head": recorded_head,
                "guest_toplevel": guest_toplevel,
                "host_toplevel": live_toplevel,
                "same_checkout": same_checkout,
                "host_tracked_unchanged": porcelain_after == porcelain_before,
                "host_head_unchanged": live_head_after == live_head_before,
                "live_head_before": live_head_before,
                "live_head_after": live_head_after,
                "sandbox_marker_absent_from_live_root": not live_marker.exists(),
                "bwrap_used": False,
                "host_mount_used": False,
                "hypervisor": probe,
                "used_fallback_head": recorded_head is None,
            }
            result = {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "guest_observe",
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": isolation,
                "reconstruct": {
                    "level": reconstruction.get("level"),
                    "side_effects": reconstruction.get("side_effects"),
                    "commit_sha": reconstruction.get("commit_sha"),
                    "timeline_events": len(reconstruction.get("timeline") or []),
                },
                "execute": {
                    "attempted": False,
                    "level": level,
                    "reason": "guest_observe_only",
                },
            }
            errors = validate_guest_proof(result)
            result["proof_errors"] = errors
            result["valid"] = not errors
            if not result["valid"]:
                result["state"] = "proof_invalid"
            self._atomic_write(proof_path, canonical_json_bytes(result) + b"\n")
            result["proof_path"] = proof_path.as_posix()
            return result
        finally:
            if not keep_guest:
                shutil.rmtree(staging, ignore_errors=True)

    def _guest_run_vm(
        self,
        *,
        sha: str,
        episode_id: str,
        level: str,
        target_head: str,
        recorded_head: str | None,
        live_toplevel: str,
        live_head_before: str,
        porcelain_before: list[str],
        proof_path: Path,
        probe: Mapping[str, Any],
        guest_id: str,
        staging: Path,
        guest_root: Path,
        resolved: Mapping[str, Path],
        keep_guest: bool,
        image_sha: str,
    ) -> dict[str, Any]:
        qemu = probe.get("qemu") or shutil.which("qemu-system-x86_64")
        if not qemu:
            return {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "environment_blocked",
                "environment_blocker": "no_qemu_or_firecracker",
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": {
                    "adapter": "vm",
                    "kind": "guest_vm",
                    "hypervisor_backend": "qemu",
                    "guest_id": guest_id,
                    "image_sha": image_sha,
                    "recorded_repo_head": recorded_head,
                    "guest_toplevel": None,
                    "host_toplevel": live_toplevel,
                    "same_checkout": None,
                    "host_tracked_unchanged": True,
                    "host_head_unchanged": True,
                    "sandbox_marker_absent_from_live_root": True,
                    "bwrap_used": False,
                    "host_mount_used": False,
                    "hypervisor": dict(probe),
                },
                "reconstruct": None,
                "execute": {"attempted": False, "level": level},
            }

        def _finish(result: dict[str, Any]) -> dict[str, Any]:
            result["proof_errors"] = validate_guest_proof(result)
            if result.get("state") != "environment_blocked":
                result["valid"] = not result["proof_errors"]
                if not result["valid"] and result.get("state") != "environment_blocked":
                    result["state"] = "proof_invalid"
            else:
                result["valid"] = False
            self._atomic_write(proof_path, canonical_json_bytes(result) + b"\n")
            result["proof_path"] = proof_path.as_posix()
            return result

        overlay = staging / "rootfs.qcow2"
        serial_proof = staging / "guest-serial.json"
        console_log = staging / "console.log"
        try:
            self._materialize_guest_snapshot(guest_root, target_head)
            guest_store_src = self.root
            guest_store_dst = guest_root / ".ndf" / "replay"
            if guest_store_src.is_dir():
                shutil.copytree(
                    guest_store_src,
                    guest_store_dst,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.lock", ".*.tmp"),
                )
            key_src = self._key_path()
            if key_src.is_file():
                key_dst = guest_root / ".ndf" / "replay-key"
                key_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(key_src, key_dst)
            subprocess.run(
                [
                    "qemu-img",
                    "create",
                    "-f",
                    "qcow2",
                    "-b",
                    str(resolved["rootfs"]),
                    "-F",
                    "raw",
                    str(overlay),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            serial_proof.write_text("", encoding="utf-8")
            append = (
                "root=/dev/vda rootfstype=ext4 rw console=ttyS0 "
                f"init=/ndf-replay-init ndf.commit={sha} ndf.level={level} "
                f"ndf.episode={episode_id}"
            )
            cmd = [
                str(qemu),
                "-enable-kvm",
                "-cpu",
                "host",
                "-m",
                "1024",
                "-smp",
                "2",
                "-machine",
                "q35,accel=kvm",
                "-display",
                "none",
                "-no-reboot",
                "-nic",
                "none",
                "-kernel",
                str(resolved["kernel"]),
                "-append",
                append,
            ]
            if resolved.get("initrd"):
                cmd.extend(["-initrd", str(resolved["initrd"])])
            cmd.extend([
                "-drive",
                f"file={overlay},format=qcow2,if=virtio",
                "-fsdev",
                f"local,id=ndfguest,path={guest_root},security_model=mapped-xattr,readonly=on",
                "-device",
                "virtio-9p-pci,fsdev=ndfguest,mount_tag=ndfguest",
                "-device",
                "virtio-serial-pci",
                "-chardev",
                f"file,id=proof,path={serial_proof}",
                "-device",
                "virtserialport,chardev=proof,name=org.ndf.proof",
                "-serial",
                f"file:{console_log}",
            ])
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=staging,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return _finish(
                    {
                        "schema": "ndf-replay-guest-proof/v1",
                        "valid": False,
                        "state": "environment_blocked",
                        "environment_blocker": "qemu_timeout",
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "isolation": {
                            "adapter": "vm",
                            "kind": "guest_vm",
                            "hypervisor_backend": "qemu",
                            "guest_id": guest_id,
                            "image_sha": image_sha,
                            "recorded_repo_head": recorded_head,
                            "guest_toplevel": "/guest",
                            "host_toplevel": live_toplevel,
                            "same_checkout": False,
                            "host_tracked_unchanged": True,
                            "host_head_unchanged": True,
                            "sandbox_marker_absent_from_live_root": True,
                            "bwrap_used": False,
                            "host_mount_used": False,
                            "hypervisor": dict(probe),
                        },
                        "reconstruct": None,
                        "execute": {"attempted": True, "level": level},
                        "qemu_returncode": None,
                    }
                )
            guest_payload: dict[str, Any] = {}
            serial_text = serial_proof.read_text(encoding="utf-8", errors="replace").strip()
            if serial_text:
                try:
                    guest_payload = json.loads(serial_text.splitlines()[-1])
                except json.JSONDecodeError:
                    guest_payload = {"error": "guest_serial_not_json", "raw": serial_text[:500]}
            live_head_after = self._git_head(self.repo_root)
            porcelain_after = self._live_porcelain()
            live_marker = self.repo_root / "NDF_GUEST_MARKER"
            guest_toplevel = str(guest_payload.get("guest_toplevel") or "/guest")
            same_checkout = Path(guest_toplevel).resolve() == Path(live_toplevel).resolve()
            reconstruct = guest_payload.get("reconstruct")
            if not isinstance(reconstruct, Mapping):
                reconstruct = None
            isolation = {
                "adapter": "vm",
                "kind": "guest_vm",
                "hypervisor_backend": "qemu",
                "guest_id": guest_id,
                "image_sha": image_sha,
                "recorded_repo_head": recorded_head,
                "guest_toplevel": guest_toplevel,
                "host_toplevel": live_toplevel,
                "same_checkout": same_checkout,
                "host_tracked_unchanged": porcelain_after == porcelain_before,
                "host_head_unchanged": live_head_after == live_head_before,
                "live_head_before": live_head_before,
                "live_head_after": live_head_after,
                "sandbox_marker_absent_from_live_root": not live_marker.exists(),
                "bwrap_used": False,
                "host_mount_used": False,
                "hypervisor": dict(probe),
                "qemu_returncode": proc.returncode,
            }
            if guest_payload.get("error") and reconstruct is None:
                return _finish(
                    {
                        "schema": "ndf-replay-guest-proof/v1",
                        "valid": False,
                        "state": "environment_blocked",
                        "environment_blocker": str(guest_payload.get("error")),
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "isolation": isolation,
                        "reconstruct": None,
                        "execute": {"attempted": True, "level": level},
                        "console_log": console_log.as_posix(),
                        "qemu_stderr": (proc.stderr or "")[:2000],
                    }
                )
            if reconstruct is None:
                return _finish(
                    {
                        "schema": "ndf-replay-guest-proof/v1",
                        "valid": False,
                        "state": "environment_blocked",
                        "environment_blocker": "guest_proof_missing",
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "isolation": isolation,
                        "reconstruct": None,
                        "execute": {"attempted": True, "level": level},
                        "console_log": console_log.as_posix(),
                        "qemu_stderr": (proc.stderr or "")[:2000],
                    }
                )
            result = {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "guest_observe",
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": isolation,
                "reconstruct": {
                    "level": reconstruct.get("level"),
                    "side_effects": reconstruct.get("side_effects"),
                    "commit_sha": reconstruct.get("commit_sha"),
                    "timeline_events": reconstruct.get("timeline_events"),
                },
                "execute": {
                    "attempted": False,
                    "level": level,
                    "reason": "guest_observe_only",
                },
                "console_log": console_log.as_posix(),
            }
            return _finish(result)
        finally:
            if not keep_guest:
                shutil.rmtree(staging, ignore_errors=True)

    def _guest_run_cube(
        self,
        *,
        sha: str,
        episode_id: str,
        level: str,
        target_head: str,
        recorded_head: str | None,
        live_toplevel: str,
        live_head_before: str,
        porcelain_before: list[str],
        proof_path: Path,
        cube_probe: Mapping[str, Any],
        probe: Mapping[str, Any],
        cube_client: Any | None,
        keep_guest: bool,
        host_mount: str | None,
    ) -> dict[str, Any]:
        template_id = str(
            cube_probe.get("template_id")
            or os.environ.get("NDF_CUBE_TEMPLATE_ID")
            or os.environ.get("CUBE_TEMPLATE_ID")
            or ""
        )
        image_sha = hashlib.sha256(
            f"cube-template:{template_id}:{target_head}".encode("utf-8")
        ).hexdigest()

        def _blocked(reason: str) -> dict[str, Any]:
            result = {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "environment_blocked",
                "environment_blocker": reason,
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": {
                    "adapter": "vm",
                    "kind": "guest_vm",
                    "hypervisor_backend": "cube",
                    "guest_id": str(uuid.uuid4()),
                    "image_sha": image_sha,
                    "recorded_repo_head": recorded_head,
                    "guest_toplevel": None,
                    "host_toplevel": live_toplevel,
                    "same_checkout": None,
                    "host_tracked_unchanged": True,
                    "host_head_unchanged": True,
                    "sandbox_marker_absent_from_live_root": True,
                    "bwrap_used": False,
                    "host_mount_used": bool(host_mount),
                    "hypervisor": probe,
                    "cube": dict(cube_probe),
                },
                "reconstruct": None,
                "execute": {"attempted": False, "level": level},
            }
            result["proof_errors"] = validate_guest_proof(result)
            self._atomic_write(proof_path, canonical_json_bytes(result) + b"\n")
            result["proof_path"] = proof_path.as_posix()
            return result

        if host_mount:
            return _blocked("host_mount_forbidden_for_replay")

        client = cube_client
        if client is None:
            if not cube_probe.get("available"):
                return _blocked(
                    str(cube_probe.get("blocker") or "cube_api_unavailable")
                )
            return _blocked(
                "cube_live_client_not_wired: set a Cube cluster and inject "
                "client, or use tests MockCubeSandboxClient; refuse soft fallback"
            )
        if not template_id:
            return _blocked("no_CUBE_TEMPLATE_ID")

        sandbox_id = None
        try:
            created = client.create(
                template_id=template_id,
                airgap=True,
                host_mount=None,
            )
            sandbox_id = str(created["sandbox_id"])
            guest_toplevel = str(
                Path(created.get("guest_toplevel") or "").resolve()
                if created.get("guest_toplevel")
                else ""
            )
            if not guest_toplevel:
                return _blocked("cube_create_missing_guest_toplevel")
            if Path(guest_toplevel).resolve() == Path(live_toplevel).resolve():
                return _blocked("cube_guest_same_as_live_checkout")

            archive = subprocess.check_output(
                ["git", "archive", "--format=tar", target_head],
                cwd=self.repo_root,
            )
            if hasattr(client, "materialize_snapshot"):
                client.materialize_snapshot(sandbox_id, archive)
            if self.root.is_dir() and hasattr(client, "write_tree"):
                client.write_tree(sandbox_id, ".ndf/replay", self.root)

            guest_root = Path(guest_toplevel)
            # Ensure guest looks like a git checkout for ReplayStore bounds.
            if not (guest_root / ".git").exists():
                subprocess.run(["git", "init", "-q"], cwd=guest_root, check=True)
                subprocess.run(
                    ["git", "config", "user.email", "replay-guest@local"],
                    cwd=guest_root,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "replay-guest"],
                    cwd=guest_root,
                    check=True,
                )
                subprocess.run(["git", "add", "-A"], cwd=guest_root, check=False)
                subprocess.run(
                    ["git", "commit", "-qm", f"cube-guest {target_head}"],
                    cwd=guest_root,
                    check=False,
                )

            marker = guest_root / "NDF_GUEST_MARKER"
            marker.write_text(
                json.dumps(
                    {
                        "episode_id": episode_id,
                        "commit_sha": sha,
                        "guest_id": sandbox_id,
                        "hypervisor_backend": "cube",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            reconstruction = self._reconstruct_copied_store(guest_root, sha, level)
            live_head_after = self._git_head(self.repo_root)
            porcelain_after = self._live_porcelain()
            live_marker = self.repo_root / "NDF_GUEST_MARKER"
            same_checkout = Path(guest_toplevel).resolve() == Path(live_toplevel).resolve()
            isolation = {
                "adapter": "vm",
                "kind": "guest_vm",
                "hypervisor_backend": "cube",
                "guest_id": sandbox_id,
                "image_sha": image_sha,
                "recorded_repo_head": recorded_head,
                "guest_toplevel": guest_toplevel,
                "host_toplevel": live_toplevel,
                "same_checkout": same_checkout,
                "host_tracked_unchanged": porcelain_after == porcelain_before,
                "host_head_unchanged": live_head_after == live_head_before,
                "live_head_before": live_head_before,
                "live_head_after": live_head_after,
                "sandbox_marker_absent_from_live_root": not live_marker.exists(),
                "bwrap_used": False,
                "host_mount_used": False,
                "hypervisor": probe,
                "cube": dict(cube_probe),
                "template_id": template_id,
                "used_fallback_head": recorded_head is None,
            }
            result = {
                "schema": "ndf-replay-guest-proof/v1",
                "valid": False,
                "state": "guest_observe",
                "episode_id": episode_id,
                "commit_sha": sha,
                "isolation": isolation,
                "reconstruct": {
                    "level": reconstruction.get("level"),
                    "side_effects": reconstruction.get("side_effects"),
                    "commit_sha": reconstruction.get("commit_sha"),
                    "timeline_events": len(reconstruction.get("timeline") or []),
                },
                "execute": {
                    "attempted": False,
                    "level": level,
                    "reason": "guest_observe_only",
                },
            }
            errors = validate_guest_proof(result)
            result["proof_errors"] = errors
            result["valid"] = not errors
            if not result["valid"]:
                result["state"] = "proof_invalid"
            self._atomic_write(proof_path, canonical_json_bytes(result) + b"\n")
            result["proof_path"] = proof_path.as_posix()
            return result
        except ValueError as exc:
            return _blocked(str(exc))
        finally:
            if sandbox_id and cube_client is not None and not keep_guest:
                try:
                    cube_client.kill(sandbox_id)
                except Exception:  # noqa: BLE001
                    pass

    def _materialize_guest_snapshot(self, guest_root: Path, repo_head: str) -> None:
        guest_root.mkdir(parents=True, exist_ok=True)
        archive = subprocess.check_output(
            ["git", "archive", "--format=tar", repo_head],
            cwd=self.repo_root,
        )
        subprocess.run(
            ["tar", "-xf", "-"],
            cwd=guest_root,
            input=archive,
            check=True,
        )
        subprocess.run(["git", "init", "-q"], cwd=guest_root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "replay-guest@local"],
            cwd=guest_root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "replay-guest"],
            cwd=guest_root,
            check=True,
        )
        subprocess.run(["git", "add", "-A"], cwd=guest_root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", f"guest-snapshot {repo_head}"],
            cwd=guest_root,
            check=True,
        )

    def fork(
        self,
        start: str,
        branch: str,
        *,
        changes: Iterable[str] = (),
    ) -> dict[str, Any]:
        sha = self.read_ref(start) or start
        source = self.get_object(sha, "commit")["data"]
        change_list = list(changes)
        metadata = self.put_blob(
            {
                "schema": "ndf-replay-counterfactual/v1",
                "source_commit": sha,
                "changes": change_list,
                "historical_reproduction": False,
                "created_at": now_iso(),
            }
        )
        tree = self.put_tree(
            {
                "source-tree": source["tree"],
                "counterfactual": metadata,
            }
        )
        commit = self.put_commit(
            tree,
            parents=[sha],
            actor="fork",
            topic=source.get("topic"),
            task="counterfactual_fork",
            track=source.get("track") or "process",
            repo_head=source.get("repo_head"),
            manifest_sha=source.get("manifest_sha"),
            context_plan_sha=source.get("context_plan_sha"),
            message="R3 counterfactual fork",
            coverage={"counterfactual": True},
        )
        self.update_ref(f"branches/{branch}", commit, expected_old=None)
        return {
            "schema": "ndf-replay-fork/v1",
            "level": "R3",
            "from": sha,
            "branch": branch,
            "commit_sha": commit,
            "changes": change_list,
            "counterfactual": True,
        }

    @staticmethod
    def tool_cassette(
        *,
        tool: str,
        name: str,
        invocation_id: str,
        cwd: str,
        argv: Iterable[str],
        normalized_input: Any,
        stdin_sha: str | None,
        env_allowlist_fingerprint: str,
        timeout_ms: int,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: int,
        replay_policy: str,
        external_resource_version: str | None,
        bindings: Mapping[str, Any],
    ) -> dict[str, Any]:
        cassette = {
            "schema": "ndf-tool-cassette/v1",
            "tool": tool,
            "name": name,
            "invocation_id": invocation_id,
            "cwd": cwd,
            "argv": list(argv),
            "normalized_input": _json_copy(normalized_input),
            "stdin_sha": stdin_sha,
            "env_allowlist_fingerprint": env_allowlist_fingerprint,
            "timeout_ms": timeout_ms,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "replay_policy": replay_policy,
            "external_resource_version": external_resource_version,
            **dict(bindings),
        }
        required = (
            "repo_head",
            "worktree",
            "manifest_sha",
            "plan_sha",
            "run_id",
        )
        missing = [field for field in required if not cassette.get(field)]
        if missing:
            raise ValueError(f"tool cassette missing bindings: {missing}")
        if replay_policy not in {"recorded-only", "sandbox", "live-readonly"}:
            raise ValueError(f"invalid replay policy: {replay_policy}")
        if tool.lower() in {"mcp", "remote", "web"} and replay_policy == "sandbox":
            raise ValueError("remote tools default to recorded-only")
        if replay_policy == "live-readonly" and not external_resource_version:
            raise ValueError("live-readonly requires external_resource_version")
        _assert_no_plaintext_secrets(cassette)
        return cassette

    def put_tool_cassette(self, cassette: Mapping[str, Any]) -> str:
        value = _json_copy(cassette)
        if value.get("schema") != "ndf-tool-cassette/v1":
            raise ValueError("expected ndf-tool-cassette/v1")
        required = (
            "tool",
            "name",
            "invocation_id",
            "cwd",
            "argv",
            "normalized_input",
            "env_allowlist_fingerprint",
            "timeout_ms",
            "exit_code",
            "duration_ms",
            "repo_head",
            "worktree",
            "manifest_sha",
            "plan_sha",
            "run_id",
            "replay_policy",
        )
        missing = [
            field
            for field in required
            if field not in value or value[field] is None or value[field] == ""
        ]
        if missing:
            raise ValueError(f"tool cassette missing fields: {missing}")
        _assert_no_plaintext_secrets(value)
        for stream_name in ("stdout", "stderr"):
            content = str(value.pop(stream_name, ""))
            blob_sha = self.put_blob(content, media_type="text/plain")
            value[f"{stream_name}_blob"] = blob_sha
            value[f"{stream_name}_sha"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
        return self.put_object("tool-cassette", value)

    @staticmethod
    def model_turn(**values: Any) -> dict[str, Any]:
        turn = {"schema": "ndf-model-turn/v1", **_json_copy(values)}
        turn.setdefault("hidden_chain_of_thought", "not_recorded")
        turn.setdefault("visible_surface_coverage", "unknown_hidden_surface")
        _assert_no_plaintext_secrets(turn)
        return turn

    def put_model_turn(self, turn: Mapping[str, Any]) -> str:
        value = _json_copy(turn)
        if value.get("schema") != "ndf-model-turn/v1":
            raise ValueError("expected ndf-model-turn/v1")
        required = (
            "provider",
            "model_id",
            "api_version",
            "parameters",
            "runtime_build",
            "tool_schema_sha",
            "skill_rule_sha",
            "manifest_sha",
            "role_plan_sha",
            "visible_system_surface_sha",
            "user_message",
            "assistant_response",
            "stop_reason",
            "token_usage",
        )
        missing = [field for field in required if field not in value or value[field] is None]
        if missing:
            raise ValueError(f"model turn missing fields: {missing}")
        for field in (
            "tool_schema_sha",
            "skill_rule_sha",
            "manifest_sha",
            "role_plan_sha",
            "visible_system_surface_sha",
        ):
            if not SHA_RE.fullmatch(str(value.get(field) or "")):
                raise ValueError(f"model turn invalid SHA: {field}")
        _assert_no_plaintext_secrets(value)
        for field in ("user_message", "assistant_response"):
            content = str(value.pop(field))
            value[f"{field}_blob"] = self.put_blob(
                content,
                media_type="text/plain",
                sensitivity="sensitive",
            )
            value[f"{field}_sha"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
        for reference in value.get("input_tool_cassette_refs", []):
            self.get_object(str(reference), "tool-cassette")
        return self.put_object("model-turn", value)

    def redact_export(self, commit_or_ref: str) -> dict[str, Any]:
        source_sha = self.read_ref(commit_or_ref) or commit_or_ref
        source = self.get_object(source_sha, "commit")["data"]
        tree = self.get_object(source["tree"], "tree")["data"]["entries"]
        redacted_entries: dict[str, str] = {}
        replacements: list[dict[str, Any]] = []
        object_map: dict[str, str] = {}

        sensitive_value_patterns = (
            (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]", "private_key"),
            (re.compile(r"\b(?:Bearer\s+)?(?:sk|ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{12,}\b", re.I), "[REDACTED_TOKEN]", "secret_value"),
            (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I), "Bearer [REDACTED_TOKEN]", "authorization"),
            (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]", "secret_value"),
            (
                re.compile(
                    r"(?i)\b(password|passwd|token|secret|api[_-]?key|session[_-]?key)"
                    r"(\s*[:=]\s*)([^\s,;\"']+)"
                ),
                r"\1\2[REDACTED]",
                "secret_assignment",
            ),
            (re.compile(r"\b(?:ou|oc|on|cli)_[A-Za-z0-9]{8,}\b"), "[REDACTED_ID]", "service_id"),
            (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[REDACTED_EMAIL]", "pii_email"),
            (
                re.compile(r"(?i)\bhttps?://[^/\s:@]+:[^/\s@]+@"),
                "https://[REDACTED_CREDENTIAL]@",
                "url_credential",
            ),
        )
        secret_argv_flags = {
            "--token",
            "--api-key",
            "--apikey",
            "--password",
            "--passwd",
            "--secret",
            "--authorization",
            "-p",
        }

        def redact(value: Any, path: str = "") -> Any:
            if isinstance(value, dict):
                output = {}
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else key
                    if SECRET_KEY_RE.search(key):
                        output[key] = "[REDACTED]"
                        replacements.append({"path": child_path, "reason": "secret_key"})
                    else:
                        output[key] = redact(child, child_path)
                return output
            if isinstance(value, list):
                output = []
                redact_next = False
                for index, child in enumerate(value):
                    child_path = f"{path}[{index}]"
                    if redact_next:
                        output.append("[REDACTED]")
                        replacements.append(
                            {"path": child_path, "reason": "argv_secret_value"}
                        )
                        redact_next = False
                        continue
                    if isinstance(child, str):
                        flag = child.lower()
                        if flag in secret_argv_flags:
                            output.append(child)
                            redact_next = True
                            continue
                        if any(
                            flag.startswith(f"{secret_flag}=")
                            for secret_flag in secret_argv_flags
                        ):
                            output.append(child.split("=", 1)[0] + "=[REDACTED]")
                            replacements.append(
                                {"path": child_path, "reason": "argv_secret_assignment"}
                            )
                            continue
                        if flag in {"-h", "--header"} and index + 1 < len(value):
                            output.append(child)
                            redact_next = True
                            continue
                    output.append(redact(child, child_path))
                return output
            if isinstance(value, str):
                output = value
                for pattern, replacement, reason in sensitive_value_patterns:
                    revised, count = pattern.subn(replacement, output)
                    if count:
                        replacements.append(
                            {"path": path, "reason": reason, "count": count}
                        )
                    output = revised
                return output
            return value

        def redact_object(object_sha: str, path: str) -> str:
            if object_sha in object_map:
                return object_map[object_sha]
            obj = self.get_object(object_sha)
            kind = obj["type"]
            data = _json_copy(obj["data"])
            if kind == "tree":
                data["entries"] = {
                    name: redact_object(target, f"{path}/{name}")
                    for name, target in data.get("entries", {}).items()
                }
            elif kind == "tool-cassette":
                for field in ("stdout_blob", "stderr_blob"):
                    if data.get(field):
                        data[field] = redact_object(
                            str(data[field]),
                            f"{path}/{field}",
                        )
                data = redact(data, path)
            elif kind == "model-turn":
                for field in ("user_message_blob", "assistant_response_blob"):
                    if data.get(field):
                        data[field] = redact_object(
                            str(data[field]),
                            f"{path}/{field}",
                        )
                data["input_tool_cassette_refs"] = [
                    redact_object(str(target), f"{path}/input-tool-{index}")
                    for index, target in enumerate(
                        data.get("input_tool_cassette_refs", [])
                    )
                ]
                data = redact(data, path)
            else:
                data = redact(data, path)
            redacted_sha = self.put_object(kind, data)
            object_map[object_sha] = redacted_sha
            return redacted_sha

        for name, object_sha in tree.items():
            redacted_entries[name] = redact_object(object_sha, name)
        redaction_map = {
            "schema": "ndf-redaction-map/v1",
            "source_commit": source_sha,
            "replacements": replacements,
            "object_map": object_map,
            "original_objects_unchanged": True,
        }
        redacted_entries["redaction-map"] = self.put_blob(redaction_map)
        redacted_tree = self.put_tree(redacted_entries)
        scanner_findings: list[str] = []
        for original_sha, exported_sha in object_map.items():
            exported = self.get_object(exported_sha)
            serialized = json.dumps(
                exported,
                ensure_ascii=False,
                sort_keys=True,
            )
            scan_text = re.sub(r"\[REDACTED[^\]]*\]", "", serialized)
            for pattern, _, reason in sensitive_value_patterns:
                if pattern.search(scan_text):
                    scanner_findings.append(f"{exported_sha}:{reason}")
            if re.search(
                r'(?i)"(?:token|password|secret|api[_-]?key)"\s*:\s*"[^"]+"',
                scan_text,
            ):
                scanner_findings.append(f"{exported_sha}:secret_key_value")
        if scanner_findings:
            raise ValueError(
                "share-safe export secret scan failed: "
                + ",".join(sorted(set(scanner_findings)))
            )
        commit = self.put_commit(
            redacted_tree,
            # A share-safe export must not make the secret-bearing source
            # history reachable from the exported commit closure.
            parents=[],
            actor="redactor",
            topic=source.get("topic"),
            task="redacted_export",
            track=source.get("track") or "process",
            repo_head=source.get("repo_head"),
            manifest_sha=source.get("manifest_sha"),
            context_plan_sha=source.get("context_plan_sha"),
            message="share-safe redacted export",
            coverage={"redaction_map": redacted_entries["redaction-map"]},
        )
        return {
            "schema": "ndf-replay-export/v1",
            "source_commit": source_sha,
            "redacted_commit": commit,
            "redaction_map_sha": redacted_entries["redaction-map"],
            "secret_scan_findings": [],
        }

    def ledger_entry(self, episode_id: str, *, write: bool = False) -> dict[str, Any]:
        head = self.read_ref(f"episodes/{episode_id}/HEAD")
        if head is None:
            raise ValueError(f"unknown episode: {episode_id}")
        commit = self.get_object(head, "commit")["data"]
        topic = commit.get("topic")
        if not topic:
            raise ValueError("project-level episode has no topic binder ledger")
        branch_events = self.read_all_events(episode_id)
        chains = {
            branch: validate_event_chain(events)
            for branch, events in branch_events.items()
        }
        history = [value for _, value in self.walk_commits(head)]
        manifest_sha = next(
            (value.get("manifest_sha") for value in history if value.get("manifest_sha")),
            None,
        )
        plan_sha = next(
            (
                value.get("context_plan_sha")
                for value in history
                if value.get("context_plan_sha")
            ),
            None,
        )
        runtime_coverage = [
            value.get("coverage", {}).get("runtime_stream")
            for value in history
            if value.get("coverage", {}).get("runtime_stream")
        ]
        line = (
            f"| {now_iso()} | {episode_id} | {commit.get('task')} | "
            f"{manifest_sha or 'missing'} | "
            f"{plan_sha or 'missing'} | {head} | "
            f"R0={'yes' if chains and all(item['valid'] for item in chains.values()) else 'no'}; "
            f"runtime={','.join(str(item) for item in runtime_coverage) or 'unknown'} | "
            f".ndf/replay/ | coverage gaps retained |"
        )
        path = self.repo_root / "poc" / str(topic) / "ndf" / "REPLAYS.md"
        if write:
            if not path.parent.is_dir():
                raise ValueError(f"topic binder missing: {path.parent}")
            if not path.exists():
                path.write_text(
                    "# Agent Episode Replay Ledger\n\n"
                    "> schema: ndf-replay-ledger/v1\n\n"
                    "| recorded_at | episode_id | task | manifest_sha | role_plan_sha | completion_commit | replay_coverage | artifact_location | note |\n"
                    "|---|---|---|---|---|---|---|---|---|\n",
                    encoding="utf-8",
                )
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return {
            "schema": "ndf-replay-ledger-entry/v1",
            "episode_id": episode_id,
            "topic": topic,
            "head": head,
            "line": line,
            "path": path.relative_to(self.repo_root).as_posix(),
            "written": write,
        }

    def retention_plan(self) -> dict[str, Any]:
        """Return a non-destructive hot/cold plan; never deletes evidence."""
        config_path = self.root / "config.json"
        if not config_path.is_file():
            return {
                "schema": "ndf-replay-retention-plan/v1",
                "state": "not_initialized",
                "candidates": [],
            }
        config = json.loads(config_path.read_text(encoding="utf-8"))
        hot_days = int(config.get("retention", {}).get("large_tool_blob_hot_days", 90))
        model_days = int(
            config.get("retention", {}).get("sensitive_model_turn_hot_days", 30)
        )
        referenced: set[str] = set()
        pending: list[str] = []
        if self.refs.is_dir():
            for path in self.refs.rglob("*"):
                if path.is_file():
                    pending.append(path.read_text(encoding="utf-8").strip())
        while pending:
            sha = pending.pop()
            if sha in referenced or not SHA_RE.fullmatch(sha):
                continue
            referenced.add(sha)
            try:
                obj = self.get_object(sha)
            except (FileNotFoundError, ValueError):
                continue
            data = obj.get("data", {})
            if obj.get("type") == "commit":
                pending.extend([data.get("tree"), *data.get("parents", [])])
            elif obj.get("type") == "tree":
                pending.extend(data.get("entries", {}).values())
            elif obj.get("type") == "tool-cassette":
                pending.extend(
                    data.get(field)
                    for field in ("stdout_blob", "stderr_blob")
                    if data.get(field)
                )
        current = datetime.now(timezone.utc).timestamp()
        candidates = []
        if self.objects.is_dir():
            for path in sorted(item for item in self.objects.rglob("*") if item.is_file()):
                sha = path.parent.name + path.name
                age_days = max(0, int((current - path.stat().st_mtime) / 86400))
                try:
                    obj = self.get_object(sha)
                except (FileNotFoundError, ValueError):
                    continue
                threshold = (
                    model_days
                    if obj.get("type") == "model-turn"
                    or obj.get("data", {}).get("sensitivity") in {
                        "sensitive",
                        "secret",
                    }
                    else hot_days
                )
                if age_days >= threshold:
                    candidates.append(
                        {
                            "sha": sha,
                            "age_days": age_days,
                            "hot_days": threshold,
                            "reachable": sha in referenced,
                            "action": (
                                "keep-core"
                                if sha in referenced
                                else "eligible-for-cold-store-after-location-receipt"
                            ),
                        }
                    )
        return {
            "schema": "ndf-replay-retention-plan/v1",
            "state": "planned",
            "hot_days": hot_days,
            "destructive": False,
            "candidates": candidates,
        }

    def fsck(self) -> dict[str, Any]:
        errors: list[str] = []
        object_count = 0
        commits: dict[str, dict[str, Any]] = {}
        config_path = self.root / "config.json"
        if self.root.is_dir():
            if not config_path.is_file():
                errors.append("missing replay config")
            else:
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    if config.get("schema") != "ndf-replay-config/v1":
                        errors.append("invalid replay config schema")
                    if config.get("storage_security") not in {
                        "encrypted-local",
                        "controlled-artifact-store",
                    }:
                        errors.append("uncontrolled replay storage")
                    if (
                        config.get("storage_security") == "encrypted-local"
                        and config.get("key_id") != self._key_id()
                    ):
                        errors.append("replay encryption key mismatch")
                except json.JSONDecodeError:
                    errors.append("invalid replay config")
        if self.objects.is_dir():
            for path in sorted(
                item
                for item in self.objects.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                sha = path.parent.name + path.name
                object_count += 1
                if not path.read_bytes().startswith(ENCRYPTED_MAGIC):
                    errors.append(f"plaintext replay object:{sha}")
                try:
                    obj = self.get_object(sha)
                except (ValueError, FileNotFoundError) as exc:
                    errors.append(str(exc))
                    continue
                data = obj.get("data", {})
                if obj.get("type") == "tree":
                    if not isinstance(data.get("entries"), dict):
                        errors.append(f"invalid tree entries:{sha}")
                        continue
                    for name, target in data.get("entries", {}).items():
                        try:
                            self.get_object(target)
                        except (ValueError, FileNotFoundError):
                            errors.append(f"missing tree object:{sha}:{name}:{target}")
                elif obj.get("type") == "commit":
                    commits[sha] = data
                    try:
                        self.get_object(str(data.get("tree")), "tree")
                    except (ValueError, FileNotFoundError):
                        errors.append(
                            f"commit_tree_wrong_type_or_missing:{sha}:{data.get('tree')}"
                        )
                    for target in data.get("parents", []):
                        try:
                            self.get_object(str(target), "commit")
                        except (ValueError, FileNotFoundError):
                            errors.append(
                                f"commit_parent_wrong_type_or_missing:{sha}:{target}"
                            )
                elif obj.get("type") == "tool-cassette":
                    for field in ("stdout_blob", "stderr_blob"):
                        try:
                            self.get_object(str(data[field]), "blob")
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing cassette stream:{sha}:{field}")
                elif obj.get("type") == "model-turn":
                    for field in ("user_message_blob", "assistant_response_blob"):
                        try:
                            self.get_object(str(data[field]), "blob")
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing model turn message:{sha}:{field}")
                    for target in data.get("input_tool_cassette_refs", []):
                        try:
                            self.get_object(str(target), "tool-cassette")
                        except (ValueError, FileNotFoundError):
                            errors.append(f"missing model turn cassette:{sha}:{target}")
                elif obj.get("type") == "blob":
                    value = data.get("value")
                    if (
                        data.get("encoding") == "json"
                        and isinstance(value, dict)
                        and value.get("schema") == "ndf-redaction-map/v1"
                    ):
                        try:
                            self.get_object(str(value["source_commit"]), "commit")
                            for original, redacted in value.get(
                                "object_map", {}
                            ).items():
                                self.get_object(str(original))
                                self.get_object(str(redacted))
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"invalid redaction lineage:{sha}")
                    if (
                        data.get("encoding") == "json"
                        and isinstance(value, dict)
                        and value.get("schema") == "ndf-replay-event-chain/v1"
                    ):
                        try:
                            count = int(value["count"])
                            events = self.read_events(
                                str(value["episode_id"]),
                                str(value.get("branch") or "main"),
                            )
                            prefix = validate_event_chain(events[:count])
                            if (
                                prefix["count"] != count
                                or prefix["tip_sha"] != value.get("tip_sha")
                            ):
                                errors.append(f"event chain object mismatch:{sha}")
                        except (KeyError, TypeError, ValueError):
                            errors.append(f"invalid event chain object:{sha}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit_commit(current: str) -> None:
            if current in visited:
                return
            if current in visiting:
                errors.append(f"commit_cycle:{current}")
                return
            visiting.add(current)
            for parent in commits.get(current, {}).get("parents", []):
                if parent in commits:
                    visit_commit(parent)
            visiting.remove(current)
            visited.add(current)

        for sha in commits:
            visit_commit(sha)
        ref_count = 0
        if self.refs.is_dir():
            for path in sorted(
                item
                for item in self.refs.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                ref_count += 1
                sha = path.read_text(encoding="utf-8").strip()
                relative_ref = path.relative_to(self.refs).as_posix()
                try:
                    obj = self.get_object(sha)
                    if (
                        relative_ref.startswith(
                            ("episodes/", "branches/", "topics/", "runs/", "tags/")
                        )
                        and obj.get("type") != "commit"
                    ):
                        errors.append(
                            f"ref_wrong_type:{relative_ref}:{obj.get('type')}"
                        )
                except (ValueError, FileNotFoundError):
                    errors.append(f"dangling_ref:{relative_ref}:{sha}")
        event_count = 0
        if self.events.is_dir():
            for path in sorted(self.events.rglob("*.jsonl")):
                try:
                    relative = path.relative_to(self.events)
                    if len(relative.parts) == 1:
                        episode_id = path.stem
                        branch = "main"
                    else:
                        episode_id = relative.parts[0]
                        branch = Path(*relative.parts[1:]).with_suffix("").as_posix()
                    events = self.read_events(episode_id, branch)
                    validation = validate_event_chain(events)
                    event_count += len(events)
                    errors.extend(f"{path.name}:{error}" for error in validation["errors"])
                    for event in events:
                        if event.get("episode_id") != episode_id:
                            errors.append(
                                f"event_episode_mismatch:{path.name}:{event.get('seq')}"
                            )
                        if event.get("branch") != branch:
                            errors.append(
                                f"event_branch_mismatch:{path.name}:{event.get('seq')}"
                            )
                        try:
                            self.get_object(event["payload_sha"])
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing_event_payload:{path.name}:{event.get('seq')}")
                except ValueError as exc:
                    errors.append(f"{path.name}:{exc}")
        if self.refs.is_dir():
            for path in sorted(self.refs.glob("flows/*/children/*")):
                if not path.is_file():
                    continue
                try:
                    pointer = self.get_object(
                        path.read_text(encoding="utf-8").strip(), "blob"
                    )["data"].get("value")
                except (ValueError, FileNotFoundError):
                    errors.append(f"control_child_pointer_missing:{path}")
                    continue
                if not isinstance(pointer, dict):
                    errors.append(f"control_child_pointer_invalid:{path}")
                    continue
                child_id = str(pointer.get("episode_id") or "")
                parent_id = str(pointer.get("parent_episode_id") or "")
                stage = pointer.get("stage")
                flow_id = pointer.get("flow_id")
                identity = self.episode_identity(child_id) or {}
                if identity.get("stage") != stage or identity.get("flow_id") != flow_id:
                    errors.append(f"control_child_identity_mismatch:{child_id}")
                if parent_id and self.read_ref(f"episodes/{parent_id}/HEAD") is None:
                    errors.append(f"control_parent_missing:{parent_id}")
        return {
            "schema": "ndf-replay-fsck/v1",
            "valid": not errors,
            "objects": object_count,
            "refs": ref_count,
            "events": event_count,
            "errors": sorted(set(errors)),
        }


def _load_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    parser.add_argument("--store", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("episode-init")
    init.add_argument("--topic")
    init.add_argument("--task", required=True)
    init.add_argument("--role", required=True)
    init.add_argument("--track", default="poc")
    init.add_argument("--manifest")
    init.add_argument("--episode")

    record = sub.add_parser("record")
    record.add_argument("--episode", required=True)
    record.add_argument("--kind", required=True, choices=tuple(sorted(EVENT_KINDS)))
    record.add_argument("--payload", required=True)
    record.add_argument("--actor", default="tool")
    record.add_argument("--topic")
    record.add_argument("--task", required=True)
    record.add_argument("--track", default="poc")
    record.add_argument("--repo-head")
    record.add_argument("--manifest-sha")
    record.add_argument("--plan-sha")
    record.add_argument("--session-id")
    record.add_argument("--run-id")
    record.add_argument("--branch", default="main")
    cassette = sub.add_parser("cassette-record")
    cassette.add_argument("--episode", required=True)
    cassette.add_argument("--file", required=True)
    cassette.add_argument("--actor", default="tool")
    cassette.add_argument("--branch", default="main")
    model_turn = sub.add_parser("model-turn-record")
    model_turn.add_argument("--episode", required=True)
    model_turn.add_argument("--file", required=True)
    model_turn.add_argument("--actor", default="model")
    model_turn.add_argument("--branch", default="main")

    commit = sub.add_parser("commit")
    commit.add_argument("--episode", required=True)
    commit.add_argument("--message", required=True)
    commit.add_argument("--actor", default="tool")
    commit.add_argument("--branch", default="main")

    show = sub.add_parser("show")
    show.add_argument("object")
    log = sub.add_parser("log")
    log.add_argument("start")
    diff = sub.add_parser("diff")
    diff.add_argument("left")
    diff.add_argument("right")

    branch = sub.add_parser("branch")
    branch.add_argument("name")
    branch.add_argument("start")
    tag = sub.add_parser("tag")
    tag.add_argument("name")
    tag.add_argument("target")
    gate_tag = sub.add_parser("gate-tag")
    gate_tag.add_argument("--name", required=True)
    gate_tag.add_argument("--target", required=True)
    gate_tag.add_argument("--receipt", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--episode", required=True)
    merge.add_argument("--left", required=True)
    merge.add_argument("--right", required=True)
    merge.add_argument("--message", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--episode", required=True)
    checkpoint.add_argument("--strategy", choices=("context-recompile",), default="context-recompile")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--manifest-sha")
    checkpoint.add_argument("--plan-sha")
    checkpoint.add_argument("--open-decision", action="append", default=[])
    checkpoint.add_argument("--resolved-decision", action="append", default=[])
    checkpoint.add_argument("--summary-provenance")
    checkpoint.add_argument("--branch", default="main")

    audit = sub.add_parser("audit")
    audit.add_argument("--commit", required=True)
    audit.add_argument("--strict", action="store_true")
    reconstruct = sub.add_parser("reconstruct")
    reconstruct.add_argument("--commit", required=True)
    reconstruct.add_argument("--level", choices=("R0", "R1"), default="R1")
    sandbox = sub.add_parser("sandbox")
    sandbox.add_argument("--commit", required=True)
    sandbox.add_argument("--profile", required=True)
    sandbox.add_argument("--execute", action="store_true")
    sandbox.add_argument("--episode")
    isolate = sub.add_parser("isolate")
    isolate.add_argument("--commit", required=True)
    isolate.add_argument("--episode", required=True)
    isolate.add_argument("--keep-worktree", action="store_true")
    isolate.add_argument("--write-proof")
    guest = sub.add_parser("guest-run")
    guest.add_argument("--commit", required=True)
    guest.add_argument("--episode", required=True)
    guest.add_argument("--level", choices=("R0", "R1"), default="R0")
    guest.add_argument(
        "--adapter",
        choices=("vm", "cube", "fake-vm"),
        default="vm",
        help="vm=local KVM image; cube=CubeSandbox/E2B API (Lvm); fake-vm=tests-only",
    )
    guest.add_argument("--image", help="Guest rootfs/image path for adapter=vm")
    guest.add_argument(
        "--cube-api-url",
        help="Cube/E2B API URL (else NDF_CUBE_API_URL or E2B_API_URL)",
    )
    guest.add_argument(
        "--cube-template-id",
        help="Cube template id (else NDF_CUBE_TEMPLATE_ID or CUBE_TEMPLATE_ID)",
    )
    guest.add_argument(
        "--host-mount",
        help="FORBIDDEN on replay path; any value yields environment_blocked",
    )
    guest.add_argument("--keep-guest", action="store_true")
    guest.add_argument("--write-proof")
    guest_image = sub.add_parser("guest-image")
    guest_image.add_argument(
        "--dest",
        help="Image directory (default: tmp/ndf-replay-images/alpine-ndf-replay)",
    )
    sub.add_parser("guest-probe")
    fork = sub.add_parser("fork")
    fork.add_argument("--from", dest="start", required=True)
    fork.add_argument("--branch", required=True)
    fork.add_argument("--change", action="append", default=[])
    export = sub.add_parser("export")
    export.add_argument("--commit", required=True)
    export.add_argument("--redact", default="share-safe")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("--episode", required=True)
    ledger.add_argument("--write", action="store_true")
    canvas_index = sub.add_parser("canvas-index")
    canvas_index.add_argument(
        "--write-cache",
        action="store_true",
        help="Write derived .ndf/replay/canvas-index.json (deletable)",
    )
    canvas_ledger = sub.add_parser("canvas-ledger")
    canvas_ledger.add_argument("--episode", required=True)
    canvas_ledger.add_argument(
        "--write-cache",
        action="store_true",
        help="Write derived .ndf/replay/canvas-ledger/<id>.json (deletable)",
    )
    sub.add_parser("retention-plan")
    sub.add_parser("fsck")

    args = parser.parse_args(argv)
    repo = Path(args.root).resolve()
    store = ReplayStore(repo, Path(args.store).resolve() if args.store else None)
    try:
        if args.command == "episode-init":
            result = store.init_episode(
                topic=args.topic,
                task=args.task,
                role=args.role,
                track=args.track,
                manifest=_load_json(args.manifest) if args.manifest else None,
                episode_id=args.episode,
            )
        elif args.command == "record":
            payload = _load_json(args.payload)
            payload_sha = store.put_blob(payload)
            result = store.append_event(
                args.episode,
                kind=args.kind,
                actor=args.actor,
                payload_sha=payload_sha,
                topic=args.topic,
                task=args.task,
                track=args.track,
                repo_head=args.repo_head,
                manifest_sha=args.manifest_sha,
                context_plan_sha=args.plan_sha,
                session_id=args.session_id,
                run_id=args.run_id,
                branch=args.branch,
                verified=False,
            )
        elif args.command in {"cassette-record", "model-turn-record"}:
            payload = _load_json(args.file)
            expected_schema = (
                "ndf-tool-cassette/v1"
                if args.command == "cassette-record"
                else "ndf-model-turn/v1"
            )
            if payload.get("schema") != expected_schema:
                raise ValueError(f"expected {expected_schema}")
            _assert_no_plaintext_secrets(payload)
            payload_sha = (
                store.put_tool_cassette(payload)
                if args.command == "cassette-record"
                else store.put_model_turn(payload)
            )
            result = store.append_event(
                args.episode,
                kind="tool.result" if args.command == "cassette-record" else "model.response",
                actor=args.actor,
                payload_sha=payload_sha,
                topic=payload.get("topic"),
                task=str(payload.get("task") or args.command),
                track=str(payload.get("track") or "process"),
                repo_head=payload.get("repo_head"),
                manifest_sha=payload.get("manifest_sha"),
                context_plan_sha=payload.get("plan_sha") or payload.get("context_plan_sha"),
                session_id=payload.get("session_id"),
                run_id=payload.get("run_id"),
                branch=args.branch,
            )
        elif args.command == "commit":
            result = {"commit_sha": store.commit_events(args.episode, message=args.message, actor=args.actor, branch=args.branch)}
        elif args.command == "show":
            sha = store.read_ref(args.object) or args.object
            result = {"sha": sha, "object": store.get_object(sha)}
        elif args.command == "log":
            result = {
                "schema": "ndf-replay-log/v1",
                "commits": [{"sha": sha, **value} for sha, value in store.walk_commits(args.start)],
            }
        elif args.command == "diff":
            result = store.diff(args.left, args.right)
        elif args.command == "branch":
            sha = store.read_ref(args.start) or args.start
            store.update_ref(f"branches/{args.name}", sha)
            result = {"branch": args.name, "sha": sha}
        elif args.command == "tag":
            if args.name.startswith("gates/"):
                raise ValueError("gate tags require gate-tag and a verified human receipt")
            sha = store.read_ref(args.target) or args.target
            store.update_ref(f"tags/{args.name}", sha, immutable=True)
            result = {"tag": args.name, "sha": sha}
        elif args.command == "gate-tag":
            result = store.create_gate_tag(
                args.name,
                args.target,
                _load_json(args.receipt),
            )
        elif args.command == "merge":
            result = {"commit_sha": store.merge(args.episode, args.left, args.right, message=args.message)}
        elif args.command == "checkpoint":
            result = {
                "commit_sha": store.checkpoint(
                    args.episode,
                    summary=args.summary,
                    manifest_sha=args.manifest_sha,
                    plan_sha=args.plan_sha,
                    open_decisions=args.open_decision,
                    resolved_decisions=args.resolved_decision,
                    summary_provenance=(
                        _load_json(args.summary_provenance)
                        if args.summary_provenance
                        else None
                    ),
                    branch=args.branch,
                )
            }
        elif args.command == "audit":
            result = store.audit(args.commit, strict=args.strict)
        elif args.command == "reconstruct":
            result = store.reconstruct(args.commit, args.level)
        elif args.command == "isolate":
            result = store.isolate_observe(
                args.commit,
                episode_id=args.episode,
                keep_worktree=args.keep_worktree,
                write_proof=Path(args.write_proof) if args.write_proof else None,
            )
        elif args.command == "guest-image":
            dest = Path(args.dest) if args.dest else Path(args.root) / DEFAULT_VM_IMAGE_REL
            result = provision_replay_guest_image(dest)
        elif args.command == "guest-probe":
            result = guest_environment_probe(repo)
        elif args.command == "guest-run":
            result = store.guest_run(
                args.commit,
                episode_id=args.episode,
                level=args.level,
                adapter=args.adapter,
                image=args.image,
                keep_guest=args.keep_guest,
                write_proof=Path(args.write_proof) if args.write_proof else None,
                host_mount=args.host_mount,
                cube_api_url=args.cube_api_url,
                cube_template_id=args.cube_template_id,
            )
        elif args.command == "sandbox":
            if args.execute and not args.episode:
                raise ValueError("executed R2 replay requires --episode")
            profile = _load_json(args.profile)
            result = store.sandbox_replay(
                args.commit,
                profile,
                execute=args.execute,
            )
            if args.execute and args.episode:
                result_blob = store.put_blob(result)
                source_commit = store.get_object(
                    store.read_ref(args.commit) or args.commit,
                    "commit",
                )["data"]
                event = store.append_event(
                    args.episode,
                    kind="verification.completed",
                    actor="sandbox",
                    payload_sha=result_blob,
                    topic=source_commit.get("topic"),
                    task="r2_sandbox_replay",
                    track=str(source_commit.get("track") or "process"),
                    repo_head=source_commit.get("repo_head"),
                    manifest_sha=source_commit.get("manifest_sha"),
                    context_plan_sha=source_commit.get("context_plan_sha"),
                    branch="replay-r2",
                )
                commit_sha = store.commit_events(
                    args.episode,
                    message=f"R2 sandbox {result.get('state')}",
                    actor="sandbox",
                    branch="replay-r2",
                    coverage={
                        "sandbox_profile": result.get("profile_sha"),
                        "sandbox_outcome": result.get("state"),
                    },
                )
                result["replay"] = {
                    "event_sha": event["event_sha"],
                    "commit_sha": commit_sha,
                }
        elif args.command == "fork":
            result = store.fork(args.start, args.branch, changes=args.change)
        elif args.command == "export":
            if args.redact != "share-safe":
                raise ValueError("only share-safe redaction profile is supported")
            result = store.redact_export(args.commit)
        elif args.command == "ledger":
            result = store.ledger_entry(args.episode, write=args.write)
        elif args.command == "canvas-index":
            result = store.canvas_index(
                write_cache=bool(getattr(args, "write_cache", False))
            )
        elif args.command == "canvas-ledger":
            result = store.canvas_ledger(
                args.episode,
                write_cache=bool(getattr(args, "write_cache", False)),
            )
        elif args.command == "retention-plan":
            result = store.retention_plan()
        else:
            result = store.fsck()
        _emit(result)
        return 0 if result.get("valid", True) else 1
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit({"schema": "ndf-replay-error/v1", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
