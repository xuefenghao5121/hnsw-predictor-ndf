#!/usr/bin/env python3
"""Tests for pack → hook dispatch-send and gate expected SHA alignment."""

from __future__ import annotations

import json
import os
import subprocess
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
    def setUp(self) -> None:
        self._snap_patch = mock.patch.object(
            dispatch, "_run_snapshot", return_value={"exit_code": 0}
        )
        self._snap_patch.start()
        self.addCleanup(self._snap_patch.stop)
        self._last_patch = mock.patch.object(
            dispatch, "DISPATCH_LAST", Path(tempfile.mkdtemp()) / "last.json"
        )
        self._last_patch.start()
        self.addCleanup(self._last_patch.stop)

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
        self.assertIn("--fork-session", argv)

    def test_acp_argv_fork_session_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"NDF_ACP_FORK_SESSION": "0"}, clear=False):
            argv = dispatch._acp_argv(
                {"safe_to_dispatch": True},
                session_id="sess-1",
                message="run it",
                executable="/usr/bin/claude",
            )
        self.assertIsNotNone(argv)
        assert argv is not None
        self.assertNotIn("--fork-session", argv)

    def test_slim_worker_message_omits_task_manifest_graph(self) -> None:
        pack = {
            "provider": "claude-code-acp",
            "task": "poc_implementation",
            "topic": "demo",
            "manifest_sha": "abc",
            "plan_sha": "def",
            "task_manifest": {"shared_graph_closure": {"nodes": [{"id": "BEH-001"}]}},
            "context_plan": {
                "plan_sha": "def",
                "graph": {"nodes": [{"id": "BEH-001"}]},
                "ordered_reads": [{"order": 0, "path": "poc/demo/ndf/TOPIC.md"}],
            },
        }
        slim = dispatch._slim_pack_for_acp_worker(pack)
        self.assertNotIn("task_manifest", slim)
        self.assertIn("task_manifest_ref", slim)
        self.assertNotIn("graph", slim.get("context_plan") or {})
        msg = dispatch._build_worker_message(pack)
        self.assertNotIn("shared_graph_closure", msg)

    def test_acp_context_over_budget_blocks_preflight(self) -> None:
        pack = {
            "provider": "claude-code-acp",
            "safe_to_dispatch": True,
            "workspace_truth": {"workspace_bound": True},
            "base_sha": "abc",
            "workspace": {"repo_root": "/repo"},
            "allowed_write_root": "poc/demo/",
            "acp_context_budget": {"over_budget": True},
        }
        blockers = dispatch._pack_preflight_blockers(pack)
        self.assertIn("acp_context_over_budget", blockers)

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


class CloseoutCommitGateTests(unittest.TestCase):
    def _run_closeout(self, **kwargs):
        runs: list[list[str]] = []

        def fake_run(cmd, **_kw):
            runs.append(list(cmd))
            return mock.Mock(returncode=0, stdout="{}", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tmp").mkdir()
            with (
                mock.patch.object(dispatch, "ROOT", root),
                mock.patch.object(dispatch.subprocess, "run", side_effect=fake_run),
                mock.patch.object(dispatch, "_action_has_started", return_value=True),
            ):
                steps = dispatch._closeout(
                    catalog_action_id=kwargs.get("catalog_action_id", "delegate-poc"),
                    action_id=kwargs.get("action_id", "act-1"),
                    result=kwargs["result"],
                    blockers=list(kwargs.get("blockers") or []),
                    result_summary=kwargs.get("result_summary", "test"),
                    agent_completion=kwargs.get("agent_completion"),
                    pack=kwargs.get("pack") or {"task": "poc_implementation"},
                )
        return steps, runs

    def test_failed_skips_action_commit(self) -> None:
        steps, runs = self._run_closeout(
            result="failed",
            blockers=["acp_stalled"],
            result_summary="acp_stalled",
        )
        self.assertTrue(steps["action_commit"]["skipped"])
        self.assertEqual(steps["action_commit"]["skip_reason"], "dispatch_not_succeeded")
        self.assertFalse(any("action-commit" in cmd for cmd in runs))
        # ActionSpec retired: action-finish is skipped, not invoked (ADR-META-004).
        self.assertFalse(any("action-finish" in cmd for cmd in runs))
        self.assertEqual(steps["action_finish"].get("skip_reason"), "action_spec_retired")

    def test_cancelled_skips_action_commit(self) -> None:
        steps, runs = self._run_closeout(result="cancelled", blockers=["waiting_human"])
        self.assertTrue(steps["action_commit"]["skipped"])
        self.assertFalse(any("action-commit" in cmd for cmd in runs))

    def test_succeeded_without_completion_skips_commit(self) -> None:
        steps, runs = self._run_closeout(result="succeeded", agent_completion=None)
        self.assertTrue(steps["action_commit"]["skipped"])
        self.assertEqual(
            steps["action_commit"]["skip_reason"], "missing_validated_completion"
        )
        self.assertFalse(any("action-commit" in cmd for cmd in runs))

    def test_succeeded_with_validated_completion_commits(self) -> None:
        completion = {
            "schema": "ndf-agent-completion/v1",
            "result": "success",
            "changed_files": ["poc/demo/ndf/DELTA.md"],
        }
        steps, runs = self._run_closeout(
            result="succeeded",
            agent_completion=completion,
        )
        # ActionSpec retired: closeout records skip, never calls action-commit.
        self.assertTrue(steps["action_closeout"].get("skipped"))
        self.assertEqual(steps["action_closeout"].get("reason"), "action_spec_retired")
        self.assertFalse(any("action-commit" in cmd for cmd in runs))
        self.assertFalse(any("action-finish" in cmd for cmd in runs))


class SnapshotOrderTests(unittest.TestCase):
    def test_final_state_written_before_snapshot(self) -> None:
        pack = {
            "schema": "ndf-implementation-repair-pack/v2",
            "provider": "claude-code-acp",
            "task": "poc_implementation",
            "topic": "demo",
            "safe_to_dispatch": True,
            "pack_sha": "s" * 64,
            "base_sha": "1" * 40,
            "workspace": {"repo_root": "/tmp/repo"},
            "allowed_write_root": "poc/demo/",
            "workspace_truth": {"workspace_bound": True},
        }
        writes: list[str] = []
        snap_saw: list[str] = []

        def fake_write(payload):
            writes.append(str(payload.get("state") or payload.get("dispatch_state") or ""))

        def fake_snap(_pack):
            snap_saw.append(writes[-1] if writes else "")
            return {"exit_code": 0}

        send_result = {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": "acp_stalled",
            "response_text": None,
        }
        with (
            mock.patch.object(dispatch, "_send_acp", return_value=send_result),
            mock.patch.object(
                dispatch, "_closeout", return_value={"final_result": "failed"}
            ),
            mock.patch.object(dispatch, "_write_last", side_effect=fake_write),
            mock.patch.object(dispatch, "_run_snapshot", side_effect=fake_snap),
        ):
            payload, code = dispatch.dispatch_send(
                pack, catalog_action_id="delegate-poc", action_id="act-1"
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "failed")
        self.assertIn("failed", snap_saw)
        self.assertEqual(snap_saw[0], "failed")
        self.assertIn("sent", writes)


class AcpHeartbeatTests(unittest.TestCase):
    def _proc(self) -> mock.Mock:
        stdout = mock.Mock()
        stdout.readline.return_value = ""
        stdout.read.return_value = ""
        proc = mock.Mock()
        proc.stdout = stdout
        proc.poll.return_value = None
        return proc

    def test_acp_heartbeat_stalls_without_progress(self) -> None:
        pack = {
            "provider": "claude-code-acp",
            "pack_sha": "d" * 64,
            "request_id": "req-acp-stall",
            "completion_receipt_path": "poc/demo/ndf/evidence/x.json",
        }
        proc = self._proc()
        frozen = {"t": 1000.0}

        with mock.patch.dict(
            os.environ,
            {
                "NDF_ACP_PING_SEC": "1",
                "NDF_ACP_STALL_SEC": "3",
                "NDF_ACP_MAX_SEC": "100",
            },
            clear=False,
        ):
            with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc):
                with mock.patch.object(dispatch.time, "time", side_effect=lambda: frozen["t"]):
                    with mock.patch.object(
                        dispatch.select,
                        "select",
                        side_effect=lambda *a, **k: (
                            frozen.__setitem__("t", frozen["t"] + 1.0) or ([], [], [])
                        ),
                    ):
                        with mock.patch.object(
                            dispatch, "_acp_resume_signature", return_value=(None, None)
                        ):
                            with mock.patch.object(
                                dispatch, "_disk_completion_present", return_value=False
                            ):
                                with mock.patch.object(dispatch, "_write_heartbeat"):
                                    result = dispatch._wait_acp_with_heartbeat(
                                        pack,
                                        cmd=["claude", "--resume", "sess"],
                                        session_id="sess",
                                        timeout_sec=5,
                                    )
        self.assertEqual(result.get("error"), "acp_stalled")
        self.assertFalse(result.get("transport_ok"))
        proc.kill.assert_called()
        self.assertLess(
            result.get("acp_heartbeat", {}).get("elapsed_sec", 999),
            100,
        )

    def test_disk_completion_finishes_before_max(self) -> None:
        pack = {
            "provider": "claude-code-acp",
            "pack_sha": "e" * 64,
            "request_id": "req-acp-disk",
        }
        proc = self._proc()
        frozen = {"t": 1000.0}

        with mock.patch.dict(
            os.environ,
            {
                "NDF_ACP_PING_SEC": "1",
                "NDF_ACP_STALL_SEC": "3",
                "NDF_ACP_MAX_SEC": "100",
            },
            clear=False,
        ):
            with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc):
                with mock.patch.object(dispatch.time, "time", side_effect=lambda: frozen["t"]):
                    with mock.patch.object(
                        dispatch.select,
                        "select",
                        side_effect=lambda *a, **k: (
                            frozen.__setitem__("t", frozen["t"] + 1.0) or ([], [], [])
                        ),
                    ):
                        with mock.patch.object(
                            dispatch, "_acp_resume_signature", return_value=(None, None)
                        ):
                            with mock.patch.object(
                                dispatch, "_disk_completion_present", return_value=True
                            ):
                                with mock.patch.object(dispatch, "_write_heartbeat"):
                                    result = dispatch._wait_acp_with_heartbeat(
                                        pack,
                                        cmd=["claude", "--resume", "sess"],
                                        session_id="sess",
                                        timeout_sec=5,
                                    )
        self.assertTrue(result.get("transport_ok"))
        self.assertEqual(result.get("acp_heartbeat", {}).get("finished"), "disk_or_notify")
        self.assertNotEqual(result.get("error"), "acp_timeout")

    def test_stdout_fragments_refresh_stall(self) -> None:
        pack = {
            "provider": "claude-code-acp",
            "pack_sha": "f" * 64,
            "request_id": "req-acp-stdout",
        }
        stdout = mock.Mock()
        stdout.readline.side_effect = ["chunk\n"] * 8 + [""] * 20
        stdout.read.return_value = ""
        proc = mock.Mock()
        proc.stdout = stdout
        proc.poll.return_value = None
        frozen = {"t": 1000.0}
        selects = {"n": 0}

        def fake_select(*_a, **_k):
            frozen["t"] += 1.0
            selects["n"] += 1
            # First 8 loops have stdout; afterwards stall.
            return ([proc.stdout], [], []) if selects["n"] <= 8 else ([], [], [])

        with mock.patch.dict(
            os.environ,
            {
                "NDF_ACP_PING_SEC": "1",
                "NDF_ACP_STALL_SEC": "3",
                "NDF_ACP_MAX_SEC": "100",
            },
            clear=False,
        ):
            with mock.patch.object(dispatch.subprocess, "Popen", return_value=proc):
                with mock.patch.object(dispatch.time, "time", side_effect=lambda: frozen["t"]):
                    with mock.patch.object(dispatch.select, "select", side_effect=fake_select):
                        with mock.patch.object(
                            dispatch, "_acp_resume_signature", return_value=(None, None)
                        ):
                            with mock.patch.object(
                                dispatch, "_disk_completion_present", return_value=False
                            ):
                                with mock.patch.object(dispatch, "_write_heartbeat"):
                                    result = dispatch._wait_acp_with_heartbeat(
                                        pack,
                                        cmd=["claude", "--resume", "sess"],
                                        session_id="sess",
                                        timeout_sec=5,
                                    )
        self.assertEqual(result.get("error"), "acp_stalled")
        self.assertGreaterEqual(result.get("acp_heartbeat", {}).get("elapsed_sec", 0), 8)


class DispatchProbeTests(unittest.TestCase):
    def test_in_flight_probe_refreshes_stall_without_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            last = root / "tmp" / "ndf-dispatch-last.json"
            pack_path = root / "tmp" / "ndf-dispatch-last-pack.json"
            last.parent.mkdir(parents=True)
            last.write_text(
                json.dumps(
                    {
                        "schema": "ndf-dispatch-send/v1",
                        "dispatch_state": "awaiting_result",
                        "state": "sent",
                    }
                ),
                encoding="utf-8",
            )
            pack_path.write_text(json.dumps({"topic": "demo"}), encoding="utf-8")
            send_called = {"n": 0}

            def boom(*_a, **_k):
                send_called["n"] += 1
                raise AssertionError("dispatch_send must not run from probe")

            with (
                mock.patch.object(dispatch, "ROOT", root),
                mock.patch.object(dispatch, "DISPATCH_LAST", last),
                mock.patch.object(dispatch, "dispatch_send", side_effect=boom),
                mock.patch(
                    "ndf_workflow_status.configured_acp_session_id",
                    return_value="sess-1",
                ),
                mock.patch(
                    "ndf_workflow_status.probe_claude_acp_light",
                    return_value={"reachable": True, "resume_available": True},
                ),
                mock.patch.object(
                    dispatch, "_acp_resume_signature", return_value=(1, 2)
                ),
                mock.patch.object(
                    dispatch, "_openclaw_session_progress", return_value=None
                ),
                mock.patch.object(
                    dispatch, "_disk_completion_present", return_value=False
                ),
            ):
                payload, code = dispatch.dispatch_probe(probed_by="human_progress")
            self.assertEqual(code, 0)
            self.assertEqual(payload["schema"], "ndf-dispatch-probe/v1")
            self.assertTrue(payload["in_flight"])
            self.assertTrue(payload["acp"]["alive"])
            self.assertEqual(payload["probed_by"], "human_progress")
            self.assertEqual(send_called["n"], 0)
            stored = json.loads(last.read_text(encoding="utf-8"))
            self.assertIn("last_progress_at", stored)
            self.assertEqual(stored["dispatch_state"], "awaiting_result")

    def test_send_acp_lease_only_records_isolated_lease(self) -> None:
        pack = {
            "topic": "demo",
            "task": "poc_implementation",
            "episode_id": "ep-demo",
            "base_sha": "a" * 40,
            "allowed_write_root": "poc/demo/",
            "workspace": {"repo_root": "/repo"},
        }
        prepared = {
            "ok": True,
            "transport_ok": True,
            "state": "succeeded",
            "lease_only": True,
            "session_id": "sess-1",
            "run_id": "run-lease-prep-demo",
            "worktree": "/repo/.worktrees/demo-lease",
            "response_text": "lease_recorded_no_implementation_start",
        }
        with (
            mock.patch(
                "ndf_workflow_status.configured_acp_session_id",
                return_value="sess-1",
            ),
            mock.patch.object(
                dispatch, "_prepare_isolated_lease", return_value=prepared
            ) as prep,
        ):
            result = dispatch._send_acp(
                pack, message="m", timeout_sec=1, lease_only=True
            )
        prep.assert_called_once()
        self.assertEqual(result["run_id"], "run-lease-prep-demo")
        self.assertEqual(result["worktree"], "/repo/.worktrees/demo-lease")
        self.assertNotEqual(result.get("response_text"), "lease_only_no_implementation_start")

    def test_prepare_isolated_lease_requires_pack_fields(self) -> None:
        result = dispatch._prepare_isolated_lease(
            {"workspace": {"repo_root": "/repo"}},
            session_id="sess-1",
        )
        self.assertFalse(result["ok"])
        self.assertIn("lease_pack_incomplete", result["error"])

    def test_lease_only_transport_fails_without_jsonl(self) -> None:
        pack = {
            "topic": "demo",
            "task": "prepare_acp_lease",
            "episode_id": "ep-demo",
            "base_sha": "a" * 40,
            "allowed_write_root": "poc/demo/",
        }
        send_result = {
            "transport_ok": True,
            "run_id": "run-lease-prep-demo",
            "worktree": "/repo/.worktrees/demo-lease",
            "response_text": "lease_recorded_no_implementation_start",
        }
        with mock.patch.object(
            dispatch,
            "_verify_lease_only_outcome",
            return_value=(False, ["missing:active_runtime_lease"], "lease_verification_failed"),
        ):
            result, blockers, summary, completion = dispatch._task_outcome_from_transport(
                send_result, pack=pack, lease_only=True
            )
        self.assertEqual(result, "failed")
        self.assertIn("missing:active_runtime_lease", blockers)
        self.assertIsNone(completion)

    def test_already_sent_rejects_lease_stub_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            last = root / "tmp" / "ndf-dispatch-last.json"
            last.parent.mkdir(parents=True)
            last.write_text(
                json.dumps(
                    {
                        "pack_sha": "abc",
                        "state": "succeeded",
                        "result_summary": "lease_only_no_implementation_start",
                        "send": {"lease_only": True, "transport_ok": True},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(dispatch, "DISPATCH_LAST", last):
                prior = dispatch._already_sent("abc", None)
            self.assertIsNone(prior)

    def test_closeout_lease_only_fails_without_artifact(self) -> None:
        steps, runs = CloseoutCommitGateTests()._run_closeout(
            catalog_action_id="prepare-acp-lease",
            result="succeeded",
            result_summary="lease_recorded_no_implementation_start",
            pack={
                "task": "prepare_acp_lease",
                "topic": "demo",
                "episode_id": "ep-demo",
                "base_sha": "a" * 40,
            },
        )
        self.assertEqual(steps["final_result"], "failed")
        self.assertTrue(steps["action_commit"].get("skipped"))


class LeaseLocalDepsLinkTests(unittest.TestCase):
    def test_link_lease_worktree_local_deps_symlinks_ignored_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            worktree = Path(tmp) / "wt"
            root.mkdir()
            worktree.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text(
                "hnswlib/\noutput/\ndata/*.fvecs\n",
                encoding="utf-8",
            )
            (root / "README").write_text("x\n", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "tracked.txt").write_text("keep\n", encoding="utf-8")
            (root / "data" / "sift_base.fvecs").write_text("vecs\n", encoding="utf-8")
            (root / "hnswlib").mkdir()
            (root / "hnswlib" / "hnswlib.h").write_text("//h\n", encoding="utf-8")
            (root / "output").mkdir()
            (root / "output" / "graph.bin").write_text("bin\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", ".gitignore", "README", "data/tracked.txt"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-qm", "init"],
                cwd=root,
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "t",
                    "GIT_AUTHOR_EMAIL": "t@e",
                    "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@e",
                },
            )
            # Simulate worktree checkout of tracked data/.
            (worktree / "data").mkdir()
            (worktree / "data" / "tracked.txt").write_text("keep\n", encoding="utf-8")

            linked = dispatch.link_lease_worktree_local_deps(root, worktree)
            self.assertTrue((worktree / "hnswlib").is_symlink())
            self.assertTrue((worktree / "output").is_symlink())
            self.assertTrue((worktree / "data" / "sift_base.fvecs").is_symlink())
            self.assertFalse((worktree / "data" / "tracked.txt").is_symlink())
            self.assertTrue((worktree / "build").is_dir())
            self.assertTrue((worktree / "results").is_dir())
            self.assertIn("hnswlib->hnswlib", linked)
            self.assertIn("data/sift_base.fvecs", linked)


class DiskReceiptWorktreeTests(unittest.TestCase):
    def test_load_disk_completion_from_lease_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree = root / "wt"
            worktree.mkdir()
            rel = "poc/demo/ndf/evidence/poc_implementation-completion.json"
            receipt = worktree / rel
            receipt.parent.mkdir(parents=True)
            completion = {
                "schema": "ndf-agent-completion/v1",
                "result": "success",
                "topic": "demo",
                "task": "poc_implementation",
                "episode_id": "ep-demo",
                "attempt_id": "act-demo",
                "base_sha": "b" * 40,
            }
            receipt.write_text(json.dumps(completion), encoding="utf-8")
            pack = {
                "topic": "demo",
                "task": "poc_implementation",
                "episode_id": "ep-demo",
                "action_id": "act-demo",
                "attempt_id": "act-demo",
                "base_sha": "b" * 40,
                "allowed_write_root": "poc/demo/",
                "workspace": {"repo_root": str(root)},
                "completion_receipt_path": rel,
            }
            notify = {"receipt_path": rel}
            with mock.patch(
                "ndf_workflow_status.active_isolated_lease_for_topic",
                return_value=(
                    True,
                    {
                        "worktree": str(worktree),
                        "result": "active",
                        "topic": "demo",
                    },
                ),
            ):
                data, errors = dispatch.load_disk_agent_completion(pack, notify)
            self.assertIsNotNone(data)
            self.assertEqual(errors, [])
            mirrored = root / rel
            self.assertTrue(mirrored.is_file())

    def test_disk_completion_present_rejects_stale_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "poc/demo/ndf/evidence/poc_implementation-completion.json"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": "ndf-agent-completion/v1",
                        "result": "success",
                        "topic": "demo",
                        "task": "poc_implementation",
                        "episode_id": "ep-old",
                        "attempt_id": "old-attempt",
                        "base_sha": "b" * 40,
                    }
                ),
                encoding="utf-8",
            )
            pack = {
                "topic": "demo",
                "task": "poc_implementation",
                "episode_id": "ep-new",
                "action_id": "new-attempt",
                "base_sha": "b" * 40,
                "workspace": {"repo_root": str(root)},
                "completion_receipt_path": rel,
            }
            with mock.patch.object(
                dispatch,
                "_pack_evidence_roots",
                return_value=[root],
            ):
                self.assertFalse(dispatch._disk_completion_present(pack))


if __name__ == "__main__":
    unittest.main()
