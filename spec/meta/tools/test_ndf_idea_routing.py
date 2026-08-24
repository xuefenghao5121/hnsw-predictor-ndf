#!/usr/bin/env python3
"""Idea plane routing tests (ADR-META-004)."""

from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ndf_workflow_status as workflow


class IdeaPlaneClassifyTest(unittest.TestCase):
    def test_product_markers(self) -> None:
        result = workflow.classify_idea_plane("提高 HNSW QPS 并修 recall bug")
        self.assertEqual(result["plane"], "product")
        self.assertEqual(result["task"], "product_proposal")
        self.assertEqual(result["write_roots"], ["spec/open/"])

    def test_process_markers(self) -> None:
        result = workflow.classify_idea_plane("优化 NDF 工作流 skill 与 poc-dispatch")
        self.assertEqual(result["plane"], "process")
        self.assertEqual(result["task"], "process_proposal")
        self.assertEqual(result["write_roots"], ["spec/meta/open/"])

    def test_mixed_splits(self) -> None:
        result = workflow.classify_idea_plane(
            "修 HNSW bug 并同时改 NDF 工作流 graphcheck 门禁"
        )
        self.assertEqual(result["plane"], "mixed")
        self.assertEqual(result["confidence"], "ask")
        self.assertEqual(len(result["split"]), 2)

    def test_ambiguous_asks(self) -> None:
        result = workflow.classify_idea_plane("帮我看看这个")
        self.assertEqual(result["plane"], "ambiguous")
        self.assertEqual(result["confidence"], "ask")

    def test_bootstrap_routes_product(self) -> None:
        result = workflow.classify_idea_plane("初始化项目 Genesis greenfield")
        self.assertEqual(result["plane"], "product")
        self.assertEqual(result["track"], "bootstrap")


class IdeaWriteRootGuardTest(unittest.TestCase):
    def test_product_rejects_meta_root(self) -> None:
        with self.assertRaises(ValueError):
            workflow.assert_idea_write_roots(
                "product_proposal", ["spec/open/", "spec/meta/open/"]
            )

    def test_process_rejects_open_root(self) -> None:
        with self.assertRaises(ValueError):
            workflow.assert_idea_write_roots(
                "process_proposal", ["spec/meta/open/", "spec/open/"]
            )

    def test_canonical_alias(self) -> None:
        self.assertEqual(
            workflow.canonicalize_proposal_task("control_proposal"),
            "product_proposal",
        )
        self.assertEqual(
            workflow.canonicalize_proposal_task("ndf_improvement_proposal"),
            "process_proposal",
        )


class IdeaPackPlaneTest(unittest.TestCase):
    def test_product_pack_roots(self) -> None:
        with mock.patch.object(workflow, "runtime_status", return_value={
            "control": {
                "gateway_reachable": True,
                "session_configured": True,
                "session_dispatchable": True,
                "resolved_session_id": None,
                "session_transport": "sessionKey",
            }
        }):
            with mock.patch.object(workflow, "control_runtime_dispatch_ready", return_value=True):
                with mock.patch.object(
                    workflow, "control_runtime_dispatch_blockers", return_value=[]
                ):
                    with mock.patch.object(
                        workflow,
                        "context_binding",
                        return_value={
                            "context_verify": {"valid": True},
                            "manifest": {},
                            "role_plan": {},
                        },
                    ):
                        with mock.patch.object(workflow, "git_head", return_value="abc"):
                            with mock.patch.object(
                                workflow, "workspace_binding", return_value={}
                            ):
                                with mock.patch.object(
                                    workflow,
                                    "workspace_truth_view",
                                    return_value={"workspace_bound": True},
                                ):
                                    with mock.patch.object(
                                        workflow,
                                        "bind_pack_to_episode",
                                        side_effect=lambda p, **k: p,
                                    ):
                                        with mock.patch.object(
                                            workflow,
                                            "_with_completion_receipt_path",
                                            side_effect=lambda p: p,
                                        ):
                                            with mock.patch.object(
                                                workflow,
                                                "openclaw_session_key",
                                                return_value="k",
                                            ):
                                                pack, code = workflow.control_proposal_idea_pack(
                                                    intent="提高 QPS",
                                                    task="product_proposal",
                                                )
        self.assertEqual(pack["idea_plane"], "product")
        self.assertEqual(pack["allowed_write_roots"], ["spec/open/"])
        self.assertIn("spec/meta/open/", pack["forbidden"])
        self.assertNotIn("replay_episode_missing", pack.get("blockers", []))

    def test_process_pack_roots(self) -> None:
        with mock.patch.object(workflow, "runtime_status", return_value={
            "control": {
                "gateway_reachable": True,
                "session_configured": True,
                "session_dispatchable": True,
                "resolved_session_id": None,
                "session_transport": "sessionKey",
            }
        }):
            with mock.patch.object(workflow, "control_runtime_dispatch_ready", return_value=True):
                with mock.patch.object(
                    workflow, "control_runtime_dispatch_blockers", return_value=[]
                ):
                    with mock.patch.object(
                        workflow,
                        "context_binding",
                        return_value={
                            "context_verify": {"valid": True},
                            "manifest": {},
                            "role_plan": {},
                        },
                    ):
                        with mock.patch.object(workflow, "git_head", return_value="abc"):
                            with mock.patch.object(
                                workflow, "workspace_binding", return_value={}
                            ):
                                with mock.patch.object(
                                    workflow,
                                    "workspace_truth_view",
                                    return_value={"workspace_bound": True},
                                ):
                                    with mock.patch.object(
                                        workflow,
                                        "bind_pack_to_episode",
                                        side_effect=lambda p, **k: p,
                                    ):
                                        with mock.patch.object(
                                            workflow,
                                            "_with_completion_receipt_path",
                                            side_effect=lambda p: p,
                                        ):
                                            with mock.patch.object(
                                                workflow,
                                                "openclaw_session_key",
                                                return_value="k",
                                            ):
                                                pack, _ = workflow.control_proposal_idea_pack(
                                                    intent="改进 NDF 工作流",
                                                    task="process_proposal",
                                                )
        self.assertEqual(pack["idea_plane"], "process")
        self.assertEqual(pack["allowed_write_roots"], ["spec/meta/open/"])
        self.assertIn("spec/open/", pack["forbidden"])


class MetaGraphRepairRouteTest(unittest.TestCase):
    def test_meta_graph_routes_to_process(self) -> None:
        self.assertEqual(
            workflow.PROJECT_CHECK_ROUTES["meta_graph"]["repair_task"],
            "process_proposal",
        )
        self.assertEqual(
            workflow.PROJECT_CHECK_ROUTES["product_graph"]["repair_task"],
            "product_proposal",
        )


if __name__ == "__main__":
    unittest.main()
