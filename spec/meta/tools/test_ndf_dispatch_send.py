#!/usr/bin/env python3
"""Tests for pack → hook dispatch-send and gate expected SHA alignment."""

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

    def test_waiting_human_closeout_is_cancelled(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_measurement",
            "topic": "demo",
            "safe_to_dispatch": False,
            "dispatch_state": "waiting_human",
            "blockers": ["waiting_human"],
            "pack_sha": "w" * 64,
            "base_sha": "b" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
        }
        with mock.patch.object(dispatch, "_closeout", return_value={"snapshot": {"exit_code": 0}}) as close:
            with mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"):
                payload, code = dispatch.dispatch_send(
                    pack,
                    catalog_action_id="poc-measurement",
                    action_id="act-wait",
                    dry_run=False,
                )
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(close.call_args.kwargs["result"], "cancelled")
        self.assertEqual(close.call_args.kwargs["action_id"], "act-wait")

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

    def test_extract_dispatch_notify_from_fence(self) -> None:
        text = (
            "```json\n"
            + json.dumps(
                {
                    "schema": "ndf-dispatch-notify/v1",
                    "result": "success",
                    "receipt_path": "poc/demo/ndf/evidence/poc_measurement-completion.json",
                    "topic": "demo",
                    "task": "poc_measurement",
                    "episode_id": "ep-demo",
                    "attempt_id": "act-1",
                }
            )
            + "\n```\n"
        )
        notify, errors = dispatch.extract_dispatch_notify(text)
        self.assertIsNotNone(notify)
        assert notify is not None
        self.assertEqual(notify["receipt_path"].endswith("-completion.json"), True)
        self.assertEqual(errors, [])

    def _measurement_pack(self, repo: Path, **extra: object) -> dict:
        evidence = repo / "poc" / "demo" / "ndf" / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_measurement",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "f" * 64,
            "base_sha": "1" * 40,
            "workspace": {
                "repo_root": str(repo),
                "topic_ndf_dir": "poc/demo/ndf/",
            },
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
            "replay": {"episode_id": "ep-demo"},
            "action_id": "act-1",
            "attempt_id": "act-1",
            "completion_receipt_path": (
                "poc/demo/ndf/evidence/poc_measurement-completion.json"
            ),
        }
        pack.update(extra)
        return pack

    def _notify(self, **extra: object) -> dict:
        body = {
            "schema": "ndf-dispatch-notify/v1",
            "result": "failed",
            "receipt_path": "poc/demo/ndf/evidence/poc_measurement-completion.json",
            "topic": "demo",
            "task": "poc_measurement",
            "episode_id": "ep-demo",
            "attempt_id": "act-1",
        }
        body.update(extra)
        return body

    def test_stdout_thin_completion_is_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack = self._measurement_pack(repo)
            receipt = {
                "schema": "ndf-agent-completion/v1",
                "result": "success",
                "status": "success",
                "summary": "thin stdout must not close the hop",
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
                    return_value={"final_result": "failed"},
                ) as closeout,
                mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
            ):
                payload, code = dispatch.dispatch_send(
                    pack, catalog_action_id="poc-measurement", action_id="act-1"
                )
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertTrue(payload.get("transport_ok"))
        self.assertIn("missing_dispatch_notify", payload["blockers"])
        self.assertEqual(closeout.call_args.kwargs["result"], "failed")

    def test_transport_ok_with_failed_disk_receipt_is_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack = self._measurement_pack(repo)
            disk = {
                "schema": "ndf-agent-completion/v1",
                "result": "failed",
                "status": "failed",
                "blockers": ["measurement_approval_required", "poc_write_denied"],
                "summary": "could not measure",
                "session_id": "sess",
            }
            receipt_path = repo / pack["completion_receipt_path"]
            receipt_path.write_text(json.dumps(disk), encoding="utf-8")
            send_result = {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "exit_code": 0,
                "session_id": "sess",
                "response_text": "```json\n" + json.dumps(self._notify()) + "\n```",
            }
            with (
                mock.patch.object(dispatch, "_send_acp", return_value=send_result),
                mock.patch.object(
                    dispatch,
                    "_closeout",
                    return_value={
                        "final_result": "failed",
                        "completion": {"blockers": disk["blockers"]},
                    },
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

    def test_notify_plus_disk_success_is_task_succeeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack = self._measurement_pack(repo)
            disk = {
                "schema": "ndf-agent-completion/v1",
                "result": "success",
                "status": "success",
                "summary": "measured",
                "session_id": "sess",
                "run_id": "run-1",
                "worktree": "/tmp/wt",
                "branch": "impl",
                "changed_files": ["poc/demo/ndf/PERF_BASELINE.md"],
                "reproduce_commands": ["echo ok"],
            }
            (repo / pack["completion_receipt_path"]).write_text(
                json.dumps(disk), encoding="utf-8"
            )
            send_result = {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "exit_code": 0,
                "session_id": "sess",
                "response_text": "```json\n"
                + json.dumps(self._notify(result="success"))
                + "\n```",
            }
            with (
                mock.patch.object(dispatch, "_send_acp", return_value=send_result),
                mock.patch.object(
                    dispatch,
                    "_closeout",
                    return_value={"final_result": "succeeded"},
                ) as closeout,
                mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
            ):
                payload, code = dispatch.dispatch_send(
                    pack, catalog_action_id="poc-measurement", action_id="act-1"
                )
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "succeeded")
        self.assertEqual(closeout.call_args.kwargs["result"], "succeeded")
        self.assertEqual(closeout.call_args.kwargs["agent_completion"]["run_id"], "run-1")

    def test_receipt_path_escape_is_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack = self._measurement_pack(repo)
            stolen = repo / "src" / "stolen.json"
            stolen.parent.mkdir(parents=True)
            stolen.write_text(
                json.dumps(
                    {
                        "schema": "ndf-agent-completion/v1",
                        "result": "success",
                        "summary": "must not be read",
                    }
                ),
                encoding="utf-8",
            )
            notify = self._notify(
                result="success",
                receipt_path="src/stolen.json",
            )
            send_result = {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "exit_code": 0,
                "session_id": "sess",
                "response_text": "```json\n" + json.dumps(notify) + "\n```",
            }
            with (
                mock.patch.object(dispatch, "_send_acp", return_value=send_result),
                mock.patch.object(
                    dispatch, "_closeout", return_value={"final_result": "failed"}
                ),
                mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
            ):
                payload, code = dispatch.dispatch_send(
                    pack, catalog_action_id="poc-measurement", action_id="act-1"
                )
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertIn("receipt_path_mismatch", payload["blockers"])
        self.assertIsNone(payload.get("agent_completion"))

    def test_openclaw_stdout_thin_completion_is_task_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack = self._measurement_pack(repo, provider="openclaw", task="control_proposal")
            pack["topic"] = ""
            pack["allowed_write_root"] = "spec/open/"
            pack["workspace"] = {"repo_root": str(repo)}
            pack["completion_receipt_path"] = (
                "spec/open/.ndf-completion/control_proposal-act-1.json"
            )
            pack["replay"] = {"episode_id": "ep-ctl"}
            send_result = {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "exit_code": 0,
                "response_text": "```json\n"
                + json.dumps(
                    {
                        "schema": "ndf-agent-completion/v1",
                        "result": "success",
                        "changed_files": ["spec/open/proposal.md"],
                    }
                )
                + "\n```",
            }
            with (
                mock.patch.object(dispatch, "_send_openclaw", return_value=send_result),
                mock.patch.object(
                    dispatch, "_closeout", return_value={"final_result": "failed"}
                ),
                mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
            ):
                payload, code = dispatch.dispatch_send(
                    pack, catalog_action_id="new-proposal", action_id="act-1"
                )
        self.assertEqual(code, 1)
        self.assertIn("missing_dispatch_notify", payload["blockers"])

    def test_openclaw_notify_plus_disk_success_is_task_succeeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            rel = "spec/open/.ndf-completion/control_proposal-act-1.json"
            pack = self._measurement_pack(
                repo,
                provider="openclaw",
                task="control_proposal",
                topic="",
                allowed_write_root="spec/open/",
                completion_receipt_path=rel,
            )
            pack["workspace"] = {"repo_root": str(repo)}
            pack["replay"] = {"episode_id": "ep-ctl"}
            disk = {
                "schema": "ndf-agent-completion/v1",
                "result": "success",
                "summary": "proposal drafted",
                "changed_files": ["spec/open/proposal.md"],
                "changed_file_shas": {"spec/open/proposal.md": "a" * 64},
                "reproduce_commands": ["echo ok"],
                "evidence_paths": [],
                "evidence_bundle_sha": "b" * 64,
            }
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(disk), encoding="utf-8")
            notify = {
                "schema": "ndf-dispatch-notify/v1",
                "result": "success",
                "receipt_path": rel,
                "topic": "",
                "task": "control_proposal",
                "episode_id": "ep-ctl",
                "attempt_id": "act-1",
            }
            send_result = {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "exit_code": 0,
                "response_text": "```json\n" + json.dumps(notify) + "\n```",
            }
            with (
                mock.patch.object(dispatch, "_send_openclaw", return_value=send_result),
                mock.patch.object(
                    dispatch, "_closeout", return_value={"final_result": "succeeded"}
                ) as closeout,
                mock.patch.object(dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"),
            ):
                payload, code = dispatch.dispatch_send(
                    pack, catalog_action_id="new-proposal", action_id="act-1"
                )
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], "succeeded")
        self.assertEqual(
            closeout.call_args.kwargs["agent_completion"]["changed_files"],
            ["spec/open/proposal.md"],
        )

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
        self.assertIn("missing_dispatch_notify", payload["blockers"])

    def test_acp_argv_inherits_commander_permissions(self) -> None:
        pack = {
            "safe_to_dispatch": True,
            "execution_capabilities_ready": True,
        }
        argv = dispatch._acp_argv(
            pack, session_id="sess-1", message="run it", executable="/usr/bin/claude"
        )
        self.assertIsNotNone(argv)
        assert argv is not None
        self.assertIn("--dangerously-skip-permissions", argv)
        self.assertIn("bypassPermissions", argv)
        self.assertEqual(argv[0], "/usr/bin/claude")
        self.assertIn("--resume", argv)
        self.assertIn("sess-1", argv)

    def test_acp_argv_override_is_unchanged(self) -> None:
        with mock.patch.dict(os.environ, {"NDF_ACP_DISPATCH_CMD": "echo skip-me"}, clear=False):
            argv = dispatch._acp_argv(
                {"safe_to_dispatch": True},
                session_id="sess-1",
                message="run it",
                executable="/usr/bin/claude",
            )
        self.assertEqual(argv, ["echo", "skip-me"])

    def test_worker_message_forbids_acp_second_gate(self) -> None:
        msg = dispatch._build_worker_message(
            {
                "provider": "claude-code-acp",
                "task": "poc_measurement",
                "topic": "demo",
                "safe_to_dispatch": True,
                "replay": {"episode_id": "ep-1"},
                "action_id": "act-1",
            }
        )
        self.assertIn("only human capability surface", msg)
        self.assertIn("MUST NOT wait for a Claude Code", msg)
        self.assertIn("execution_binding_stale", msg)
        self.assertIn("ndf-dispatch-notify/v1", msg)
        self.assertIn("reproduce_commands", msg)
        self.assertIn("lease-record", msg)

    def test_completion_receipt_path_defaults(self) -> None:
        poc = dispatch.completion_receipt_path_for_pack(
            {
                "topic": "demo",
                "task": "poc_measurement",
                "allowed_write_root": "poc/demo/",
                "workspace": {"topic_ndf_dir": "poc/demo/ndf/"},
            }
        )
        self.assertEqual(
            poc, "poc/demo/ndf/evidence/poc_measurement-completion.json"
        )
        process = dispatch.completion_receipt_path_for_pack(
            {
                "task": "ndf_improvement_land",
                "attempt_id": "act-9",
                "allowed_write_roots": ["spec/meta/open/"],
            }
        )
        self.assertEqual(
            process,
            "spec/meta/open/.ndf-completion/ndf_improvement_land-act-9.json",
        )

    def test_openclaw_send_prefers_resolved_session_id(self) -> None:
        pack = {
            "session_key": "agent:main:feishu:direct:ou_demo",
            "resolved_session_id": "bb867085-0457-4d41-8134-aec801e3a0df",
            "session_transport": "session_id",
            "pack_sha": "a" * 64,
        }
        stdout = mock.Mock()
        stdout.readline.return_value = ""
        stdout.read.return_value = "ok"
        proc = mock.Mock()
        proc.stdout = stdout
        proc.poll.side_effect = [None, 0]
        with mock.patch.object(dispatch.shutil, "which", return_value="/usr/bin/openclaw"):
            with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc) as popen:
                with mock.patch.object(
                    dispatch, "_openclaw_session_progress", return_value=None
                ):
                    with mock.patch.object(
                        dispatch.select, "select", return_value=([], [], [])
                    ):
                        result = dispatch._send_openclaw(pack, message="hi", timeout_sec=5)
        self.assertTrue(result.get("transport_ok"))
        argv = popen.call_args.args[0]
        self.assertIn("--session-id", argv)
        self.assertEqual(
            argv[argv.index("--session-id") + 1],
            "bb867085-0457-4d41-8134-aec801e3a0df",
        )

    def test_openclaw_send_routing_key_uses_gateway_session_key(self) -> None:
        pack = {
            "session_key": "agent:main:feishu:direct:ou_demo",
            "session_transport": "session_key",
            "pack_sha": "a" * 64,
        }
        stdout = mock.Mock()
        stdout.readline.return_value = ""
        stdout.read.return_value = "{}"
        proc = mock.Mock()
        proc.stdout = stdout
        proc.poll.side_effect = [0]
        with mock.patch.object(dispatch.shutil, "which", return_value="/usr/bin/openclaw"):
            with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc) as popen:
                with mock.patch.object(
                    dispatch, "_openclaw_session_progress", return_value=None
                ):
                    with mock.patch.object(
                        dispatch.select, "select", return_value=([], [], [])
                    ):
                        result = dispatch._send_openclaw(pack, message="hi", timeout_sec=5)
        self.assertTrue(result.get("transport_ok"))
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:4], ["/usr/bin/openclaw", "gateway", "call", "agent"])
        self.assertNotIn("--session-id", argv)
        params = json.loads(argv[argv.index("--params") + 1])
        self.assertEqual(params["sessionKey"], "agent:main:feishu:direct:ou_demo")
        self.assertEqual(params["message"], "hi")
        self.assertIn("idempotencyKey", params)
        # Absolute ceiling, not the short timeout_sec alone.
        self.assertGreaterEqual(int(params["timeout"]), 900)

    def test_openclaw_heartbeat_stalls_without_progress(self) -> None:
        pack = {
            "session_key": "agent:main:feishu:direct:ou_demo",
            "session_transport": "session_key",
            "provider": "openclaw",
            "pack_sha": "b" * 64,
            "request_id": "req-stall",
        }
        stdout = mock.Mock()
        stdout.readline.return_value = ""
        stdout.read.return_value = ""
        proc = mock.Mock()
        proc.stdout = stdout
        proc.poll.return_value = None
        frozen = {"t": 1000.0}

        def fake_time() -> float:
            return frozen["t"]

        with mock.patch.dict(
            os.environ,
            {
                "NDF_OPENCLAW_PING_SEC": "1",
                "NDF_OPENCLAW_STALL_SEC": "3",
                "NDF_OPENCLAW_MAX_SEC": "100",
            },
            clear=False,
        ):
            with mock.patch.object(dispatch.shutil, "which", return_value="/usr/bin/openclaw"):
                with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc):
                    with mock.patch.object(dispatch.time, "time", side_effect=fake_time):
                        with mock.patch.object(
                            dispatch.select,
                            "select",
                            side_effect=lambda *a, **k: (
                                frozen.__setitem__("t", frozen["t"] + 1.0) or ([], [], [])
                            ),
                        ):
                            with mock.patch.object(
                                dispatch,
                                "_openclaw_session_progress",
                                return_value={
                                    "updatedAt": 1,
                                    "totalTokens": 10,
                                },
                            ):
                                with mock.patch.object(
                                    dispatch, "_write_openclaw_heartbeat"
                                ):
                                    result = dispatch._send_openclaw(
                                        pack, message="hi", timeout_sec=5
                                    )
        self.assertEqual(result.get("error"), "openclaw_stalled")
        proc.kill.assert_called()

    def test_openclaw_heartbeat_extends_on_token_progress(self) -> None:
        pack = {
            "session_key": "agent:main:feishu:direct:ou_demo",
            "session_transport": "session_key",
            "provider": "openclaw",
            "pack_sha": "c" * 64,
            "request_id": "req-progress",
        }
        stdout = mock.Mock()
        stdout.readline.return_value = ""
        stdout.read.return_value = "final-ok"
        proc = mock.Mock()
        proc.stdout = stdout
        # Stay running through several pings, then finish.
        poll_seq = [None, None, None, None, 0]
        proc.poll.side_effect = poll_seq
        tokens = {"n": 10}
        frozen = {"t": 1000.0}

        def fake_time() -> float:
            return frozen["t"]

        def progress(_key: str, executable: str | None = None) -> dict:
            tokens["n"] += 5
            return {"updatedAt": tokens["n"], "totalTokens": tokens["n"]}

        with mock.patch.dict(
            os.environ,
            {
                "NDF_OPENCLAW_PING_SEC": "1",
                "NDF_OPENCLAW_STALL_SEC": "3",
                "NDF_OPENCLAW_MAX_SEC": "100",
            },
            clear=False,
        ):
            with mock.patch.object(dispatch.shutil, "which", return_value="/usr/bin/openclaw"):
                with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc):
                    with mock.patch.object(dispatch.time, "time", side_effect=fake_time):
                        with mock.patch.object(
                            dispatch.select,
                            "select",
                            side_effect=lambda *a, **k: (
                                frozen.__setitem__("t", frozen["t"] + 1.0) or ([], [], [])
                            ),
                        ):
                            with mock.patch.object(
                                dispatch,
                                "_openclaw_session_progress",
                                side_effect=progress,
                            ):
                                with mock.patch.object(
                                    dispatch, "_write_openclaw_heartbeat"
                                ):
                                    result = dispatch._send_openclaw(
                                        pack, message="hi", timeout_sec=5
                                    )
        self.assertTrue(result.get("transport_ok"))
        self.assertEqual(result.get("error"), None)
        proc.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
