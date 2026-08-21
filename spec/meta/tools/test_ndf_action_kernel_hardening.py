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
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(workflow, "ROOT", Path(tmp)):
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

    def test_waiting_human_pack_without_episode_returns_json(self) -> None:
        payload = {
            "task": "poc_measurement",
            "track": "poc",
            "provider": "claude-code-acp",
            "safe_to_dispatch": False,
            "safe_to_delegate": True,
            "runtime_dispatch_ready": True,
            "execution_capabilities_ready": False,
            "dispatch_state": "waiting_human",
            "blockers": ["waiting_human"],
            "allowed_write_root": "poc/demo/",
            "context_plan": {"privileges": {"allowed_write_roots": ["poc/demo/"]}},
        }
        out = workflow.bind_pack_to_episode(payload)
        self.assertEqual(out["dispatch_state"], "waiting_human")
        self.assertFalse(out["safe_to_dispatch"])

    def test_correlate_error_pack_from_repair_pack_command(self) -> None:
        receipts = [
            {
                "action_id": "uuid-1",
                "status": "started",
                "catalog_action_id": "poc-measurement",
                "operation": "poc_measurement",
            }
        ]
        pack = {
            "schema": "ndf-workflow-error/v1",
            "error": "writable pack requires explicit Replay Episode",
        }
        matched = dispatch.correlate_started_action(
            pack,
            command=(
                "python3 spec/meta/tools/ndf_workflow_status.py repair-pack "
                "--topic hotspot-optimization --task poc_measurement --json"
            ),
            receipts=receipts,
        )
        self.assertIsNotNone(matched)
        assert matched is not None
        self.assertEqual(matched["action_id"], "uuid-1")

    def test_capability_approve_finishes_started_and_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "actions.jsonl"
            (root / "tmp").mkdir()
            log.write_text(
                json.dumps(
                    {
                        "action_id": "act-wait",
                        "status": "started",
                        "catalog_action_id": "poc-measurement",
                        "operation": "poc_measurement",
                        "topic": "demo",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(workflow, "ROOT", root),
                mock.patch.object(workflow, "ACTION_LOG", log),
                mock.patch.object(
                    workflow,
                    "write_live_commander_snapshot",
                    return_value={"freshness": "fresh"},
                ),
                mock.patch.object(
                    workflow,
                    "action_finish",
                    return_value={"action_id": "act-wait", "status": "finished"},
                ) as finish,
            ):
                result = workflow.capability_approve(
                    "poc-measurement",
                    ["run_sustained", "sudo_cgroup"],
                    topic="demo",
                )
            finish.assert_called_once()
            self.assertEqual(result["finished_actions"], ["act-wait"])
            receipt = json.loads(
                (root / "tmp" / "ndf-capability-receipt.json").read_text(encoding="utf-8")
            )
            self.assertIn("run_sustained", receipt["approved_capabilities"])
            self.assertEqual(result["snapshot"]["freshness"], "fresh")

    def test_close_unsent_skips_in_flight_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            last = Path(tmp) / "last.json"
            last.write_text(
                json.dumps({"state": "awaiting_result", "action_id": "a1"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    workflow,
                    "read_action_receipts",
                    return_value=[{"action_id": "a1", "status": "started"}],
                ),
                mock.patch.object(dispatch, "DISPATCH_LAST", last),
            ):
                out = workflow.close_unsent_started_action()
            self.assertEqual(out["skipped"], "dispatch_in_flight")

    def test_close_unsent_skips_awaiting_human_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack_path = root / "tmp" / "ndf-dispatch-last-pack.json"
            pack_path.parent.mkdir(parents=True)
            pack_path.write_text(
                json.dumps(
                    {
                        "safe_to_dispatch": True,
                        "action_id": "a1",
                        "topic": "demo",
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(workflow, "ROOT", root),
                mock.patch.object(workflow, "DISPATCH_PACK_PATH", pack_path),
                mock.patch.object(
                    workflow,
                    "read_action_receipts",
                    return_value=[{"action_id": "a1", "status": "started"}],
                ),
                mock.patch.object(
                    dispatch, "DISPATCH_LAST", root / "missing-dispatch-last.json"
                ),
            ):
                out = workflow.close_unsent_started_action()
            self.assertEqual(out["skipped"], "awaiting_human_dispatch")
            self.assertEqual(out["action_id"], "a1")

    def test_measurement_prompt_requires_capability_approve_not_serve_restart(self) -> None:
        payload = {
            "projectionFreshness": {"state": "fresh"},
            "business": {
                "focusedTopicId": "hotspot-optimization",
                "focusedTopic": {"id": "hotspot-optimization"},
            },
        }
        prompt = actions.composer_prompt(
            "poc-measurement",
            payload,
            topic="hotspot-optimization",
            placeholders=True,
        )
        self.assertIn("capability-approve", prompt)
        self.assertIn("--action-id", prompt)
        self.assertIn("MUST NOT restart --serve", prompt)
        self.assertIn("dispatch-send --pack-file", prompt)
        self.assertIn("「派发」", prompt)
        self.assertIn("ndf-dispatch-notify", prompt)
        self.assertIn("MUST NOT send the human into the Claude Code ACP session", prompt)
        self.assertNotIn("afterShellExecution hook sends", prompt)


if __name__ == "__main__":
    unittest.main()
