#!/usr/bin/env python3
"""Closed NDF commander action catalog (META-011).

The React+D3 cockpit MAY only render ids from action-registry.json.
Enablement is derived from a canvas snapshot, never from ad-hoc UI ifs.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

TOOLS = Path(__file__).resolve().parent
COCKPIT = TOOLS.parent / "cockpit"
REGISTRY_PATH = COCKPIT / "action-registry.json"
SNAPSHOT_OUT = TOOLS.parents[2] / "tmp" / "ndf-canvas-snapshot.json"

WRITE_DISPATCH = frozenset({"composer", "snapshot"})
LEGACY_EMBED_ACTION_IDS = frozenset({"refresh-snapshot"})


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "ndf-action-registry/v1":
        raise ValueError(f"unexpected action registry schema: {data.get('schema')}")
    ids = [item["id"] for item in data.get("actions") or []]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate action ids in registry")
    return data


def registry_actions() -> list[dict[str, Any]]:
    return list(load_registry()["actions"])


def registry_by_id() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in registry_actions()}


def forbidden_entries() -> list[dict[str, Any]]:
    return list(load_registry().get("forbidden") or [])


def _freshness_state(payload: Mapping[str, Any]) -> str:
    freshness = payload.get("projectionFreshness") or payload.get("projection_freshness") or {}
    if isinstance(freshness, Mapping):
        return str(freshness.get("state") or "unknown")
    return "unknown"


def _topic_ids(payload: Mapping[str, Any]) -> list[str]:
    business = payload.get("business") or {}
    ids: list[str] = []
    for item in business.get("topics") or []:
        if isinstance(item, Mapping) and item.get("id"):
            ids.append(str(item["id"]))
        elif isinstance(item, Mapping) and item.get("topic_id"):
            ids.append(str(item["topic_id"]))
    return ids


def _hop_ids(payload: Mapping[str, Any]) -> list[str]:
    replay = payload.get("replay") or {}
    ids: list[str] = []
    for item in replay.get("episodes") or []:
        if isinstance(item, Mapping) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


def _focused(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    business = payload.get("business") or {}
    topic = business.get("focusedTopic")
    return topic if isinstance(topic, Mapping) else None


def _git_field(payload: Mapping[str, Any], *keys: str, default: str = "") -> str:
    git = payload.get("git") if isinstance(payload.get("git"), Mapping) else {}
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip()
        if isinstance(git, Mapping) and git.get(key):
            return str(git.get(key)).strip()
    return default


def _git_execution_values(
    payload: Mapping[str, Any],
    *,
    remote: str | None = None,
    remote_url: str | None = None,
    branch: str | None = None,
    placeholders: bool = False,
) -> dict[str, str]:
    if placeholders:
        return {
            "remote": "__NDF_REMOTE__",
            "remote_url": "__NDF_REMOTE_URL__",
            "branch": "__NDF_BRANCH__",
            "upstream_ref": "__NDF_UPSTREAM_REF__",
            "head": _git_field(payload, "repoHead", "repo_head", "head", default="<unknown>")
            or "<unknown>",
        }
    remote_name = (remote or _git_field(payload, "repoRemote", "repo_remote", "remote", default="origin") or "origin")
    url = (
        remote_url
        or _git_field(
            payload,
            "repoRemoteUrl",
            "repo_remote_url",
            "remoteUrl",
            default="<unresolved-remote-url>",
        )
        or "<unresolved-remote-url>"
    )
    branch_name = (
        branch
        or _git_field(
            payload,
            "repoBranch",
            "repo_branch",
            "branch",
            default="<unresolved-target-branch>",
        )
        or "<unresolved-target-branch>"
    )
    upstream = _git_field(payload, "repoUpstream", "repo_upstream", "upstreamRef")
    if branch or remote or not upstream:
        unresolved = branch_name.startswith("<") or remote_name.startswith("<")
        upstream = "<unresolved-upstream-ref>" if unresolved else f"{remote_name}/{branch_name}"
    return {
        "remote": remote_name,
        "remote_url": url,
        "branch": branch_name,
        "upstream_ref": upstream,
        "head": _git_field(payload, "repoHead", "repo_head", "head", default="<unknown>") or "<unknown>",
    }


def _git_execution_contract(
    payload: Mapping[str, Any],
    *,
    remote: str | None = None,
    remote_url: str | None = None,
    branch: str | None = None,
    placeholders: bool = False,
) -> list[str]:
    values = _git_execution_values(
        payload,
        remote=remote,
        remote_url=remote_url,
        branch=branch,
        placeholders=placeholders,
    )
    return [
        "BEGIN NDF GIT INPUT",
        f"remote={values['remote']}",
        f"remote_url={values['remote_url']}",
        f"remote_branch={values['branch']}",
        f"upstream_ref={values['upstream_ref']}",
        f"snapshot_repo_head={values['head']}",
        "END NDF GIT INPUT",
        "The NDF GIT INPUT block is mandatory execution input from the commander.",
        "Use exactly that remote_url and remote_branch. This is the branch the human specified.",
        (
            "Keep the Command Agent workspace on exactly remote_branch. Do not create, rename, "
            "or switch to a replacement feature branch."
        ),
        (
            "An NDF runtime-lease worker MAY use its required isolated branch/worktree, but that "
            "worker branch MUST NOT replace the Command Agent target branch."
        ),
        "Required first commands before any other git mutation:",
        f"git fetch {values['remote']} {values['branch']}",
        f"git checkout {values['branch']}",
        f"git pull --ff-only {values['remote']} {values['branch']}",
        (
            "If the remote branch is missing, checkout is unsafe, or fast-forward fails, stop and "
            "report the blocker; never substitute a newly named branch."
        ),
    ]


def _space_gaps(payload: Mapping[str, Any], space: str) -> list[str]:
    focused = _focused(payload)
    if not focused:
        return []
    spaces = focused.get("spaces") or {}
    card = spaces.get(space) if isinstance(spaces, Mapping) else None
    if not isinstance(card, Mapping):
        return []
    return [str(item) for item in card.get("gaps") or []]


def _finding_kinds(payload: Mapping[str, Any]) -> set[str]:
    focused = _focused(payload)
    if not focused:
        return set()
    health = focused.get("health") or {}
    kinds: set[str] = set()
    for item in health.get("findings") or []:
        if isinstance(item, Mapping) and item.get("kind"):
            kinds.add(str(item["kind"]))
    return kinds


def _meta_graph(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    control = payload.get("control") or {}
    health = control.get("metaGraph") or control.get("spec_health") or {}
    return health if isinstance(health, Mapping) else {}


def _meta_graph_findings(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in _meta_graph(payload).get("findings") or [] if isinstance(item, Mapping)]


def _check_state(payload: Mapping[str, Any], name: str) -> str | None:
    checks = _meta_graph(payload).get("checks") or {}
    check = checks.get(name) if isinstance(checks, Mapping) else None
    if isinstance(check, Mapping):
        state = check.get("state")
        return str(state) if state is not None else None
    return None


def _selected_decision(payload: Mapping[str, Any]) -> str | None:
    focused = _focused(payload)
    if not focused:
        return None
    decision = focused.get("decision") or {}
    if isinstance(decision, Mapping):
        selected = decision.get("selected") or decision.get("selected_decision")
        return str(selected) if selected else None
    return None


def _delegation(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    focused = _focused(payload)
    if not focused:
        return {}
    data = focused.get("delegation") or {}
    return data if isinstance(data, Mapping) else {}


def _process_hop(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    control = payload.get("control") or {}
    hop = control.get("processHop") or control.get("process_hop")
    return hop if isinstance(hop, Mapping) else None


def _golden_status(payload: Mapping[str, Any]) -> str:
    business = payload.get("business") or {}
    performance = business.get("performance") or {}
    return str(performance.get("goldenHeadStatus") or performance.get("golden_head_status") or "")


PREDICATES = {
    "fresh": lambda payload, ctx: _freshness_state(payload) == "fresh",
    "charterExists": lambda payload, ctx: bool(
        ((payload.get("business") or {}).get("identity") or {}).get("charterExists", True)
    ),
    "goldenAlignedOrDocsOnly": lambda payload, ctx: _golden_status(payload)
    in {"aligned", "docs_only_ahead"},
    "goldenNotAligned": lambda payload, ctx: _golden_status(payload)
    not in {"aligned", ""},
    "focusedTopic": lambda payload, ctx: _focused(payload) is not None,
    "topicNotFocused": lambda payload, ctx: (
        bool(ctx.get("topicId"))
        and ctx.get("topicId") != ((payload.get("business") or {}).get("focusedTopicId"))
        if ctx.get("topicId")
        else any(
            topic_id != ((payload.get("business") or {}).get("focusedTopicId"))
            for topic_id in _topic_ids(payload)
        )
    ),
    "gapMissingBaseline": lambda payload, ctx: "missing_baseline_workspace"
    in _space_gaps(payload, "implementation"),
    "gapNumbersPending": lambda payload, ctx: "numbers_pending"
    in _space_gaps(payload, "test"),
    "findingIsolation": lambda payload, ctx: any(
        "isolation" in kind or kind in {"trunk_write", "poc_isolation"}
        for kind in _finding_kinds(payload)
    ),
    "selectedImplementOrExplore": lambda payload, ctx: _selected_decision(payload)
    in {"implement", "continue_exploring"},
    "staticPreflight": lambda payload, ctx: bool(
        _delegation(payload).get("static_preflight_passed")
        or _delegation(payload).get("staticPreflightPassed")
    ),
    "runtimeDispatchReady": lambda payload, ctx: bool(
        _delegation(payload).get("runtime_dispatch_ready")
        or _delegation(payload).get("runtimeDispatchReady")
    ),
    "runtimeNotReady": lambda payload, ctx: not (
        _delegation(payload).get("runtime_dispatch_ready")
        or _delegation(payload).get("runtimeDispatchReady")
    ),
    "closeSelected": lambda payload, ctx: _selected_decision(payload)
    in {"reject", "promote", "partial"},
    "genesisNotAccepted": lambda payload, ctx: not bool(
        ((payload.get("control") or {}).get("genesis") or {}).get("accepted")
    ),
    "specHealthFindings": lambda payload, ctx: any(
        item.get("severity") in {"error", "warning"} or item.get("kind")
        for item in _meta_graph_findings(payload)
    ),
    "productGraphFinding": lambda payload, ctx: _check_state(payload, "product_graph")
    == "failed",
    "binderHealthActivePoc": lambda payload, ctx: _check_state(payload, "binder_health")
    not in {None, "not_applicable", "passed", "n/a", "not_run"},
    "processHopConfirm": lambda payload, ctx: (_process_hop(payload) or {}).get("hop")
    in {"waiting_confirm", "confirm_land"},
    "processHopReview": lambda payload, ctx: (_process_hop(payload) or {}).get("hop")
    in {"waiting_review", "review", "implemented_pending_review"},
    "hopNotFocused": lambda payload, ctx: (
        bool(ctx.get("episodeId"))
        and ctx.get("episodeId")
        != (((payload.get("replay") or {}).get("focused") or {}).get("id"))
        if ctx.get("episodeId")
        else any(
            hop_id != (((payload.get("replay") or {}).get("focused") or {}).get("id"))
            for hop_id in _hop_ids(payload)
        )
    ),
    "canRestoreRecord": lambda payload, ctx: bool(
        ((payload.get("replay") or {}).get("focused") or {}).get("canRestoreRecord")
    ),
    "timelineStepSelected": lambda payload, ctx: (
        ctx.get("timelineStep") is not None
        if "timelineStep" in ctx
        else bool(((payload.get("replay") or {}).get("focused") or {}).get("timeline"))
    ),
}


def predicate_holds(name: str, payload: Mapping[str, Any], ctx: Mapping[str, Any] | None) -> bool:
    fn = PREDICATES.get(name)
    if fn is None:
        raise ValueError(f"unknown enableWhen predicate: {name}")
    return bool(fn(payload, ctx or {}))


def evaluate_action(
    action: Mapping[str, Any],
    payload: Mapping[str, Any],
    ctx: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(ctx or {})
    reasons: list[str] = []
    enabled = True
    for name in action.get("enableWhen") or []:
        if not predicate_holds(str(name), payload, context):
            enabled = False
            reasons.append(name)
    if action.get("dispatch") in WRITE_DISPATCH and "fresh" in (action.get("enableWhen") or []):
        if _freshness_state(payload) != "fresh":
            enabled = False
            if "fresh" not in reasons:
                reasons.append(_freshness_state(payload) or "unknown")
    return {
        "id": action["id"],
        "enabled": enabled,
        "reason": None if enabled else "+".join(reasons) or "fail_closed",
        "requiresIntent": bool(action.get("requiresIntent")),
        "dispatch": action.get("dispatch"),
        "failClosed": action.get("failClosed") or "disable",
        "label": action.get("label"),
        "humanPhrase": action.get("humanPhrase"),
        "operation": action.get("operation"),
        "task": action.get("task"),
        "tab": action.get("tab"),
        "module": action.get("module"),
    }


def evaluate_enabled_actions(
    payload: Mapping[str, Any],
    ctx: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for action in registry_actions():
        evaluated = evaluate_action(action, payload, ctx)
        result[action["id"]] = {
            "enabled": evaluated["enabled"],
            "reason": evaluated["reason"],
            "requiresIntent": evaluated["requiresIntent"],
            "dispatch": evaluated["dispatch"],
            "failClosed": evaluated["failClosed"],
        }
    return result


def canvas_launcher_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Legacy embedded receipt projection; not a visual or command surface."""
    business = payload.get("business") or {}
    identity = business.get("identity") or {}
    enabled = payload.get("enabledActions") or {}
    stub_enabled = {
        key: value
        for key, value in enabled.items()
        if key in LEGACY_EMBED_ACTION_IDS
    }
    if not stub_enabled:
        stub_enabled = {
            key: value
            for key, value in evaluate_enabled_actions(payload).items()
            if key in LEGACY_EMBED_ACTION_IDS
        }
    fresh = payload.get("projectionFreshness") or {}
    now_next = business.get("nowNextBlocked") or {}
    return {
        "schema": "ndf-workflow-canvas-launcher/v1",
        "generatedAt": payload.get("generatedAt"),
        "repoHead": payload.get("repoHead"),
        "snapshotSha": payload.get("snapshotSha"),
        "payloadSha": payload.get("payloadSha"),
        "absorbedActionId": payload.get("absorbedActionId"),
        "projectionFreshness": {
            "state": fresh.get("state"),
            "snapshot_sha": fresh.get("snapshot_sha"),
        },
        "business": {
            "identity": {
                "name": identity.get("name"),
                "goal": identity.get("goal"),
                "charterExists": identity.get("charterExists"),
            },
            "nowNextBlocked": {
                "now": now_next.get("now"),
                "next": now_next.get("next"),
                "blocked": now_next.get("blocked"),
            },
        },
        "enabledActions": stub_enabled,
        "commander": {
            "outPath": "tmp/ndf-canvas-snapshot.json",
            "bind": "127.0.0.1",
            "port": 8765,
            "cloudIngress": False,
            "serveCommand": (
                "python3 spec/meta/tools/ndf_workflow_status.py snapshot "
                "--serve --format canvas-json --json"
            ),
        },
    }


def dispatch_prompt_header(action: Mapping[str, Any]) -> list[str]:
    """Slash command + skill path + unique CLI. No actions.md fallback."""
    command = action.get("command")
    skill = action.get("skill")
    tool = action.get("tool")
    if not command or not skill or not tool:
        raise ValueError(f"{action.get('id')} missing command/skill/tool mapping")
    return [str(command), f"skill={skill}", f"tool={tool}"]


def composer_prompt(
    action_id: str,
    payload: Mapping[str, Any],
    *,
    intent: str = "",
    topic: str | None = None,
    episode_id: str | None = None,
    remote: str | None = None,
    remote_url: str | None = None,
    branch: str | None = None,
    placeholders: bool = False,
) -> str:
    action = registry_by_id().get(action_id)
    if action is None:
        raise ValueError(f"unregistered action: {action_id}")
    if action.get("dispatch") != "composer":
        raise ValueError(f"{action_id} is not a composer dispatch")
    focused = _focused(payload) or {}
    topic_id = topic or focused.get("id") or payload.get("business", {}).get("focusedTopicId")
    hop = _process_hop(payload) or {}
    phrase = action.get("humanPhrase") or ""
    click_rule = (
        "Button click is not approval. Wait for the exact human phrase "
        f"`{phrase}` before writing receipts."
        if phrase
        else "Button click is not a human gate."
    )
    lines = [
        *dispatch_prompt_header(action),
        *_git_execution_contract(
            payload,
            remote=remote,
            remote_url=remote_url,
            branch=branch,
            placeholders=placeholders,
        ),
        "0. EXECUTE now. Do not explain this template or stop after newComposerChat.",
        "This Composer task is an NDF commander dispatch from the closed action catalog.",
        f"action_id={action_id}",
        f"label={action.get('label')}",
        f"operation={action.get('operation')}",
        f"clauses={', '.join(action.get('clauseRefs') or [])}",
        f"Follow {action.get('skill')} and {action.get('command')}.",
        click_rule,
        "Wrap mutating work: action-begin → operation → action-finish → snapshot --out tmp/ndf-canvas-snapshot.json",
        (
            "If snapshot --serve is running at http://127.0.0.1:8765 on this machine, "
            "that page auto-reloads the written snapshot. Do not curl localhost:8081. "
            "htmlpreview or docs/ndf-commander.html is static: rebuild HTML then refresh the browser."
        ),
        "MUST NOT write .openclaw/state.json from Cursor. MUST NOT invent 已确认 / TOPIC已审核 / 可以开始实现.",
    ]
    if action_id == "new-proposal":
        lines.append("Write the exact human product intent below to tmp/ndf-product-intent-<action_id>.md")
        lines.append("BEGIN HUMAN PRODUCT INTENT")
        lines.append(intent.strip())
        lines.append("END HUMAN PRODUCT INTENT")
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py control-pack "
            "--task control_proposal --intent-file <tmp-file> --json"
        )
        lines.append("MUST NOT create poc/ before 已确认. MUST NOT write spec/meta/open/.")
    elif action_id == "align-golden":
        lines.append("action-begin --operation align-golden")
        lines.append("If Trunk src/include/tests changed since Golden: re-run Golden matrix.")
        lines.append("Docs-only ahead: do not re-run; refresh snapshot.")
    elif action_id == "submit-process-improvement":
        lines.append("Write exact META intent to tmp/ndf-process-intent-<action_id>.md")
        lines.append("BEGIN HUMAN META INTENT")
        lines.append(intent.strip())
        lines.append("END HUMAN META INTENT")
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py project-control-pack "
            "--task ndf_improvement_proposal --origin human_intent "
            "--intent-file <tmp-file> --episode <id> --json"
        )
        lines.append("Draft spec/meta/open/ only. Status: Pending confirmation.")
    elif action_id in {"land-confirm", "land-review"}:
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py project-control-pack "
            f"--task ndf_improvement_land --proposal {hop.get('focusedPath') or '<path>'} "
            "--episode <id> --json"
        )
        lines.append(f"Wait for exact phrase: {phrase}")
    elif action_id == "generate-next-step":
        lines.append(f"topic={topic_id}")
        lines.append("BEGIN HUMAN POC DECISION")
        lines.append(intent.strip())
        lines.append("END HUMAN POC DECISION")
        lines.append("Map text to selected_decision. Empty MUST NOT default to continue_exploring.")
        lines.append("Do not delegate implementation from this hop.")
        lines.append(
            "If selected_decision is reject|promote|partial, run "
            f"python3 spec/meta/tools/ndf_close.py plan --topic {topic_id} --mode <mode> "
            "(not silent promote). Else do not run ndf_close."
        )
    elif action_id == "delegate-poc":
        lines.append(
            f"python3 spec/meta/tools/ndf_workflow_status.py pack --topic {topic_id} "
            "--episode <id> --json"
        )
        lines.append("Require static_preflight_passed and runtime_dispatch_ready. Then acp-delegate.md#poc.")
        lines.append("POST_DISPATCH_SYNC. Worker markdown is not the command surface.")
    elif action.get("task") in {
        "gate_pipeline",
        "binder_pipeline",
        "binder_amend",
        "control_proposal",
    }:
        lines.append(
            f"python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic {topic_id} "
            f"--task {action.get('task')} --json"
        )
        lines.append("Actual openclaw.chat_send. Composer creation alone is not acknowledged.")
    elif action.get("task") in {
        "poc_prepare_baseline",
        "poc_isolation_repair",
        "poc_measurement",
    }:
        lines.append(
            f"python3 spec/meta/tools/ndf_workflow_status.py repair-pack --topic {topic_id} "
            f"--task {action.get('task')} --json"
        )
    elif action_id in {"guest-replay-hop", "guest-replay-prefix"}:
        hop_id = episode_id or ((payload.get("replay") or {}).get("focused") or {}).get("id")
        lines.append(
            "python3 spec/meta/tools/ndf_replay.py guest-run --adapter vm "
            f"--episode {hop_id} --commit <sha>"
        )
        lines.append("Proof ndf-replay-guest-proof/v1 adapter=vm. MUST NOT host-mount live repo_root.")
    elif action_id == "prepare-acp-lease":
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py pack "
            f"--topic {topic_id} --episode <id> --json"
        )
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py lease-record "
            "--file tmp/lease.json --episode <id> --json"
        )
        lines.append("context-verify + full handshake + lease-record. Do not start implementation.")
        lines.append("Follow .cursor/skills/ndf-workflow-canvas/acp-delegate.md runtime lease.")
    elif action_id == "next-close-hop":
        lines.append(f"topic={topic_id}")
        lines.append(
            "python3 spec/meta/tools/ndf_close.py plan "
            f"--topic {topic_id} --mode <promote|partial|reject>"
        )
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py close-plan "
            f"--topic {topic_id} --mode <mode> --json"
        )
        lines.append("Not silent promote. Follow close-console.md. Wait for exact phrase 已审核.")
    elif action_id == "new-genesis":
        lines.append("python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json")
        lines.append("Draft spec/open/proposal-project-genesis.md track=bootstrap.")
        lines.append("Stop at IDEA已审核. Follow .cursor/skills/ndf-workflow-canvas/genesis.md.")
    elif action_id == "run-ndf-control-check":
        lines.append("python3 spec/meta/tools/ndf_workflow_status.py spec-health --json")
        lines.append("Render plane-routed findings. Do not repair. Do not treat product/binder failures as process proposals.")
    elif action_id == "diagnose-topic":
        lines.append("python3 spec/meta/tools/ndf_workflow_status.py spec-health --json")
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py topic-health "
            f"--topic {topic_id} --json"
        )
        lines.append("Do not repair. Route findings to space cards or page-bottom decision.")
    elif action_id == "diagnose-advisor":
        lines.append("python3 spec/meta/tools/ndf_workflow_status.py spec-health --json")
        lines.append("python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit")
        lines.append("Read-only. Never apply. Never copy product clauses or POC binder fields into spec/meta/.")
    elif action_id == "repair-kernel":
        lines.append(
            "python3 spec/meta/tools/ndf_workflow_status.py project-control-pack "
            "--task ndf_improvement_proposal --origin health_finding "
            "--episode <id> --json"
        )
        lines.append("Draft spec/meta/open/ only. Status: Pending confirmation. Actual openclaw.chat_send.")
    else:
        raise ValueError(f"composer action has no prompt body: {action_id}")
    if action.get("mustNotWrite"):
        lines.append("MUST NOT write: " + ", ".join(action["mustNotWrite"]))
    return "\n".join(lines) + "\n"


def standalone_action_template(
    action_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the canonical static-commander response for one catalog action."""
    action = registry_by_id().get(action_id)
    if action is None:
        raise ValueError(f"unregistered action: {action_id}")
    dispatch = action.get("dispatch")
    if dispatch == "composer":
        return {
            "id": action_id,
            "dispatch": dispatch,
            "prompt": composer_prompt(
                action_id,
                payload,
                intent="__NDF_HUMAN_INTENT__",
                topic="__NDF_TOPIC__",
                episode_id="__NDF_EPISODE__",
                placeholders=True,
            ),
        }
    if dispatch == "openFile":
        return {
            "id": action_id,
            "dispatch": dispatch,
            "path": open_file_path(action_id, payload),
        }
    if dispatch == "snapshot":
        topic = "__NDF_TOPIC__"
        episode = "__NDF_EPISODE__"
        command = {
            "refresh-snapshot": (
                "python3 spec/meta/tools/ndf_workflow_status.py snapshot "
                "--out tmp/ndf-canvas-snapshot.json --probe-runtime --json"
            ),
            "open-workbench": (
                "python3 spec/meta/tools/ndf_workflow_status.py snapshot "
                f"--out tmp/ndf-canvas-snapshot.json --topic {topic} --json"
            ),
            "refresh-topic": (
                "python3 spec/meta/tools/ndf_workflow_status.py snapshot "
                f"--out tmp/ndf-canvas-snapshot.json --topic {topic} --json"
            ),
            "inspect-ledger": (
                "python3 spec/meta/tools/ndf_workflow_status.py snapshot "
                f"--out tmp/ndf-canvas-snapshot.json --replay-episode {episode} --json"
            ),
        }.get(action_id)
        if command is None:
            raise ValueError(f"snapshot action has no static command: {action_id}")
        prompt = "\n".join(
            [
                *dispatch_prompt_header(action),
                *_git_execution_contract(payload, placeholders=True),
                "0. EXECUTE now. Do not explain this template.",
                "This task is an NDF commander snapshot dispatch from the closed action catalog.",
                f"action_id={action_id}",
                f"label={action.get('label')}",
                f"operation={action.get('operation')}",
                f"clauses={', '.join(action.get('clauseRefs') or [])}",
                f"Follow {action.get('skill')} and {action.get('command')}.",
                "Button click is not a human gate.",
                (
                    "python3 spec/meta/tools/ndf_workflow_status.py action-begin "
                    f"--operation {action.get('operation')} --topic {topic} --json"
                ),
                command,
                (
                    "If snapshot --serve is running at http://127.0.0.1:8765 on this machine, "
                    "that page auto-reloads tmp/ndf-canvas-snapshot.json. Do not curl localhost:8081."
                ),
                "python3 spec/meta/cockpit/build_standalone.py",
                "Record action-finish success|failed after the operation.",
                "MUST NOT write .openclaw/state.json from Cursor.",
            ]
        )
        return {"id": action_id, "dispatch": dispatch, "prompt": prompt + "\n"}
    return {"id": action_id, "dispatch": "projection_only"}


def open_file_path(action_id: str, payload: Mapping[str, Any]) -> str | None:
    focused = _focused(payload) or {}
    topic_id = focused.get("id") or (payload.get("business") or {}).get("focusedTopicId")
    identity = (payload.get("business") or {}).get("identity") or {}
    mapping = {
        "open-charter": identity.get("charterPath") or "spec/00-charter/charter.md",
        "open-golden": "golden-baseline.md",
        "open-topic": f"poc/{topic_id}/ndf/TOPIC.md" if topic_id else None,
        "open-delta": f"poc/{topic_id}/ndf/DELTA.md" if topic_id else None,
        "open-language-md": "spec/meta/language.md",
        "open-process-md": "spec/meta/process.md",
        "open-meta-readme": "spec/meta/README.md",
    }
    return mapping.get(action_id)
