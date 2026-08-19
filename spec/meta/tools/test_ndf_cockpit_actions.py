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
                    "implementation": {"gaps": []},
                    "test": {"gaps": []},
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
            if action["dispatch"] == "openFile":
                self.assertTrue(response["path"])

    def test_standalone_intent_template_preserves_human_slot(self) -> None:
        response = actions.standalone_action_template("new-proposal", _payload())
        self.assertIn("BEGIN HUMAN PRODUCT INTENT", response["prompt"])
        self.assertIn("__NDF_HUMAN_INTENT__", response["prompt"])

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
