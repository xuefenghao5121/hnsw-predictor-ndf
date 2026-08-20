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
        }
        with mock.patch.object(dispatch, "_closeout", return_value={"snapshot": {"exit_code": 0}}):
            with mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"):
                payload, code = dispatch.dispatch_send(pack, dry_run=False)
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertFalse(payload.get("sent"))

    def test_dry_run_safe_pack(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_prepare_baseline",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "b" * 64,
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


if __name__ == "__main__":
    unittest.main()
