import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("ndf_workflow_status.py")
SPEC = importlib.util.spec_from_file_location("ndf_workflow_status", MODULE_PATH)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workflow
SPEC.loader.exec_module(workflow)


class WorkflowHealthTest(unittest.TestCase):
    def test_perf_and_isolation_findings_route_to_different_owners(self) -> None:
        checks = {
            "perf_baseline": {
                "exit_code": 1,
                "output": "[error] missing_config_id: config missing",
            },
            "isolation": {
                "exit_code": 1,
                "output": "- [error] `trunk_write` (demo) wrote src/x.cpp",
            },
            "bindcheck": {"exit_code": 0, "output": ""},
        }
        findings = workflow.external_check_findings("demo", checks)
        by_kind = {item["kind"]: item for item in findings}
        self.assertEqual(by_kind["missing_config_id"]["repair_owner"], "openclaw")
        self.assertEqual(by_kind["missing_config_id"]["repair_task"], "binder_amend")
        self.assertEqual(by_kind["trunk_write"]["repair_owner"], "claude-code")
        self.assertEqual(
            by_kind["trunk_write"]["allowed_write_root"],
            "poc/demo/",
        )

    def test_unverified_and_empty_numbers_route_to_measurement(self) -> None:
        checks = {
            "perf_baseline": {
                "exit_code": 1,
                "output": (
                    "[error] unverified_measurement_claim: Numbers lack a verified run\n"
                    "[error] empty_numbers: ## Numbers is empty\n"
                    "[error] missing_vs: card missing vs:\n"
                    "[error] missing_config: card missing config_id:\n"
                ),
            },
            "isolation": {"exit_code": 0, "output": ""},
            "bindcheck": {"exit_code": 0, "output": ""},
        }
        findings = workflow.external_check_findings("demo", checks)
        by_kind = {item["kind"]: item for item in findings}
        self.assertEqual(
            by_kind["unverified_measurement_claim"]["repair_task"],
            "poc_measurement",
        )
        self.assertEqual(
            by_kind["unverified_measurement_claim"]["repair_owner"],
            "claude-code",
        )
        self.assertIsNone(by_kind["unverified_measurement_claim"]["binder_facet"])
        self.assertEqual(by_kind["empty_numbers"]["repair_task"], "poc_measurement")
        self.assertEqual(by_kind["missing_vs"]["repair_task"], "binder_amend")
        self.assertEqual(by_kind["missing_vs"]["binder_facet"], "perf_baseline")
        self.assertEqual(by_kind["missing_config"]["repair_task"], "binder_amend")
        self.assertEqual(by_kind["missing_config"]["binder_facet"], "perf_baseline")

    def test_upsert_replaces_wrong_measurement_route(self) -> None:
        findings = [
            workflow.finding(
                scope="topic",
                space="Test",
                kind="unverified_measurement_claim",
                severity="error",
                evidence="wrong",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            )
        ]
        workflow.upsert_finding(
            findings,
            workflow.finding(
                scope="topic",
                space="Test",
                kind="unverified_measurement_claim",
                severity="error",
                evidence="right",
                repair_owner="claude-code",
                repair_task="poc_measurement",
                allowed_write_root="poc/demo/",
            ),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["repair_task"], "poc_measurement")
        self.assertIsNone(findings[0]["binder_facet"])

    def test_binder_amend_actions_are_ordered_and_named(self) -> None:
        findings = [
            workflow.finding(
                scope="topic",
                space="Test",
                kind="missing_delta",
                severity="warning",
                evidence="missing DELTA",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            ),
            workflow.finding(
                scope="topic",
                space="Design",
                kind="missing_design",
                severity="warning",
                evidence="missing DESIGN",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            ),
            workflow.finding(
                scope="topic",
                space="Test",
                kind="missing_perf_baseline_field",
                severity="error",
                evidence="missing perf_baseline field",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            ),
            workflow.finding(
                scope="topic",
                space="Design",
                kind="missing_interface",
                severity="warning",
                evidence="missing INTERFACE",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            ),
        ]
        actions = workflow.unique_actions(findings)
        self.assertEqual(
            [item["label"] for item in actions],
            [
                "装订器 2/6 装订器分步修订 · DESIGN.md",
                "装订器 3/6 装订器分步修订 · PERF_BASELINE / 金标绑定",
                "装订器 4/6 装订器分步修订 · DELTA.md",
                "装订器 5/6 装订器分步修订 · INTERFACE.md",
            ],
        )

    def test_gate_findings_preserve_human_phrase(self) -> None:
        gates = {
            "topic_review": {"state": "legacy_unknown"},
            "design_review": {"state": "valid"},
            "implementation_approval": {"state": "missing"},
        }
        findings = workflow.gate_findings("demo", gates)
        by_kind = {item["kind"]: item for item in findings}
        self.assertEqual(
            by_kind["gate_topic_review_legacy_unknown"]["repair_task"],
            "legacy_gate_audit",
        )
        self.assertEqual(
            by_kind["gate_implementation_approval_missing"]["human_gate"],
            "可以开始实现",
        )
        self.assertEqual(
            by_kind["gate_topic_review_legacy_unknown"]["label"],
            "门禁 1/3 门禁分步审计 · TOPIC已审核",
        )
        self.assertEqual(
            by_kind["gate_implementation_approval_missing"]["label"],
            "门禁 3/3 门禁准备回执 · 可以开始实现",
        )
        actions = workflow.unique_actions(findings)
        self.assertEqual(
            [item["label"] for item in actions],
            [
                "门禁 1/3 门禁分步审计 · TOPIC已审核",
                "门禁 3/3 门禁准备回执 · 可以开始实现",
            ],
        )

    def test_gate_parser_uses_latest_row_across_append_only_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GATES.md"
            header = (
                "| gate | phrase | approved_by | approved_at | "
                "approved_content_sha | source_ref | status |\n"
                "|---|---|---|---|---|---|---|\n"
            )
            path.write_text(
                header
                + "| topic_review | TOPIC已审核 | human | old | "
                + "a" * 64
                + " | TOPIC.md | approved |\n\n"
                + "## Later append-only episode\n\n"
                + header
                + "| topic_review | TOPIC已审核 | | | | TOPIC.md | pending |\n",
                encoding="utf-8",
            )
            latest = workflow.latest_gate_rows(path)
            self.assertEqual(latest["topic_review"]["status"], "pending")
            self.assertEqual(
                latest["topic_review"]["approved_content_sha"], ""
            )

    def test_bundle_sha_is_not_raw_single_file_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "TOPIC.md"
            path.write_text("# topic\n", encoding="utf-8")
            old_root = workflow.ROOT
            try:
                workflow.ROOT = root
                self.assertNotEqual(
                    workflow.bundle_sha([path]),
                    workflow.file_sha(path),
                )
            finally:
                workflow.ROOT = old_root

    def test_legacy_receipt_does_not_validate_review_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gates = Path(tmp) / "GATES.md"
            expected = "a" * 64
            gates.write_text(
                "| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |\n"
                "|---|---|---|---|---|---|---|\n"
                f"| topic_review | TOPIC已审核 | human | now | {expected} | TOPIC.md | approved |\n",
                encoding="utf-8",
            )
            view = workflow.gate_view(
                gates,
                {
                    "topic_review": {
                        "bundle_mode": "review_slice",
                        "expected_content_sha": expected,
                        "bundle_paths": ["TOPIC.md"],
                        "slices": [{"slice_id": "topic_contract"}],
                        "slice_manifest_sha": "b" * 64,
                        "errors": [],
                    }
                },
            )
            self.assertEqual(view["topic_review"]["state"], "invalidated")
            self.assertFalse(view["topic_review"]["bundle_mode_aligned"])

    def test_content_aligned_review_slice_tolerates_manifest_line_drift(self) -> None:
        """promote/partial selected_decision must not fake-invalidate when content matches."""
        with tempfile.TemporaryDirectory() as tmp:
            gates = Path(tmp) / "GATES.md"
            expected = "c" * 64
            receipt_manifest = "d" * 64
            current_manifest = "e" * 64
            gates.write_text(
                "| gate | phrase | approved_by | approved_at | approved_content_sha |"
                " bundle_mode | slice_manifest_sha | source_ref | status |\n"
                "|---|---|---|---|---|---|---|---|---|\n"
                f"| topic_review | TOPIC已审核 | human | now | {expected} |"
                f" review_slice | {receipt_manifest} | TOPIC.md | approved |\n",
                encoding="utf-8",
            )
            view = workflow.gate_view(
                gates,
                {
                    "topic_review": {
                        "bundle_mode": "review_slice",
                        "expected_content_sha": expected,
                        "bundle_paths": ["TOPIC.md"],
                        "slices": [{"slice_id": "topic_contract"}],
                        "slice_manifest_sha": current_manifest,
                        "errors": [],
                    }
                },
            )
            self.assertEqual(view["topic_review"]["state"], "valid")
            self.assertTrue(view["topic_review"]["sha_aligned"])
            self.assertTrue(view["topic_review"]["bundle_mode_aligned"])

            # Real contract edit: content sha mismatch still invalidates.
            view_bad = workflow.gate_view(
                gates,
                {
                    "topic_review": {
                        "bundle_mode": "review_slice",
                        "expected_content_sha": "f" * 64,
                        "bundle_paths": ["TOPIC.md"],
                        "slices": [{"slice_id": "topic_contract"}],
                        "slice_manifest_sha": current_manifest,
                        "errors": [],
                    }
                },
            )
            self.assertEqual(view_bad["topic_review"]["state"], "invalidated")
            self.assertFalse(view_bad["topic_review"]["sha_aligned"])

    def test_control_pipelines_are_split(self) -> None:
        findings = workflow.gate_findings(
            "demo",
            {
                "topic_review": {"state": "legacy_unknown"},
                "design_review": {"state": "legacy_unknown"},
                "implementation_approval": {"state": "legacy_unknown"},
            },
        ) + [
            workflow.finding(
                scope="topic",
                space="Design",
                kind="missing_design",
                severity="warning",
                evidence="missing DESIGN",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            )
        ]
        pipelines = workflow.control_pipelines_view("demo", findings)
        self.assertTrue(pipelines["gate"]["needed"])
        self.assertTrue(pipelines["binder"]["needed"])
        self.assertEqual(pipelines["gate"]["task"], "gate_pipeline")
        self.assertEqual(pipelines["binder"]["task"], "binder_pipeline")
        self.assertEqual(pipelines["gate"]["step_count"], 3)
        self.assertEqual(pipelines["binder"]["step_count"], 6)
        self.assertTrue(all(step.get("pipeline") == "gate" for step in pipelines["gate"]["steps"]))
        self.assertTrue(
            all(step.get("pipeline") == "binder" for step in pipelines["binder"]["steps"])
        )

    def test_stale_dispatch_forces_new_episode_and_clears_binding(self) -> None:
        self.assertTrue(
            workflow.dispatch_forces_new_episode(
                [
                    "episode_manifest_mismatch",
                    "control_pack_resume_failed: episode manifest does not match generated pack",
                ]
            )
        )
        self.assertFalse(
            workflow.dispatch_forces_new_episode(["runtime_unavailable"])
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = workflow.ROOT
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            old_dispatch = workflow.CONTROL_DISPATCH_LOG
            try:
                workflow.ROOT = root
                workflow.PIPELINE_EPISODE_DIR = root / "tmp" / "ndf-control-pipelines"
                workflow.CONTROL_DISPATCH_LOG = (
                    root / "tmp" / "ndf-control-dispatch.jsonl"
                )
                workflow.bind_control_pipeline_episode(
                    "demo", "gate", "ep-stale-demo"
                )
                workflow.append_control_dispatch_receipt(
                    {
                        "topic": "demo",
                        "pipeline": "gate",
                        "task": "gate_pipeline",
                        "episode_id": "ep-stale-demo",
                        "request_id": "req-stale",
                        "state": "blocked",
                        "manifest_sha": "a" * 64,
                        "context_plan_sha": "b" * 64,
                        "blockers": [
                            "episode_manifest_mismatch",
                            "control_pack_resume_failed: episode manifest does not match generated pack",
                        ],
                        "recorded_at": "2026-08-13T00:00:00Z",
                        "request_event_sha": None,
                        "response_event_sha": None,
                        "previous_state": "requested",
                    }
                )
                proj = workflow.pipeline_resume_projection(
                    "demo",
                    "gate",
                    active_episode="ep-stale-demo",
                    dispatch=workflow.control_dispatch_view("demo", "gate"),
                )
                self.assertTrue(proj["force_new_episode"])
                self.assertFalse(proj["resume"])
                self.assertIsNone(proj["active_episode_id"])
                self.assertIsNone(proj["retry_request_id"])
                self.assertIsNone(
                    workflow.active_control_episode("demo", "gate")
                )
            finally:
                workflow.ROOT = old_root
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir
                workflow.CONTROL_DISPATCH_LOG = old_dispatch

    def test_pipeline_step_record_rejects_agent_gate_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "poc" / "demo" / "ndf").mkdir(parents=True)
            (root / "poc" / "demo" / "ndf" / "TOPIC.md").write_text(
                "> topic_id: demo\n> status: exploring\n",
                encoding="utf-8",
            )
            old_root = workflow.ROOT
            old_poc = workflow.POC
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            try:
                workflow.ROOT = root
                workflow.POC = root / "poc"
                workflow.PIPELINE_EPISODE_DIR = root / "tmp" / "ndf-control-pipelines"
                store = workflow.ndf_replay.ReplayStore(root)
                episode = store.init_episode(
                    topic="demo",
                    task="gate_pipeline",
                    role="openclaw",
                    track="poc",
                    episode_id="ep-gate-demo",
                )
                workflow.bind_control_pipeline_episode("demo", "gate", "ep-gate-demo")
                ok, code = workflow.record_control_pipeline_step(
                    topic="demo",
                    pipeline="gate",
                    kind="gate.audit",
                    step_id="topic_review",
                    episode_id="ep-gate-demo",
                    actor="openclaw",
                )
                self.assertEqual(code, 0)
                self.assertEqual(ok["kind"], "gate.audit")
                with self.assertRaises(ValueError):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="gate",
                        kind="gate.confirmed",
                        step_id="topic_review",
                        episode_id="ep-gate-demo",
                        actor="openclaw",
                    )
                confirmed, code2 = workflow.record_control_pipeline_step(
                    topic="demo",
                    pipeline="gate",
                    kind="gate.confirmed",
                    step_id="topic_review",
                    episode_id="ep-gate-demo",
                    actor="human-tester",
                )
                self.assertEqual(code2, 0)
                self.assertEqual(confirmed["kind"], "gate.confirmed")
                self.assertEqual(
                    workflow.active_control_episode("demo", "gate"),
                    "ep-gate-demo",
                )
                self.assertEqual(episode["episode_id"], "ep-gate-demo")
            finally:
                workflow.ROOT = old_root
                workflow.POC = old_poc
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir

    def test_control_dispatch_requires_matching_openclaw_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = workflow.ROOT
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            old_dispatch_log = workflow.CONTROL_DISPATCH_LOG
            try:
                workflow.ROOT = root
                workflow.PIPELINE_EPISODE_DIR = root / "tmp" / "ndf-control-pipelines"
                workflow.CONTROL_DISPATCH_LOG = root / "tmp" / "ndf-control-dispatch.jsonl"
                manifest_sha = "m" * 64
                plan_sha = "p" * 64
                episode_id = "ep-dispatch-demo"
                request_id = "req-demo"
                pack = workflow.bind_pack_to_episode(
                    {
                        "topic": "demo",
                        "task": "gate_pipeline",
                        "track": "poc",
                        "provider": "openclaw",
                        "pipeline": "gate",
                        "base_sha": "a" * 40,
                        "manifest_sha": manifest_sha,
                        "plan_sha": plan_sha,
                        "safe_to_delegate": True,
                        "safe_to_dispatch": True,
                        "runtime_dispatch_ready": True,
                    },
                    episode_id=episode_id,
                )
                self.assertEqual(pack["replay"]["episode_id"], episode_id)
                requested, code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="requested",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(code, 0)
                again, code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="requested",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(code, 0)
                self.assertTrue(again["idempotent"])
                self.assertEqual(requested["event_sha"], again["event_sha"])

                request_path = root / "request.json"
                message = {
                    "schema": "ndf-agent-message/v1",
                    "request_id": request_id,
                    "pipeline": "gate",
                    "topic": "demo",
                    "task": "gate_pipeline",
                    "track": "poc",
                    "repo_head": "a" * 40,
                    "manifest_sha": manifest_sha,
                    "context_plan_sha": plan_sha,
                    "session_id": "session-demo",
                    "run_id": request_id,
                    "message": "audit gate pipeline",
                }
                response_before_request = root / "response-before-request.json"
                response_before_request.write_text(
                    json.dumps({**message, "message": "premature response"}),
                    encoding="utf-8",
                )
                premature, premature_code = workflow.record_agent_message(
                    response_before_request,
                    episode_id=episode_id,
                    role="openclaw",
                    direction="response",
                    coverage="messages_only",
                )
                self.assertEqual(premature_code, 1)
                self.assertIn("missing:matching_request", premature["errors"])
                request_path.write_text(json.dumps(message), encoding="utf-8")
                request_result, request_code = workflow.record_agent_message(
                    request_path,
                    episode_id=episode_id,
                    role="openclaw",
                    direction="request",
                    coverage="messages_only",
                )
                self.assertEqual(request_code, 0)
                self.assertTrue(request_result["valid"])
                sent, sent_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="sent",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(sent_code, 0)
                self.assertEqual(sent["state"], "sent")
                with self.assertRaisesRegex(ValueError, "response receipt missing"):
                    workflow.record_control_dispatch(
                        topic="demo",
                        pipeline="gate",
                        task="gate_pipeline",
                        episode_id=episode_id,
                        request_id=request_id,
                        state="acknowledged",
                        manifest_sha=manifest_sha,
                        context_plan_sha=plan_sha,
                        blockers=[],
                    )

                response_path = root / "response.json"
                response_path.write_text(
                    json.dumps({**message, "message": "next_human_phrase=TOPIC已审核"}),
                    encoding="utf-8",
                )
                response_result, response_code = workflow.record_agent_message(
                    response_path,
                    episode_id=episode_id,
                    role="openclaw",
                    direction="response",
                    coverage="messages_only",
                )
                self.assertEqual(response_code, 0)
                self.assertTrue(response_result["valid"])
                acknowledged, ack_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="acknowledged",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(ack_code, 0)
                self.assertEqual(acknowledged["state"], "acknowledged")
                waiting, waiting_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="waiting_human",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(waiting_code, 0)
                self.assertEqual(waiting["state"], "waiting_human")
                view = workflow.control_dispatch_view("demo", "gate")
                self.assertTrue(view["acknowledged"])
                self.assertEqual(view["request_id"], request_id)
            finally:
                workflow.ROOT = old_root
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir
                workflow.CONTROL_DISPATCH_LOG = old_dispatch_log

    def test_control_dispatch_timeout_late_ack_and_terminal(self) -> None:
        self.assertIn("delivery_unknown", workflow.CONTROL_DISPATCH_STATES)
        self.assertIn(
            "delivery_unknown",
            workflow.CONTROL_DISPATCH_TRANSITIONS["sent"],
        )
        self.assertIn(
            "acknowledged",
            workflow.CONTROL_DISPATCH_TRANSITIONS["delivery_unknown"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = workflow.ROOT
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            old_dispatch_log = workflow.CONTROL_DISPATCH_LOG
            try:
                workflow.ROOT = root
                workflow.PIPELINE_EPISODE_DIR = root / "tmp" / "ndf-control-pipelines"
                workflow.CONTROL_DISPATCH_LOG = root / "tmp" / "ndf-control-dispatch.jsonl"
                manifest_sha = "m" * 64
                plan_sha = "p" * 64
                episode_id = "ep-timeout-demo"
                request_id = "req-timeout"
                workflow.bind_pack_to_episode(
                    {
                        "topic": "demo",
                        "task": "gate_pipeline",
                        "track": "poc",
                        "provider": "openclaw",
                        "pipeline": "gate",
                        "base_sha": "a" * 40,
                        "manifest_sha": manifest_sha,
                        "plan_sha": plan_sha,
                        "safe_to_delegate": True,
                        "safe_to_dispatch": True,
                        "runtime_dispatch_ready": True,
                    },
                    episode_id=episode_id,
                )
                workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="requested",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                message = {
                    "schema": "ndf-agent-message/v1",
                    "request_id": request_id,
                    "pipeline": "gate",
                    "topic": "demo",
                    "task": "gate_pipeline",
                    "track": "poc",
                    "repo_head": "a" * 40,
                    "manifest_sha": manifest_sha,
                    "context_plan_sha": plan_sha,
                    "session_id": "session-timeout",
                    "run_id": request_id,
                    "message": "audit",
                }
                request_path = root / "request.json"
                request_path.write_text(json.dumps(message), encoding="utf-8")
                workflow.record_agent_message(
                    request_path,
                    episode_id=episode_id,
                    role="openclaw",
                    direction="request",
                    coverage="messages_only",
                )
                workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="sent",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                unknown, unknown_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="delivery_unknown",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                )
                self.assertEqual(unknown_code, 0)
                self.assertEqual(unknown["state"], "delivery_unknown")
                response_path = root / "response.json"
                response_path.write_text(
                    json.dumps({**message, "message": "late ack"}),
                    encoding="utf-8",
                )
                workflow.record_agent_message(
                    response_path,
                    episode_id=episode_id,
                    role="openclaw",
                    direction="response",
                    coverage="messages_only",
                )
                late, late_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="acknowledged",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                    response_sha="r" * 64,
                )
                self.assertEqual(late_code, 0)
                self.assertEqual(late["state"], "acknowledged")
                self.assertTrue(late["late"])
                done, done_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="gate",
                    task="gate_pipeline",
                    episode_id=episode_id,
                    request_id=request_id,
                    state="succeeded",
                    manifest_sha=manifest_sha,
                    context_plan_sha=plan_sha,
                    blockers=[],
                    response_sha="r" * 64,
                )
                self.assertEqual(done_code, 0)
                with self.assertRaisesRegex(ValueError, "terminal dispatch"):
                    workflow.record_control_dispatch(
                        topic="demo",
                        pipeline="gate",
                        task="gate_pipeline",
                        episode_id=episode_id,
                        request_id=request_id,
                        state="requested",
                        manifest_sha=manifest_sha,
                        context_plan_sha=plan_sha,
                        blockers=[],
                    )
                with self.assertRaisesRegex(ValueError, "conflicting dispatch response"):
                    workflow.record_control_dispatch(
                        topic="demo",
                        pipeline="gate",
                        task="gate_pipeline",
                        episode_id=episode_id,
                        request_id=request_id,
                        state="succeeded",
                        manifest_sha=manifest_sha,
                        context_plan_sha=plan_sha,
                        blockers=[],
                        response_sha="s" * 64,
                    )
            finally:
                workflow.ROOT = old_root
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir
                workflow.CONTROL_DISPATCH_LOG = old_dispatch_log

    def test_blocked_control_dispatch_has_retryable_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = workflow.ROOT
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            old_dispatch_log = workflow.CONTROL_DISPATCH_LOG
            try:
                workflow.ROOT = root
                workflow.PIPELINE_EPISODE_DIR = root / "tmp" / "ndf-control-pipelines"
                workflow.CONTROL_DISPATCH_LOG = root / "tmp" / "ndf-control-dispatch.jsonl"
                workflow.bind_pack_to_episode(
                    {
                        "topic": "demo",
                        "task": "binder_pipeline",
                        "track": "poc",
                        "provider": "openclaw",
                        "pipeline": "binder",
                        "base_sha": "a" * 40,
                        "safe_to_delegate": True,
                        "safe_to_dispatch": True,
                        "runtime_dispatch_ready": True,
                    },
                    episode_id="ep-binder-demo",
                )
                workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="binder",
                    task="binder_pipeline",
                    episode_id="ep-binder-demo",
                    request_id="req-blocked",
                    state="requested",
                    manifest_sha=None,
                    context_plan_sha=None,
                    blockers=[],
                )
                blocked, code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="binder",
                    task="binder_pipeline",
                    episode_id="ep-binder-demo",
                    request_id="req-blocked",
                    state="blocked",
                    manifest_sha=None,
                    context_plan_sha=None,
                    blockers=["runtime_unavailable"],
                )
                self.assertEqual(code, 0)
                self.assertEqual(blocked["state"], "blocked")
                retried, retry_code = workflow.record_control_dispatch(
                    topic="demo",
                    pipeline="binder",
                    task="binder_pipeline",
                    episode_id="ep-binder-demo",
                    request_id="req-blocked",
                    state="requested",
                    manifest_sha=None,
                    context_plan_sha=None,
                    blockers=[],
                )
                self.assertEqual(retry_code, 0)
                self.assertEqual(retried["previous_state"], "blocked")
            finally:
                workflow.ROOT = old_root
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir
                workflow.CONTROL_DISPATCH_LOG = old_dispatch_log

    def test_pack_uses_strict_preflight_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            fake_view = {
                "topic_id": "demo",
                "gates": {"implementation_approval": {"state": "valid"}},
                "delegation": {
                    "safe_to_dispatch": False,
                    "static_preflight_passed": False,
                    "runtime_dispatch_ready": False,
                    "context_plan": {"schema": "ndf-context-plan/v1"},
                    "context_verify": {"valid": False},
                    "task_manifest": {"schema": "ndf-task-manifest/v1"},
                    "manifest_sha": "m" * 64,
                    "plan_sha": "p" * 64,
                    "dispatch_blockers": ["isolation_check_failed"],
                },
                "baseline_status": "current",
                "spaces": {},
                "phase_hint": "implementing",
                "health": {
                    "checks": {
                        "perf_baseline": {"state": "passed"},
                        "isolation": {"state": "failed"},
                    }
                },
            }
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake_view),
                patch.object(
                    workflow,
                    "ensure_spec_health",
                    return_value={"state": "current"},
                ),
                patch.object(
                    workflow,
                    "poc_gate_bundles",
                    return_value={"implementation_approval": []},
                ),
                patch.object(
                    workflow,
                    "implementation_dispatch_runtime",
                    return_value=(
                        {"pipeline_reachable": False},
                        False,
                        None,
                    ),
                ),
            ):
                payload, code = workflow.pack_topic("demo")
            self.assertEqual(code, 1)
            self.assertFalse(payload["safe_to_dispatch"])
            self.assertFalse(payload["safe_to_delegate"])
            self.assertIn("isolation_check_failed", payload["blockers"])
            self.assertIn("runtime_unavailable", payload["blockers"])
            self.assertEqual(payload["manifest_sha"], "m" * 64)
            self.assertEqual(
                payload["task_manifest"]["schema"],
                "ndf-task-manifest/v1",
            )

    def test_spec_health_is_structured_and_persisted(self) -> None:
        passed = {"command": "ok", "exit_code": 0, "state": "passed", "output": "ok"}
        failed = {
            "command": "bad",
            "exit_code": 1,
            "state": "failed",
            "output": "dangling refs",
        }
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(workflow, "HEALTH_DIR", Path(tmp)),
                patch.object(
                    workflow,
                    "run_tool",
                    side_effect=[passed, passed, failed, passed],
                ),
                patch.object(workflow, "active_poc_topic_ids", return_value=["demo"]),
                patch.object(workflow, "source_generation_sha", return_value="sha-a"),
                patch.object(workflow, "git_head", return_value="git-a"),
                patch.object(workflow, "proposal_plane_warnings", return_value=[]),
            ):
                payload, code = workflow.spec_health()
                artifact = json.loads((Path(tmp) / "spec.json").read_text())
            self.assertEqual(code, 1)
            self.assertEqual(payload["checks"]["index_consistency"]["state"], "failed")
            self.assertEqual(payload["checks"]["binder_health"]["state"], "passed")
            self.assertEqual(
                payload["findings"][0]["repair_task"],
                "index_plane_split",
            )
            self.assertEqual(payload["findings"][0]["plane"], "index")
            self.assertEqual(artifact["snapshot_sha"], "sha-a")

    def test_spec_health_skips_binder_when_no_active_topics(self) -> None:
        passed = {"command": "ok", "exit_code": 0, "state": "passed", "output": "ok"}
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(workflow, "HEALTH_DIR", Path(tmp)),
                patch.object(workflow, "run_tool", return_value=passed) as run_tool,
                patch.object(workflow, "active_poc_topic_ids", return_value=[]),
                patch.object(workflow, "source_generation_sha", return_value="sha-a"),
                patch.object(workflow, "git_head", return_value="git-a"),
                patch.object(workflow, "proposal_plane_warnings", return_value=[]),
            ):
                payload, code = workflow.spec_health()
            self.assertEqual(code, 0)
            binder = payload["checks"]["binder_health"]
            self.assertEqual(binder["state"], "not_applicable")
            self.assertEqual(binder["exit_code"], 0)
            self.assertIn("trunk", binder["summary"].lower())
            kinds = [item["kind"] for item in payload["findings"]]
            self.assertNotIn("binder_health_failed", kinds)
            called_tools = [call.args[0] for call in run_tool.call_args_list]
            self.assertNotIn("ndf_bindcheck.py", called_tools)
            self.assertEqual(run_tool.call_count, 3)

    def test_spec_health_runs_bindcheck_when_active_topics_exist(self) -> None:
        passed = {"command": "ok", "exit_code": 0, "state": "passed", "output": "ok"}
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(workflow, "HEALTH_DIR", Path(tmp)),
                patch.object(workflow, "run_tool", return_value=passed) as run_tool,
                patch.object(workflow, "active_poc_topic_ids", return_value=["demo"]),
                patch.object(workflow, "source_generation_sha", return_value="sha-a"),
                patch.object(workflow, "git_head", return_value="git-a"),
                patch.object(workflow, "proposal_plane_warnings", return_value=[]),
            ):
                payload, code = workflow.spec_health()
            self.assertEqual(code, 0)
            self.assertEqual(payload["checks"]["binder_health"]["state"], "passed")
            called_tools = [call.args[0] for call in run_tool.call_args_list]
            self.assertIn("ndf_bindcheck.py", called_tools)
            bind_call = next(
                call
                for call in run_tool.call_args_list
                if call.args[0] == "ndf_bindcheck.py"
            )
            self.assertIn("--all-topics", bind_call.args)

    def test_active_poc_topic_ids_skips_closed_binders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            exploring = poc / "live" / "ndf"
            exploring.mkdir(parents=True)
            (exploring / "TOPIC.md").write_text(
                "> topic_id: live\n> status: exploring\n",
                encoding="utf-8",
            )
            rejected = poc / "dead" / "ndf"
            rejected.mkdir(parents=True)
            (rejected / "TOPIC.md").write_text(
                "> topic_id: dead\n> status: rejected\n",
                encoding="utf-8",
            )
            with patch.object(workflow, "POC", poc):
                self.assertEqual(workflow.active_poc_topic_ids(), ["live"])

    def test_health_artifact_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workflow, "HEALTH_DIR", Path(tmp)):
                path = Path(tmp) / "topic-demo.json"
                path.write_text(json.dumps({"snapshot_sha": "old"}), encoding="utf-8")
                payload = workflow.latest_topic_health("demo", "new")
            self.assertIsNotNone(payload)
            self.assertEqual(payload["state"], "stale")

    def test_action_receipts_form_append_only_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "actions.jsonl"
            with (
                patch.object(workflow, "ACTION_LOG", log),
                patch.object(workflow, "git_head", return_value="a" * 40),
                patch.object(workflow, "source_generation_sha", return_value="b" * 64),
            ):
                started = workflow.action_begin("refresh", "demo", "action-1")
                workflow.action_finish(started["action_id"], "success", [])
                records = workflow.read_action_receipts()
            self.assertEqual([record["seq"] for record in records], [1, 2])
            self.assertTrue(workflow.validate_event_chain(records)["valid"])

    def test_corrupt_action_chain_forces_unknown_projection_and_blocks_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "actions.jsonl"
            with (
                patch.object(workflow, "ACTION_LOG", log),
                patch.object(workflow, "git_head", return_value="a" * 40),
                patch.object(workflow, "source_generation_sha", return_value="b" * 64),
            ):
                workflow.action_begin("refresh", "demo", "action-1")
                record = json.loads(log.read_text(encoding="utf-8"))
                record["operation"] = "tampered"
                log.write_text(json.dumps(record) + "\n", encoding="utf-8")
                freshness = workflow.projection_freshness("b" * 64)
                self.assertEqual(freshness["state"], "unknown")
                with self.assertRaisesRegex(ValueError, "invalid action chain"):
                    workflow.action_begin("refresh", "demo", "action-2")

    def test_legacy_close_projection_is_quarantined(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "quarantined"):
            workflow._legacy_close_projection([])

    def test_project_control_pack_never_allows_stable_meta_body(self) -> None:
        with (
            patch.object(
                workflow,
                "latest_spec_health",
                return_value={
                    "state": "current",
                    "findings": [{"kind": "meta_graph_failed"}],
                    "advisor": {"read_only": True},
                },
            ),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": False}},
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal"
            )
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["allowed_write_roots"]), 1)
        self.assertTrue(
            payload["allowed_write_roots"][0].startswith(
                "spec/meta/open/proposal-meta-"
            )
        )
        self.assertTrue(payload["allowed_write_roots"][0].endswith(".md"))
        self.assertFalse(payload["runtime_dispatch_ready"])
        self.assertTrue(
            any("stable body" in item for item in payload["forbidden"])
        )

    def test_project_control_pack_accepts_bound_human_intent_without_findings(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(workflow, "latest_spec_health", return_value=None),
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal",
                "ep-human-intent",
                origin="human_intent",
                intent="Draft 是候选映射，不新增 drafts 目录。",
            )
        self.assertEqual(code, 0)
        self.assertTrue(payload["safe_to_delegate"])
        self.assertTrue(payload["safe_to_dispatch"])
        self.assertEqual(payload["request"]["origin"], "human_intent")
        self.assertEqual(len(payload["request"]["intent_sha"]), 64)
        self.assertNotIn("spec_health_findings_missing", payload["blockers"])
        self.assertIn(".openclaw/state.json", payload["forbidden"])

    def test_project_control_pack_rejects_empty_intent_and_missing_episode(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(workflow, "latest_spec_health", return_value=None),
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal",
                origin="human_intent",
                intent="   ",
            )
        self.assertEqual(code, 1)
        self.assertFalse(payload["safe_to_delegate"])
        self.assertFalse(payload["safe_to_dispatch"])
        self.assertIn("human_intent_missing", payload["blockers"])
        self.assertIn("replay_episode_missing", payload["blockers"])

    def test_project_control_pack_human_intent_separates_static_and_runtime_ready(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(workflow, "latest_spec_health", return_value=None),
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": False}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal",
                "ep-runtime-blocked",
                origin="human_intent",
                intent="改进 META 工作流入口。",
            )
        self.assertEqual(code, 1)
        self.assertTrue(payload["safe_to_delegate"])
        self.assertFalse(payload["safe_to_dispatch"])
        self.assertIn("runtime_unavailable", payload["blockers"])

    def test_project_control_pack_human_intent_fails_on_context_drift(self) -> None:
        context = {
            "task_manifest": None,
            "manifest_sha": None,
            "context_plan": None,
            "context_verify": {
                "valid": False,
                "errors": [{"kind": "file_drift"}],
                "warnings": [],
            },
            "plan_sha": None,
        }
        with (
            patch.object(workflow, "latest_spec_health", return_value=None),
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal",
                "ep-context-drift",
                origin="human_intent",
                intent="改进 META 工作流入口。",
            )
        self.assertEqual(code, 1)
        self.assertFalse(payload["safe_to_delegate"])
        self.assertIn("context_verify_failed", payload["blockers"])

    def test_project_control_pack_health_origin_still_requires_findings(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(
                workflow,
                "latest_spec_health",
                return_value={
                    "state": "current",
                    "findings": [{"kind": "meta_graph_failed"}],
                    "advisor": {"read_only": True},
                },
            ),
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.project_control_pack(
                "ndf_improvement_proposal",
                "ep-health-finding",
                origin="health_finding",
            )
        self.assertEqual(code, 0)
        self.assertTrue(payload["safe_to_dispatch"])
        self.assertEqual(payload["request"]["origin"], "health_finding")
        self.assertTrue(payload["request"]["intent_sha"])
        self.assertEqual(
            payload["required_proposal_status"],
            workflow.REQUIRED_PROCESS_PROPOSAL_STATUS,
        )
        self.assertTrue(
            any("stable body" in item for item in payload["forbidden"])
        )

    def _write_process_proposal(self, root: Path, name: str, body: str) -> Path:
        path = root / "spec" / "meta" / "open" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_process_proposal_hops_keep_implemented_until_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            self._write_process_proposal(
                root,
                "proposal-meta-pending.md",
                "# Pending hop\n\n> track: process\n> Status: Pending confirmation\n",
            )
            self._write_process_proposal(
                root,
                "proposal-meta-landed.md",
                "# Landed hop\n\n> track: process\n> Status: Implemented on 2026-08-17\n",
            )
            self._write_process_proposal(
                root,
                "proposal-meta-reviewed.md",
                "# Reviewed hop\n\n> track: process\n"
                "> Status: Implemented on 2026-08-17\n> reviewed: 已审核\n",
            )
            self._write_process_proposal(
                root,
                "proposal-meta-rejected.md",
                "# Rejected hop\n\n> track: process\n> Status: Rejected\n",
            )
            unknown = self._write_process_proposal(
                root,
                "proposal-meta-unknown.md",
                "# Unknown hop\n\n> track: process\n",
            )
            pending = root / "spec" / "meta" / "open" / "proposal-meta-pending.md"
            pending.write_text(pending.read_text(encoding="utf-8"), encoding="utf-8")
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
            ):
                _, process = workflow.scan_proposals()
                hop = workflow.focused_process_hop(process)
            by_name = {Path(item["path"]).name: item for item in process}
            self.assertEqual(
                by_name["proposal-meta-pending.md"]["lifecycle"],
                "legacy_pending_unknown",
            )
            self.assertEqual(
                by_name["proposal-meta-unknown.md"]["lifecycle"],
                "legacy_pending_unknown",
            )
            self.assertEqual(
                by_name["proposal-meta-landed.md"]["lifecycle"],
                "legacy_implemented_unbound",
            )
            self.assertEqual(
                by_name["proposal-meta-reviewed.md"]["lifecycle"],
                "legacy_reviewed_unbound",
            )
            self.assertEqual(
                by_name["proposal-meta-rejected.md"]["lifecycle"],
                "legacy_rejected_unbound",
            )
            for name in by_name:
                self.assertIsNone(by_name[name]["hop"])
                self.assertFalse(by_name[name]["actionable"])
            self.assertIsNone(hop)
            self.assertGreaterEqual(unknown.stat().st_mtime, 0)

    def test_managed_process_proposals_use_receipts_and_quarantine_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            managed_body = (
                "# Managed\n\n"
                "> track: process\n"
                "> Status: Draft\n"
                "> control-flow: managed\n"
                "> proposal-id: meta-managed\n"
                "> flow-id: flow-managed\n"
                "> land-targets: spec/meta/process.md, spec/meta/tools/ndf_context.py\n"
            )
            contract_sha = workflow.proposal_contract_sha(managed_body)
            self._write_process_proposal(
                root,
                "proposal-meta-managed.md",
                managed_body
                + "\n## Control receipts\n\n"
                + "| event | phrase | actor | at | proposal_sha | flow_id | hop | status |\n"
                + "|---|---|---|---|---|---|---|---|\n"
                + f"| proposal.confirmed | 已确认 | human | 2026-08-17T14:57:00+03:00 | {contract_sha} | flow-managed | confirm_land | valid |\n",
            )
            self._write_process_proposal(
                root,
                "proposal-meta-legacy.md",
                "# Legacy\n\n> track: process\n> Status: Implemented on 2026-08-16\n",
            )
            draft_map = spec / "meta" / "open" / "draft-map" / "proposal-meta-fake.md"
            draft_map.parent.mkdir(parents=True)
            draft_map.write_text(
                "# Mapping entry\n\n> track: process\n> Status: Draft\n",
                encoding="utf-8",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
            ):
                _, process = workflow.scan_proposals()
                focused = workflow.focused_process_hop(process)
            by_name = {Path(item["path"]).name: item for item in process}
            self.assertEqual(
                by_name["proposal-meta-managed.md"]["lifecycle"],
                "confirmed_pending_land",
            )
            self.assertEqual(
                by_name["proposal-meta-managed.md"]["hop"],
                "confirm_land",
            )
            self.assertTrue(by_name["proposal-meta-managed.md"]["actionable"])
            self.assertEqual(
                by_name["proposal-meta-legacy.md"]["lifecycle"],
                "legacy_implemented_unbound",
            )
            self.assertIsNone(by_name["proposal-meta-legacy.md"]["hop"])
            self.assertFalse(by_name["proposal-meta-legacy.md"]["actionable"])
            self.assertNotIn("proposal-meta-fake.md", by_name)
            self.assertEqual(focused["focused_path"], by_name["proposal-meta-managed.md"]["path"])

    def test_draft_map_warnings_are_warnings_not_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            charter = spec / "00-charter" / "charter.md"
            charter.parent.mkdir(parents=True)
            charter.write_text(
                "## Draft clause {#CHR-999}\n"
                "<!-- ndf: kind=arch level=may layer=L0 status=draft since=0.2 -->\n",
                encoding="utf-8",
            )
            mapped = spec / "20-behavior" / "search.md"
            mapped.parent.mkdir(parents=True)
            mapped.write_text(
                "## Mapped draft {#BEH-999}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=draft since=0.2 -->\n",
                encoding="utf-8",
            )
            stable = spec / "10-architecture" / "modules.md"
            stable.parent.mkdir(parents=True)
            stable.write_text(
                "## Stable clause {#ARCH-999}\n"
                "<!-- ndf: kind=arch level=must layer=L1 status=stable since=0.2 -->\n",
                encoding="utf-8",
            )
            entry = spec / "meta" / "open" / "draft-map" / "BEH-999.md"
            entry.parent.mkdir(parents=True)
            entry.write_text(
                "# BEH-999\n\n"
                "> clause_id: BEH-999\n"
                "> topic: demo\n"
                "> topic_ndf: poc/demo/ndf/TOPIC.md\n"
                "> proposed_status: exploring\n"
                "> refs: spec/open/proposal-demo.md\n"
                "> sha: abc\n",
                encoding="utf-8",
            )
            (spec / "meta" / "open" / "draft-map" / "README.md").write_text(
                "# mapping\n",
                encoding="utf-8",
            )
            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
            ):
                warnings = workflow.draft_map_warnings()
            by_id = {item["clause_id"]: item for item in warnings}
            self.assertIn("CHR-999", by_id)
            self.assertNotIn("BEH-999", by_id)
            self.assertNotIn("ARCH-999", by_id)
            self.assertEqual(by_id["CHR-999"]["severity"], "warning")
            self.assertEqual(by_id["CHR-999"]["kind"], "missing_draft_map_entry")

    def test_project_control_land_pack_allows_meta_body_on_confirm_hop(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/", "spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            path = self._write_process_proposal(
                root,
                "proposal-meta-draft-mapping.md",
                "# Draft mapping\n\n> track: process\n> Status: Pending confirmation\n",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
                patch.object(workflow, "latest_spec_health", return_value=None),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "runtime_status",
                    return_value={"control": {"reachable": True}},
                ),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, episode_id=None: payload,
                ),
            ):
                payload, code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "ep-land",
                    proposal=str(path.relative_to(root)),
                )
        self.assertEqual(code, 1)
        self.assertFalse(payload["safe_to_delegate"])
        self.assertIn("process_proposal_legacy_unbound", payload["blockers"])
        self.assertEqual(payload["allowed_write_roots"], [])
        self.assertIsNone(payload["next_human_phrase"])

    def test_managed_land_pack_uses_exact_land_targets_and_bound_identity(self) -> None:
        context = {
            "task_manifest": {
                "schema": "ndf-task-manifest/v1",
                "control": {
                    "proposal_id": "meta-managed",
                    "flow_id": "flow-managed",
                    "hop": "confirm_land",
                },
            },
            "manifest_sha": "a" * 64,
            "context_plan": {
                "control": {
                    "proposal_id": "meta-managed",
                    "flow_id": "flow-managed",
                    "hop": "confirm_land",
                },
                "privileges": {
                    "allowed_write_roots": [
                        "spec/meta/process.md",
                        "spec/meta/tools/ndf_context.py",
                        "spec/meta/open/proposal-meta-managed.md",
                    ]
                },
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            managed_body = (
                "# Managed\n\n"
                "> track: process\n"
                "> Status: Draft\n"
                "> control-flow: managed\n"
                "> proposal-id: meta-managed\n"
                "> flow-id: flow-managed\n"
                "> land-targets: spec/meta/process.md, spec/meta/tools/ndf_context.py\n"
            )
            contract_sha = workflow.proposal_contract_sha(managed_body)
            path = self._write_process_proposal(
                root,
                "proposal-meta-managed.md",
                managed_body
                + "\n## Control receipts\n\n"
                + "| event | phrase | actor | at | proposal_sha | flow_id | hop | status |\n"
                + "|---|---|---|---|---|---|---|---|\n"
                + f"| proposal.confirmed | 已确认 | human | 2026-08-17T14:57:00+03:00 | {contract_sha} | flow-managed | confirm_land | valid |\n",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
                patch.object(workflow, "latest_spec_health", return_value=None),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "runtime_status",
                    return_value={"control": {"reachable": True}},
                ),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, episode_id=None: payload,
                ),
            ):
                payload, code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "flow-managed--confirm-land",
                    proposal=str(path.relative_to(root)),
                )
        self.assertEqual(code, 0, payload.get("blockers"))
        self.assertEqual(payload["proposal"]["lifecycle"], "confirmed_pending_land")
        self.assertEqual(payload["proposal"]["proposal_id"], "meta-managed")
        self.assertEqual(payload["proposal"]["flow_id"], "flow-managed")
        self.assertEqual(
            payload["allowed_write_roots"],
            [
                "spec/meta/process.md",
                "spec/meta/tools/ndf_context.py",
                "spec/meta/open/proposal-meta-managed.md",
            ],
        )
        self.assertEqual(payload["next_human_phrase"], "已审核")

    def test_project_control_land_pack_review_hop_forbids_stable_body(self) -> None:
        context = {
            "task_manifest": {
                "schema": "ndf-task-manifest/v1",
                "control": {
                    "proposal_id": "meta-managed",
                    "flow_id": "flow-managed",
                    "hop": "review",
                },
            },
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {
                    "allowed_write_roots": [
                        "spec/meta/open/proposal-meta-landed.md"
                    ]
                }
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            managed_body = (
                "# Landed\n\n"
                "> track: process\n"
                "> Status: Implemented on 2026-08-17\n"
                "> control-flow: managed\n"
                "> proposal-id: meta-managed\n"
                "> flow-id: flow-managed\n"
                "> land-targets: spec/meta/process.md\n"
            )
            contract_sha = workflow.proposal_contract_sha(managed_body)
            path = self._write_process_proposal(
                root,
                "proposal-meta-landed.md",
                managed_body
                + "\n## Control receipts\n\n"
                + "| event | phrase | actor | at | proposal_sha | flow_id | hop | status |\n"
                + "|---|---|---|---|---|---|---|---|\n"
                + f"| proposal.confirmed | 已确认 | human | 2026-08-17T14:57:00+03:00 | {contract_sha} | flow-managed | confirm_land | valid |\n",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
                patch.object(workflow, "latest_spec_health", return_value=None),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "runtime_status",
                    return_value={"control": {"reachable": True}},
                ),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, episode_id=None: payload,
                ),
            ):
                payload, code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "ep-review",
                    proposal=str(path.relative_to(root)),
                    human_phrase="已审核",
                )
        self.assertEqual(code, 0, payload.get("blockers"))
        self.assertEqual(payload["proposal"]["lifecycle"], "implemented_pending_review")
        self.assertEqual(payload["proposal"]["hop"], "review")
        self.assertEqual(
            payload["allowed_write_roots"],
            ["spec/meta/open/proposal-meta-landed.md"],
        )
        self.assertTrue(any("stable body" in item for item in payload["forbidden"]))
        self.assertEqual(payload["next_human_phrase"], "已审核")

    def test_project_control_land_pack_rejects_missing_product_and_done(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {
                "privileges": {"allowed_write_roots": ["spec/meta/open/"]}
            },
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            product = spec / "open" / "proposal-product.md"
            product.parent.mkdir(parents=True)
            product.write_text("> track: poc\n", encoding="utf-8")
            self._write_process_proposal(
                root,
                "proposal-meta-done.md",
                "# Done\n\n> track: process\n"
                "> Status: Implemented on 2026-08-17\n> reviewed: true\n",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "META", spec / "meta"),
                patch.object(workflow, "latest_spec_health", return_value=None),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "runtime_status",
                    return_value={"control": {"reachable": True}},
                ),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, episode_id=None: payload,
                ),
            ):
                missing, missing_code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "ep-missing",
                    proposal="spec/meta/open/proposal-meta-missing.md",
                )
                product_pack, product_code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "ep-product",
                    proposal="spec/open/proposal-product.md",
                )
                done, done_code = workflow.project_control_pack(
                    "ndf_improvement_land",
                    "ep-done",
                    proposal="spec/meta/open/proposal-meta-done.md",
                )
        self.assertEqual(missing_code, 1)
        self.assertIn("process_proposal_missing", missing["blockers"])
        self.assertEqual(product_code, 1)
        self.assertIn("process_proposal_not_process_plane", product_pack["blockers"])
        self.assertEqual(done_code, 1)
        self.assertIn("process_proposal_legacy_unbound", done["blockers"])
        self.assertFalse(done["safe_to_delegate"])

    def test_process_intent_file_must_be_under_repo_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intent_dir = root / "tmp"
            intent_dir.mkdir()
            intent_path = intent_dir / "intent.md"
            intent_path.write_text("流程改进", encoding="utf-8")
            outside = root / "outside.md"
            outside.write_text("不允许", encoding="utf-8")
            with patch.object(workflow, "ROOT", root):
                self.assertEqual(
                    workflow.read_process_intent_file("tmp/intent.md"),
                    "流程改进",
                )
                with self.assertRaisesRegex(ValueError, "under repo tmp"):
                    workflow.read_process_intent_file(str(outside))

    def test_writable_pack_without_episode_fails_closed(self) -> None:
        payload = {
            "task": "poc_implementation",
            "track": "poc",
            "safe_to_dispatch": True,
            "allowed_write_root": "poc/demo/",
            "context_plan": {
                "privileges": {"allowed_write_roots": ["poc/demo/"]}
            },
        }
        with self.assertRaisesRegex(ValueError, "explicit Replay Episode"):
            workflow.bind_pack_to_episode(payload)

    def test_gate_sha_requires_full_exact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = root / "poc" / "demo"
            ndf = topic / "ndf"
            ndf.mkdir(parents=True)
            target = ndf / "TOPIC.md"
            target.write_text("topic", encoding="utf-8")
            gates = ndf / "GATES.md"
            with patch.object(workflow, "ROOT", root):
                expected = workflow.bundle_sha([target])
                gates.write_text(
                    "| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |\n"
                    "|---|---|---|---|---|---|---|\n"
                    f"| topic_review | TOPIC已审核 | human | now | {expected} | x | approved |\n",
                    encoding="utf-8",
                )
                view = workflow.gate_view(gates, {"topic_review": [target]})
            self.assertEqual(view["topic_review"]["state"], "valid")
            self.assertTrue(view["topic_review"]["sha_aligned"])

    def test_gate_short_hash_is_legacy_weak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "TOPIC.md"
            target.write_text("topic", encoding="utf-8")
            with patch.object(workflow, "ROOT", root):
                expected = workflow.bundle_sha([target])
                gates = root / "GATES.md"
                gates.write_text(
                    "| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |\n"
                    "|---|---|---|---|---|---|---|\n"
                    f"| topic_review | TOPIC已审核 | h | n | {expected[:12]} | x | approved |\n",
                    encoding="utf-8",
                )
                view = workflow.gate_view(gates, {"topic_review": [target]})
            self.assertEqual(view["topic_review"]["state"], "legacy_weak")
            self.assertFalse(view["topic_review"]["sha_aligned"])

    def test_workspace_file_exists_without_binding_is_unbound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".openclaw" / "state.json"
            state.parent.mkdir()
            state.write_text("{}", encoding="utf-8")
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "git_head", return_value="a" * 40),
            ):
                result = workflow.project_workspace_view()
            self.assertTrue(result["state_exists"])
            self.assertFalse(result["match"])
            self.assertEqual(result["state"], "unbound")

    def test_golden_head_aligned_and_baseline_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec"
            index = spec / "50-verification" / "golden-baseline.md"
            index.parent.mkdir(parents=True)
            sha = "a" * 40
            index.write_text(
                f"现行 Trunk 金标: **bl-demo**\n| 代码 | `{sha}` |\n",
                encoding="utf-8",
            )
            baseline = index.parent / "baselines" / "bl-demo.md"
            baseline.parent.mkdir()
            baseline.write_text("baseline", encoding="utf-8")
            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "git_head", return_value=sha),
                patch.object(workflow, "git", return_value=(0, sha)),
            ):
                result = workflow.performance_summary()
            self.assertEqual(result["golden_head_status"], "aligned")
            self.assertTrue(result["baseline_file_exists"])

    def test_golden_head_ahead_and_unresolvable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec"
            index = spec / "50-verification" / "golden-baseline.md"
            index.parent.mkdir(parents=True)
            index.write_text(
                f"现行 Trunk 金标: **bl-demo**\n| 代码 | `{'a' * 40}` |\n",
                encoding="utf-8",
            )
            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "git_head", return_value="b" * 40),
                patch.object(workflow, "git", return_value=(0, "a" * 40)),
            ):
                self.assertEqual(
                    workflow.performance_summary()["golden_head_status"],
                    "head_ahead_of_golden",
                )
            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "git_head", return_value="b" * 40),
                patch.object(workflow, "git", return_value=(1, "")),
            ):
                self.assertEqual(
                    workflow.performance_summary()["golden_head_status"],
                    "golden_unresolvable",
                )

    def test_golden_docs_only_ahead_when_trunk_tree_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec"
            index = spec / "50-verification" / "golden-baseline.md"
            index.parent.mkdir(parents=True)
            golden = "a" * 40
            index.write_text(
                f"现行 Trunk 金标: **bl-demo**\n| 代码 | `{golden}` |\n",
                encoding="utf-8",
            )
            baseline = index.parent / "baselines" / "bl-demo.md"
            baseline.parent.mkdir()
            baseline.write_text("baseline", encoding="utf-8")

            def fake_git(*args: str) -> tuple[int, str]:
                if args and args[0] == "rev-parse":
                    return (0, golden)
                if args and args[0] == "diff":
                    return (0, "")
                return (1, "")

            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "git_head", return_value="b" * 40),
                patch.object(workflow, "git", side_effect=fake_git),
            ):
                result = workflow.performance_summary()
            self.assertEqual(result["golden_head_status"], "docs_only_ahead")
            self.assertEqual(result["trunk_changed_since_golden"], [])

    def test_golden_src_ahead_lists_trunk_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec"
            index = spec / "50-verification" / "golden-baseline.md"
            index.parent.mkdir(parents=True)
            golden = "a" * 40
            index.write_text(
                f"现行 Trunk 金标: **bl-demo**\n| 代码 | `{golden}` |\n",
                encoding="utf-8",
            )
            baseline = index.parent / "baselines" / "bl-demo.md"
            baseline.parent.mkdir()
            baseline.write_text("baseline", encoding="utf-8")

            def fake_git(*args: str) -> tuple[int, str]:
                if args and args[0] == "rev-parse":
                    return (0, golden)
                if args and args[0] == "diff":
                    return (0, "src/foo.cpp\ninclude/bar.h")
                return (1, "")

            with (
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "git_head", return_value="b" * 40),
                patch.object(workflow, "git", side_effect=fake_git),
            ):
                result = workflow.performance_summary()
            self.assertEqual(result["golden_head_status"], "head_ahead_of_golden")
            self.assertEqual(
                result["trunk_changed_since_golden"],
                ["src/foo.cpp", "include/bar.h"],
            )

    def test_active_lease_latest_record_wins(self) -> None:
        records = [
            {"run_id": "r1", "topic": "demo", "result": "active"},
            {"run_id": "r1", "topic": "demo", "result": "released"},
            {"run_id": "r2", "topic": "demo", "result": "active"},
        ]
        with (
            patch.object(workflow, "read_leases", return_value=records),
            patch.object(
                workflow,
                "context_binding",
                return_value={"plan_sha": "p", "manifest_sha": "m"},
            ),
            patch.object(
                workflow,
                "validate_runtime_lease_binding",
                return_value={"valid": True, "errors": []},
            ),
            patch.object(
                workflow,
                "replay_pack_binding",
                return_value=(
                    "9" * 64,
                    {
                        "base_sha": "a" * 40,
                        "allowed_write_root": "poc/demo/",
                    },
                ),
            ),
        ):
            active = workflow.active_runtime_leases()
        self.assertEqual([item["run_id"] for item in active], ["r2"])

    def test_terminal_runtime_lease_cannot_resurrect_same_run_id(self) -> None:
        active = {
            "run_id": "r1",
            "episode_id": "ep",
            "result": "active",
            "session_id": "session",
            "task": "implement",
            "topic": "demo",
            "base_sha": "a" * 40,
            "worktree": "/repo/worktree",
            "branch": "run-r1",
            "allowed_write_root": "poc/demo/",
            "pack_sha": "b" * 64,
            "manifest_sha": "c" * 64,
            "context_plan_sha": "d" * 64,
        }
        released = {**active, "result": "released"}
        self.assertEqual(
            workflow.validate_lease_transition([active], released),
            [],
        )
        resurrected = {**active, "result": "active"}
        self.assertEqual(
            workflow.validate_lease_transition(
                [active, released],
                resurrected,
            ),
            ["run_id_already_has_lease_history"],
        )

    def test_pack_blocks_active_topic_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            fake = {
                "topic_id": "demo",
                "gates": {"implementation_approval": {"state": "valid"}},
                "delegation": {
                    "static_preflight_passed": True,
                    "runtime_dispatch_ready": False,
                    "context_plan": {},
                    "context_verify": {"valid": True},
                    "task_manifest": {"schema": "ndf-task-manifest/v1"},
                    "manifest_sha": "b" * 64,
                    "plan_sha": "a" * 64,
                    "dispatch_blockers": ["topic_active_lease"],
                },
                "spaces": {},
                "phase_hint": "implementing",
                "health": {"checks": {"perf_baseline": {}, "isolation": {}}},
            }
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake),
                patch.object(
                    workflow,
                    "ensure_spec_health",
                    return_value={"state": "current"},
                ),
                patch.object(workflow, "poc_gate_bundles", return_value={"implementation_approval": []}),
                patch.object(
                    workflow,
                    "implementation_dispatch_runtime",
                    return_value=(
                        {"pipeline_reachable": True},
                        False,
                        {"run_id": "r-active"},
                    ),
                ),
            ):
                payload, code = workflow.pack_topic("demo")
            self.assertEqual(code, 1)
            self.assertIn("topic_active_lease", payload["blockers"])
            self.assertNotIn("runtime_unavailable", payload["blockers"])
            self.assertTrue(payload["safe_to_delegate"])
            self.assertFalse(payload["safe_to_dispatch"])

    def test_repair_pack_requires_isolation_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            fake = {
                "topic_id": "demo",
                "lifecycle": "exploring",
                "gates": {"implementation_approval": {"state": "valid"}},
                "delegation": {"perf_check_passed": True},
                "health": {
                    "checks": {"isolation": {"state": "passed"}},
                    "findings": [],
                },
            }
            context = {"context_plan": {}, "context_verify": {"valid": True}, "plan_sha": "a" * 64}
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "implementation_dispatch_runtime",
                    return_value=({"pipeline_reachable": False}, False, None),
                ),
            ):
                payload, code = workflow.repair_pack("demo", "poc_isolation_repair")
            self.assertEqual(code, 1)
            self.assertIn("isolation_finding_missing", payload["blockers"])
            self.assertFalse(payload["static_preflight_passed"])
            self.assertFalse(payload["safe_to_delegate"])

    def test_repair_pack_measurement_allows_unverified_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            fake = {
                "topic_id": "demo",
                "lifecycle": "exploring",
                "gates": {"implementation_approval": {"state": "valid"}},
                "perf": {
                    "errors": [],
                    "bind": {
                        "vs": "bl-demo",
                        "config_id": "cfg-demo",
                        "measure_script": "scripts/run_sustained.sh",
                    },
                    "numbers": "pending",
                    "unverified": True,
                },
                "delegation": {"perf_check_passed": False},
                "health": {
                    "checks": {"isolation": {"state": "passed"}},
                    "findings": [],
                },
            }
            context = {
                "context_plan": {},
                "context_verify": {"valid": True},
                "plan_sha": "a" * 64,
            }
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "implementation_dispatch_runtime",
                    return_value=({"pipeline_reachable": False}, False, None),
                ),
            ):
                payload, code = workflow.repair_pack("demo", "poc_measurement")
            self.assertTrue(payload["static_preflight_passed"], payload["blockers"])
            self.assertNotIn("perf_binding_not_ready", payload["blockers"])
            self.assertIn("runtime_unavailable", payload["blockers"])
            self.assertEqual(code, 1)
            self.assertTrue(payload["safe_to_delegate"])
            self.assertFalse(payload["safe_to_dispatch"])

    def test_repair_pack_measurement_dispatches_when_acp_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            fake = {
                "topic_id": "demo",
                "lifecycle": "exploring",
                "gates": {"implementation_approval": {"state": "valid"}},
                "perf": {
                    "errors": [],
                    "bind": {
                        "vs": "bl-demo",
                        "config_id": "cfg-demo",
                        "measure_script": "scripts/run_sustained.sh",
                    },
                    "numbers": "pending",
                    "unverified": True,
                },
                "delegation": {"perf_check_passed": False},
                "health": {
                    "checks": {"isolation": {"state": "passed"}},
                    "findings": [],
                },
            }
            context = {
                "context_plan": {},
                "context_verify": {"valid": True},
                "plan_sha": "a" * 64,
            }
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(
                    workflow,
                    "implementation_dispatch_runtime",
                    return_value=({"pipeline_reachable": True}, True, None),
                ),
                patch.object(
                    workflow,
                    "bind_pack_to_episode",
                    side_effect=lambda payload, episode_id=None: payload,
                ),
            ):
                payload, code = workflow.repair_pack("demo", "poc_measurement")
            self.assertEqual(code, 0, payload["blockers"])
            self.assertTrue(payload["safe_to_delegate"])
            self.assertTrue(payload["safe_to_dispatch"])
            self.assertTrue(payload["runtime_dispatch_ready"])
            self.assertNotIn("runtime_unavailable", payload["blockers"])

    def test_probe_claude_acp_does_not_treat_cli_alone_as_reachable(self) -> None:
        workflow._ACP_PROBE = None
        with (
            patch.object(workflow.shutil, "which", return_value="/usr/bin/claude"),
            patch.object(workflow, "configured_acp_session_id", return_value=None),
        ):
            probe = workflow.probe_claude_acp(refresh=True)
        self.assertFalse(probe["reachable"])
        self.assertEqual(probe["error"], "acp_session_unconfigured")
        self.assertTrue(probe["cli_available"])
        workflow._ACP_PROBE = None

    def test_probe_claude_acp_requires_doctor_and_resume_artifact(self) -> None:
        workflow._ACP_PROBE = None
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "session.jsonl"
            resume.write_text("{}\n", encoding="utf-8")
            doctor = subprocess.CompletedProcess(
                ["claude", "doctor"],
                0,
                stdout="Claude Code doctor\nNo installation issues found.\n",
                stderr="",
            )
            agents = subprocess.CompletedProcess(
                ["claude", "agents", "--json"],
                0,
                stdout="[]",
                stderr="",
            )

            def fake_run(command, **_kwargs):
                if command[1] == "doctor":
                    return doctor
                return agents

            with (
                patch.object(workflow.shutil, "which", return_value="/usr/bin/claude"),
                patch.object(
                    workflow,
                    "configured_acp_session_id",
                    return_value="sess-1",
                ),
                patch.object(
                    workflow,
                    "claude_acp_resume_path",
                    return_value=resume,
                ),
                patch.object(workflow.subprocess, "run", side_effect=fake_run),
            ):
                probe = workflow.probe_claude_acp(refresh=True)
                status = workflow.runtime_status(False)["implementation"]
        self.assertTrue(probe["reachable"])
        self.assertTrue(probe["doctor_ok"])
        self.assertTrue(probe["resume_available"])
        self.assertTrue(status["pipeline_reachable"])
        self.assertEqual(status["status"], "idle")
        workflow._ACP_PROBE = None

    def test_replay_pack_binding_accepts_static_ready_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
            )
            (root / "README.md").write_text("ok\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "ok"], cwd=root, check=True)
            store = workflow.ndf_replay.ReplayStore(root)
            store.init_episode(
                topic="demo",
                task="poc_measurement",
                role="claude-code",
                track="poc",
                episode_id="ep-lease",
            )
            pack = {
                "schema": "ndf-implementation-repair-pack/v2",
                "topic": "demo",
                "task": "poc_measurement",
                "track": "poc",
                "manifest_sha": "b" * 64,
                "plan_sha": "c" * 64,
                "safe_to_delegate": True,
                "static_preflight_passed": True,
                "safe_to_dispatch": False,
                "runtime_dispatch_ready": False,
            }
            pack_sha = store.put_blob(pack)
            store.append_event(
                "ep-lease",
                kind="dispatch.preflight",
                actor="claude-code-acp",
                payload_sha=pack_sha,
                topic="demo",
                task="poc_measurement",
                track="poc",
                repo_head="a" * 40,
                manifest_sha="b" * 64,
                context_plan_sha="c" * 64,
                branch="implementation",
            )
            with patch.object(workflow, "ROOT", root):
                found_sha, found = workflow.replay_pack_binding(
                    "ep-lease",
                    task="poc_measurement",
                    manifest_sha="b" * 64,
                    context_plan_sha="c" * 64,
                )
            self.assertEqual(found_sha, pack_sha)
            self.assertTrue(found["safe_to_delegate"])
            self.assertFalse(found["safe_to_dispatch"])

    @staticmethod
    def _close_view() -> dict:
        exists = {"exists": True}
        return {
            "topic_id": "demo",
            "path": "poc/demo",
            "lifecycle": "exploring",
            "binder": {
                "TOPIC.md": exists,
                "DESIGN.md": exists,
                "PERF_BASELINE.md": exists,
                "DELTA.md": exists,
                "INTERFACE.md": exists,
                "evidence": {"count": 0},
            },
            "perf": {"numbers": "pending", "delta_exists": True},
            "health": {
                "checks": {"perf_baseline": {"state": "passed"}},
                "blockers": [],
            },
        }

    def test_notes_only_does_not_make_close_evidence_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "poc" / "demo" / "NOTES.md"
            notes.parent.mkdir(parents=True)
            notes.write_text("## Results\nfast\n", encoding="utf-8")
            spec = root / "spec"
            (spec / "open").mkdir(parents=True)
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
                patch.object(workflow, "CLOSE_EVIDENCE_DIR", root / "tmp" / "ndf-close-evidence"),
            ):
                result = workflow.close_projection([self._close_view()])
            topic = result["topics"][0]
            self.assertFalse(topic["evidence_ready"])
            self.assertIn("close:notes_only_untrusted", topic["blockers"])

    def test_legacy_tmp_close_report_is_never_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "tmp" / "close-plan-demo-promote.md"
            legacy.parent.mkdir()
            legacy.write_text("plan", encoding="utf-8")
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "CLOSE_EVIDENCE_DIR", root / "tmp" / "ndf-close-evidence"),
            ):
                view = workflow.close_receipt_view("demo", "promote", "plan")
            self.assertEqual(view["state"], "legacy_unbound")
            self.assertFalse(view["ready"])

    def test_valid_close_receipt_matches_current_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "proof.txt"
            evidence.write_text("ok", encoding="utf-8")
            receipt = {
                "schema": "ndf-close-evidence/v1",
                "task": "close",
                "topic": "demo",
                "mode": "promote",
                "step": "verify",
                "repo_head": "a" * 40,
                "source_generation_sha": "b" * 64,
                "manifest_sha": "f" * 64,
                "context_plan_sha": "c" * 64,
                "command": "python3 spec/meta/tools/ndf_perf_baseline.py check --topic demo",
                "input_sha": "d" * 64,
                "output_sha": workflow.evidence_bundle_sha(
                    ["proof.txt"],
                    root=root,
                ),
                "evidence_paths": ["proof.txt"],
                "started_at": "now",
                "finished_at": "later",
                "result": "passed",
                "blockers": [],
            }
            context = {
                "context_plan": {},
                "context_verify": {"valid": True},
                "manifest_sha": "f" * 64,
                "plan_sha": "c" * 64,
            }
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "git_head", return_value="a" * 40),
                patch.object(workflow, "source_generation_sha", return_value="b" * 64),
                patch.object(workflow, "context_binding", return_value=context),
            ):
                result = workflow.verify_close_receipt(receipt)
            self.assertTrue(result["valid"], result["errors"])

    def test_close_receipt_rejects_wrong_evidence_hash_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proof.txt").write_text("ok", encoding="utf-8")
            receipt = {
                "schema": "ndf-close-evidence/v1",
                "task": "close_verify",
                "topic": "demo",
                "mode": "promote",
                "step": "verify",
                "repo_head": "a" * 40,
                "source_generation_sha": "b" * 64,
                "manifest_sha": "f" * 64,
                "context_plan_sha": "c" * 64,
                "command": "echo trust-me",
                "input_sha": "d" * 64,
                "output_sha": "e" * 64,
                "evidence_paths": ["proof.txt"],
                "started_at": "now",
                "finished_at": "later",
                "result": "passed",
                "blockers": [],
            }
            context = {
                "plan_sha": "c" * 64,
                "manifest_sha": "f" * 64,
                "context_verify": {"valid": True},
            }
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "git_head", return_value="a" * 40),
                patch.object(workflow, "source_generation_sha", return_value="b" * 64),
                patch.object(workflow, "context_binding", return_value=context),
            ):
                result = workflow.verify_close_receipt(receipt)
            self.assertFalse(result["valid"])
            self.assertIn("command_not_allowed", result["errors"])
            self.assertIn("mismatch:output_sha", result["errors"])

    def test_close_command_allowlist_validates_the_executed_program(self) -> None:
        self.assertFalse(
            workflow.close_command_allowed(
                "graph",
                "echo spec/meta/tools/ndf_graphcheck.py",
            )
        )
        self.assertFalse(
            workflow.close_command_allowed(
                "verify",
                "echo run_sustained.sh",
            )
        )
        self.assertFalse(
            workflow.close_command_allowed(
                "graph",
                "python3 /tmp/ndf_graphcheck.py",
            )
        )
        self.assertTrue(
            workflow.close_command_allowed(
                "integrate",
                (
                    "python3 spec/meta/tools/ndf_workflow_status.py "
                    "completion-record --file tmp/completion.json"
                ),
            )
        )
        self.assertTrue(
            workflow.close_command_allowed(
                "finalize",
                (
                    "python3 spec/meta/tools/ndf_workflow_status.py "
                    "topic-health --topic demo"
                ),
            )
        )

    def test_completion_binds_historical_pack_and_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
            )
            (root / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            base_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
            ).strip()
            worktree = root / "tmp" / "implementation-worktree"
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "-q",
                    "-b",
                    "episode-implementation",
                    str(worktree),
                    base_sha,
                ],
                cwd=root,
                check=True,
            )
            proof = worktree / "proof.txt"
            proof.write_text("ok", encoding="utf-8")
            store = workflow.ndf_replay.ReplayStore(root)
            store.init_episode(
                topic="demo",
                task="poc_implementation",
                role="claude-code",
                track="poc",
                episode_id="ep-demo",
            )
            pack = {
                "schema": "ndf-workflow-pack/v2",
                "topic": "demo",
                "task": "poc_implementation",
                "track": "poc",
                "provider": "claude-code-acp",
                "base_sha": base_sha,
                "manifest_sha": "b" * 64,
                "plan_sha": "c" * 64,
                "context_plan": {
                    "privileges": {"allowed_write_roots": ["poc/demo/"]}
                },
                "allowed_write_root": "poc/demo/",
                "safe_to_dispatch": True,
            }
            pack_sha = store.put_blob(pack)
            store.append_event(
                "ep-demo",
                kind="dispatch.preflight",
                actor="claude-code-acp",
                payload_sha=pack_sha,
                topic="demo",
                task="poc_implementation",
                track="poc",
                repo_head=base_sha,
                manifest_sha="b" * 64,
                context_plan_sha="c" * 64,
                branch="implementation",
            )
            changed = worktree / "poc" / "demo" / "code.py"
            changed.parent.mkdir(parents=True)
            changed.write_text("print('ok')\n", encoding="utf-8")
            completion = {
                "schema": "ndf-agent-completion/v1",
                "topic": "demo",
                "task": "poc_implementation",
                "track": "poc",
                "base_sha": base_sha,
                "repo_head": base_sha,
                "manifest_sha": "b" * 64,
                "context_plan_sha": "c" * 64,
                "changed_files": ["poc/demo/code.py"],
                "changed_file_shas": {
                    "poc/demo/code.py": workflow.file_sha(changed)
                },
                "reproduce_commands": ["python3 poc/demo/test.py"],
                "evidence_paths": ["proof.txt"],
                "evidence_bundle_sha": workflow.evidence_bundle_sha(
                    ["proof.txt"],
                    root=worktree,
                ),
                "git_commit": "",
                "post_check_receipts": [
                    {
                        "command": (
                            "python3 spec/meta/tools/"
                            "ndf_poc_isolation.py check --topic demo"
                        ),
                        "result": "passed",
                        "output_sha": workflow.evidence_bundle_sha(
                            ["proof.txt"],
                            root=worktree,
                        ),
                        "evidence_paths": ["proof.txt"],
                        "verifier": {
                            "path": str(
                                workflow.TOOLS / "ndf_poc_isolation.py"
                            ),
                            "argv": [
                                "python3",
                                "spec/meta/tools/ndf_poc_isolation.py",
                                "check",
                                "--topic",
                                "demo",
                            ],
                            "version_sha": workflow.file_sha(
                                workflow.TOOLS / "ndf_poc_isolation.py"
                            ),
                            "exit_code": 0,
                            "output_schema": "ndf-poc-isolation/v1",
                        },
                    }
                ],
                "result": "success",
                "run_id": "run",
                "session_id": "session",
                "worktree": str(worktree),
                "branch": "episode-implementation",
            }
            lease = {
                "schema": "ndf-runtime-lease/v1",
                "task": "poc_implementation",
                "topic": "demo",
                "mode": "poc",
                "step": "start",
                "repo_head": base_sha,
                "source_generation_sha": "e" * 64,
                "manifest_sha": "b" * 64,
                "context_plan_sha": "c" * 64,
                "command": "runtime lease",
                "input_sha": "f" * 64,
                "output_sha": "1" * 64,
                "evidence_paths": [],
                "started_at": "2026-08-12T00:00:00Z",
                "finished_at": None,
                "result": "active",
                "blockers": [],
                "run_id": "run",
                "session_id": "session",
                "base_sha": base_sha,
                "worktree": str(worktree),
                "branch": "episode-implementation",
                "repo_root": str(root),
                "allowed_write_root": "poc/demo/",
                "pack_sha": pack_sha,
                "episode_id": "ep-demo",
            }
            changed.unlink()
            lease["binding_proof"] = workflow.runtime_lease_binding_proof(
                lease,
                root=root,
            )
            changed.write_text("print('ok')\n", encoding="utf-8")
            lease_log = root / "tmp" / "ndf-runtime-leases.jsonl"
            completion_path = root / "completion.json"
            completion_path.write_text(json.dumps(completion), encoding="utf-8")
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "LEASE_LOG", lease_log),
            ):
                missing_lease, missing_code = workflow.record_agent_completion(
                    completion_path,
                    episode_id="ep-demo",
                    role="claude-code",
                    coverage="completion_only",
                )
                self.assertEqual(missing_code, 1)
                self.assertIn(
                    "missing:active_runtime_lease",
                    missing_lease["errors"],
                )
                workflow.append_lease(lease_log, lease, root=root)
                result, code = workflow.record_agent_completion(
                    completion_path,
                    episode_id="ep-demo",
                    role="claude-code",
                    coverage="completion_only",
                )
            self.assertEqual(code, 0, result)
            self.assertTrue(result["valid"])
            self.assertEqual(result["coverage"], "completion_only")
            self.assertEqual(
                store.read_events("ep-demo", "implementation")[-1]["kind"],
                "acp.complete",
            )

    def test_project_control_git_extras_ignore_unchanged_preexisting_dirt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
            )
            (root / "README.md").write_text("ok\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            leftover = root / "poc" / "other" / "NOTES.md"
            leftover.parent.mkdir(parents=True)
            leftover.write_text("old\n", encoding="utf-8")
            target = root / "spec" / "meta" / "process.md"
            target.parent.mkdir(parents=True)
            target.write_text("landed\n", encoding="utf-8")
            acquisition = workflow.git_mutation_snapshot(root)
            leftover.write_text("old\n", encoding="utf-8")
            extras = workflow.project_control_git_extras(
                root,
                ["spec/meta/process.md"],
                acquisition,
            )
            self.assertEqual(extras, [])
            leftover.write_text("changed during hop\n", encoding="utf-8")
            extras_changed = workflow.project_control_git_extras(
                root,
                ["spec/meta/process.md"],
                acquisition,
            )
            self.assertIn("poc/other/NOTES.md", extras_changed)

    def test_project_control_declared_files_prefer_pack_write_roots(self) -> None:
        self.assertEqual(
            workflow.project_control_declared_files(
                {
                    "allowed_write_roots": [
                        "spec/meta/process.md",
                        "spec/meta/open/proposal-meta-managed.md",
                    ],
                    "proposal": {
                        "path": "spec/meta/open/proposal-meta-managed.md",
                        "land_targets": ["spec/meta/README.md"],
                    },
                }
            ),
            [
                "spec/meta/process.md",
                "spec/meta/open/proposal-meta-managed.md",
            ],
        )
        self.assertEqual(
            workflow.project_control_declared_files(
                {
                    "proposal": {
                        "path": "spec/meta/open/proposal-meta-managed.md",
                        "land_targets": ["spec/meta/process.md"],
                    }
                }
            ),
            [
                "spec/meta/process.md",
                "spec/meta/open/proposal-meta-managed.md",
            ],
        )

    def test_project_control_completion_requires_exact_declared_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sidecar = Path(tmp) / "completions"
            sidecar.mkdir()
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
            )
            process = root / "spec" / "meta" / "process.md"
            proposal = root / "spec" / "meta" / "open" / "proposal-meta-managed.md"
            process.parent.mkdir(parents=True)
            proposal.parent.mkdir(parents=True)
            process.write_text("stable\n", encoding="utf-8")
            proposal.write_text("draft\n", encoding="utf-8")
            (root / "proof.txt").write_text("ok", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            base_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
            ).strip()
            process.write_text("landed\n", encoding="utf-8")
            proposal.write_text("implemented\n", encoding="utf-8")
            store = workflow.ndf_replay.ReplayStore(root)
            store.init_episode(
                topic=None,
                task="ndf_improvement_land",
                role="openclaw",
                track="process",
                episode_id="ep-land",
            )
            declared = [
                "spec/meta/process.md",
                "spec/meta/open/proposal-meta-managed.md",
            ]
            pack = {
                "schema": "ndf-project-control-pack/v3",
                "task": "ndf_improvement_land",
                "track": "process",
                "provider": "openclaw",
                "base_sha": base_sha,
                "manifest_sha": "b" * 64,
                "plan_sha": "c" * 64,
                "proposal_id": "meta-managed",
                "flow_id": "flow-managed",
                "hop": "confirm_land",
                "allowed_write_roots": declared,
                "proposal": {
                    "path": "spec/meta/open/proposal-meta-managed.md",
                    "land_targets": ["spec/meta/process.md"],
                },
                "context_plan": {
                    "privileges": {"allowed_write_roots": declared}
                },
                "safe_to_dispatch": True,
            }
            pack_sha = store.put_blob(pack)
            store.append_event(
                "ep-land",
                kind="dispatch.preflight",
                actor="openclaw",
                payload_sha=pack_sha,
                topic=None,
                task="ndf_improvement_land",
                track="process",
                repo_head=base_sha,
                manifest_sha="b" * 64,
                context_plan_sha="c" * 64,
                branch="control",
            )
            evidence_sha = workflow.evidence_bundle_sha(["proof.txt"], root=root)
            post_check = {
                "command": (
                    "python3 spec/meta/tools/"
                    "ndf_workflow_status.py spec-health --json"
                ),
                "result": "passed",
                "output_sha": evidence_sha,
                "evidence_paths": ["proof.txt"],
                "verifier": {
                    "path": str(workflow.TOOLS / "ndf_workflow_status.py"),
                    "argv": [
                        "python3",
                        "spec/meta/tools/ndf_workflow_status.py",
                        "spec-health",
                        "--json",
                    ],
                    "version_sha": workflow.file_sha(
                        workflow.TOOLS / "ndf_workflow_status.py"
                    ),
                    "exit_code": 0,
                    "output_schema": "ndf-workflow-health/v1",
                },
            }

            def completion_for(changed: list[str]) -> dict:
                return {
                    "schema": "ndf-agent-completion/v1",
                    "task": "ndf_improvement_land",
                    "track": "process",
                    "base_sha": base_sha,
                    "repo_head": base_sha,
                    "manifest_sha": "b" * 64,
                    "context_plan_sha": "c" * 64,
                    "changed_files": changed,
                    "changed_file_shas": {
                        path: workflow.file_sha(root / path) for path in changed
                    },
                    "reproduce_commands": [
                        "python3 spec/meta/tools/ndf_workflow_status.py spec-health --json"
                    ],
                    "evidence_paths": ["proof.txt"],
                    "evidence_bundle_sha": evidence_sha,
                    "git_commit": "",
                    "post_check_receipts": [post_check],
                    "result": "success",
                    "run_id": "run-land",
                    "session_id": "session-land",
                }

            extra = root / "src" / "forbidden.cpp"
            extra.parent.mkdir(parents=True)
            extra.write_text("no\n", encoding="utf-8")
            under_path = sidecar / "under.json"
            over_path = sidecar / "over.json"
            ok_path = sidecar / "ok.json"
            under_path.write_text(
                json.dumps(completion_for([declared[0]])),
                encoding="utf-8",
            )
            over_path.write_text(
                json.dumps(completion_for([*declared, "src/forbidden.cpp"])),
                encoding="utf-8",
            )
            ok_path.write_text(
                json.dumps(completion_for(declared)),
                encoding="utf-8",
            )
            with patch.object(workflow, "ROOT", root):
                under, under_code = workflow.record_agent_completion(
                    under_path,
                    episode_id="ep-land",
                    role="openclaw",
                    coverage="messages_only",
                )
                over, over_code = workflow.record_agent_completion(
                    over_path,
                    episode_id="ep-land",
                    role="openclaw",
                    coverage="messages_only",
                )
                extra.unlink()
                result, code = workflow.record_agent_completion(
                    ok_path,
                    episode_id="ep-land",
                    role="openclaw",
                    coverage="messages_only",
                )
            self.assertEqual(under_code, 1, under)
            self.assertIn("project_control_mutation_mismatch", under["errors"])
            self.assertEqual(over_code, 1, over)
            self.assertIn("project_control_mutation_mismatch", over["errors"])
            self.assertEqual(code, 0, result)
            self.assertTrue(result["valid"])
            kinds = [event["kind"] for event in store.read_events("ep-land", "control")]
            self.assertIn("openclaw.response", kinds)
            self.assertIn("filesystem.changed", kinds)
            changed_event = next(
                event
                for event in store.read_events("ep-land", "control")
                if event["kind"] == "filesystem.changed"
            )
            payload = store.get_object(changed_event["payload_sha"], "blob")["data"]["value"]
            self.assertEqual(set(payload["changed_files"]), set(declared))
            self.assertEqual(set(payload["declared_files"]), set(declared))

    def test_partial_proposal_does_not_reuse_promote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            opened = spec / "open"
            opened.mkdir(parents=True)
            (opened / "proposal-demo-promote.md").write_text(
                "> track: promote\n> Topic: demo\n> reviewed: true\n",
                encoding="utf-8",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
            ):
                records = workflow.close_proposal_records("demo", "poc/demo")
            self.assertTrue(any(item["mode"] == "promote" for item in records))
            self.assertFalse(any(item["mode"] == "partial" for item in records))

    def test_implemented_proposal_is_not_implicitly_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / "spec"
            opened = spec / "open"
            opened.mkdir(parents=True)
            (opened / "proposal-demo.md").write_text(
                "> track: promote\n> Topic: demo\n> Status: Implemented\n",
                encoding="utf-8",
            )
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(workflow, "SPEC", spec),
            ):
                records = workflow.close_proposal_records("demo", "poc/demo")
            self.assertFalse(records[0]["reviewed"])

    def test_embedded_verification_detects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Canvas.tsx"
            embedded = {"snapshotSha": "old", "payloadSha": "bad", "absorbedActionId": None}
            path.write_text(
                "const SNAPSHOT = " + json.dumps(embedded) + " as const;\n",
                encoding="utf-8",
            )
            fresh = {"snapshotSha": "new", "payloadSha": "fresh", "absorbedActionId": None}
            with (
                patch.object(workflow, "snapshot", return_value={}),
                patch.object(workflow, "canvas_snapshot", return_value=fresh),
            ):
                result = workflow.verify_embedded_snapshot(path)
            self.assertFalse(result["valid"])
            self.assertFalse(result["checks"]["snapshotSha"])

    def test_projection_verification_records_payload_and_absorbed_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Canvas.tsx"
            source.write_text("const SNAPSHOT = {} as const;\n", encoding="utf-8")
            verification = {
                "valid": True,
                "checks": {
                    "snapshotSha": True,
                    "payloadSha": True,
                    "absorbedActionId": True,
                },
                "embedded": {
                    "snapshotSha": "a" * 64,
                    "payloadSha": "b" * 64,
                    "canonicalPayloadSha": "b" * 64,
                    "absorbedActionId": "action-1",
                },
                "fresh": {
                    "snapshotSha": "a" * 64,
                    "payloadSha": "b" * 64,
                    "absorbedActionId": "action-1",
                },
            }
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(
                    workflow,
                    "PROJECTION_EVIDENCE_DIR",
                    root / "tmp" / "projection",
                ),
                patch.object(workflow, "git_head", return_value="c" * 40),
            ):
                receipt = workflow.record_projection_verification(
                    source,
                    verification,
                    topic="demo",
                    episode_id=None,
                )
            self.assertEqual(receipt["projection_sha"], "b" * 64)
            self.assertEqual(receipt["absorbed_action_id"], "action-1")
            self.assertTrue((root / receipt["receipt_path"]).is_file())

    def test_embedded_projection_update_is_atomic_and_self_verifying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Canvas.tsx"
            path.write_text(
                "const SNAPSHOT = {\"old\": true} as const;\nconst KEEP = 1;\n",
                encoding="utf-8",
            )
            payload = {
                "schema": "ndf-workflow-canvas/v2",
                "snapshotSha": "a" * 64,
                "absorbedActionId": "action-1",
            }
            payload["payloadSha"] = workflow.canvas_payload_sha(payload)
            with (
                patch.object(workflow, "snapshot", return_value={}),
                patch.object(workflow, "canvas_snapshot", return_value=payload),
            ):
                result = workflow.update_embedded_snapshot(path)
            self.assertTrue(result["updated"])
            rendered = path.read_text(encoding="utf-8")
            self.assertIn(payload["payloadSha"], rendered)
            self.assertIn("const KEEP = 1;", rendered)
            self.assertNotIn('\n  "schema"', rendered)

    def test_canvas_replay_is_index_plus_one_focused_ledger(self) -> None:
        replay = {
            "schema": "ndf-replay-summary/v1",
            "episodes": [
                {
                    "id": f"old-{index}",
                    "topic": "cluster-gbdt",
                    "happenedAt": f"2026-08-01T00:00:{index:02d}Z",
                    "assembledPrompt": {"text": "A" * 1200, "whyMissing": None},
                    "timeline": [
                        {
                            "seq": 1,
                            "kind": "openclaw.request",
                            "payloadPreview": "x" * 400,
                            "preview": {
                                "orderedReads": ["poc/x/ndf/TOPIC.md"],
                                "noise": "drop-me",
                            },
                        }
                    ],
                    "kinds": ["openclaw.request"],
                    "manifestSummary": {"intent": "task", "graph": {"nodes": [1, 2, 3]}},
                    "r2Profile": {"keep": False},
                    "currentReadinessErrors": [{"kind": "file_drift", "path": "a.md", "extra": 1}],
                }
                for index in range(39)
            ],
            "focused": {
                "id": "old-38",
                "assembledPrompt": {"text": "A" * 1200, "whyMissing": None},
                "dispatchedPrompt": {"text": "B" * 200, "whyMissing": None},
                "timeline": [
                    {
                        "seq": 1,
                        "kind": "openclaw.request",
                        "payloadPreview": "x" * 400,
                        "preview": {
                            "orderedReads": ["poc/x/ndf/TOPIC.md"],
                            "noise": "drop-me",
                        },
                    }
                ],
                "r2Profile": {"keep": False},
                "manifestSummary": {"intent": "task", "seeds": ["META-001"], "graphNodes": 3},
            },
        }
        trimmed = workflow.trim_canvas_replay_prompts(replay)
        ids = [item["id"] for item in trimmed["episodes"]]
        self.assertEqual(len(ids), 39)
        self.assertNotIn("canvasOmittedEpisodes", trimmed)
        for card in trimmed["episodes"]:
            self.assertNotIn("assembledPrompt", card)
            self.assertNotIn("timeline", card)
            self.assertNotIn("r2Profile", card)
        focused = trimmed["focused"]
        self.assertEqual(focused["id"], "old-38")
        self.assertLessEqual(
            len(focused["assembledPrompt"]["text"]),
            workflow.ndf_replay.CANVAS_PROMPT_LIMIT,
        )
        self.assertNotIn("r2Profile", focused)
        self.assertEqual(
            focused["timeline"][0]["preview"],
            {"orderedReads": ["poc/x/ndf/TOPIC.md"]},
        )
        compact = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(compact.encode("utf-8")), workflow.CANVAS_SNAPSHOT_BYTE_LIMIT)

    def test_canvas_delegation_omits_compiler_manifest(self) -> None:
        slim = workflow.slim_canvas_delegation(
            {
                "safe_to_dispatch": False,
                "plan_sha": "b" * 64,
                "manifest_sha": "a" * 64,
                "task_manifest": {"schema": "ndf-task-manifest/v1", "pad": "x" * 20_000},
                "context_plan": {
                    "schema": "ndf-context-plan/v1",
                    "role": "claude-code",
                    "task": "poc_implementation",
                    "track": "poc",
                    "topic": "hotspot-optimization",
                    "plan_sha": "b" * 64,
                    "ordered_reads": [
                        {
                            "order": 1,
                            "path": "poc/hotspot-optimization/ndf/TOPIC.md",
                            "phase": "design",
                            "reason": "binder",
                            "bytes": "y" * 8_000,
                        }
                    ],
                    "seed_ids": ["BEH-025"],
                    "graph": {
                        "nodes": [
                            {
                                "id": "BEH-025",
                                "title": "POC 装订",
                                "file": "meta/process.md",
                                "hop": 0,
                                "edges": {"depends-on": ["META-001"]},
                                "body": "z" * 8_000,
                            }
                        ],
                        "depth": 2,
                        "truncated": [],
                        "blockers": [],
                    },
                    "implementation_surface": ["poc/hotspot-optimization/"],
                    "privileges": {
                        "allowed_write_roots": ["poc/hotspot-optimization/"],
                        "forbidden_write_paths": ["src/"],
                        "summary_only": False,
                    },
                },
                "context_verify": {
                    "valid": True,
                    "plan_sha": "b" * 64,
                    "errors": [],
                    "warnings": [],
                },
            }
        )
        self.assertNotIn("task_manifest", slim)
        plan = slim["context_plan"]
        self.assertEqual(plan["ordered_reads"][0]["path"], "poc/hotspot-optimization/ndf/TOPIC.md")
        self.assertNotIn("bytes", plan["ordered_reads"][0])
        self.assertEqual(plan["graph"]["nodes"], [])
        self.assertEqual(plan["graph"]["node_count"], 1)
        compact = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(compact.encode("utf-8")), 4_000)

    def test_pick_canvas_focused_honors_replay_episode(self) -> None:
        episodes = [
            {"id": "ep-old", "topic": "cluster-gbdt", "happenedAt": "2026-08-01T00:00:00Z"},
            {"id": "ep-new", "topic": "page-packer", "happenedAt": "2026-08-18T08:00:00Z"},
        ]
        self.assertEqual(
            workflow.ndf_replay.pick_canvas_focused_id(episodes, "ep-old", "page-packer"),
            "ep-old",
        )
        self.assertEqual(
            workflow.ndf_replay.pick_canvas_focused_id(episodes, None, "page-packer"),
            "ep-new",
        )

    def test_update_embedded_snapshot_rejects_oversize_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Canvas.tsx"
            path.write_text("const SNAPSHOT = {\"old\": true};\n", encoding="utf-8")
            huge = {"schema": "ndf-workflow-canvas/v2", "pad": "x" * 130_000}
            huge["payloadSha"] = workflow.canvas_payload_sha(huge)
            with (
                patch.object(workflow, "snapshot", return_value={}),
                patch.object(workflow, "canvas_snapshot", return_value=huge),
            ):
                with self.assertRaises(ValueError) as caught:
                    workflow.update_embedded_snapshot(path)
            self.assertIn("exceeds", str(caught.exception))

    def test_canvas_payload_hash_is_deterministic_and_non_recursive(self) -> None:
        left = {"schema": "x", "value": {"b": 2, "a": 1}}
        right = {"value": {"a": 1, "b": 2}, "schema": "x", "payloadSha": "stale"}
        self.assertEqual(
            workflow.canvas_payload_sha(left),
            workflow.canvas_payload_sha(right),
        )

    def test_canvas_payload_hash_ignores_observation_clock_fields(self) -> None:
        left = {
            "schema": "x",
            "generatedAt": "t1",
            "runtime": {"probe": {"age": 1, "probed_at": "t1"}},
            "checks": {"bind": {"summary": "generated at t1", "state": "passed"}},
        }
        right = {
            "schema": "x",
            "generatedAt": "t2",
            "runtime": {"probe": {"age": 2, "probed_at": "t2"}},
            "checks": {"bind": {"summary": "generated at t2", "state": "passed"}},
        }
        self.assertEqual(
            workflow.canvas_payload_sha(left),
            workflow.canvas_payload_sha(right),
        )

    def test_control_task_allowed_roots_are_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            poc = Path(tmp)
            ndf = poc / "demo" / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text("> topic_id: demo\n", encoding="utf-8")
            gates = {
                name: {"state": "valid"}
                for name in ("topic_review", "design_review", "implementation_approval")
            }
            fake = {
                "topic_id": "demo",
                "gates": gates,
                "phase_hint": "implementing",
                "spaces": {"design": {"gaps": []}, "implementation": {"gaps": []}, "test": {"gaps": []}},
            }
            context = {"context_plan": {}, "context_verify": {"valid": True}, "plan_sha": "a" * 64}
            runtime = {"control": {"reachable": True}}
            with (
                patch.object(workflow, "POC", poc),
                patch.object(workflow, "topic_view", return_value=fake),
                patch.object(workflow, "poc_gate_bundles", return_value={name: [] for name in gates}),
                patch.object(workflow, "context_binding", return_value=context),
                patch.object(workflow, "runtime_status", return_value=runtime),
            ):
                audit, _ = workflow.control_pack("demo", "gate_sha_audit")
                gate, _ = workflow.control_pack("demo", "gate_pipeline")
                binder, _ = workflow.control_pack("demo", "binder_amend")
                focused, _ = workflow.control_pack(
                    "demo", "binder_amend", focus_binder_facet="design"
                )
                proposal, _ = workflow.control_pack("demo", "control_proposal")
            self.assertEqual(audit["allowed_write_roots"], [])
            self.assertEqual(
                gate["allowed_write_roots"], ["poc/demo/ndf/GATES.md"]
            )
            self.assertEqual(
                binder["allowed_write_roots"],
                [
                    f"poc/demo/ndf/{workflow.BINDER_FACET_FILES[facet]}"
                    for facet in workflow.BINDER_FACET_ORDER
                ],
            )
            self.assertEqual(
                focused["allowed_write_roots"], ["poc/demo/ndf/DESIGN.md"]
            )
            self.assertEqual(proposal["allowed_write_roots"], ["spec/open/", "spec/meta/open/"])
            self.assertNotIn(".openclaw/state.json", proposal["allowed_write_roots"])

    def test_control_proposal_idea_hop_does_not_require_topic(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {"privileges": {"allowed_write_roots": ["spec/open/"]}},
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.control_pack(
                None,
                "control_proposal",
                "ep-product-idea",
                intent="试 WILLNEED 替换 yield。",
            )
        self.assertEqual(code, 0)
        self.assertIsNone(payload["topic"])
        self.assertTrue(payload["safe_to_delegate"])
        self.assertEqual(payload["allowed_write_roots"], ["spec/open/"])
        self.assertEqual(payload["request"]["origin"], "human_intent")
        self.assertEqual(len(payload["request"]["intent_sha"]), 64)
        self.assertEqual(payload["next_human_phrase"], "已确认")
        self.assertIn("poc/", payload["forbidden"])
        self.assertIn("spec/meta/open/", payload["forbidden"])
        self.assertNotIn("poc/", "".join(payload["required_reads"]))

    def test_control_proposal_idea_hop_rejects_empty_intent(self) -> None:
        context = {
            "task_manifest": {"schema": "ndf-task-manifest/v1"},
            "manifest_sha": "a" * 64,
            "context_plan": {"privileges": {"allowed_write_roots": ["spec/open/"]}},
            "context_verify": {"valid": True, "errors": [], "warnings": []},
            "plan_sha": "b" * 64,
        }
        with (
            patch.object(workflow, "context_binding", return_value=context),
            patch.object(
                workflow,
                "runtime_status",
                return_value={"control": {"reachable": True}},
            ),
            patch.object(
                workflow,
                "bind_pack_to_episode",
                side_effect=lambda payload, episode_id=None: payload,
            ),
        ):
            payload, code = workflow.control_pack(
                None,
                "control_proposal",
                "ep-product-idea",
                intent="  \n",
            )
        self.assertEqual(code, 1)
        self.assertIn("human_intent_missing", payload["blockers"])
        self.assertFalse(payload["safe_to_delegate"])

    def test_control_proposal_unknown_topic_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workflow, "POC", Path(tmp)):
                with self.assertRaises(FileNotFoundError):
                    workflow.control_pack("does-not-exist", "control_proposal")

    def test_control_pack_without_topic_rejects_gate_tasks(self) -> None:
        with self.assertRaises(ValueError):
            workflow.control_pack(None, "gate_pipeline")

    def test_gate_handoff_and_decision_required_are_separate(self) -> None:
        findings = workflow.gate_findings(
            "demo",
            {
                "topic_review": {"state": "valid"},
                "design_review": {"state": "pending"},
                "implementation_approval": {"state": "pending"},
            },
        )
        findings.append(
            workflow.finding(
                scope="topic",
                space="Design",
                kind="missing_design",
                severity="error",
                evidence="DESIGN missing",
                repair_owner="openclaw",
                repair_task="binder_amend",
                allowed_write_root="poc/demo/ndf/",
            )
        )
        pipelines = workflow.control_pipelines_view("demo", findings)
        self.assertTrue(pipelines["gate"]["blocked_by_binder"])
        self.assertEqual(
            pipelines["gate"]["handoff"]["blocked_gate"], "design_review"
        )
        self.assertEqual(
            pipelines["gate"]["handoff"]["next_binder_facet"], "design"
        )
        self.assertFalse(pipelines["gate"]["decision_required"])

        binder_only = [item for item in findings if item.get("pipeline") == "binder"]
        completed = workflow.control_pipelines_view("demo", binder_only)
        self.assertTrue(completed["gate"]["decision_required"])
        self.assertFalse(completed["gate"]["close_eligible"])
        chosen = workflow.control_pipelines_view(
            "demo",
            binder_only,
            selected_decision="reject",
        )
        self.assertFalse(chosen["gate"]["decision_required"])

    def test_all_valid_gates_need_decision_before_close_phase(self) -> None:
        gates = {name: {"state": "valid"} for name in workflow.GATE_ORDER}
        spaces = {
            "implementation": {"ready": True},
            "test": {"ready": True},
        }
        self.assertEqual(
            workflow.phase_hint_for_decision(
                "exploring", gates, spaces, None
            ),
            "decision_required",
        )
        self.assertEqual(
            workflow.phase_hint_for_decision(
                "exploring", gates, spaces, "implement"
            ),
            "close_ready",
        )
        self.assertEqual(
            workflow.phase_hint_for_decision(
                "exploring", gates, spaces, "reject"
            ),
            "close_selected",
        )
        self.assertEqual(
            workflow.phase_hint_for_decision(
                "exploring", gates, spaces, "continue_exploring"
            ),
            "exploring",
        )
        self.assertEqual(
            workflow.phase_hint_for_decision(
                "exploring", gates, spaces, "amend"
            ),
            "exploring",
        )

    def test_topic_decision_view_reads_selected_decision_header(self) -> None:
        gates = {name: {"state": "valid"} for name in workflow.GATE_ORDER}
        pending = workflow.topic_decision_view(
            "> status: exploring\n> next_gate: go\n",
            "exploring",
            gates,
        )
        self.assertEqual(pending["state"], "decision_required")
        self.assertTrue(pending["decision_required"])
        self.assertIsNone(pending["selected"])
        self.assertIsNone(pending["source"])

        selected = workflow.topic_decision_view(
            "> status: exploring\n> selected_decision: continue_exploring\n",
            "exploring",
            gates,
        )
        self.assertEqual(selected["state"], "selected")
        self.assertEqual(selected["selected"], "continue_exploring")
        self.assertFalse(selected["decision_required"])
        self.assertEqual(selected["source"], "TOPIC.md:selected_decision")

        invalid = workflow.topic_decision_view(
            "> status: exploring\n> selected_decision: keep-going\n",
            "exploring",
            gates,
        )
        self.assertEqual(invalid["state"], "decision_required")
        self.assertIsNone(invalid["selected"])

    def test_not_ready_offers_early_reject_not_promote(self) -> None:
        gates = {
            "topic_review": {"state": "missing"},
            "design_review": {"state": "missing"},
            "implementation_approval": {"state": "missing"},
        }
        view = workflow.topic_decision_view(
            "> status: exploring\n",
            "exploring",
            gates,
            spaces={"implementation": {"code_files": ["poc/demo/run.sh"]}},
            delta={"latest_round": "| R0 | 2026-08-10 | +1.4% |"},
            evidence_count=1,
        )
        self.assertEqual(view["state"], "not_ready")
        self.assertFalse(view["decision_required"])
        self.assertTrue(view["early_close_allowed"])
        self.assertIn("reject", view["offered"])
        self.assertIn("amend", view["offered"])
        self.assertNotIn("promote", view["offered"])
        self.assertNotIn("partial", view["offered"])
        self.assertNotIn("implement", view["offered"])
        self.assertNotIn("continue_exploring", view["offered"])
        self.assertEqual(view["blocked"]["promote"], "gates_not_valid")
        self.assertEqual(view["blocked"]["implement"], "gates_not_valid")

    def test_implement_and_continue_exploring_are_mutually_exclusive(self) -> None:
        gates = {name: {"state": "valid"} for name in workflow.GATE_ORDER}
        first = workflow.topic_decision_view(
            "> status: exploring\n",
            "exploring",
            gates,
            spaces={"implementation": {"code_files": []}},
            delta={"latest_round": None},
            evidence_count=0,
        )
        self.assertFalse(first["round_started"])
        self.assertIn("implement", first["offered"])
        self.assertNotIn("continue_exploring", first["offered"])
        self.assertEqual(first["blocked"]["continue_exploring"], "no_poc_round_yet")

        later = workflow.topic_decision_view(
            "> status: exploring\n",
            "exploring",
            gates,
            spaces={
                "implementation": {
                    "code_files": ["poc/demo/train.py"],
                }
            },
            delta={"latest_round": "| R1 | 2026-08-14 | entropy saturated |"},
            evidence_count=3,
        )
        self.assertTrue(later["round_started"])
        self.assertIn("continue_exploring", later["offered"])
        self.assertNotIn("implement", later["offered"])
        self.assertEqual(later["blocked"]["implement"], "poc_round_exists")
        self.assertTrue(
            workflow.poc_round_started(
                {"implementation": {"code_files": ["poc/demo/train.py"]}},
                {"latest_round": "R1 entropy"},
                1,
            )
        )
        self.assertFalse(
            workflow.poc_round_started(
                {"implementation": {"code_files": []}},
                {"latest_round": "skeleton only"},
                0,
            )
        )

    def test_decision_briefing_from_completion_and_delta_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            topic_dir = Path(tmp) / "demo"
            evidence = topic_dir / "ndf" / "evidence"
            evidence.mkdir(parents=True)
            delta = (
                "# DELTA\n\n## Rounds\n\n"
                "| round | date | conclusion |\n"
                "|-------|------|------------|\n"
                "| R0 | 2026-08-10 | old |\n"
                "| R1-entropy | 2026-08-14 | **A1 rejected** |\n"
            )
            (topic_dir / "ndf" / "DELTA.md").write_text(delta, encoding="utf-8")
            fallback = workflow.decision_briefing(topic_dir, delta_text=delta)
            self.assertEqual(fallback["latest_round"], "R1-entropy")
            self.assertIn("A1 rejected", fallback["verdict"] or "")
            self.assertEqual(fallback["source"], "delta")
            self.assertEqual(fallback["suggested_paths"], [])

            (evidence / "round.md").write_text(
                "## Verdict\n\nEntropy saturated.\n\n"
                "## Decision path\n\n"
                "- Do not start PQ simulation\n"
                "- A2/A3 remain deferred\n",
                encoding="utf-8",
            )
            (evidence / "poc-implementation-completion.json").write_text(
                json.dumps(
                    {
                        "schema": "ndf-agent-completion/v1",
                        "summary": "R1 A1 has no incremental signal.",
                        "verdict": "A1 rejected: no incremental signal",
                        "decision_path": [
                            "Do not start PQ simulation",
                            "A2/A3 remain deferred",
                        ],
                        "suggested_paths": [
                            {
                                "mode": "reject",
                                "recommended": True,
                                "label": "负结果关闭",
                                "rationale": "A1 falsified",
                                "next_work": "Close reject. Do not start A2.",
                                "prefill": "A1 证伪，走负结果关闭。",
                            },
                            {
                                "mode": "not-a-mode",
                                "recommended": True,
                            },
                        ],
                        "evidence_paths": ["ndf/evidence/round.md"],
                    }
                ),
                encoding="utf-8",
            )
            filled = workflow.decision_briefing(topic_dir, delta_text=delta)
            self.assertEqual(filled["source"], "completion")
            self.assertEqual(filled["verdict"], "A1 rejected: no incremental signal")
            self.assertEqual(
                filled["suggested_paths"][0]["mode"],
                "reject",
            )
            self.assertEqual(len(filled["suggested_paths"]), 1)
            packed = workflow.next_work_for_mode(
                "reject",
                filled,
                "A1 证伪，走负结果关闭。",
                topic_id="demo",
            )
            self.assertEqual(packed["route"], "close")
            self.assertIn("ndf_close", packed["next_work"])
            self.assertIn("close-plan", packed["next_work"])
            self.assertIn("Close reject. Do not start A2.", packed["next_work"])
            self.assertIn("--topic demo --mode reject", packed["next_work"])
            with self.assertRaisesRegex(ValueError, "human decision text"):
                workflow.next_work_for_mode("reject", filled, "   ")

            promote = workflow.next_work_for_mode(
                "promote", {}, "晋升已验证切片。", topic_id="demo"
            )
            self.assertEqual(promote["route"], "close")
            self.assertIn("ndf_close.py plan --topic demo --mode promote", promote["next_work"])
            partial = workflow.next_work_for_mode(
                "partial", {}, "部分合入。", topic_id="demo"
            )
            self.assertEqual(partial["route"], "close")
            self.assertIn("ndf_close.py plan --topic demo --mode partial", partial["next_work"])

            fork = workflow.next_work_for_mode(
                "new_poc",
                {
                    "suggested_paths": [
                        {
                            "mode": "new_poc",
                            "route": "new_poc",
                            "next_work": "Open sibling topic after proposal.",
                        }
                    ]
                },
                "放弃当前假设，重提提案开平级新 POC。",
                topic_id="demo",
            )
            self.assertEqual(fork["route"], "new_poc")
            self.assertNotEqual(fork["route"], "binder")
            self.assertIn("sibling topic", fork["next_work"])
            self.assertIn("depends_on_topics MUST include demo", fork["next_work"])
            self.assertIn("MUST NOT binder_amend", fork["next_work"])

            amend_meaning = workflow.POC_DECISION_MEANINGS["amend"]
            self.assertIn("Same active_hypothesis", amend_meaning)
            self.assertNotIn("Change TOPIC/DESIGN (or INTERFACE hypothesis)", amend_meaning)
            self.assertEqual(workflow.next_work_route("amend"), "binder")
            self.assertEqual(workflow.next_work_route("new_poc"), "new_poc")

            normalized = workflow.normalize_suggested_paths(
                [
                    {"mode": "amend", "label": "同假设修订"},
                    {
                        "mode": "new_poc",
                        "route": "new_poc",
                        "label": "另开新 POC",
                    },
                    {"mode": "not-a-mode"},
                ]
            )
            self.assertEqual([item["mode"] for item in normalized], ["amend", "new_poc"])
            self.assertEqual(normalized[0]["route"], "binder")
            self.assertEqual(normalized[1]["route"], "new_poc")

    def test_pipeline_step_rejects_cross_pipeline_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = workflow.ROOT
            old_pipeline_dir = workflow.PIPELINE_EPISODE_DIR
            try:
                workflow.ROOT = root
                workflow.PIPELINE_EPISODE_DIR = (
                    root / "tmp" / "ndf-control-pipelines"
                )
                store = workflow.ndf_replay.ReplayStore(root)
                for episode, task in (
                    ("ep-gate", "gate_pipeline"),
                    ("ep-binder", "binder_pipeline"),
                ):
                    store.init_episode(
                        topic="demo",
                        task=task,
                        role="openclaw",
                        track="poc",
                        episode_id=episode,
                    )
                with self.assertRaisesRegex(ValueError, "cross_pipeline_write"):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="gate",
                        kind="gate.draft",
                        step_id="design_review",
                        episode_id="ep-gate",
                        payload_json=json.dumps(
                            {
                                "changed_files": ["poc/demo/ndf/DESIGN.md"],
                                "changed_sections": ["gate_receipts"],
                            }
                        ),
                    )
                with self.assertRaisesRegex(
                    ValueError, "cross_role_section_write"
                ):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="binder",
                        kind="binder.amend",
                        step_id="design",
                        episode_id="ep-binder",
                        payload_json=json.dumps(
                            {
                                "changed_files": [
                                    "poc/demo/ndf/DESIGN.md"
                                ],
                                "changed_sections": ["perf_numbers"],
                            }
                        ),
                    )
                with self.assertRaisesRegex(ValueError, "cross_pipeline_write"):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="binder",
                        kind="binder.amend",
                        step_id="design",
                        episode_id="ep-binder",
                        payload_json=json.dumps(
                            {
                                "changed_files": ["poc/demo/ndf/GATES.md"],
                                "changed_sections": ["design_contract"],
                            }
                        ),
                    )
                with self.assertRaisesRegex(
                    ValueError, "MUST NOT claim file mutations"
                ):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="gate",
                        kind="decision.selected",
                        step_id="implementation_approval",
                        episode_id="ep-gate",
                        actor="human",
                        payload_json=json.dumps(
                            {
                                "mode": "reject",
                                "changed_files": ["poc/demo/ndf/TOPIC.md"],
                            }
                        ),
                    )
                with self.assertRaisesRegex(ValueError, "invalid mode"):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="gate",
                        kind="decision.selected",
                        step_id="implementation_approval",
                        episode_id="ep-gate",
                        actor="human",
                        payload_json=json.dumps({"mode": "keep-going"}),
                    )
                with self.assertRaisesRegex(ValueError, "actor must be human"):
                    workflow.record_control_pipeline_step(
                        topic="demo",
                        pipeline="gate",
                        kind="decision.selected",
                        step_id="implementation_approval",
                        episode_id="ep-gate",
                        actor="openclaw",
                        payload_json=json.dumps({"mode": "reject"}),
                    )
                recorded, code = workflow.record_control_pipeline_step(
                    topic="demo",
                    pipeline="gate",
                    kind="decision.selected",
                    step_id="implementation_approval",
                    episode_id="ep-gate",
                    actor="human",
                    payload_json=json.dumps({"mode": "continue_exploring"}),
                )
                self.assertEqual(code, 0)
                self.assertEqual(recorded["kind"], "decision.selected")
                self.assertEqual(recorded["result"], "recorded")
            finally:
                workflow.ROOT = old_root
                workflow.PIPELINE_EPISODE_DIR = old_pipeline_dir

    def test_close_projection_requires_structured_decision(self) -> None:
        view = {
            "topic_id": "demo",
            "path": "poc/demo",
            "lifecycle": "exploring",
            "decision": {
                "state": "decision_required",
                "selected": None,
                "decision_required": True,
            },
            "binder": {
                name: {"exists": True}
                for name in (
                    "TOPIC.md",
                    "DESIGN.md",
                    "PERF_BASELINE.md",
                    "DELTA.md",
                    "INTERFACE.md",
                )
            }
            | {"evidence": {"count": 1}},
            "perf": {"numbers": "filled", "delta_exists": True},
            "health": {
                "checks": {"perf_baseline": {"state": "passed"}},
                "blockers": [],
            },
        }
        proposal = {
            "path": "spec/open/proposal-demo.md",
            "mode": "promote",
            "reviewed": True,
        }
        receipt = {"ready": True, "state": "verified", "source": "receipt"}
        with (
            patch.object(workflow, "close_proposal_records", return_value=[proposal]),
            patch.object(workflow, "close_receipt_view", return_value=receipt),
            patch.object(workflow, "read_text", return_value="historical negative result"),
        ):
            pending = workflow.close_projection([view])["topics"][0]
            self.assertTrue(pending["decision_required"])
            self.assertFalse(pending["close_eligible"])
            self.assertEqual(pending["next_step"], "decision")

            view["decision"] = {
                "state": "selected",
                "selected": "promote",
                "decision_required": False,
            }
            selected = workflow.close_projection([view])["topics"][0]
            self.assertTrue(selected["close_eligible"])
            self.assertEqual(selected["next_step"], "closed")

    @staticmethod
    def _close_selected_view(mode: str) -> dict:
        return {
            "topic_id": "demo",
            "path": "poc/demo",
            "lifecycle": "exploring",
            "decision": {
                "state": "selected",
                "selected": mode,
                "decision_required": False,
            },
            "binder": {
                name: {"exists": True}
                for name in (
                    "TOPIC.md",
                    "DESIGN.md",
                    "PERF_BASELINE.md",
                    "DELTA.md",
                    "INTERFACE.md",
                )
            }
            | {"evidence": {"count": 1}},
            "perf": {"numbers": "filled", "delta_exists": True},
            "health": {
                "checks": {"perf_baseline": {"state": "passed"}},
                "blockers": [],
            },
        }

    @staticmethod
    def _plan_only_receipts(_topic: str, _mode: str, step: str) -> dict:
        if step == "plan":
            return {"ready": True, "state": "verified", "source": "receipt"}
        return {"ready": False, "state": "missing", "source": None}

    def test_reject_na_skips_integrate_next_step(self) -> None:
        proposal = {
            "path": "spec/open/proposal-demo-reject.md",
            "mode": "reject",
            "reviewed": True,
        }
        with (
            patch.object(workflow, "close_proposal_records", return_value=[proposal]),
            patch.object(
                workflow, "close_receipt_view", side_effect=self._plan_only_receipts
            ),
        ):
            topic = workflow.close_projection([self._close_selected_view("reject")])[
                "topics"
            ][0]
        reject = topic["branches"]["reject"]
        self.assertEqual(reject["trunk_src_writes"], "none")
        self.assertEqual(reject["next_step"], "graph")
        integrate = next(item for item in reject["steps"] if item["id"] == "integrate")
        self.assertEqual(integrate["status"], "completed")
        self.assertEqual(integrate["evidence_state"], "na")
        self.assertNotEqual(topic["next_step"], "integrate")

    def test_promote_still_requires_integrate_when_src_writes_required(self) -> None:
        proposal = {
            "path": "spec/open/proposal-demo.md",
            "mode": "promote",
            "reviewed": True,
        }
        with (
            patch.object(workflow, "close_proposal_records", return_value=[proposal]),
            patch.object(
                workflow, "close_receipt_view", side_effect=self._plan_only_receipts
            ),
        ):
            topic = workflow.close_projection([self._close_selected_view("promote")])[
                "topics"
            ][0]
        promote = topic["branches"]["promote"]
        self.assertEqual(promote["trunk_src_writes"], "required")
        self.assertEqual(promote["next_step"], "integrate")
        integrate = next(item for item in promote["steps"] if item["id"] == "integrate")
        self.assertEqual(integrate["status"], "pending")

    def test_reject_required_header_keeps_integrate_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "tmp" / "close-plan-demo-reject.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("> trunk_src_writes: **required**\n", encoding="utf-8")
            proposal = {
                "path": "spec/open/proposal-demo-reject.md",
                "mode": "reject",
                "reviewed": True,
            }
            with (
                patch.object(workflow, "ROOT", root),
                patch.object(
                    workflow, "close_proposal_records", return_value=[proposal]
                ),
                patch.object(
                    workflow,
                    "close_receipt_view",
                    side_effect=self._plan_only_receipts,
                ),
            ):
                topic = workflow.close_projection(
                    [self._close_selected_view("reject")]
                )["topics"][0]
        reject = topic["branches"]["reject"]
        self.assertEqual(reject["trunk_src_writes"], "required")
        self.assertEqual(reject["next_step"], "integrate")


class TopicsLayoutProjectionTest(unittest.TestCase):
    def test_finding_carries_why_blocked_and_clause_refs(self) -> None:
        item = workflow.finding(
            scope="topic",
            space="Design",
            kind="gate_topic_review_missing",
            severity="error",
            evidence="topic_review receipt state is missing",
            repair_owner="openclaw",
            repair_task="gate_receipt_draft",
            allowed_write_root="poc/demo/ndf/",
            human_gate="TOPIC已审核",
            gate="topic_review",
        )
        self.assertEqual(item["source"], "gate")
        self.assertIn("不能进入 DESIGN", item["why_blocked"])
        self.assertEqual(item["clause_refs"][0]["id"], "BEH-025")

    def test_topic_overview_reads_contract_slice_not_runtime_noise(self) -> None:
        text = """# Topic: demo
> ndf_topic: demo
> status: exploring
> selected_decision: continue_exploring
<!-- ndf:gate-slice begin=topic_contract -->
> explore_surface: spec/20-behavior/learned-pruning
> depends_on_topics: vecblock-cluster-reorder (promoted)
> active_hypothesis: cluster entropy may add signal
## Hypothesis

Cluster sort concentrates similar vectors. Add cluster features to GBDT.

### R1 candidate
Ignore this as purpose.
<!-- ndf:gate-slice end=topic_contract -->
"""
        with tempfile.TemporaryDirectory() as tmp:
            topic_dir = Path(tmp) / "demo"
            (topic_dir / "ndf").mkdir(parents=True)
            overview = workflow.topic_overview(topic_dir, text, "exploring")
        self.assertEqual(overview["lifecycle"], "exploring")
        self.assertIn("cluster entropy", overview["hypothesis"])
        self.assertIn("Cluster sort concentrates", overview["purpose"])
        self.assertEqual(
            overview["explore_surface"],
            ["spec/20-behavior/learned-pruning"],
        )
        self.assertEqual(
            overview["idea_sources"]["depends_on_topics"],
            ["vecblock-cluster-reorder"],
        )
        self.assertNotIn("continue_exploring", overview["purpose"])

    def test_spaces_get_purpose_and_clause_refs(self) -> None:
        spaces = workflow.decorate_spaces(
            {
                "design": {"ready": True, "gaps": []},
                "implementation": {"ready": False, "gaps": ["missing_baseline_workspace"]},
                "test": {"ready": False, "gaps": ["numbers_pending"]},
            }
        )
        self.assertIn("契约", spaces["design"]["purpose"])
        self.assertEqual(spaces["test"]["clause_refs"][0]["id"], "META-007")

    def test_split_context_graph_separates_product_and_meta(self) -> None:
        context = {
            "context_plan": {
                "seed_ids": ["BEH-037", "BEH-025"],
                "graph": {
                    "nodes": [
                        {
                            "id": "BEH-037",
                            "title": "Cluster sort",
                            "file": "spec/20-behavior/learned-pruning.md",
                            "status": "stable",
                            "scope": None,
                            "hop": 0,
                            "edges": {"depends-on": ["BEH-034"]},
                        },
                        {
                            "id": "BEH-034",
                            "title": "Learned pruning",
                            "file": "spec/20-behavior/learned-pruning.md",
                            "status": "stable",
                            "scope": None,
                            "hop": 1,
                            "edges": {},
                        },
                        {
                            "id": "BEH-025",
                            "title": "POC 主题装订纪律",
                            "file": "spec/meta/process.md",
                            "status": "stable",
                            "scope": "ndf-process",
                            "hop": 0,
                            "edges": {},
                        },
                        {
                            "id": "META-012",
                            "title": "Context Plan",
                            "file": "spec/meta/process.md",
                            "status": "stable",
                            "scope": "ndf-process",
                            "hop": 1,
                            "edges": {},
                        },
                    ]
                },
            }
        }
        foundation, meta = workflow.split_context_graph(
            context, ["spec/20-behavior/learned-pruning"]
        )
        product_ids = {item["id"] for item in foundation["product_clauses"]}
        meta_ids = {item["id"] for item in meta["nodes"]}
        self.assertEqual(product_ids, {"BEH-037", "BEH-034"})
        self.assertEqual(meta_ids, {"BEH-025", "META-012"})
        self.assertEqual(foundation["stable_summary"]["stable"], 2)
        self.assertEqual(meta["stable_summary"]["stable"], 2)
        self.assertEqual(
            foundation["depends_on_edges"],
            [{"from": "BEH-037", "to": "BEH-034", "rel": "depends-on"}],
        )
        self.assertEqual(
            foundation["explore_surface_bind"][0]["clauses"],
            ["BEH-037", "BEH-034"],
        )
        grouped = workflow.findings_by_space(
            [
                {"space": "Design", "kind": "gate_topic_review_missing"},
                {"space": "Test", "kind": "numbers_pending"},
            ]
        )
        self.assertEqual(len(grouped["Design"]), 1)
        self.assertEqual(len(grouped["Test"]), 1)
        self.assertEqual(grouped["Implementation"], [])

    def test_spec_graph_findings_project_failed_product_graph(self) -> None:
        spec_view = {
            "state": "current",
            "checks": {
                "meta_graph": {
                    "command": "ok",
                    "exit_code": 0,
                    "state": "passed",
                    "summary": "ok",
                },
                "product_graph": {
                    "command": "ndf_graphcheck --product",
                    "exit_code": 1,
                    "state": "failed",
                    "summary": "dangling product refs",
                },
            },
        }
        findings = workflow.spec_graph_findings(spec_view)
        self.assertEqual(len(findings), 1)
        item = findings[0]
        self.assertEqual(item["kind"], "product_graph_failed")
        self.assertEqual(item["scope"], "project")
        self.assertEqual(item["space"], "Design")
        self.assertEqual(item["source"], "health_check")
        self.assertEqual(item["repair_task"], "product_plane_repair")
        self.assertEqual(item["plane"], "Product")
        self.assertEqual(item["allowed_write_root"], "spec/open/")
        self.assertEqual(item["clause_refs"][0]["id"], "BEH-019")
        self.assertIn("去 Product", item["why_blocked"])
        blockers = workflow.spec_graph_dispatch_blockers(
            spec_view, active=True, checks=workflow.spec_graph_tool_checks(spec_view)
        )
        self.assertEqual(blockers, ["graphcheck_failed"])

    def test_project_check_findings_route_by_plane(self) -> None:
        findings = workflow.project_check_findings(
            {
                "meta_graph": {"exit_code": 1, "output": "meta boom"},
                "product_graph": {"exit_code": 1, "output": "product boom"},
                "index_consistency": {"exit_code": 1, "output": "index boom"},
                "binder_health": {"exit_code": 1, "output": "binder boom"},
            }
        )
        by_kind = {item["kind"]: item for item in findings}
        self.assertEqual(by_kind["meta_graph_failed"]["plane"], "NDF Control")
        self.assertEqual(by_kind["meta_graph_failed"]["repair_task"], "control_proposal")
        self.assertEqual(by_kind["product_graph_failed"]["plane"], "Product")
        self.assertEqual(
            by_kind["product_graph_failed"]["repair_task"], "product_plane_repair"
        )
        self.assertNotEqual(
            by_kind["product_graph_failed"]["repair_task"], "control_proposal"
        )
        self.assertEqual(by_kind["binder_health_failed"]["plane"], "Topics")
        self.assertEqual(by_kind["binder_health_failed"]["repair_task"], "binder_amend")
        self.assertEqual(by_kind["index_consistency_failed"]["plane"], "index")
        self.assertIsNone(by_kind["index_consistency_failed"]["allowed_write_root"])

    def test_projection_freshness_uses_canonical_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "actions.jsonl"
            evidence = Path(tmp) / "projection"
            evidence.mkdir()
            with (
                patch.object(workflow, "ACTION_LOG", log),
                patch.object(workflow, "PROJECTION_EVIDENCE_DIR", evidence),
                patch.object(workflow, "git_head", return_value="a" * 40),
                patch.object(workflow, "source_generation_sha", return_value="b" * 64),
            ):
                empty = workflow.projection_freshness("b" * 64)
                self.assertEqual(empty["state"], "unknown")
                started = workflow.action_begin("refresh", "demo", "action-1")
                in_progress = workflow.projection_freshness("b" * 64)
                self.assertEqual(in_progress["state"], "refresh_in_progress")
                workflow.action_finish(started["action_id"], "success", [])
                stale = workflow.projection_freshness("b" * 64)
                self.assertEqual(stale["state"], "stale_after_action")
                (evidence / "receipt-fresh.json").write_text(
                    json.dumps(
                        {
                            "schema": "ndf-projection-receipt/v2",
                            "result": "passed",
                            "source_generation_sha": "b" * 64,
                            "absorbed_action_id": "action-1",
                            "finished_at": "2026-08-17T15:00:00+03:00",
                        }
                    ),
                    encoding="utf-8",
                )
                fresh = workflow.projection_freshness("b" * 64)
                self.assertEqual(fresh["state"], "fresh")
                log.write_text(log.read_text(encoding="utf-8") + "{not-json\n", encoding="utf-8")
                broken = workflow.projection_freshness("b" * 64)
                self.assertEqual(broken["state"], "unknown")

    def test_canvas_embed_marks_fresh_when_it_absorbs_latest_success(self) -> None:
        generation = "b" * 64
        payload = {
            "snapshotSha": generation,
            "evidenceGeneration": generation,
            "absorbedActionId": "action-1",
            "projectionFreshness": {
                "state": "stale_after_action",
                "latest_action": {
                    "action_id": "action-1",
                    "status": "finished",
                    "result": "success",
                    "evidence_generation": generation,
                },
            },
        }
        workflow.mark_canvas_fresh_if_absorbing(payload)
        self.assertEqual(payload["projectionFreshness"]["state"], "fresh")
        mismatch = {
            "snapshotSha": generation,
            "evidenceGeneration": generation,
            "absorbedActionId": "action-1",
            "projectionFreshness": {
                "state": "stale_after_action",
                "latest_action": {
                    "action_id": "action-1",
                    "status": "finished",
                    "result": "success",
                    "evidence_generation": "c" * 64,
                },
            },
        }
        workflow.mark_canvas_fresh_if_absorbing(mismatch)
        self.assertEqual(mismatch["projectionFreshness"]["state"], "stale_after_action")

    def test_passed_graphcheck_does_not_block_dispatch(self) -> None:
        spec_view = {
            "state": "current",
            "checks": {
                "meta_graph": {"exit_code": 0, "state": "passed", "summary": "ok"},
                "product_graph": {"exit_code": 0, "state": "passed", "summary": "ok"},
            },
        }
        blockers = workflow.spec_graph_dispatch_blockers(
            spec_view, active=True, checks=workflow.spec_graph_tool_checks(spec_view)
        )
        self.assertEqual(blockers, [])

    def test_ensure_spec_health_reuses_current_and_reruns_stale(self) -> None:
        current = {"state": "current", "snapshot_sha": "sha", "checks": {}}
        with (
            patch.object(workflow, "latest_spec_health", return_value=current),
            patch.object(workflow, "spec_health") as spec_health_fn,
        ):
            payload = workflow.ensure_spec_health("sha")
        self.assertEqual(payload["state"], "current")
        spec_health_fn.assert_not_called()

        stale = {"state": "stale", "snapshot_sha": "old", "checks": {}}
        fresh = {"state": "current", "snapshot_sha": "new", "checks": {}}
        with (
            patch.object(workflow, "latest_spec_health", return_value=stale),
            patch.object(workflow, "spec_health", return_value=(fresh, 0)),
        ):
            payload = workflow.ensure_spec_health("new")
        self.assertEqual(payload["state"], "current")

    def test_missing_spec_health_blocks_dispatch_as_stale_and_failed(self) -> None:
        blockers = workflow.spec_graph_dispatch_blockers(
            None,
            active=True,
            checks=workflow.spec_graph_tool_checks(None),
        )
        self.assertEqual(blockers, ["graphcheck_failed", "spec_health_stale"])
        self.assertEqual(
            workflow.spec_graph_dispatch_blockers(
                {"state": "current", "checks": {}},
                active=False,
                checks={},
            ),
            [],
        )


class KernelMapTest(unittest.TestCase):
    def test_kernel_map_reads_meta_graph_seeds(self) -> None:
        payload = workflow.kernel_map()
        self.assertTrue(payload["available"])
        self.assertGreater(payload["clause_count"], 0)
        self.assertEqual(payload["seed_ids"], list(workflow.KERNEL_SEED_IDS))
        self.assertEqual(payload["path"], "spec/meta/graph.json")
        seed_ids = {item["id"] for item in payload["seeds"]}
        self.assertTrue(
            {"META-009", "CHR-008", "BEH-018", "BEH-025", "CON-POC-001"} <= seed_ids
        )
        self.assertIn("stable", payload["stable_summary"])
        self.assertGreaterEqual(payload["stable_summary"]["stable"], 1)

    def test_kernel_map_empty_graph_marks_unavailable(self) -> None:
        payload = workflow.kernel_map({})
        self.assertFalse(payload["available"])
        self.assertEqual(payload["clause_count"], 0)
        self.assertEqual(payload["missing_seeds"], list(workflow.KERNEL_SEED_IDS))
        self.assertEqual(payload["seeds"], [])

    def test_genesis_flags_and_canvas_control_projection(self) -> None:
        genesis = workflow.genesis_status()
        self.assertIn(genesis["project_maturity"], {
            "uninitialized",
            "idea_review",
            "ndf_foundation",
            "trunk_candidate",
            "operational",
            "operational_legacy",
        })
        self.assertEqual(
            genesis["install_needed"],
            genesis["project_maturity"] in workflow.GENESIS_INSTALL_MATURITIES,
        )
        self.assertEqual(
            genesis["kernel_installed"],
            genesis["project_maturity"] == "operational" and genesis["accepted"],
        )
        self.assertIn("accepted", genesis)
        self.assertIn("genesis_trunk_sha", genesis)
        identity = workflow.business_identity()
        self.assertIn("charter_exists", identity)
        canvas = workflow.canvas_snapshot(self._minimal_snapshot_payload(genesis))
        self.assertEqual(
            canvas["control"]["kernelMap"]["seed_ids"],
            list(workflow.KERNEL_SEED_IDS),
        )
        self.assertTrue(canvas["control"]["kernelMap"]["available"])
        self.assertEqual(canvas["control"]["genesis"]["accepted"], genesis["accepted"])
        self.assertEqual(
            canvas["control"]["genesis"]["genesis_trunk_sha"],
            genesis["genesis_trunk_sha"],
        )
        self.assertEqual(
            canvas["control"]["nextActions"][0]["task"],
            "ndf_improvement_proposal",
        )
        self.assertEqual(
            canvas["control"]["processProposals"][0][2],
            "spec/meta/open/proposal-meta-demo.md",
        )
        self.assertEqual(canvas["control"]["processHop"]["hop"], "waiting_confirm")
        self.assertEqual(
            canvas["control"]["processHop"]["focusedPath"],
            "spec/meta/open/proposal-meta-demo.md",
        )
        self.assertTrue(canvas["business"]["identity"]["charterExists"])

    def _minimal_snapshot_payload(self, genesis: dict) -> dict:
        workspace = {
            "binding": {
                "repo_root": "/tmp",
                "state_path": ".openclaw/state.json",
                "active_topic": None,
            },
            "state_exists": False,
            "match": True,
            "state": "ok",
        }
        return {
            "generated_at": "2026-08-15T00:00:00Z",
            "repo_head": "abc",
            "snapshot_sha": "def",
            "evidence_generation": "def",
            "embedded_projection": {"status": "unknown", "verified_path": None},
            "payload_binding": {
                "repo_head": "abc",
                "source_generation_sha": "def",
            },
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
                "genesis": genesis,
                "kernel_map": workflow.kernel_map(
                    {
                        "clause_count": 1,
                        "nodes": {
                            "META-009": {
                                "id": "META-009",
                                "title": "Genesis",
                                "status": "stable",
                                "file": "meta/process.md",
                            }
                        },
                    }
                ),
                "process_proposals": [
                    {
                        "title": "Demo process",
                        "status": "open",
                        "path": "spec/meta/open/proposal-meta-demo.md",
                        "track": "process",
                        "hop": "waiting_confirm",
                        "lifecycle": "pending_confirmation",
                        "actionable": True,
                        "next_human_phrase": "已确认",
                    }
                ],
                "process_hop": {
                    "focused_path": "spec/meta/open/proposal-meta-demo.md",
                    "title": "Demo process",
                    "hop": "waiting_confirm",
                    "next_human_phrase": "已确认",
                    "remaining": 1,
                },
                "close": {"state_source": "tree", "topics": []},
                "spec_health": {
                    "meta_clause_count": 1,
                    "next_actions": [
                        {"task": "ndf_improvement_proposal", "owner": "openclaw"}
                    ],
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
                    "workspace": workspace,
                },
                "control": {
                    "provider": "openclaw",
                    "default_session_key": "agent:main:main",
                    "reachable": None,
                    "configured_session_visible": None,
                    "probe": None,
                    "workspace": workspace,
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


class CanvasBudgetAndReadModelTest(unittest.TestCase):
    def _topic_summary(self, topic_id: str) -> dict:
        return {
            "topic_id": topic_id,
            "path": f"poc/{topic_id}",
            "lifecycle": "exploring",
            "phase_hint": "await_topic_review",
            "hypothesis": "h",
            "expected_impact": "i",
            "current_evidence": {"evidence_files": 0, "numbers": "pending"},
            "next_gate": "TOPIC已审核",
            "decision": {},
            "explore_surface": ["src/demo.cpp"],
            "baseline_status": "unknown",
            "control_blockers": ["design:missing"],
            "surface_conflicts": [],
            "gates": {
                "topic_review": {"state": "missing", "phrase": "TOPIC已审核"},
                "design_review": {"state": "missing", "phrase": "DESIGN已审核"},
                "implementation_approval": {"state": "missing", "phrase": "可以开始实现"},
            },
            "next_human_phrase": "TOPIC已审核",
            "business": {
                "hypothesis": "h",
                "expected_impact": "i",
                "current_evidence": {"evidence_files": 0, "numbers": "pending", "latest_result": ""},
                "next_gate": "TOPIC已审核",
                "decision": {},
            },
        }

    def _workbench(self, topic_id: str) -> dict:
        summary = self._topic_summary(topic_id)
        return {
            **summary,
            "spaces": {
                "design": {"ready": False, "gaps": ["missing_design"]},
                "implementation": {"ready": False, "gaps": [], "code_files": []},
                "test": {"ready": False, "gaps": []},
            },
            "topic_overview": {"purpose": "p", "hypothesis": "h", "explore_surface": [], "idea_sources": {}, "lifecycle": "exploring"},
            "ndf_foundation": {
                "product_clauses": [
                    {"id": "BEH-018", "title": "iso", "status": "stable", "role": "seed"}
                ]
                + [
                    {"id": f"BEH-{index:03d}", "title": "x", "status": "draft", "role": "closure"}
                    for index in range(40)
                ],
                "depends_on_edges": [
                    {"from": "BEH-018", "to": "CON-POC-001", "rel": "depends-on"}
                ]
                * 20,
                "stable_summary": {"stable": 1},
            },
            "workflow_meta": {"nodes": [{"id": "META-001"}] * 8, "note": "meta"},
            "delegation": {
                "safe_to_dispatch": False,
                "plan_sha": "b" * 64,
                "task_manifest": {"pad": "x" * 8000},
                "context_plan": {
                    "role": "claude-code",
                    "task": "poc_implementation",
                    "track": "poc",
                    "topic": topic_id,
                    "plan_sha": "b" * 64,
                    "ordered_reads": [
                        {"order": i, "path": f"poc/{topic_id}/ndf/TOPIC.md", "phase": "design", "reason": "binder"}
                        for i in range(12)
                    ],
                    "seed_ids": ["BEH-025"],
                    "graph": {"nodes": [{"id": "BEH-025", "body": "z" * 2000}], "depth": 2},
                    "implementation_surface": [f"poc/{topic_id}/"],
                    "privileges": {"allowed_write_roots": [f"poc/{topic_id}/"], "forbidden_write_paths": ["src/"]},
                },
                "context_verify": {"valid": False, "plan_sha": "b" * 64, "errors": [], "warnings": []},
            },
            "health": {
                "blockers": ["design:missing"],
                "conflicts": [],
                "findings": [
                    {
                        "kind": "missing_design",
                        "severity": "error",
                        "space": "Design",
                        "evidence": "long evidence " + "e" * 400,
                        "repair_owner": "openclaw",
                        "repair_task": "binder_amend",
                    }
                ],
                "next_actions": [],
            },
            "control_pipelines": {"gate": {"pipeline": "gate", "label": "gate", "needed": True, "steps": [{"kind": "x", "label": "y", "repair_task": "gate_pipeline"}]}},
            "decision": {},
            "delta": {},
            "traceability": [],
            "gates": summary["gates"],
        }

    def test_canvas_directory_plus_one_workbench_stays_under_budget(self) -> None:
        genesis = {
            "project_maturity": "operational",
            "accepted": True,
            "genesis_trunk_sha": "a" * 40,
            "install_needed": False,
            "kernel_installed": True,
        }
        kernel = KernelMapTest()._minimal_snapshot_payload(genesis)
        topics = [self._topic_summary(f"topic-{i:02d}") for i in range(8)]
        workbench = self._workbench("topic-00")
        kernel["business"]["topics"] = topics
        kernel["topics_detail"] = [workbench]
        kernel["selected_topic"] = workbench
        kernel["replay"] = {
            "schema": "ndf-replay-summary/v1",
            "state": "indexed",
            "episodes": [
                {
                    "id": f"ep-{i}",
                    "title": f"hop {i}",
                    "happenedAt": f"2026-08-18T00:00:{i:02d}Z",
                    "kinds": ["openclaw.request"] * 8,
                    "participants": ["openclaw", "canvas"],
                    "assembledPrompt": {"text": "no"},
                }
                for i in range(80)
            ],
            "focused": {
                "id": "ep-0",
                "assembledPrompt": {"text": "ok", "whyMissing": None},
                "dispatchedPrompt": {"text": "ok", "whyMissing": None},
                "timeline": [{"seq": 1, "kind": "openclaw.request", "payloadPreview": "p"}],
            },
        }
        canvas = workflow.canvas_snapshot(kernel)
        compact = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(compact.encode("utf-8")), workflow.CANVAS_SNAPSHOT_BYTE_LIMIT)
        self.assertEqual(len(canvas["business"]["topics"]), 8)
        self.assertEqual(canvas["business"]["focusedTopicId"], "topic-00")
        self.assertIn("ndfFoundation", canvas["business"]["focusedTopic"])
        for row in canvas["business"]["topics"]:
            self.assertNotIn("ndfFoundation", row)
            self.assertNotIn("delegation", row)
        self.assertNotIn("task_manifest", canvas["business"]["focusedTopic"]["delegation"])
        self.assertEqual(canvas["business"]["focusedTopic"]["delegation"]["context_plan"]["graph"]["nodes"], [])
        self.assertLessEqual(len(canvas["business"]["focusedTopic"]["delegation"]["context_plan"]["ordered_reads"]), 5)
        self.assertLessEqual(
            len(canvas["business"]["focusedTopic"]["health"]["findings"][0].get("evidence") or ""),
            360,
        )

    def test_generation_sha_is_memoized_for_identical_git_view(self) -> None:
        workflow.reset_generation_cache()
        first = workflow.source_generation_sha()
        second = workflow.source_generation_sha()
        self.assertEqual(first, second)
        self.assertEqual(first, workflow.generation_layers()["root"])
        self.assertIn("meta", workflow.generation_layers())

    def test_snapshot_skips_create_manifest_for_directory_topics(self) -> None:
        directory = [self._workbench("keep"), self._workbench("skip-a"), self._workbench("skip-b")]
        for item in directory:
            item["lifecycle"] = "exploring"
        modes: list[str] = []

        def fake_view(path, mode="full"):
            modes.append(mode)
            return directory[0]

        with (
            patch.object(workflow, "probe_claude_acp"),
            patch.object(workflow, "generation_layers", return_value={"root": "a" * 64, "meta": "m", "product": "p", "poc": {}, "replay": "r"}),
            patch.object(workflow, "ensure_spec_health", return_value={"state": "current", "checks": {}}),
            patch.object(workflow, "latest_spec_health", return_value={"state": "current", "checks": {}}),
            patch.object(workflow, "list_topic_views", return_value=directory),
            patch.object(workflow, "topic_view", side_effect=fake_view),
            patch.object(workflow, "scan_proposals", return_value=([], [])),
            patch.object(workflow, "performance_summary", return_value={"warnings": [], "best_scenes": [], "protocol": "x", "baseline_id": "y", "status": "aligned", "configs": [], "trunk_sha": "", "golden_head_status": "aligned"}),
            patch.object(workflow, "kernel_map", return_value={"clause_count": 1, "generated_at": None}),
            patch.object(workflow, "business_identity", return_value={"name": "p", "phase": "operational", "goal_summary": "g", "charter_path": "c", "charter_exists": True, "scale_coverage": []}),
            patch.object(workflow, "business_goals", return_value=[]),
            patch.object(workflow, "capability_portfolio", return_value=[]),
            patch.object(workflow, "roadmap_summary", return_value=[]),
            patch.object(workflow, "genesis_status", return_value={"project_maturity": "operational", "accepted": True}),
            patch.object(workflow, "proposal_plane_warnings", return_value=[]),
            patch.object(workflow, "draft_map_warnings", return_value=[]),
            patch.object(workflow, "runtime_status", return_value={"implementation": {"provider": "x", "status": "idle", "pipeline_reachable": False, "default_session": None, "active_runs": [], "workspace": {"binding": {"repo_root": "/tmp", "state_path": ".openclaw/state.json"}, "state_exists": False}}, "control": {"provider": "openclaw", "default_session_key": "k", "reachable": None, "workspace": {"binding": {"repo_root": "/tmp", "state_path": ".openclaw/state.json"}, "state_exists": False}}}),
            patch.object(workflow, "replay_summary", return_value={"schema": "ndf-replay-summary/v1", "episodes": [], "focused": None}),
            patch.object(workflow, "close_projection", return_value={"state_source": "tree", "topics": []}),
        ):
            payload = workflow.snapshot("keep")
        self.assertEqual(payload["selected_topic"]["topic_id"], "keep")
        self.assertEqual(len(payload["topics_detail"]), 1)
        self.assertEqual(modes, ["canvas"])

    def test_spec_health_skips_meta_graphcheck_when_meta_layer_unchanged(self) -> None:
        previous = {
            "layers": {"meta": "meta-sha", "product": "old-product", "poc": {}, "replay": "r", "root": "old"},
            "raw_checks": {
                "meta_graph": {"command": "meta", "exit_code": 0, "state": "passed", "output": "ok"},
                "product_graph": {"command": "product", "exit_code": 0, "state": "passed", "output": "ok"},
                "index_consistency": {"command": "index", "exit_code": 0, "state": "passed", "output": "ok"},
                "binder_health": {"command": "", "exit_code": 0, "state": "not_applicable", "output": "n/a"},
            },
        }
        ran: list[tuple] = []

        def fake_tool(*args):
            ran.append(args)
            return {"command": " ".join(args), "exit_code": 0, "state": "passed", "output": "fresh"}

        with (
            patch.object(workflow, "generation_layers", return_value={"root": "new", "meta": "meta-sha", "product": "new-product", "poc": {}, "replay": "r"}),
            patch.object(workflow, "read_json_artifact", return_value=previous),
            patch.object(workflow, "active_poc_topic_ids", return_value=[]),
            patch.object(workflow, "run_tool", side_effect=fake_tool),
            patch.object(workflow, "write_json_artifact"),
            patch.object(workflow, "git_head", return_value="h"),
        ):
            payload, _ = workflow.spec_health(persist=False)
        self.assertEqual(payload["checks"]["meta_graph"]["command"], "meta")
        self.assertTrue(any(args[0] == "ndf_graphcheck.py" and "--product" in args for args in ran))
        self.assertFalse(any(args and args[0] == "ndf_graphcheck.py" and "--meta" in args for args in ran))

    def test_replay_index_reuses_cards_when_episode_head_unchanged(self) -> None:
        class DummyStore:
            root = Path("/tmp")
            def initialize(self):
                return None
            def _atomic_write(self, path, data):
                return None

        cached = {
            "heads": {"ep-1": "head-1"},
            "episodes": [{"id": "ep-1", "title": "cached", "happenedAt": "t"}],
        }
        with (
            patch.object(workflow.ndf_replay, "episode_head_map", return_value={"ep-1": "head-1"}),
            patch.object(workflow.ndf_replay, "project_canvas_index_card") as card,
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_text", return_value=json.dumps(cached)),
        ):
            payload = workflow.ndf_replay.project_canvas_index(DummyStore(), write_cache=False)
        self.assertEqual(payload["episodes"][0]["title"], "cached")
        card.assert_not_called()

    def test_update_embedded_budget_error_names_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Canvas.tsx"
            path.write_text("const SNAPSHOT = {\"old\": true};\n", encoding="utf-8")
            huge = {"schema": "ndf-workflow-canvas/v2", "pad": "x" * 130_000, "business": {"topics": ["t"] * 100, "focusedTopic": {"pad": "y" * 30_000}}, "control": {}, "replay": {"episodes": [], "focused": None}}
            huge["payloadSha"] = workflow.canvas_payload_sha(huge)
            with (
                patch.object(workflow, "snapshot", return_value={}),
                patch.object(workflow, "canvas_snapshot", return_value=huge),
            ):
                with self.assertRaises(ValueError) as caught:
                    workflow.update_embedded_snapshot(path)
            self.assertIn("exceeds", str(caught.exception))
            self.assertIn("focused_topic", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
