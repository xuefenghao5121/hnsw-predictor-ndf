#!/usr/bin/env python3
"""Regression contract for ADR-META-004 Idea routing + control retirement."""

from __future__ import annotations

import unittest
from pathlib import Path

import ndf_poc_dispatch as dispatch
import ndf_workflow_status as workflow

ROOT = Path(__file__).resolve().parents[3]


class RetirementSurfaceTest(unittest.TestCase):
    def test_action_spec_module_deleted(self) -> None:
        self.assertFalse((ROOT / "spec" / "meta" / "tools" / "ndf_actions.py").is_file())
        # Inline empty stub only (no importable ActionSpec module).
        self.assertEqual(workflow.ndf_actions.registry_actions(), [])
        self.assertEqual(workflow.ndf_actions.evaluate_enabled_actions({"x": 1}), [])

    def test_action_apis_are_retired_stubs(self) -> None:
        begin = workflow.action_begin("refresh", "demo", "a1")
        finish = workflow.action_finish("a1", "success", [])
        commit = workflow.action_commit("a1")
        for payload in (begin, finish, commit):
            self.assertEqual(payload.get("schema"), "ndf-commander-retired/v1")
            self.assertTrue(payload.get("deprecated"))

    def test_cockpit_gone(self) -> None:
        self.assertFalse((ROOT / "spec" / "meta" / "cockpit").exists())

    def test_workflow_canvas_skill_gone(self) -> None:
        self.assertFalse((ROOT / ".cursor" / "skills" / "ndf-workflow-canvas").exists())
        self.assertTrue(
            (ROOT / ".cursor" / "skills" / "ndf-workflow" / "SKILL.md").is_file()
        )
        self.assertTrue(
            (ROOT / ".cursor" / "skills" / "ndf-workflow" / "genesis.md").is_file()
        )

    def test_replay_sandbox_skill_gone(self) -> None:
        self.assertFalse((ROOT / ".cursor" / "skills" / "ndf-replay-sandbox").exists())

    def test_idea_planes_never_share_roots(self) -> None:
        product = workflow.allowed_roots_for_idea_plane("product")
        process = workflow.allowed_roots_for_idea_plane("process")
        self.assertEqual(product, ["spec/open/"])
        self.assertEqual(process, ["spec/meta/open/"])
        self.assertTrue(set(product).isdisjoint(process))

    def test_ambiguous_does_not_default_poc(self) -> None:
        result = workflow.classify_idea_plane("随便看看")
        self.assertEqual(result["plane"], "ambiguous")
        self.assertIsNone(result["task"])

    def test_completion_ok_without_episode(self) -> None:
        pack = {
            "topic": "demo",
            "task": "poc_implementation",
            "run_id": "run-1",
        }
        completion = {
            "schema": "ndf-agent-completion/v1",
            "result": "success",
            "topic": "demo",
            "task": "poc_implementation",
            "run_id": "run-1",
        }
        detail = dispatch.validate_poc_completion_minimal(
            pack=pack, completion=completion
        )
        self.assertTrue(detail.get("ok"))
        soft = detail.get("soft_warnings") or []
        self.assertFalse(
            any(
                "episode" in str(w).lower() and "required" in str(w).lower()
                for w in soft
            )
        )


class SoftVsHardTest(unittest.TestCase):
    def test_soft_reasons_exclude_episode(self) -> None:
        # Episode/Replay completeness must not be hard blockers.
        for reason in (
            "replay_incomplete",
            "episode_missing",
            "projection_stale",
            "enabled_actions_missing",
        ):
            self.assertNotIn(reason, dispatch.POC_DISPATCH_SOFT_REASONS)


if __name__ == "__main__":
    unittest.main()
