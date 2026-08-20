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
        self.assertEqual(enabled["new-proposal"]["reason"], "fresh")
        self.assertFalse(enabled["align-golden"]["enabled"])
        self.assertFalse(enabled["delegate-poc"]["enabled"])
        self.assertFalse(enabled["submit-process-improvement"]["enabled"])
        self.assertTrue(enabled["refresh-snapshot"]["enabled"])
        self.assertTrue(enabled["gate-pipeline"]["enabled"])
        self.assertTrue(enabled["binder-pipeline"]["enabled"])
        self.assertTrue(enabled["poc-prepare-baseline"]["enabled"])
        self.assertTrue(enabled["poc-measurement"]["enabled"])

    def test_space_repairs_explain_how_to_fill_gaps(self) -> None:
        spaces = workflow.attach_space_repairs(
            {
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
        self.assertIn("inspect-ledger", used)

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
        self.assertIn("BEGIN NDF GIT INPUT", prompt)
        git_at = prompt.index("BEGIN NDF GIT INPUT")
        self.assertLess(prompt.index("/ndf-poc-baseline"), git_at)

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
        api = (SRC / "api.ts").read_text(encoding="utf-8")
        self.assertIn("__NDF_REMOTE_URL__", api)
        self.assertIn("__NDF_BRANCH__", api)

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
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        design = source.split('space === "design"', 1)
        if len(design) == 2:
            design_block = design[1].split('space === "implementation"', 1)[0]
            self.assertNotIn('actionId="gate-pipeline"', design_block)
            self.assertNotIn('actionId="binder-pipeline"', design_block)
        command_block = source.split("OpenClaw Control", 1)[1]
        self.assertIn('actionId="gate-pipeline"', command_block)
        self.assertIn('actionId="binder-pipeline"', command_block)

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
        self.assertIn("kernelMap: true", source)
        self.assertIn("controlHealth: true", source)
        self.assertIn("!collapsed.kernelMap", source)
        self.assertIn("!collapsed.controlHealth", source)

    def test_standalone_builder_declares_offline_delivery(self) -> None:
        source = (COCKPIT / "build_standalone.py").read_text(encoding="utf-8")
        self.assertIn('"selfContained": True', source)
        self.assertIn('"runtimeNetworkRequired": False', source)

    def test_agents_and_replay_use_real_runtime_lenses(self) -> None:
        source = (SRC / "main.tsx").read_text(encoding="utf-8")
        self.assertIn('name: "Command Agent"', source)
        self.assertNotIn('name === "Canvas"', source)
        for lens in (
            "command-agent",
            "openclaw",
            "claude-code",
            "context-compiler",
        ):
            self.assertIn(f'value="{lens}"', source)
        self.assertIn('value="project"', source)
        self.assertIn('value="meta"', source)
        self.assertIn("filteredHops", source)
        self.assertIn("filteredTimeline", source)

    def test_replay_timeline_colors_actual_planes(self) -> None:
        source = (SRC / "charts" / "ReplayTimeline.tsx").read_text(encoding="utf-8")
        self.assertIn('.domain(["meta", "project"])', source)
        self.assertNotIn('.domain(["control", "business"', source)


if __name__ == "__main__":
    unittest.main()
