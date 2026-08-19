import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_workflow_evidence as evidence
import ndf_replay

SPEC = importlib.util.spec_from_file_location("ndf_context", TOOLS / "ndf_context.py")
assert SPEC and SPEC.loader
context = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context
SPEC.loader.exec_module(context)


class ContextCompilerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._write(
            "spec/meta/process.md",
            """# Process
## Context {#META-100}
<!-- ndf: kind=req level=must layer=L1 status=stable scope=ndf-process -->
<!-- ndf: depends-on=META-101 -->
MUST compile context.

## Base {#META-101}
<!-- ndf: kind=def level=must layer=L0 status=stable scope=ndf-process -->
Base.
""",
        )
        self._write(
            "spec/20-behavior/demo.md",
            """# Product
## Product behavior {#BEH-100}
<!-- ndf: kind=req level=must layer=L1 status=draft depends-on=BEH-101 conflicts-with=BEH-999 -->
Behavior.

## Product base {#BEH-101}
<!-- ndf: kind=arch level=must layer=L0 status=stable -->
Base.

## Product root {#BEH-102}
<!-- ndf: kind=arch level=must layer=L0 status=stable -->
Root.

## Product intent {#BEH-103}
<!-- ndf: kind=arch level=must layer=L0 status=stable -->
Intent.
""",
        )
        self._write(
            "spec/50-verification/demo.md",
            """# Verification
## Verify behavior {#VER-100}
<!-- ndf: kind=verif level=must layer=L3 status=draft verifies=BEH-100 -->
Verify it.
""",
        )
        self._write(
            "poc/demo/ndf/TOPIC.md",
            """> topic_id: demo
> status: exploring
> baseline_status: current
> baseline_trunk_sha: 0123456
> draft_clauses: BEH-100

## Draft clauses
[[BEH-100]]

## Proposals
| role | path | status |
|---|---|---|
| root | poc/demo/ndf/proposals/root.md | Draft |
""",
        )
        self._write("poc/demo/ndf/DESIGN.md", "# Design\n")
        self._write(
            "poc/demo/ndf/PERF_BASELINE.md",
            """# Perf
> vs: bl-demo
> config_id: cfg-demo
> measure_script: poc/demo/measure.py

## Numbers
SECRET_QPS = 12345

## Measure
QPS and Recall.
""",
        )
        self._write("poc/demo/ndf/DELTA.md", "# Delta\n")
        self._write("poc/demo/ndf/INTERFACE.md", "# Interface\n")
        self._write(
            "poc/demo/ndf/GATES.md",
            """| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |
|---|---|---|---|---|---|---|
| implementation_approval | 可以开始实现 | | | | | pending |
""",
        )
        self._write(
            "poc/demo/ndf/proposals/root.md",
            "# Proposal {#BEH-102}\nLinked [[BEH-103]].\n",
        )
        self._write(
            "poc/demo/ndf/evidence/r0.md",
            "# Evidence\nNo imported observation.\n",
        )
        self._write(
            "poc/demo/ndf/COMMITS.md",
            "| date | code_commit | ndf_commit | proposals | clauses | protocol | note |\n"
            "|---|---|---|---|---|---|---|\n"
            "| now | abc | def | root | BEH-100 | demo | Clauses: VER-100 |\n",
        )
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _plan(self, **overrides):
        args = {
            "root": self.root,
            "topic": "demo",
            "role": "openclaw",
            "task": "binder_amend",
            "track": "poc",
            "seed_ids": (),
            "depth": 2,
            "node_budget": 80,
            "byte_budget": 256_000,
        }
        args.update(overrides)
        return context.compile_plan(**args)

    @staticmethod
    def _resign(plan):
        plan["plan_sha"] = context.canonical_json_sha(
            {key: value for key, value in plan.items() if key != "plan_sha"}
        )

    def test_canonical_json_and_plan_are_deterministic(self) -> None:
        self.assertEqual(
            evidence.canonical_json_sha({"b": 2, "a": 1}),
            evidence.canonical_json_sha({"a": 1, "b": 2}),
        )
        self.assertEqual(self._plan(), self._plan())

    def test_manifest_is_shared_parent_for_role_plans(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
            business_goal="repair binder",
        )
        openclaw = context.role_plan(manifest, role="openclaw")
        canvas = context.role_plan(manifest, role="canvas")
        self.assertEqual(openclaw["manifest_sha"], manifest["manifest_sha"])
        self.assertEqual(canvas["manifest_sha"], manifest["manifest_sha"])
        self.assertNotEqual(openclaw["plan_sha"], canvas["plan_sha"])
        self.assertTrue(
            context.verify_plan(
                openclaw,
                root=self.root,
                manifest=manifest,
            )["valid"]
        )

    def test_context_cli_resolves_replay_object_shas_and_records_episode(self) -> None:
        store = ndf_replay.ReplayStore(self.root)
        store.init_episode(
            topic="demo",
            task="binder_amend",
            role="openclaw",
            track="poc",
            episode_id="ep-context",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            code = context.main(
                [
                    "--root",
                    str(self.root),
                    "manifest-create",
                    "--topic",
                    "demo",
                    "--task",
                    "binder_amend",
                    "--track",
                    "poc",
                    "--episode",
                    "ep-context",
                ]
            )
        self.assertEqual(code, 0)
        manifest_event = next(
            event
            for event in store.read_events("ep-context")
            if event["kind"] == "manifest.created"
        )
        with contextlib.redirect_stdout(io.StringIO()):
            code = context.main(
                [
                    "--root",
                    str(self.root),
                    "role-plan",
                    "--manifest",
                    manifest_event["payload_sha"],
                    "--role",
                    "openclaw",
                    "--episode",
                    "ep-context",
                ]
            )
        self.assertEqual(code, 0)
        plan_event = [
            event
            for event in store.read_events("ep-context")
            if event["kind"] == "context.compiled"
        ][-1]
        with contextlib.redirect_stdout(io.StringIO()):
            code = context.main(
                [
                    "--root",
                    str(self.root),
                    "context-verify",
                    "--plan",
                    plan_event["payload_sha"],
                    "--manifest",
                    manifest_event["payload_sha"],
                    "--strict",
                    "--episode",
                    "ep-context",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(store.read_events("ep-context")[-1]["kind"], "context.verified")

    def test_plan_rejects_wrong_manifest_parent(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        plan = context.role_plan(manifest, role="openclaw")
        other = dict(manifest)
        other["business_goal"] = "changed"
        other["manifest_sha"] = context.canonical_json_sha(
            {key: value for key, value in other.items() if key != "manifest_sha"}
        )
        result = context.verify_plan(
            plan,
            root=self.root,
            manifest=other,
        )
        self.assertIn(
            "plan_manifest_sha_mismatch",
            {item["kind"] for item in result["errors"]},
        )

    def test_resigned_role_plan_cannot_escalate_privileges(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        plan = context.role_plan(manifest, role="openclaw")
        plan["privileges"]["allowed_write_roots"].append("spec/40-constraints/")
        self._resign(plan)
        result = context.verify_plan(
            plan,
            root=self.root,
            manifest=manifest,
            require_manifest=True,
        )
        self.assertIn(
            "role_plan_derivation_mismatch",
            {item["kind"] for item in result["errors"]},
        )

    def test_resigned_manifest_cannot_escalate_role_policy(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        manifest["role_policies"]["openclaw"]["allowed_write_roots"].append(
            "spec/40-constraints/"
        )
        manifest["manifest_sha"] = context.canonical_json_sha(
            {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha"
            }
        )
        result = context.verify_manifest(manifest, root=self.root)
        self.assertIn(
            "manifest_role_policy_mismatch",
            {item["kind"] for item in result["errors"]},
        )

    def test_strict_verification_rejects_legacy_plan_without_manifest(self) -> None:
        plan = self._plan()
        plan["schema"] = "ndf-context-plan/v1"
        self._resign(plan)
        result = context.verify_plan(
            plan,
            root=self.root,
            require_manifest=True,
        )
        self.assertIn(
            "manifest_required_for_role_plan",
            {item["kind"] for item in result["errors"]},
        )

    def test_bundle_sha_is_order_independent_and_path_bound(self) -> None:
        first = self.root / "one"
        second = self.root / "two"
        first.write_bytes(b"same")
        second.write_bytes(b"same")
        left = evidence.bundle_sha([first, second], root=self.root)
        right = evidence.bundle_sha([second, first], root=self.root)
        self.assertEqual(left, right)
        second.write_bytes(b"different")
        self.assertNotEqual(left, evidence.bundle_sha([first, second], root=self.root))

    def test_binder_order_is_fixed(self) -> None:
        paths = [record["path"] for record in self._plan()["ordered_reads"]]
        names = [Path(path).name for path in paths]
        self.assertEqual(
            names[:6],
            ["TOPIC.md", "DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md", "GATES.md"],
        )
        self.assertLess(paths.index("poc/demo/ndf/proposals/root.md"), paths.index("poc/demo/ndf/evidence/r0.md"))
        self.assertEqual(names[-1], "COMMITS.md")

    def test_graph_closure_obeys_depth_and_budget(self) -> None:
        shallow = self._plan(seed_ids=["BEH-100"], depth=0)
        ids = {node["id"] for node in shallow["graph"]["nodes"]}
        self.assertIn("BEH-100", ids)
        self.assertNotIn("BEH-101", ids)
        self.assertIn("depth", shallow["graph"]["truncated"])
        bounded = self._plan(seed_ids=["BEH-100"], node_budget=1)
        self.assertLessEqual(len(bounded["graph"]["nodes"]), 1)
        self.assertIn("node_budget", bounded["graph"]["truncated"])

    def test_measurement_adds_verifier_and_conflict_is_blocker(self) -> None:
        plan = self._plan(task="measurement", seed_ids=["BEH-100"])
        ids = {node["id"] for node in plan["graph"]["nodes"]}
        self.assertIn("VER-100", ids)
        self.assertTrue(
            any(item["kind"] == "clause_conflict" for item in plan["graph"]["blockers"])
        )

    def test_project_control_is_meta_only(self) -> None:
        plan = self._plan(
            role="project-control",
            task="ndf_improvement_proposal",
            track="process",
            seed_ids=["META-100", "BEH-100"],
        )
        ids = {node["id"] for node in plan["graph"]["nodes"]}
        self.assertIn("META-100", ids)
        self.assertNotIn("BEH-100", ids)
        self.assertIn("BEH-100", plan["graph"]["missing_seeds"])

    def test_prepare_baseline_is_claude_code_poc_task(self) -> None:
        self.assertTrue(
            context._role_task_compatible("claude-code", "poc_prepare_baseline", "poc")
        )
        self.assertEqual(
            context.TASK_DEFAULT_SEEDS["poc_prepare_baseline"],
            ("BEH-018", "BEH-025", "META-012"),
        )
        priv = context._privileges("claude-code", "poc_prepare_baseline", "poc", "demo")
        self.assertEqual(priv["allowed_write_roots"], ["poc/demo/"])
        self.assertIn("src/", priv["forbidden_write_paths"])
        self.assertIn("spec/meta/", priv["forbidden_write_paths"])

    def test_prepare_baseline_bundle_omits_perf_numbers(self) -> None:
        bundle = context.expand_plan(
            self._plan(role="claude-code", task="poc_prepare_baseline"),
            root=self.root,
        )
        perf = next(
            item["content"]
            for item in bundle["files"]
            if item["path"].endswith("PERF_BASELINE.md")
        )
        self.assertNotIn("SECRET_QPS", perf)

    def test_non_measurement_bundle_omits_perf_numbers(self) -> None:
        bundle = context.expand_plan(self._plan(), root=self.root)
        perf = next(item["content"] for item in bundle["files"] if item["path"].endswith("PERF_BASELINE.md"))
        self.assertNotIn("SECRET_QPS", perf)
        self.assertIn("measure_script", perf)
        measured = context.expand_plan(self._plan(task="poc_measurement"), root=self.root)
        measured_perf = next(
            item["content"] for item in measured["files"] if item["path"].endswith("PERF_BASELINE.md")
        )
        self.assertIn("SECRET_QPS", measured_perf)
        surface = context.compile_prompt_surface(bundle)
        self.assertEqual(surface["bundle_sha"], bundle["bundle_sha"])
        self.assertIn("visible_prompt", surface)
        self.assertTrue(surface["source_refs"]["files"])

    def test_verify_detects_file_drift(self) -> None:
        plan = self._plan()
        self._write("poc/demo/ndf/DESIGN.md", "# Changed\n")
        result = context.verify_plan(plan, root=self.root)
        self.assertFalse(result["valid"])
        self.assertIn("file_drift", {item["kind"] for item in result["errors"]})

    def test_manifest_verification_detects_gate_drift(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        self._write("poc/demo/ndf/GATES.md", "# changed gate\n")
        result = context.verify_manifest(manifest, root=self.root)
        self.assertFalse(result["valid"])
        self.assertIn("gate_drift", {item["kind"] for item in result["errors"]})

    def test_verify_detects_bundle_tampering(self) -> None:
        plan = self._plan()
        bundle = context.expand_plan(plan, root=self.root)
        bundle["files"][0]["content"] += "tampered"
        result = context.verify_plan(plan, root=self.root, bundle=bundle)
        kinds = {item["kind"] for item in result["errors"]}
        self.assertIn("bundle_sha_mismatch", kinds)
        self.assertIn("bundle_content_sha_mismatch", kinds)

    def test_verify_rejects_forbidden_write_overlap(self) -> None:
        plan = self._plan()
        plan["privileges"]["allowed_write_roots"] = ["src/"]
        plan["privileges"]["forbidden_write_paths"].append("src/")
        self._resign(plan)
        result = context.verify_plan(plan, root=self.root)
        self.assertIn("forbidden_path", {item["kind"] for item in result["errors"]})

    def test_verify_rejects_stale_baseline(self) -> None:
        plan = self._plan()
        plan["baseline"]["baseline_status"] = "stale"
        self._resign(plan)
        result = context.verify_plan(plan, root=self.root)
        self.assertIn("baseline_stale", {item["kind"] for item in result["errors"]})

    def test_explicit_seed_is_preserved(self) -> None:
        plan = self._plan(seed_ids=["BEH-101"])
        self.assertIn("BEH-101", plan["seed_ids"])
        self.assertIn("BEH-101", plan["seed_sources"]["explicit"])

    def test_safe_tmp_guard_and_workspace_truth(self) -> None:
        safe = evidence.safe_tmp_report_path("tmp/report.json", root=self.root)
        self.assertEqual(safe, self.root / "tmp/report.json")
        with self.assertRaises(ValueError):
            evidence.safe_tmp_report_path("../escape.json", root=self.root)
        binding = {"repo_root": str(self.root), "repo_head": "a" * 40, "active_topic": "demo"}
        self.assertFalse(evidence.workspace_truth(binding, {})["workspace_bound"])
        self.assertTrue(
            evidence.workspace_truth(binding, {"workspace": dict(binding)})["workspace_bound"]
        )

    def test_receipt_validation_and_lease_round_trip(self) -> None:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            text=True,
        ).strip()
        worktree = self.root / "tmp" / "lease-worktree"
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "lease-test", str(worktree), head],
            cwd=self.root,
            check=True,
        )
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": "implement",
            "topic": "demo",
            "mode": "poc",
            "step": "start",
            "repo_head": head,
            "source_generation_sha": "b" * 64,
            "manifest_sha": "f" * 64,
            "context_plan_sha": "c" * 64,
            "command": "run",
            "input_sha": "d" * 64,
            "output_sha": "e" * 64,
            "evidence_paths": [],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": None,
            "result": "active",
            "blockers": [],
            "run_id": "run",
            "session_id": "session",
            "base_sha": head,
            "worktree": str(worktree),
            "branch": "lease-test",
            "repo_root": str(self.root),
            "allowed_write_root": "poc/demo/",
            "pack_sha": "9" * 64,
            "episode_id": "ep-demo",
        }
        self.assertTrue(evidence.validate_receipt(lease)["valid"])
        path = evidence.append_lease("tmp/leases.jsonl", lease, root=self.root)
        self.assertEqual(evidence.read_leases(path, root=self.root), [lease])
        bound = evidence.validate_runtime_lease_binding(
            lease,
            root=self.root,
            expected={
                "topic": "demo",
                "task": "implement",
                "plan_sha": "c" * 64,
                "allowed_write_root": "poc/demo/",
                "pack_sha": "9" * 64,
                "episode_id": "ep-demo",
                "branch": "lease-test",
                "repo_root": str(self.root),
            },
        )
        self.assertTrue(bound["valid"], bound["errors"])
        escaped = dict(lease, worktree="/tmp/outside-ndf-repo")
        self.assertFalse(
            evidence.validate_runtime_lease_binding(
                escaped,
                root=self.root,
            )["valid"]
        )
        bad = dict(lease, schema="unknown")
        self.assertFalse(evidence.validate_receipt(bad)["valid"])

    def test_short_gate_sha_never_verifies(self) -> None:
        plan = self._plan()
        receipt = {
            "gate": "implementation_approval",
            "status": "approved",
            "approved_content_sha": "abc123",
            "expected_content_sha": "abc123" + "0" * 58,
        }
        plan["gates"]["receipts"] = [receipt]
        self._resign(plan)
        result = context.verify_plan(plan, root=self.root)
        self.assertIn("gate_sha_mismatch", {item["kind"] for item in result["errors"]})

    def test_manifest_resigned_after_closure_tamper_fails_rederivation(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        manifest["shared_graph_closure"]["nodes"] = []
        manifest["compiler_derivation"]["derived_sha"] = (
            context._manifest_derivation_digest(manifest)
        )
        manifest["manifest_sha"] = context.canonical_json_sha(
            {key: value for key, value in manifest.items() if key != "manifest_sha"}
        )
        result = context.verify_manifest_current(manifest, root=self.root)
        self.assertIn(
            "manifest_compiler_derivation_mismatch",
            {item["kind"] for item in result["errors"]},
        )

    def test_role_task_matrix_rejects_control_task_for_claude(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic="demo",
            task="binder_amend",
            track="poc",
        )
        with self.assertRaisesRegex(ValueError, "incompatible role/task/track"):
            context.role_plan(manifest, role="claude-code")

    def test_recorded_lease_proof_survives_worktree_cleanup(self) -> None:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        worktree = self.root / "tmp" / "recorded-proof"
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "recorded-proof", str(worktree), head],
            cwd=self.root,
            check=True,
        )
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": "implement",
            "topic": "demo",
            "mode": "poc",
            "step": "start",
            "repo_head": head,
            "source_generation_sha": "b" * 64,
            "manifest_sha": "f" * 64,
            "context_plan_sha": "c" * 64,
            "command": "run",
            "input_sha": "d" * 64,
            "output_sha": "e" * 64,
            "evidence_paths": [],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": None,
            "result": "active",
            "blockers": [],
            "run_id": "run",
            "session_id": "session",
            "base_sha": head,
            "worktree": str(worktree),
            "branch": "recorded-proof",
            "repo_root": str(self.root),
            "allowed_write_root": "poc/demo/",
            "pack_sha": "9" * 64,
            "episode_id": "ep-demo",
        }
        lease["binding_proof"] = evidence.runtime_lease_binding_proof(
            lease, root=self.root
        )
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=self.root,
            check=True,
        )
        self.assertTrue(
            evidence.validate_recorded_runtime_lease_binding(lease)["valid"]
        )
        self.assertFalse(
            evidence.validate_runtime_lease_binding(lease, root=self.root)["valid"]
        )


if __name__ == "__main__":
    unittest.main()
