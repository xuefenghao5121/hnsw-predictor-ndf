#!/usr/bin/env python3
"""Tests for pack → hook dispatch-send and gate expected SHA alignment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(TOOLS))

import ndf_context as context  # noqa: E402
import ndf_dispatch_send as dispatch  # noqa: E402


class ProposalPathsGateShaTests(unittest.TestCase):
    def test_stub_proposal_without_contract_is_skipped_when_real_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ndf = root / "poc" / "demo" / "ndf"
            proposals = ndf / "proposals"
            proposals.mkdir(parents=True)
            stub = proposals / "proposal-poc-demo.md"
            stub.write_text(
                "Canonical text: `spec/open/proposal-poc-demo.md`\nStub only.\n",
                encoding="utf-8",
            )
            real = root / "spec" / "open" / "proposal-poc-demo.md"
            real.parent.mkdir(parents=True)
            real.write_text(
                "<!-- ndf:gate-slice begin=proposal_contract -->\n"
                "body\n"
                "<!-- ndf:gate-slice end=proposal_contract -->\n",
                encoding="utf-8",
            )
            topic_text = (
                "See [proposal](spec/open/proposal-poc-demo.md) and "
                "ndf/proposals/proposal-poc-demo.md\n"
            )
            paths = context._proposal_paths(topic_text, ndf, root)
            self.assertEqual([p.resolve() for p in paths], [real.resolve()])


class DispatchSendTests(unittest.TestCase):
    def test_blocked_pack_does_not_send(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_prepare_baseline",
            "topic": "demo",
            "safe_to_dispatch": False,
            "blockers": ["context_verify_failed"],
            "pack_sha": "a" * 64,
            "base_sha": "b" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
        }
        with mock.patch.object(dispatch, "_closeout", return_value={"snapshot": {"exit_code": 0}}):
            with mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"):
                payload, code = dispatch.dispatch_send(pack, dry_run=False)
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertFalse(payload.get("sent"))

    def test_workspace_unbound_blocks_even_if_flag_true(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_measurement",
            "topic": "demo",
            "safe_to_dispatch": True,
            "blockers": [],
            "pack_sha": "c" * 64,
            "base_sha": "d" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": False},
        }
        with mock.patch.object(dispatch, "_closeout", return_value={"final_result": "failed"}):
            with mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"):
                payload, code = dispatch.dispatch_send(pack, dry_run=False)
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertIn("workspace_unbound", payload["blockers"])

    def test_dry_run_safe_pack(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_prepare_baseline",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "b" * 64,
            "base_sha": "e" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
        }
        with mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"):
            payload, code = dispatch.dispatch_send(pack, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "sent")
        self.assertTrue(payload.get("dry_run"))

    def test_extract_pack_from_shell_output(self) -> None:
        blob = json.dumps(
            {
                "schema": "ndf-implementation-repair-pack/v2",
                "provider": "claude-code-acp",
                "safe_to_dispatch": True,
            }
        )
        parsed = dispatch.extract_pack_from_shell_output("noise\n" + blob + "\n")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertTrue(parsed["safe_to_dispatch"])

    def test_extract_agent_completion_from_fence(self) -> None:
        text = (
            "notes\n```json\n"
            + json.dumps(
                {
                    "schema": "ndf-agent-completion/v1",
                    "result": "failed",
                    "status": "failed",
                    "blockers": ["sandbox_denied"],
                    "summary": "blocked",
                }
            )
            + "\n```\n"
        )
        completion, errors = dispatch.extract_agent_completion(text)
        self.assertIsNotNone(completion)
        assert completion is not None
        self.assertEqual(completion["result"], "failed")
        self.assertEqual(errors, [])

    def test_transport_ok_with_failed_receipt_is_task_failed(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_measurement",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "f" * 64,
            "base_sha": "1" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
            "replay": {"episode_id": "ep-demo"},
        }
        receipt = {
            "schema": "ndf-agent-completion/v1",
            "result": "failed",
            "status": "failed",
            "blockers": ["measurement_approval_required", "poc_write_denied"],
            "summary": "could not measure",
        }
        send_result = {
            "ok": True,
            "transport_ok": True,
            "state": "transport_acknowledged",
            "exit_code": 0,
            "session_id": "sess",
            "response_text": "```json\n" + json.dumps(receipt) + "\n```",
        }
        with (
            mock.patch.object(dispatch, "_send_acp", return_value=send_result),
            mock.patch.object(
                dispatch,
                "_closeout",
                return_value={"final_result": "failed", "completion": {"blockers": receipt["blockers"]}},
            ) as closeout,
            mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
        ):
            payload, code = dispatch.dispatch_send(
                pack, catalog_action_id="poc-measurement", action_id="act-1"
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(payload.get("transport_ok"))
        self.assertIn("measurement_approval_required", payload["blockers"])
        self.assertEqual(closeout.call_args.kwargs["result"], "failed")

    def test_transport_ok_without_receipt_is_task_failed(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_measurement",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "9" * 64,
            "base_sha": "2" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
        }
        send_result = {
            "ok": True,
            "transport_ok": True,
            "state": "transport_acknowledged",
            "exit_code": 0,
            "response_text": "done without receipt",
        }
        with (
            mock.patch.object(dispatch, "_send_acp", return_value=send_result),
            mock.patch.object(dispatch, "_closeout", return_value={"final_result": "failed"}),
            mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
        ):
            payload, code = dispatch.dispatch_send(pack)
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertIn("missing_agent_completion", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
