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
                    "poc_gate_bundles",
                    return_value={"implementation_approval": []},
                ),
            ):
                payload, code = workflow.pack_topic("demo")
            self.assertEqual(code, 1)
            self.assertFalse(payload["safe_to_dispatch"])
            self.assertEqual(payload["blockers"], ["isolation_check_failed"])

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
                patch.object(workflow, "source_generation_sha", return_value="sha-a"),
                patch.object(workflow, "git_head", return_value="git-a"),
                patch.object(workflow, "proposal_plane_warnings", return_value=[]),
            ):
                payload, code = workflow.spec_health()
                artifact = json.loads((Path(tmp) / "spec.json").read_text())
            self.assertEqual(code, 1)
            self.assertEqual(payload["checks"]["index_consistency"]["state"], "failed")
            self.assertEqual(
                payload["findings"][0]["repair_task"],
                "control_proposal",
            )
            self.assertEqual(artifact["snapshot_sha"], "sha-a")

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
        self.assertEqual(payload["allowed_write_roots"], ["spec/meta/open/"])
        self.assertFalse(payload["runtime_dispatch_ready"])
        self.assertTrue(
            any("stable body" in item for item in payload["forbidden"])
        )

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
                patch.object(workflow, "poc_gate_bundles", return_value={"implementation_approval": []}),
            ):
                payload, code = workflow.pack_topic("demo")
            self.assertEqual(code, 1)
            self.assertIn("topic_active_lease", payload["blockers"])
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
                patch.object(workflow, "topic_active_lease", return_value=None),
            ):
                payload, code = workflow.repair_pack("demo", "poc_isolation_repair")
            self.assertEqual(code, 1)
            self.assertIn("isolation_finding_missing", payload["blockers"])
            self.assertFalse(payload["static_preflight_passed"])

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
                binder, _ = workflow.control_pack("demo", "binder_amend")
                proposal, _ = workflow.control_pack("demo", "control_proposal")
            self.assertEqual(audit["allowed_write_roots"], [])
            self.assertEqual(binder["allowed_write_roots"], ["poc/demo/ndf/"])
            self.assertEqual(proposal["allowed_write_roots"], ["spec/open/", "spec/meta/open/"])
            self.assertNotIn(".openclaw/state.json", proposal["allowed_write_roots"])


if __name__ == "__main__":
    unittest.main()
