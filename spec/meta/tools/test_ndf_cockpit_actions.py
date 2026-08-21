#!/usr/bin/env python3
"""Closed NDF action catalog: enablement is snapshot-derived, UI cannot invent hops."""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
COCKPIT = TOOLS.parent / "cockpit"
SRC = COCKPIT / "src"

SPEC = importlib.util.spec_from_file_location("ndf_actions", TOOLS / "ndf_actions.py")
assert SPEC and SPEC.loader
actions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = actions
SPEC.loader.exec_module(actions)

WORKFLOW_SPEC = importlib.util.spec_from_file_location(
    "ndf_workflow_status_actions", TOOLS / "ndf_workflow_status.py"
)
assert WORKFLOW_SPEC and WORKFLOW_SPEC.loader
workflow = importlib.util.module_from_spec(WORKFLOW_SPEC)
sys.modules[WORKFLOW_SPEC.name] = workflow
WORKFLOW_SPEC.loader.exec_module(workflow)

FORBIDDEN_UI_PATTERNS = (
    r"R3 Fork",
    r"Replay diff",
    r"Delegate to OpenClaw",
    r"prepare-pack",
    r"open the Close page",
)


def _payload(**overrides: object) -> dict:
    base = {
        "schema": "ndf-workflow-canvas-snapshot/v1",
        "repoBranch": "cursor/ndf-meta-integrate-pev95-063a",
        "repoHead": "abc123",
        "repoRemote": "origin",
        "repoRemoteUrl": "https://github.com/example/hnsw-predictor-ndf.git",
        "repoUpstream": "origin/cursor/ndf-meta-integrate-pev95-063a",
        "git": {
            "remote": "origin",
            "remoteUrl": "https://github.com/example/hnsw-predictor-ndf.git",
            "branch": "cursor/ndf-meta-integrate-pev95-063a",
            "upstreamRef": "origin/cursor/ndf-meta-integrate-pev95-063a",
            "head": "abc123",
        },
        "projectionFreshness": {"state": "fresh"},
        "business": {
            "identity": {
                "name": "DiskHNSW",
                "goal": "g",
                "charterExists": True,
                "charterPath": "spec/00-charter/charter.md",
            },
            "performance": {"goldenHeadStatus": "aligned"},
            "focusedTopicId": "hotspot-optimization",
            "focusedTopic": {
                "id": "hotspot-optimization",
                "decision": {"selected": None},
                "spaces": {
                    "implementation": {"gaps": ["missing_baseline_workspace"]},
                    "test": {"gaps": ["numbers_pending"]},
                },
                "health": {"findings": []},
                "delegation": {
                    "static_preflight_passed": False,
                    "runtime_dispatch_ready": False,
                },
            },
            "topics": [{"id": "hotspot-optimization"}, {"id": "other-topic"}],
        },
        "control": {
            "genesis": {"accepted": True},
            "processHop": None,
            "metaGraph": {"checks": {}, "findings": []},
        },
        "replay": {
            "episodes": [{"id": "ep-1"}],
            "focused": {"id": "ep-1", "canRestoreRecord": False},
        },
    }
    base.update(overrides)
    return base


class ActionRegistryTest(unittest.TestCase):
    def test_registry_ids_unique_and_labeled(self) -> None:
        seen: set[str] = set()
        for item in actions.registry_actions():
            self.assertNotIn(item["id"], seen)
            seen.add(item["id"])
            self.assertTrue(item["label"])
            self.assertTrue(item["clauseRefs"])
            self.assertIn(
                item["dispatch"],
                {"composer", "openFile", "snapshot", "projection_only"},
            )
            self.assertIn(item["failClosed"], {"disable", "hide"})

    def test_stale_projection_disables_write_ctas(self) -> None:
        stale = _payload(projectionFreshness={"state": "stale_after_action"})
        enabled = actions.evaluate_enabled_actions(stale)
        self.assertFalse(enabled["new-proposal"]["enabled"])
        self.assertIn("fresh", enabled["new-proposal"]["reason"] or "")
        self.assertFalse(enabled["align-golden"]["enabled"])
        self.assertFalse(enabled["delegate-poc"]["enabled"])
        self.assertTrue(enabled["refresh-snapshot"]["enabled"])
        # Writable repairs requireFresh under ActionSpec — visible but not executable.
        self.assertFalse(enabled["gate-pipeline"]["enabled"])
        self.assertFalse(enabled["binder-pipeline"]["enabled"])
        self.assertFalse(enabled["poc-prepare-baseline"]["enabled"])
        self.assertFalse(enabled["poc-measurement"]["enabled"])

    def test_poc_measurement_enables_on_vs_unmentioned_finding(self) -> None:
        """Numbers already filled (no numbers_pending gap) but vs_unmentioned advisory."""
        payload = _payload(
            projectionFreshness={"state": "fresh"},
            business={
                "identity": {
                    "name": "DiskHNSW",
                    "goal": "g",
                    "charterExists": True,
                    "charterPath": "spec/00-charter/charter.md",
                },
                "performance": {"goldenHeadStatus": "aligned"},
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {
                    "id": "hotspot-optimization",
                    "decision": {"selected": None},
                    "spaces": {
                        "implementation": {"gaps": []},
                        "test": {"gaps": [], "ready": True},
                    },
                    "health": {
                        "findings": [
                            {
                                "kind": "vs_unmentioned",
                                "severity": "info",
                                "repair_owner": "claude-code",
                                "repair_task": "poc_measurement",
                            }
                        ]
                    },
                    "delegation": {
                        "static_preflight_passed": True,
                        "runtime_dispatch_ready": True,
                    },
                },
                "topics": [{"id": "hotspot-optimization"}],
            },
        )
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertTrue(enabled["poc-measurement"]["enabled"])
        self.assertIn("gapMeasurementWork", actions.registry_by_id()["poc-measurement"]["enableWhen"])
        # Without the finding (and without numbers_pending), measure stays off.
        payload["business"]["focusedTopic"]["health"]["findings"] = []
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertFalse(enabled["poc-measurement"]["enabled"])
        self.assertIn("gapMeasurementWork", enabled["poc-measurement"]["reason"] or "")

    def test_action_matrix_covers_writable_delegates(self) -> None:
        matrix = {row["id"]: row for row in actions.action_matrix()}
        for action_id in ("poc-measurement", "delegate-poc", "gate-pipeline", "new-proposal"):
            row = matrix[action_id]
            self.assertEqual(row["episodePolicy"], "required")
            self.assertIn(row["provider"], {"openclaw", "claude-code-acp"})
            self.assertTrue(row["requireFresh"])
            self.assertEqual(row["closeoutPolicy"], "transactional")
        self.assertFalse(matrix["guest-replay-hop"]["commanderSurface"])
        report = actions.validate_registry()
        self.assertTrue(report["valid"], report["errors"])

    def test_writable_prompts_require_episode_flag(self) -> None:
        payload = _payload(
            projectionFreshness={"state": "fresh"},
            business={
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {"id": "hotspot-optimization"},
                "topics": [{"id": "hotspot-optimization"}],
            },
        )
        prompt = actions.composer_prompt(
            "poc-measurement",
            payload,
            topic="hotspot-optimization",
            placeholders=True,
        )
        self.assertIn("--episode", prompt)
        self.assertIn("episode_policy=required", prompt)
        self.assertIn("repair-pack", prompt)

    def test_refresh_snapshot_does_not_default_probe_runtime(self) -> None:
        catalog = actions.registry_by_id()["refresh-snapshot"]
        self.assertFalse(catalog.get("probeRuntime"))

    def test_agents_page_maps_compiler_and_runtime_states(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        self.assertIn('probeMode: "light"', source)
        self.assertIn("not_probed", source)
        self.assertIn("Prefer pipeline probe status", source)
        self.assertIn("local ndf_context", source)
        self.assertNotIn(
            "focused?.agentRun?.status || snapshot?.runtime?.implementation?.status",
            source,
        )
        # Must not treat missing context_verify.valid as generic "blocked".
        self.assertIn('"not_compiled"', source)
        self.assertIn('"failed"', source)
        self.assertIn('"verified"', source)

    def test_absorbing_fresh_enables_product_and_process_writes(self) -> None:
        payload = _payload(
            absorbedActionId="action-1",
            evidenceGeneration="b" * 64,
            snapshotSha="b" * 64,
            projectionFreshness={
                "state": "stale_after_action",
                "latest_action": {
                    "action_id": "action-1",
                    "status": "finished",
                    "result": "success",
                    "evidence_generation": "c" * 64,
                },
            },
            business={
                "identity": {
                    "name": "DiskHNSW",
                    "goal": "g",
                    "charterExists": True,
                    "charterPath": "spec/00-charter/charter.md",
                },
                "performance": {"goldenHeadStatus": "docs_only_ahead"},
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {
                    "id": "hotspot-optimization",
                    "decision": {"selected": None},
                    "spaces": {
                        "implementation": {"gaps": []},
                        "test": {"gaps": []},
                    },
                    "health": {"findings": []},
                    "delegation": {
                        "static_preflight_passed": False,
                        "runtime_dispatch_ready": False,
                    },
                },
                "topics": [{"id": "hotspot-optimization"}],
            },
        )
        workflow.mark_canvas_fresh_if_absorbing(payload)
        self.assertEqual(payload["projectionFreshness"]["state"], "fresh")
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertTrue(enabled["new-proposal"]["enabled"])
        self.assertTrue(enabled["submit-process-improvement"]["enabled"])

    def test_space_repairs_explain_how_to_fill_gaps(self) -> None:
        spaces = workflow.attach_space_repairs(
            {
                "design": {"ready": False, "gaps": ["DESIGN.md"]},
                "implementation": {"ready": False, "gaps": ["missing_baseline_workspace"]},
                "test": {"ready": False, "gaps": ["numbers_pending"]},
            },
            {
                "findings": [
                    {
                        "kind": "missing_baseline_workspace",
                        "why_blocked": "缺少 Implementation 基线工作区",
                        "repair_owner": "claude-code",
                        "repair_task": "poc_prepare_baseline",
                        "allowed_write_root": "poc/hotspot-optimization/",
                    }
                ],
                "next_actions": [
                    {
                        "kind": "numbers_pending",
                        "task": "poc_measurement",
                        "label": "补测 / 写 DELTA",
                        "owner": "claude-code",
                        "allowed_write_root": "poc/hotspot-optimization/",
                    }
                ],
            },
            topic_id="hotspot-optimization",
        )
        design = spaces["design"]["repairs"][0]
        self.assertEqual(design["actionId"], "design-prepare")
        self.assertIn("准备设计文档", design["fix"])
        impl = spaces["implementation"]["repairs"][0]
        self.assertEqual(impl["actionId"], "poc-prepare-baseline")
        self.assertIn("基线准备", impl["fix"])
        self.assertIn("缺少 Implementation 基线工作区", impl["why"])
        test = spaces["test"]["repairs"][0]
        self.assertEqual(test["actionId"], "poc-measurement")
        self.assertIn("补测 / 写 DELTA", test["fix"])

    def test_empty_intent_does_not_clear_requires_intent(self) -> None:
        enabled = actions.evaluate_enabled_actions(_payload())
        self.assertTrue(enabled["new-proposal"]["enabled"])
        self.assertTrue(enabled["new-proposal"]["requiresIntent"])
        self.assertTrue(enabled["generate-next-step"]["requiresIntent"])
        self.assertTrue(enabled["submit-process-improvement"]["requiresIntent"])

    def test_delegate_poc_needs_decision_and_preflight(self) -> None:
        payload = _payload()
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertFalse(enabled["delegate-poc"]["enabled"])
        payload["business"]["focusedTopic"]["decision"]["selected"] = "implement"
        payload["business"]["focusedTopic"]["delegation"] = {
            "static_preflight_passed": True,
            "runtime_dispatch_ready": True,
        }
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertTrue(enabled["delegate-poc"]["enabled"])

    def test_new_genesis_disabled_when_accepted(self) -> None:
        payload = _payload()
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertFalse(enabled["new-genesis"]["enabled"])
        payload["control"]["genesis"]["accepted"] = False
        enabled = actions.evaluate_enabled_actions(payload)
        self.assertTrue(enabled["new-genesis"]["enabled"])

    def test_open_workbench_and_inspect_ledger_are_focus_hops(self) -> None:
        payload = _payload()
        workbench = actions.evaluate_action(
            actions.registry_by_id()["open-workbench"],
            payload,
            {"topicId": "other-topic"},
        )
        self.assertTrue(workbench["enabled"])
        same = actions.evaluate_action(
            actions.registry_by_id()["open-workbench"],
            payload,
            {"topicId": "hotspot-optimization"},
        )
        self.assertFalse(same["enabled"])
        ledger = actions.evaluate_action(
            actions.registry_by_id()["inspect-ledger"],
            payload,
            {"episodeId": "ep-2"},
        )
        self.assertTrue(ledger["enabled"])

    def test_canvas_snapshot_emits_enabled_actions(self) -> None:
        canvas = workflow.canvas_snapshot(
            {
                "generated_at": "2026-08-15T00:00:00Z",
                "repo_head": "abc",
                "repo_branch": "cursor/existing-target",
                "repo_remote": "origin",
                "repo_remote_url": "https://github.com/example/hnsw-predictor-ndf.git",
                "repo_upstream": "origin/cursor/existing-target",
                "snapshot_sha": "def",
                "evidence_generation": "def",
                "embedded_projection": {"status": "unknown", "verified_path": None},
                "payload_binding": {"repo_head": "abc", "source_generation_sha": "def"},
                "projection_freshness": {
                    "state": "unknown",
                    "latest_action": None,
                    "receipt_path": None,
                },
                "business": {
                    "identity": {
                        "name": "Demo",
                        "phase": "unknown",
                        "goal_summary": "goal",
                        "charter_path": "spec/00-charter/charter.md",
                        "charter_exists": True,
                        "scale_coverage": [],
                    },
                    "performance": {
                        "protocol": "sustained",
                        "baseline_id": "bl",
                        "trunk_sha": "abc",
                        "golden_head_status": "aligned",
                        "repo_head_full": "abc",
                        "status": "ok",
                        "configs": [],
                        "warnings": [],
                        "best_scenes": [],
                    },
                    "capabilities": [],
                    "topics": [],
                    "product_proposals": [],
                    "roadmap": [],
                    "risks": [],
                    "now_next_blocked": {"now": "x", "next": "y", "blocked": 0},
                },
                "control": {
                    "genesis": {
                        "project_maturity": "operational",
                        "accepted": True,
                        "genesis_trunk_sha": "abc",
                        "install_needed": False,
                        "kernel_installed": True,
                    },
                    "kernel_map": workflow.kernel_map(),
                    "process_proposals": [],
                    "process_hop": None,
                    "close": {"state_source": "tree", "topics": []},
                    "spec_health": {
                        "meta_clause_count": 1,
                        "next_actions": [],
                        "proposal_plane_warnings": [],
                    },
                    "gate_summary": {
                        "legacy_unknown_topics": 0,
                        "invalidated_receipts": 0,
                    },
                },
                "runtime": {
                    "implementation": {
                        "provider": "claude-code-acp",
                        "status": "idle",
                        "pipeline_reachable": False,
                        "default_session": None,
                        "active_runs": [],
                        "cli_available": False,
                        "doctor_ok": None,
                        "resume_available": None,
                        "probe_error": None,
                        "probe_note": None,
                        "workspace": {
                            "binding": {
                                "repo_root": "/tmp",
                                "state_path": ".openclaw/state.json",
                                "active_topic": None,
                            },
                            "state_exists": False,
                            "match": True,
                            "state": "ok",
                        },
                    },
                    "control": {
                        "provider": "openclaw",
                        "default_session_key": "agent:main:main",
                        "reachable": None,
                        "configured_session_visible": None,
                        "probe": None,
                        "workspace": {
                            "binding": {
                                "repo_root": "/tmp",
                                "state_path": ".openclaw/state.json",
                                "active_topic": None,
                            },
                            "state_exists": False,
                            "match": True,
                            "state": "ok",
                        },
                    },
                },
                "topics_detail": [],
                "replay": {
                    "schema": "ndf-replay-summary/v1",
                    "state": "not_initialized",
                    "fsck": None,
                    "episodes": [],
                },
            }
        )
        self.assertIn("enabledActions", canvas)
        self.assertEqual(canvas["repoBranch"], "cursor/existing-target")
        self.assertEqual(canvas["repoRemoteUrl"], "https://github.com/example/hnsw-predictor-ndf.git")
        self.assertEqual(canvas["git"]["upstreamRef"], "origin/cursor/existing-target")
        self.assertIn("refresh-snapshot", canvas["enabledActions"])
        self.assertFalse(canvas["enabledActions"]["new-proposal"]["enabled"])
        launcher = actions.canvas_launcher_snapshot(canvas)
        self.assertEqual(launcher["schema"], "ndf-workflow-canvas-launcher/v1")
        self.assertIn("refresh-snapshot", launcher["enabledActions"])
        self.assertNotIn("delegate-poc", launcher["enabledActions"])
        self.assertEqual(
            set(launcher["projectionFreshness"]),
            {"state", "snapshot_sha"},
        )
        self.assertFalse(launcher["commander"]["cloudIngress"])
        self.assertEqual(launcher["commander"]["bind"], "127.0.0.1")

    def test_cockpit_source_buttons_are_registered(self) -> None:
        if not SRC.is_dir():
            self.skipTest("cockpit src not present")
        registry_ids = set(actions.registry_by_id())
        used: set[str] = set()
        for path in SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'data-ndf-action=["\']([a-z0-9-]+)["\']', text):
                used.add(match.group(1))
            for match in re.finditer(r'actionId=["\']([a-z0-9-]+)["\']', text):
                used.add(match.group(1))
            naked = re.findall(r"<button(?![^>]*data-ndf-action)[^>]*>", text)
            self.assertFalse(naked, f"unregistered <button> in {path}: {naked}")
            for pattern in FORBIDDEN_UI_PATTERNS:
                self.assertIsNone(
                    re.search(pattern, text),
                    f"forbidden control {pattern!r} in {path}",
                )
        unknown = used - registry_ids
        self.assertFalse(unknown, f"UI references unregistered actions: {sorted(unknown)}")
        self.assertIn("open-workbench", used)
        self.assertIn("command-replay-run", used)
        self.assertIn("command-replay-compare", used)

    def test_standalone_templates_cover_every_non_projection_action(self) -> None:
        payload = _payload()
        for action in actions.registry_actions():
            if action["dispatch"] == "projection_only":
                continue
            response = actions.standalone_action_template(action["id"], payload)
            self.assertEqual(response["id"], action["id"])
            self.assertEqual(response["dispatch"], action["dispatch"])
            if action["dispatch"] in {"composer", "snapshot"}:
                self.assertIn(f"action_id={action['id']}", response["prompt"])
                self.assertNotIn("在当前 Cloud Agent 对话执行这个 NDF hop", response["prompt"])
                self.assertTrue(
                    response["prompt"].startswith(action["command"] + "\n"),
                    action["id"],
                )
                self.assertIn(f"skill={action['skill']}", response["prompt"])
                self.assertIn(f"tool={action['tool']}", response["prompt"])
                self.assertNotIn(
                    "Follow .cursor/skills/ndf-workflow-canvas/actions.md",
                    response["prompt"],
                )
            if action["dispatch"] == "openFile":
                self.assertTrue(response["path"])

    def test_composer_snapshot_actions_map_to_existing_command_and_skill(self) -> None:
        repo = TOOLS.parents[2]
        mapped = 0
        for action in actions.registry_actions():
            if action["dispatch"] in {"projection_only", "openFile"}:
                self.assertNotIn("command", action)
                self.assertNotIn("skill", action)
                self.assertNotIn("tool", action)
                continue
            self.assertEqual(action["dispatch"] in {"composer", "snapshot"}, True)
            command = action["command"]
            self.assertTrue(command.startswith("/ndf-"), action["id"])
            skill_path = repo / action["skill"]
            self.assertTrue(skill_path.is_file(), action["skill"])
            command_file = repo / ".cursor" / "commands" / f"{command[1:]}.md"
            self.assertTrue(command_file.is_file(), str(command_file))
            self.assertIn(command, command_file.read_text(encoding="utf-8"))
            self.assertTrue(action["tool"].startswith("python3 spec/meta/tools/"))
            mapped += 1
        self.assertGreaterEqual(mapped, 20)

    def test_composer_prompt_cites_slash_command_skill_and_cli(self) -> None:
        prompt = actions.composer_prompt("poc-prepare-baseline", _payload())
        self.assertTrue(prompt.startswith("/ndf-poc-baseline\n"))
        self.assertIn(
            "skill=.cursor/skills/ndf-workflow-canvas/workflows/poc-baseline.md",
            prompt,
        )
        self.assertIn(
            "tool=python3 spec/meta/tools/ndf_workflow_status.py repair-pack "
            "--task poc_prepare_baseline",
            prompt,
        )
        self.assertIn("delegate_to=claude-code-acp", prompt)
        self.assertIn("delegate_hook=dispatch-send", prompt)
        self.assertIn("MUST NOT perform the worker write", prompt)
        self.assertIn("Do not copy files", prompt)
        self.assertIn("BEGIN NDF GIT INPUT", prompt)
        git_at = prompt.index("BEGIN NDF GIT INPUT")
        self.assertLess(prompt.index("/ndf-poc-baseline"), git_at)

    def test_composer_prompt_openclaw_delegate_lines(self) -> None:
        prompt = actions.composer_prompt("gate-pipeline", _payload(), topic="hotspot-optimization")
        self.assertIn("delegate_to=openclaw", prompt)
        self.assertIn("delegate_hook=dispatch-send", prompt)
        self.assertIn("dispatch-send", prompt)
        self.assertIn("「派发」", prompt)
        self.assertNotIn("Actual openclaw.chat_send", prompt)
        self.assertNotIn("afterShellExecution hook", prompt)

    def test_standalone_intent_template_preserves_human_slot(self) -> None:
        response = actions.standalone_action_template("new-proposal", _payload())
        self.assertIn("BEGIN HUMAN PRODUCT INTENT", response["prompt"])
        self.assertIn("__NDF_HUMAN_INTENT__", response["prompt"])

    def test_composer_prompt_emits_remote_branch_input_block(self) -> None:
        prompt = actions.composer_prompt("new-proposal", _payload(), intent="ship")
        self.assertIn("BEGIN NDF GIT INPUT", prompt)
        self.assertIn("remote_url=https://github.com/example/hnsw-predictor-ndf.git", prompt)
        self.assertIn("remote_branch=cursor/ndf-meta-integrate-pev95-063a", prompt)
        self.assertIn("upstream_ref=origin/cursor/ndf-meta-integrate-pev95-063a", prompt)
        self.assertIn("END NDF GIT INPUT", prompt)
        self.assertIn("git fetch origin cursor/ndf-meta-integrate-pev95-063a", prompt)
        self.assertIn("git checkout cursor/ndf-meta-integrate-pev95-063a", prompt)
        self.assertIn("git pull --ff-only origin cursor/ndf-meta-integrate-pev95-063a", prompt)

    def test_composer_prompt_uses_request_remote_branch_override(self) -> None:
        prompt = actions.composer_prompt(
            "new-proposal",
            _payload(),
            intent="ship",
            remote="origin",
            remote_url="https://github.com/acme/repo.git",
            branch="cursor/human-specified-branch",
        )
        self.assertIn("remote_url=https://github.com/acme/repo.git", prompt)
        self.assertIn("remote_branch=cursor/human-specified-branch", prompt)
        self.assertIn("upstream_ref=origin/cursor/human-specified-branch", prompt)
        self.assertIn("git checkout cursor/human-specified-branch", prompt)

    def test_standalone_git_input_uses_placeholders(self) -> None:
        for action_id in ("new-proposal", "refresh-snapshot"):
            prompt = actions.standalone_action_template(action_id, _payload())["prompt"]
            self.assertIn("BEGIN NDF GIT INPUT", prompt)
            self.assertIn("remote=__NDF_REMOTE__", prompt)
            self.assertIn("remote_url=__NDF_REMOTE_URL__", prompt)
            self.assertIn("remote_branch=__NDF_BRANCH__", prompt)
            self.assertIn("upstream_ref=__NDF_UPSTREAM_REF__", prompt)
            self.assertIn("git fetch __NDF_REMOTE__ __NDF_BRANCH__", prompt)
            self.assertIn("Do not create, rename, or switch to a replacement feature branch.", prompt)

    def test_sanitize_git_remote_url_strips_credentials(self) -> None:
        self.assertEqual(
            workflow.sanitize_git_remote_url(
                "https://x-access-token:ghs_secret@github.com/org/repo.git"
            ),
            "https://github.com/org/repo.git",
        )
        self.assertEqual(
            workflow.sanitize_git_remote_url("git@github.com:org/repo.git"),
            "git@github.com:org/repo.git",
        )

    def test_header_exposes_editable_remote_branch_inputs(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        self.assertIn('className="git-inputs"', source)
        self.assertIn("远程仓库", source)
        self.assertIn("远程分支", source)
        self.assertIn("BEGIN NDF GIT INPUT", source)
        self.assertIn("自动刷新已开", source)
        self.assertIn("watchLiveSnapshot", source)
        self.assertIn("isStandaloneCommander", source)
        api = (SRC / "api.ts").read_text(encoding="utf-8")
        self.assertIn("__NDF_REMOTE_URL__", api)
        self.assertIn("__NDF_BRANCH__", api)
        self.assertIn('EventSource("/api/events")', api)
        self.assertIn("isStandaloneCommander", api)

    def test_composer_prompt_cites_local_serve_auto_reload(self) -> None:
        prompt = actions.composer_prompt("poc-prepare-baseline", _payload())
        self.assertIn("http://127.0.0.1:8765", prompt)
        self.assertIn("Do not curl localhost:8081", prompt)
        snap = actions.standalone_action_template("refresh-snapshot", _payload())["prompt"]
        self.assertIn("http://127.0.0.1:8765", snap)

    def test_get_refresh_reads_disk_snapshot_without_rebuild(self) -> None:
        import json
        import tempfile
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "ndf-canvas-snapshot.json"
            snap.write_text(
                json.dumps({"schema": "ndf-workflow-canvas-snapshot/v1", "payloadSha": "aaa"}),
                encoding="utf-8",
            )
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<html></html>", encoding="utf-8")
            state = {
                "topic": None,
                "replay_episode": None,
                "probe_runtime": False,
                "out": snap,
                "event_interval": 0.05,
            }
            handler = workflow.commander_http_handler(dist=dist, state=state)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address[:2]
                with urllib.request.urlopen(f"http://{host}:{port}/api/refresh", timeout=2) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload["payloadSha"], "aaa")
                snap.write_text(
                    json.dumps({"schema": "ndf-workflow-canvas-snapshot/v1", "payloadSha": "bbb-live"}),
                    encoding="utf-8",
                )
                with urllib.request.urlopen(f"http://{host}:{port}/snapshot.json", timeout=2) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload["payloadSha"], "bbb-live")
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_post_refresh_snapshot_does_not_force_probe(self) -> None:
        import json
        import tempfile
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "ndf-canvas-snapshot.json"
            initial = _payload(
                absorbedActionId="action-1",
                payloadSha="before",
                projectionFreshness={
                    "state": "stale_after_action",
                    "latest_action": {
                        "action_id": "action-1",
                        "status": "finished",
                        "result": "success",
                        "evidence_generation": "old",
                    },
                },
                business={
                    "identity": {
                        "name": "DiskHNSW",
                        "goal": "g",
                        "charterExists": True,
                        "charterPath": "spec/00-charter/charter.md",
                    },
                    "performance": {"goldenHeadStatus": "docs_only_ahead"},
                    "focusedTopicId": "hotspot-optimization",
                    "focusedTopic": {
                        "id": "hotspot-optimization",
                        "decision": {"selected": None},
                        "spaces": {
                            "implementation": {"gaps": []},
                            "test": {"gaps": []},
                        },
                        "health": {"findings": []},
                        "delegation": {
                            "static_preflight_passed": False,
                            "runtime_dispatch_ready": False,
                        },
                    },
                    "topics": [{"id": "hotspot-optimization"}],
                },
            )
            initial["enabledActions"] = actions.evaluate_enabled_actions(initial)
            snap.write_text(json.dumps(initial), encoding="utf-8")
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<html></html>", encoding="utf-8")
            state = {
                "topic": None,
                "replay_episode": None,
                "probe_runtime": False,
                "out": snap,
                "event_interval": 0.05,
            }
            probe_seen: list[bool] = []

            def fake_snapshot(topic, probe_runtime, replay_episode=None):
                probe_seen.append(bool(probe_runtime))
                return {"topic": topic, "probe": probe_runtime}

            def fake_canvas_snapshot(_raw):
                rebuilt = _payload(
                    absorbedActionId="action-1",
                    evidenceGeneration="new-gen",
                    snapshotSha="new-gen",
                    payloadSha="after-refresh",
                    projectionFreshness={
                        "state": "stale_after_action",
                        "latest_action": {
                            "action_id": "action-1",
                            "status": "finished",
                            "result": "success",
                            "evidence_generation": "old",
                        },
                    },
                    business={
                        "identity": {
                            "name": "DiskHNSW",
                            "goal": "g",
                            "charterExists": True,
                            "charterPath": "spec/00-charter/charter.md",
                        },
                        "performance": {"goldenHeadStatus": "docs_only_ahead"},
                        "focusedTopicId": "hotspot-optimization",
                        "focusedTopic": {
                            "id": "hotspot-optimization",
                            "decision": {"selected": None},
                            "spaces": {
                                "implementation": {"gaps": []},
                                "test": {"gaps": []},
                            },
                            "health": {"findings": []},
                            "delegation": {
                                "static_preflight_passed": False,
                                "runtime_dispatch_ready": False,
                            },
                        },
                        "topics": [{"id": "hotspot-optimization"}],
                    },
                )
                workflow.mark_canvas_fresh_if_absorbing(rebuilt)
                rebuilt["enabledActions"] = actions.evaluate_enabled_actions(rebuilt)
                return rebuilt

            handler = workflow.commander_http_handler(dist=dist, state=state)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address[:2]
                with (
                    patch.object(workflow, "snapshot", side_effect=fake_snapshot),
                    patch.object(
                        workflow, "canvas_snapshot", side_effect=fake_canvas_snapshot
                    ),
                    patch.object(workflow, "write_commander_snapshot"),
                ):
                    req = urllib.request.Request(
                        f"http://{host}:{port}/api/action",
                        data=json.dumps({"id": "refresh-snapshot"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(probe_seen, [False])
                self.assertEqual(
                    body["snapshot"]["projectionFreshness"]["state"], "fresh"
                )
                self.assertTrue(body["snapshot"]["enabledActions"]["new-proposal"]["enabled"])
                self.assertTrue(
                    body["snapshot"]["enabledActions"]["submit-process-improvement"][
                        "enabled"
                    ]
                )
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_sse_pushes_payload_sha_when_snapshot_file_changes(self) -> None:
        import json
        import tempfile
        import threading
        import time
        import urllib.request
        from http.server import ThreadingHTTPServer
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "ndf-canvas-snapshot.json"
            snap.write_text(
                json.dumps({"schema": "ndf-workflow-canvas-snapshot/v1", "payloadSha": "sha-one"}),
                encoding="utf-8",
            )
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<html></html>", encoding="utf-8")
            state = {
                "topic": None,
                "replay_episode": None,
                "probe_runtime": False,
                "out": snap,
                "event_interval": 0.05,
            }
            handler = workflow.commander_http_handler(dist=dist, state=state)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address[:2]
                conn = urllib.request.urlopen(f"http://{host}:{port}/api/events", timeout=5)
                shas: list[str] = []
                deadline = time.time() + 4
                while time.time() < deadline and len(shas) < 2:
                    line = conn.readline()
                    if not line:
                        break
                    text = line.decode("utf-8").strip()
                    if text.startswith("data: "):
                        shas.append(json.loads(text[6:])["payloadSha"])
                        if len(shas) == 1:
                            snap.write_text(
                                json.dumps(
                                    {
                                        "schema": "ndf-workflow-canvas-snapshot/v1",
                                        "payloadSha": "sha-two",
                                    }
                                ),
                                encoding="utf-8",
                            )
                conn.close()
                self.assertIn("sha-one", shas)
                self.assertIn("sha-two", shas)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_space_cards_and_pipelines_expose_repair_commands(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        self.assertIn("gap-recipe", source)
        self.assertIn("pipeline-checklist", source)
        self.assertIn('actionId="poc-prepare-baseline"', source)
        self.assertIn('actionId="poc-measurement"', source)
        registry = actions.registry_by_id()
        self.assertEqual(registry["poc-prepare-baseline"]["failClosed"], "disable")
        self.assertEqual(registry["poc-measurement"]["failClosed"], "disable")
        self.assertNotIn("fresh", registry["gate-pipeline"]["enableWhen"])
        self.assertNotIn("fresh", registry["poc-measurement"]["enableWhen"])

    def test_control_pipeline_actions_live_on_bottom_command_surface(self) -> None:
        registry = actions.registry_by_id()
        for action_id in ("gate-pipeline", "binder-pipeline", "binder-amend"):
            self.assertEqual(registry[action_id]["module"], "control-pipelines")
        design_action = registry["design-prepare"]
        self.assertEqual(design_action["module"], "space-design")
        self.assertEqual(design_action["failClosed"], "hide")
        self.assertIn("designDocsMissing", design_action["enableWhen"])
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        design = source.split('space === "design"', 1)
        self.assertEqual(len(design), 2)
        design_block = design[1].split('space === "implementation"', 1)[0]
        self.assertIn('actionId="design-prepare"', design_block)
        self.assertNotIn('actionId="gate-pipeline"', design_block)
        self.assertNotIn('actionId="binder-pipeline"', design_block)
        self.assertNotIn('actionId="binder-amend"', design_block)
        command_block = source.split("OpenClaw Control", 1)[1]
        self.assertIn('actionId="gate-pipeline"', command_block)
        self.assertIn('actionId="binder-pipeline"', command_block)

    def test_design_prepare_enablement_and_prompt(self) -> None:
        missing = _payload(
            business={
                "identity": {
                    "name": "DiskHNSW",
                    "goal": "g",
                    "charterExists": True,
                    "charterPath": "spec/00-charter/charter.md",
                },
                "performance": {"goldenHeadStatus": "aligned"},
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {
                    "id": "hotspot-optimization",
                    "decision": {"selected": None},
                    "spaces": {
                        "design": {"ready": False, "gaps": ["DESIGN.md"]},
                        "implementation": {"gaps": []},
                        "test": {"gaps": []},
                    },
                    "health": {"findings": []},
                    "delegation": {
                        "static_preflight_passed": False,
                        "runtime_dispatch_ready": False,
                    },
                },
                "topics": [{"id": "hotspot-optimization"}],
            }
        )
        enabled = actions.evaluate_enabled_actions(missing)
        self.assertTrue(enabled["design-prepare"]["enabled"])
        prompt = actions.composer_prompt("design-prepare", missing)
        self.assertIn("--focus-binder-facet design", prompt)
        self.assertIn("MUST NOT write GATES.md approved_by", prompt)

        gate_only = _payload(
            business={
                "identity": {
                    "name": "DiskHNSW",
                    "goal": "g",
                    "charterExists": True,
                    "charterPath": "spec/00-charter/charter.md",
                },
                "performance": {"goldenHeadStatus": "aligned"},
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {
                    "id": "hotspot-optimization",
                    "decision": {"selected": None},
                    "spaces": {
                        "design": {
                            "ready": False,
                            "gaps": ["gate:topic_review:pending"],
                        },
                        "implementation": {"gaps": []},
                        "test": {"gaps": []},
                    },
                    "health": {"findings": []},
                    "delegation": {
                        "static_preflight_passed": False,
                        "runtime_dispatch_ready": False,
                    },
                },
                "topics": [{"id": "hotspot-optimization"}],
            }
        )
        gate_enabled = actions.evaluate_enabled_actions(gate_only)
        self.assertFalse(gate_enabled["design-prepare"]["enabled"])
        self.assertEqual(gate_enabled["design-prepare"]["failClosed"], "hide")
        self.assertEqual(gate_enabled["design-prepare"]["reason"], "designDocsMissing")

        ready = _payload(
            business={
                "identity": {
                    "name": "DiskHNSW",
                    "goal": "g",
                    "charterExists": True,
                    "charterPath": "spec/00-charter/charter.md",
                },
                "performance": {"goldenHeadStatus": "aligned"},
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {
                    "id": "hotspot-optimization",
                    "decision": {"selected": None},
                    "spaces": {
                        "design": {"ready": True, "gaps": []},
                        "implementation": {"gaps": []},
                        "test": {"gaps": []},
                    },
                    "health": {"findings": []},
                    "delegation": {
                        "static_preflight_passed": False,
                        "runtime_dispatch_ready": False,
                    },
                },
                "topics": [{"id": "hotspot-optimization"}],
            }
        )
        ready_enabled = actions.evaluate_enabled_actions(ready)
        self.assertFalse(ready_enabled["design-prepare"]["enabled"])

    def test_control_ui_renders_operational_sections(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        for label in (
            "Genesis",
            "NDF 内核地图",
            "内核自洽性",
            "工作流演进",
            "执行面卫生",
        ):
            self.assertIn(label, source)
        for field in (
            "kernelMap?.seeds",
            "metaGraph?.checks",
            "processProposals",
            "legacyUnknownTopics",
            "invalidatedReceipts",
            "proposalPlaneWarnings",
        ):
            self.assertIn(field, source)
        self.assertIn("kernelMap: false", source)
        self.assertIn("controlHealth: false", source)
        self.assertIn("!collapsed.kernelMap", source)
        self.assertIn("!collapsed.controlHealth", source)
        self.assertGreaterEqual(source.count('actionId="run-ndf-control-check"'), 2)
        self.assertGreaterEqual(source.count('actionId="diagnose-advisor"'), 2)

    def test_standalone_builder_declares_offline_delivery(self) -> None:
        source = (COCKPIT / "build_standalone.py").read_text(encoding="utf-8")
        self.assertIn('"selfContained": True', source)
        self.assertIn('"runtimeNetworkRequired": False', source)

    def test_agents_and_replay_use_button_action_layout(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        self.assertIn('name: "Command Agent"', source)
        self.assertNotIn('name === "Canvas"', source)
        self.assertIn("command-replay-run", source)
        self.assertIn("command-replay-compare", source)
        self.assertIn("replay-compare-grid", source)
        self.assertNotIn("filteredTimeline", source)
        self.assertNotIn("ReplayTimeline", source)
        self.assertNotIn('value="meta"', source)
        self.assertIn("复制委派 Prompt · 不自动执行", source)
        self.assertIn("本按钮只打开文件，不派 Agent", source)

    def test_agents_page_does_not_navigate_to_replay(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        agents = source.split('tab === "agents"', 1)[1].split('tab === "replay"', 1)[0]
        self.assertNotIn('setTab("replay")', agents)
        self.assertNotIn('actionId="replay-agent-filter"', agents)
        replay = source.split('tab === "replay"', 1)[1]
        self.assertIn('actionId="command-replay-run"', replay)
        self.assertIn('actionId="command-replay-compare"', replay)
        self.assertNotIn('actionId="inspect-ledger"', replay)
        self.assertNotIn('actionId="guest-replay-hop"', replay)
        self.assertNotIn('actionId="guest-replay-prefix"', replay)
        registry = actions.registry_by_id()
        self.assertEqual(registry["guest-replay-hop"]["failClosed"], "hide")
        self.assertEqual(registry["guest-replay-prefix"]["failClosed"], "hide")
        self.assertEqual(registry["inspect-ledger"]["failClosed"], "hide")
        self.assertIn("command-replay-run", registry)
        self.assertIn("command-replay-compare", registry)

    def test_replay_timeline_file_optional(self) -> None:
        # D3 hop timeline is no longer on the Replay main path.
        path = SRC / "charts" / "ReplayTimeline.tsx"
        self.assertTrue(path.is_file() or not path.exists())

    def test_composer_prompts_bind_catalog_action_id_and_action_commit(self) -> None:
        payload = _payload()
        for action in actions.registry_actions():
            if action.get("dispatch") != "composer":
                continue
            aid = action["id"]
            prompt = actions.composer_prompt(
                aid,
                payload,
                intent="test intent",
                topic="hotspot-optimization",
                episode_id="ba-demo",
            )
            self.assertIn(f"catalog_action_id={aid}", prompt, aid)
            self.assertIn(f"--catalog-action-id {aid}", prompt, aid)
            if aid in actions.PACK_DELEGATE_ACTIONS:
                self.assertIn("delegate_hook=dispatch-send", prompt, aid)
                self.assertIn("dispatch-send --pack-file", prompt, aid)
                self.assertIn("「派发」", prompt, aid)
                self.assertNotIn(
                    "ndf_workflow_status.py action-commit",
                    prompt,
                    aid,
                )
                self.assertNotIn("afterShellExecution hook sends", prompt, aid)
            else:
                self.assertIn("ndf_workflow_status.py action-commit", prompt, aid)
                self.assertIn(actions.action_prompt_relpath(aid), prompt, aid)
            if action.get("tool"):
                # Unique tool line appears in header via dispatch_prompt_header.
                self.assertIn(f"tool={action['tool']}", prompt, aid)

    def test_shared_skill_prompts_differ_by_unique_cli(self) -> None:
        payload = _payload(
            control={
                "processHop": {
                    "focusedPath": "spec/meta/open/proposal-meta-x.md",
                }
            }
        )
        design = actions.composer_prompt("design-prepare", payload, topic="hotspot-optimization")
        binder = actions.composer_prompt("binder-pipeline", payload, topic="hotspot-optimization")
        amend = actions.composer_prompt("binder-amend", payload, topic="hotspot-optimization")
        self.assertIn("--focus-binder-facet design", design)
        self.assertIn("--task binder_pipeline", binder)
        self.assertNotIn("--focus-binder-facet design", binder)
        self.assertIn("--task binder_amend", amend)

        delegate = actions.composer_prompt("delegate-poc", payload, topic="hotspot-optimization")
        lease = actions.composer_prompt("prepare-acp-lease", payload, topic="hotspot-optimization")
        self.assertIn(" pack --topic ", delegate)
        self.assertIn("delegate_to=claude-code-acp", lease)
        self.assertIn("delegate_hook=dispatch-send", lease)
        self.assertIn("lease-record only", lease)
        self.assertIn("dispatch-send", lease)
        self.assertNotIn("Actual openclaw.chat_send", lease)

        next_step = actions.composer_prompt(
            "generate-next-step", payload, intent="promote", topic="hotspot-optimization"
        )
        close_hop = actions.composer_prompt("next-close-hop", payload, topic="hotspot-optimization")
        self.assertIn("BEGIN HUMAN POC DECISION", next_step)
        self.assertIn("close-plan", close_hop)
        self.assertIn("from selected_decision only", close_hop)

        repair = actions.composer_prompt("repair-kernel", payload)
        improve = actions.composer_prompt(
            "submit-process-improvement", payload, intent="tighten META"
        )
        self.assertIn("--origin health_finding", repair)
        self.assertIn("--origin human_intent", improve)

        topic = actions.composer_prompt("diagnose-topic", payload, topic="hotspot-optimization")
        control = actions.composer_prompt("run-ndf-control-check", payload)
        self.assertIn("topic-health", topic)
        self.assertIn("spec-health", control)
        self.assertNotIn("topic-health", control)

        land_c = actions.composer_prompt("land-confirm", payload)
        land_r = actions.composer_prompt("land-review", payload)
        self.assertIn("proposal_path=spec/meta/open/proposal-meta-x.md", land_c)
        self.assertIn("proposal_path=spec/meta/open/proposal-meta-x.md", land_r)
        self.assertIn("已确认", land_c)
        self.assertIn("已审核", land_r)

    def test_persist_action_prompt_and_begin_catalog_id(self) -> None:
        from unittest import mock

        prompt = actions.composer_prompt("align-golden", _payload())
        path = actions.persist_action_prompt("align-golden", prompt)
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), prompt if prompt.endswith("\n") else prompt + "\n")
        with mock.patch.object(workflow, "git_head", return_value="abc123deadbeef"):
            with mock.patch.object(workflow, "source_generation_sha", return_value="gensha"):
                with mock.patch.object(workflow, "append_action_receipt"):
                    with mock.patch.object(workflow, "ensure_host_pid_headroom", return_value=None):
                        begin = workflow.action_begin(
                            "align-golden",
                            None,
                            "wf-align-test-1",
                            catalog_action_id="align-golden",
                        )
        self.assertEqual(begin["catalog_action_id"], "align-golden")
        self.assertEqual(begin["status"], "started")
        self.assertEqual(begin["action_id"], "wf-align-test-1")
        self.assertEqual(begin["repo_head_before"], "abc123deadbeef")

        fake_receipts = [begin]
        store = workflow.ndf_replay.ReplayStore(workflow.ROOT)
        written_path = None

        def fake_write(_store, record):
            nonlocal written_path
            written_path = store.root / "button-actions" / f"{record['id']}.json"
            written_path.parent.mkdir(parents=True, exist_ok=True)
            written_path.write_text("{}", encoding="utf-8")
            return written_path

        with mock.patch.object(workflow, "read_action_receipts", return_value=fake_receipts):
            with mock.patch.object(workflow, "git_head", return_value="abc123deadbeef"):
                with mock.patch.object(workflow.subprocess, "run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                    with mock.patch.object(
                        workflow.ndf_replay, "list_button_actions", return_value=[]
                    ):
                        with mock.patch.object(
                            workflow.ndf_replay, "write_button_action", side_effect=fake_write
                        ):
                            first = workflow.action_commit(
                                begin["action_id"],
                                catalog_action_id="align-golden",
                                prompt=prompt,
                            )
        self.assertEqual(first.get("skip_reason"), "clean_worktree")
        self.assertEqual(first.get("catalog_action_id"), "align-golden")
        recorded = [
            {
                "id": first["button_action_id"],
                "workflowActionId": begin["action_id"],
                "baselineSha": "abc123deadbeef",
                "resultSha": "abc123deadbeef",
            }
        ]
        with mock.patch.object(workflow, "read_action_receipts", return_value=fake_receipts):
            with mock.patch.object(
                workflow.ndf_replay, "list_button_actions", return_value=recorded
            ):
                second = workflow.action_commit(
                    begin["action_id"],
                    catalog_action_id="align-golden",
                    prompt=prompt,
                )
        self.assertEqual(second.get("skip_reason"), "already_recorded")
        self.assertFalse(second.get("committed"))
        if written_path and written_path.is_file():
            written_path.unlink()


if __name__ == "__main__":
    unittest.main()
