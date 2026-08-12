import importlib.util
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

    def test_verify_detects_file_drift(self) -> None:
        plan = self._plan()
        self._write("poc/demo/ndf/DESIGN.md", "# Changed\n")
        result = context.verify_plan(plan, root=self.root)
        self.assertFalse(result["valid"])
        self.assertIn("file_drift", {item["kind"] for item in result["errors"]})

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
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": "implement",
            "topic": "demo",
            "mode": "poc",
            "step": "start",
            "repo_head": "a" * 40,
            "source_generation_sha": "b" * 64,
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
            "base_sha": "a" * 40,
            "worktree": str(self.root),
            "allowed_write_root": "poc/demo/",
        }
        self.assertTrue(evidence.validate_receipt(lease)["valid"])
        path = evidence.append_lease("tmp/leases.jsonl", lease, root=self.root)
        self.assertEqual(evidence.read_leases(path, root=self.root), [lease])
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


if __name__ == "__main__":
    unittest.main()
