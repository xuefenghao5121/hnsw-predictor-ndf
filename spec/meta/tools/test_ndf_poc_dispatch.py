#!/usr/bin/env python3
"""Regression: text-first poc-dispatch hard gates (ADR-META-003 / ADR-META-004)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Load workflow under its real module name so ndf_poc_dispatch._workflow()
# and patch.object(workflow, ...) share one module object.
MODULE_PATH = Path(__file__).with_name("ndf_workflow_status.py")
SPEC = importlib.util.spec_from_file_location("ndf_workflow_status", MODULE_PATH)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
sys.modules["ndf_workflow_status"] = workflow
SPEC.loader.exec_module(workflow)

import ndf_poc_dispatch as dispatch  # noqa: E402


class ImplementationLicenseTest(unittest.TestCase):
    def test_accepts_classic_gate3(self) -> None:
        gates = {
            "implementation_approval": {
                "state": "valid",
                "approved_content_sha": "a" * 64,
                "expected_content_sha": "a" * 64,
            },
            "bundle_dispatch": {"state": "missing"},
        }
        info = workflow.implementation_license(gates)
        self.assertTrue(info["ok"])
        self.assertEqual(info["source"], "implementation_approval")

    def test_accepts_text_first_bundle_dispatch(self) -> None:
        gates = {
            "implementation_approval": {"state": "missing"},
            "bundle_dispatch": {
                "state": "valid",
                "approved_content_sha": "b" * 64,
                "expected_content_sha": "b" * 64,
            },
        }
        info = workflow.implementation_license(gates)
        self.assertTrue(info["ok"])
        self.assertEqual(info["source"], "bundle_dispatch")
        self.assertEqual(info["phrase"], "派发")

    def test_rejects_missing_license(self) -> None:
        gates = {
            "implementation_approval": {"state": "invalidated"},
            "bundle_dispatch": {"state": "missing"},
        }
        info = workflow.implementation_license(gates)
        self.assertFalse(info["ok"])


class HardBlockersTest(unittest.TestCase):
    def _base(self, **over):
        view = {"lifecycle": "exploring"}
        truth = {"workspace_bound": True}
        license_info = {"ok": True, "state": "valid"}
        kwargs = dict(
            topic="demo",
            view=view,
            truth=truth,
            context_valid=True,
            isolation_passed=True,
            license_info=license_info,
        )
        kwargs.update(over)
        return dispatch.poc_dispatch_hard_blockers(**kwargs)

    def test_clean_path_no_blockers(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            self.assertEqual(self._base(), [])

    def test_rejects_unbound_workspace(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            blockers = self._base(truth={"workspace_bound": False})
        self.assertIn("workspace_unbound", blockers)

    def test_rejects_missing_human_dispatch(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            blockers = self._base(license_info={"ok": False, "state": "missing"})
        self.assertTrue(any(b.startswith("missing_human_dispatch") for b in blockers))

    def test_rejects_isolation_failure(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            blockers = self._base(isolation_passed=False)
        self.assertIn("isolation_check_failed", blockers)

    def test_rejects_context_drift(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            blockers = self._base(context_valid=False)
        self.assertIn("context_verify_failed", blockers)

    def test_rejects_concurrent_write_run(self) -> None:
        with patch.object(
            dispatch, "_concurrent_write_run_blocker", return_value="concurrent_write_run"
        ):
            blockers = self._base()
        self.assertIn("concurrent_write_run", blockers)

    def test_rejects_closed_topic(self) -> None:
        with patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None):
            blockers = self._base(view={"lifecycle": "promoted"})
        self.assertIn("topic_lifecycle_closed", blockers)


class SoftAuditNotHardTest(unittest.TestCase):
    def test_soft_reasons_listed(self) -> None:
        for reason in (
            "bindcheck_failed",
            "meta_graphcheck_failed",
            "product_graphcheck_failed",
            "spec_health_stale",
            "runtime_not_probed",
            "missing_active_isolated_lease",
        ):
            self.assertIn(reason, dispatch.POC_DISPATCH_SOFT_REASONS)
            # Re-export compat from workflow_status.
            self.assertIn(reason, workflow.POC_DISPATCH_SOFT_REASONS)


class CompletionIdentityTest(unittest.TestCase):
    def test_accepts_matching_success(self) -> None:
        pack = {"topic": "demo", "task": "poc_implementation", "run_id": "run-1"}
        completion = {
            "schema": "ndf-agent-completion/v1",
            "topic": "demo",
            "task": "poc_implementation",
            "run_id": "run-1",
            "result": "success",
        }
        out = dispatch.validate_poc_completion_minimal(pack=pack, completion=completion)
        self.assertTrue(out["ok"])
        self.assertEqual(out["errors"], [])

    def test_soft_warnings_for_optional_episode_fields(self) -> None:
        pack = {"topic": "demo", "task": "poc_implementation", "run_id": "run-1"}
        completion = {
            "schema": "ndf-agent-completion/v1",
            "topic": "demo",
            "task": "poc_implementation",
            "run_id": "run-1",
            "result": "success",
            # missing episode_id / attempt_id / projection_sha on purpose
        }
        out = dispatch.validate_poc_completion_minimal(pack=pack, completion=completion)
        self.assertTrue(out["ok"])
        self.assertTrue(any(w.startswith("optional_missing:") for w in out["soft_warnings"]))

    def test_rejects_forged_topic(self) -> None:
        pack = {"topic": "demo", "task": "poc_implementation", "run_id": "run-1"}
        completion = {
            "schema": "ndf-agent-completion/v1",
            "topic": "other",
            "task": "poc_implementation",
            "run_id": "run-1",
            "result": "success",
        }
        out = dispatch.validate_poc_completion_minimal(pack=pack, completion=completion)
        self.assertFalse(out["ok"])
        self.assertIn("completion_topic_mismatch", out["errors"])

    def test_rejects_missing_disk_completion(self) -> None:
        out = dispatch.validate_poc_completion_minimal(pack={}, completion=None)
        self.assertFalse(out["ok"])
        self.assertIn("missing_disk_completion", out["errors"])


class PocDispatchPackPathTest(unittest.TestCase):
    def test_pack_without_send_uses_hard_gates_only(self) -> None:
        topic = "text-first-demo"
        topic_dir = workflow.POC / topic
        view = {
            "topic_id": topic,
            "lifecycle": "exploring",
            "gates": {
                "implementation_approval": {"state": "missing"},
                "bundle_dispatch": {
                    "state": "valid",
                    "approved_content_sha": "c" * 64,
                    "expected_content_sha": "c" * 64,
                },
            },
            "spaces": {},
            "health": {
                "checks": {
                    "isolation": {"exit_code": 0, "state": "passed"},
                    "bindcheck": {"exit_code": 1},
                    "meta_graph": {"exit_code": 1},
                    "product_graph": {"exit_code": 1},
                    "perf_baseline": {"exit_code": 1},
                }
            },
            "delegation": {
                "dispatch_blockers": [
                    "bindcheck_failed",
                    "meta_graphcheck_failed",
                    "product_graphcheck_failed",
                    "spec_health_stale",
                    "runtime_not_probed",
                ],
                "context_plan": {"privileges": {"allowed_sections": []}},
                "context_verify": {"valid": True},
                "task_manifest": {"schema": "ndf-task-manifest/v1"},
                "manifest_sha": "m" * 64,
                "plan_sha": "p" * 64,
            },
            "phase_hint": "implement",
        }

        def fake_topic_view(path, *, mode="full"):
            self.assertTrue(str(path).endswith(topic) or path == topic_dir)
            return view

        with tempfile.TemporaryDirectory() as tmp:
            ndf = Path(tmp) / "poc" / topic / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: text-first-demo\n", encoding="utf-8")
            with (
                patch.object(workflow, "POC", Path(tmp) / "poc"),
                patch.object(workflow, "topic_view", side_effect=fake_topic_view),
                patch.object(
                    workflow,
                    "context_binding",
                    return_value={
                        "context_plan": {"privileges": {"allowed_sections": []}},
                        "context_verify": {"valid": True},
                        "task_manifest": {"schema": "ndf-task-manifest/v1"},
                        "manifest_sha": "m" * 64,
                        "plan_sha": "p" * 64,
                    },
                ),
                patch.object(
                    workflow,
                    "workspace_truth_view",
                    return_value={"workspace_bound": True},
                ),
                patch.object(
                    workflow,
                    "workspace_binding",
                    return_value={"repo_root": str(Path(tmp))},
                ),
                patch.object(workflow, "git_head", return_value="deadbeef"),
                patch.object(
                    workflow,
                    "poc_gate_bundle_specs",
                    return_value={
                        "implementation_approval": {"expected_content_sha": "c" * 64},
                        "bundle_dispatch": {"expected_content_sha": "c" * 64},
                    },
                ),
                patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None),
                patch.object(
                    dispatch,
                    "ensure_inline_isolated_lease",
                    return_value={
                        "ok": True,
                        "reused": True,
                        "run_id": "run-reuse",
                        "worktree": "/tmp/wt",
                        "session_id": "sess",
                    },
                ),
                patch.object(workflow, "persist_dispatch_pack", return_value=Path(tmp) / "pack.json"),
                patch.object(workflow, "apply_acp_context_budget_to_pack"),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, **kw: payload,
                ),
                patch.object(
                    workflow,
                    "_with_completion_receipt_path",
                    side_effect=lambda payload: {
                        **payload,
                        "completion_receipt_path": "tmp/completion.json",
                    },
                ),
            ):
                result, code = dispatch.poc_dispatch(topic, intent="implement", send=False)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"])
        pack = result["pack"]
        self.assertTrue(pack["text_first"])
        self.assertTrue(pack["poc_dispatch_hard_passed"])
        self.assertTrue(pack["safe_to_dispatch"])
        # Soft audit must not appear as hard blockers.
        for soft in (
            "bindcheck_failed",
            "meta_graphcheck_failed",
            "product_graphcheck_failed",
            "spec_health_stale",
        ):
            self.assertNotIn(soft, pack["blockers"])
            self.assertIn(soft, result["soft_warnings"])
        self.assertEqual(result["implementation_license"]["source"], "bundle_dispatch")
        self.assertFalse(result["sent"])

    def test_missing_license_blocks_without_commander(self) -> None:
        topic = "no-license-demo"
        view = {
            "topic_id": topic,
            "lifecycle": "exploring",
            "gates": {
                "implementation_approval": {"state": "missing"},
                "bundle_dispatch": {"state": "missing"},
            },
            "spaces": {},
            "health": {"checks": {"isolation": {"exit_code": 0}}},
            "delegation": {"dispatch_blockers": ["meta_graphcheck_failed"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            ndf = Path(tmp) / "poc" / topic / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("x\n", encoding="utf-8")
            with (
                patch.object(workflow, "POC", Path(tmp) / "poc"),
                patch.object(workflow, "topic_view", return_value=view),
                patch.object(
                    workflow,
                    "context_binding",
                    return_value={
                        "context_plan": {},
                        "context_verify": {"valid": True},
                        "task_manifest": {},
                        "manifest_sha": "m",
                        "plan_sha": "p",
                    },
                ),
                patch.object(
                    workflow, "workspace_truth_view", return_value={"workspace_bound": True}
                ),
                patch.object(workflow, "workspace_binding", return_value={"repo_root": str(tmp)}),
                patch.object(workflow, "git_head", return_value="abc"),
                patch.object(
                    workflow,
                    "poc_gate_bundle_specs",
                    return_value={
                        "implementation_approval": {},
                        "bundle_dispatch": {},
                    },
                ),
                patch.object(dispatch, "_concurrent_write_run_blocker", return_value=None),
                patch.object(workflow, "persist_dispatch_pack", return_value=Path(tmp) / "p.json"),
                patch.object(workflow, "apply_acp_context_budget_to_pack"),
                patch.object(
                    workflow, "bind_pack_to_episode", side_effect=lambda payload, **kw: payload
                ),
                patch.object(
                    workflow,
                    "_with_completion_receipt_path",
                    side_effect=lambda payload: payload,
                ),
            ):
                result, code = dispatch.poc_dispatch(topic, intent="implement", send=False)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(b.startswith("missing_human_dispatch") for b in result["hard_blockers"])
        )
        # Commander / meta graph soft warning must not be the hard failure.
        self.assertNotIn("meta_graphcheck_failed", result["hard_blockers"])


class RegistrySurfaceTest(unittest.TestCase):
    def test_action_spec_module_deleted(self) -> None:
        tools = Path(__file__).resolve().parent
        self.assertFalse((tools / "ndf_actions.py").is_file())
        # Inline stub on workflow only; no importable ActionSpec module.
        self.assertTrue(hasattr(workflow, "ndf_actions"))
        self.assertEqual(workflow.ndf_actions.registry_actions(), [])
        self.assertEqual(workflow.ndf_actions.evaluate_enabled_actions({}), [])
        self.assertNotIn("poc-dispatch", workflow.ndf_actions.registry_by_id())


class KernelReexportTest(unittest.TestCase):
    def test_workflow_reexports_kernel_symbols(self) -> None:
        self.assertIs(workflow.poc_dispatch, dispatch.poc_dispatch)
        self.assertIs(workflow.poc_dispatch_hard_blockers, dispatch.poc_dispatch_hard_blockers)
        self.assertIs(
            workflow.validate_poc_completion_minimal,
            dispatch.validate_poc_completion_minimal,
        )


if __name__ == "__main__":
    unittest.main()
