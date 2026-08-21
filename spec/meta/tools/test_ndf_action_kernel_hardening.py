#!/usr/bin/env python3
"""Regression gates for Action Kernel / capability / closeout hardening."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(TOOLS))

import ndf_actions as actions
import ndf_dispatch_send as dispatch
import ndf_replay as replay
import ndf_workflow_evidence as evidence
import ndf_workflow_status as workflow


class ActionKernelHardeningTests(unittest.TestCase):
    def test_registry_v2_and_matrix(self) -> None:
        data = actions.load_registry()
        self.assertEqual(data["schema"], "ndf-action-registry/v2")
        report = actions.validate_registry()
        self.assertTrue(report["valid"], report["errors"])
        matrix = actions.action_matrix()
        self.assertGreaterEqual(len(matrix), 40)
        measurement = next(row for row in matrix if row["id"] == "poc-measurement")
        self.assertIn("poc/*/ndf/evidence/", measurement["mayWrite"])
        self.assertIn("sudo_cgroup", measurement["requiredCapabilities"])

    def test_action_button_fail_closed_default(self) -> None:
        source = (
            TOOLS.parent / "cockpit" / "src" / "ActionButton.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("enabled?.enabled === true", source)
        self.assertIn("missing_enabledActions", source)
        self.assertNotIn("enabled ?? true", source)

    def test_project_canvas_replay_strips_prompt_and_trims(self) -> None:
        huge = "P" * 8000
        episodes = []
        for idx in range(20):
            episodes.append(
                {
                    "id": f"ba-{idx}",
                    "actionId": "poc-measurement",
                    "baselineSha": "a" * 40,
                    "resultSha": "b" * 40,
                    "prompt": huge,
                    "happenedAt": f"2026-08-20T{idx:02d}:00:00Z",
                }
            )
        projected = replay.project_canvas_replay(
            {
                "mode": "button_actions",
                "episodes": episodes,
                "focused": {
                    "schema": "ndf-button-action-focused/v1",
                    "id": "ba-0",
                    "prompt": huge,
                    "baselineSha": "a" * 40,
                    "resultSha": "b" * 40,
                    "actionId": "poc-measurement",
                },
            }
        )
        self.assertNotIn("prompt", projected["focused"] or {})
        self.assertTrue(projected["focused"].get("promptSha"))
        for card in projected["episodes"]:
            self.assertNotIn("prompt", card)
            self.assertIn("promptSha", card)
        encoded = json.dumps(projected["episodes"], ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(encoded), replay.CANVAS_REPLAY_DIRECTORY_LIMIT)

    def test_measurement_capability_waiting_human(self) -> None:
        caps = workflow.evaluate_execution_capabilities(
            catalog_action_id="poc-measurement",
            task="poc_measurement",
            topic="demo",
            provider="claude-code-acp",
        )
        self.assertFalse(caps["execution_capabilities_ready"])
        self.assertIn("sudo_cgroup", caps["waiting_human"])
        with mock.patch.dict(os.environ, {"NDF_HARNESS_APPROVED": "1"}):
            ok = workflow.evaluate_execution_capabilities(
                catalog_action_id="poc-measurement",
                task="poc_measurement",
                topic="demo",
                provider="claude-code-acp",
            )
        self.assertTrue(ok["execution_capabilities_ready"])

    def test_pack_episode_id_prefers_replay_nested(self) -> None:
        pack = {"replay": {"episode_id": "ep-nested"}, "safe_to_dispatch": True}
        self.assertEqual(dispatch._pack_episode_id(pack), "ep-nested")
        msg = dispatch._build_worker_message(
            {
                **pack,
                "provider": "claude-code-acp",
                "task": "poc_measurement",
                "catalog_action_id": "poc-measurement",
                "action_id": "attempt-1",
            }
        )
        self.assertIn("episode_id=ep-nested", msg)
        self.assertIn("attempt_id=attempt-1", msg)

    def test_mark_fresh_absorbs_failed_terminal(self) -> None:
        payload = {
            "absorbedActionId": "a1",
            "projectionFreshness": {
                "state": "stale_after_action",
                "latest_action": {
                    "action_id": "a1",
                    "status": "finished",
                    "result": "failed",
                },
            },
        }
        workflow.mark_canvas_fresh_if_absorbing(payload)
        self.assertEqual(payload["projectionFreshness"]["state"], "fresh")
        self.assertEqual(payload["projectionFreshness"]["absorbed_terminal"], "failed")

    def test_workspace_identity_survives_head_drift(self) -> None:
        binding = {
            "repo_root": "/tmp/repo",
            "repo_head": "a" * 40,
            "active_topic": "hotspot-optimization",
        }
        persisted = {
            "workspace": {
                "repo_root": "/tmp/repo",
                "repo_head": "b" * 40,
                "active_topic": "hotspot-optimization",
            }
        }
        truth = evidence.workspace_truth(binding, persisted)
        self.assertTrue(truth["workspace_bound"])
        self.assertTrue(truth["execution_binding_stale"])


if __name__ == "__main__":
    unittest.main()
