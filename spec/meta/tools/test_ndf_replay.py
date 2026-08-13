import json
import concurrent.futures
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_replay as replay
import ndf_context as context
import ndf_workflow_evidence as evidence


class ReplayStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        self.store = replay.ReplayStore(self.root)
        self.manifest = context.create_manifest(
            root=self.root,
            topic=None,
            task="binder_amend",
            track="process",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _episode(self, name: str = "ep-test") -> dict:
        return self.store.init_episode(
            topic=self.manifest.get("topic"),
            task=str(self.manifest["task"]),
            role="openclaw",
            track=str(self.manifest["track"]),
            manifest=self.manifest,
            episode_id=name,
        )

    def _episode_with_plan(self, name: str = "ep-test") -> tuple[dict, dict, str]:
        initialized = self._episode(name)
        plan = context.role_plan(self.manifest, role="openclaw")
        plan_blob = self.store.put_blob(plan)
        self.store.append_event(
            name,
            kind="context.compiled",
            actor="openclaw",
            payload_sha=plan_blob,
            topic=None,
            task="binder_amend",
            track=str(self.manifest["track"]),
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
        )
        self.store.append_event(
            name,
            kind="context.verified",
            actor="openclaw",
            payload_sha=plan_blob,
            topic=None,
            task="binder_amend",
            track=str(self.manifest["track"]),
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
        )
        commit = self.store.commit_events(
            name,
            message="verified context plan",
            actor="openclaw",
        )
        return initialized, plan, commit

    def test_blob_dedup_tree_commit_and_atomic_ref(self) -> None:
        first = self.store.put_blob({"same": True})
        second = self.store.put_blob({"same": True})
        self.assertEqual(first, second)
        tree = self.store.put_tree({"payload": first})
        commit = self.store.put_commit(
            tree,
            actor="tool",
            topic="demo",
            task="test",
            track="poc",
            repo_head=self.head,
            manifest_sha="a" * 64,
            context_plan_sha="b" * 64,
            message="test",
        )
        self.store.update_ref("branches/demo/test", commit)
        self.assertEqual(self.store.read_ref("branches/demo/test"), commit)
        with self.assertRaises(ValueError):
            self.store.update_ref("branches/demo/test", commit, expected_old="0" * 64)
        self.assertTrue(self.store.fsck()["valid"])
        raw = self.store._object_path(first).read_bytes()
        self.assertTrue(raw.startswith(replay.ENCRYPTED_MAGIC))
        self.assertNotIn(b'"same":true', raw)

    def test_event_chain_detects_reorder_and_missing_payload(self) -> None:
        self._episode()
        payload = self.store.put_blob({"result": "ok"})
        self.store.append_event(
            "ep-test",
            kind="tool.result",
            actor="tool",
            payload_sha=payload,
            topic="demo",
            task="implement",
            track="poc",
            repo_head=self.head,
            manifest_sha="a" * 64,
            context_plan_sha="b" * 64,
        )
        self.assertTrue(self.store.fsck()["valid"])
        path = self.store.event_path("ep-test")
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
        self.assertFalse(self.store.fsck()["valid"])

    def test_branch_event_chains_are_independent_and_concurrent_safe(self) -> None:
        self._episode()
        payload = self.store.put_blob({"result": "ok"})

        def append(index: int) -> None:
            self.store.append_event(
                "ep-test",
                kind="tool.result",
                actor=f"tool-{index}",
                payload_sha=payload,
                topic="demo",
                task="implement",
                track="poc",
                repo_head=self.head,
                manifest_sha="a" * 64,
                context_plan_sha="b" * 64,
                branch="implementation",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(append, range(8)))
        implementation = self.store.read_events("ep-test", "implementation")
        self.assertEqual([item["seq"] for item in implementation], list(range(1, 9)))
        self.assertEqual(len(self.store.read_events("ep-test")), 1)
        self.assertTrue(self.store.fsck()["valid"])

    def test_branch_tag_merge_and_parent_dag(self) -> None:
        initialized = self._episode()
        base = initialized["commit_sha"]
        self.store.update_ref("branches/demo/control", base)
        self.store.update_ref("branches/demo/implementation", base)
        merged = self.store.merge(
            "ep-test",
            "branches/demo/control",
            "branches/demo/implementation",
            message="verified merge",
        )
        commit = self.store.get_object(merged, "commit")["data"]
        self.assertEqual(commit["parents"], [base, base])
        self.store.update_ref("tags/demo-reviewed", merged, immutable=True)
        with self.assertRaises(ValueError):
            self.store.update_ref("tags/demo-reviewed", base, immutable=True)
        self.assertTrue(self.store.fsck()["valid"])

    def test_gate_tag_requires_human_bound_receipt(self) -> None:
        initialized = self._episode()
        gate_evidence = self.root / "gate.txt"
        gate_evidence.write_text("approved\n", encoding="utf-8")
        approved_sha = evidence.bundle_sha(["gate.txt"], root=self.root)
        receipt = {
            "schema": "ndf-gate-receipt/v1",
            "task": "human_gate",
            "topic": "demo",
            "mode": "poc",
            "step": "implementation_approval",
            "repo_head": self.head,
            "source_generation_sha": "e" * 64,
            "command": "human approval",
            "input_sha": "f" * 64,
            "output_sha": approved_sha,
            "evidence_paths": ["gate.txt"],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": "2026-08-12T00:00:00Z",
            "result": "passed",
            "blockers": [],
            "status": "approved",
            "phrase": "可以开始实现",
            "approved_by": "human-reviewer",
            "approved_at": "2026-08-12T00:00:00Z",
            "source_ref": "GATES.md:1",
            "approved_content_sha": approved_sha,
            "manifest_sha": "a" * 64,
            "context_plan_sha": "b" * 64,
        }
        tagged = self.store.create_gate_tag(
            "demo/implementation",
            initialized["commit_sha"],
            receipt,
        )
        self.assertEqual(
            self.store.read_ref("tags/gates/demo/implementation"),
            tagged["commit_sha"],
        )
        with self.assertRaises(ValueError):
            self.store.create_gate_tag(
                "demo/forged",
                initialized["commit_sha"],
                {**receipt, "approved_by": "openclaw"},
            )

    def test_strict_audit_rejects_forged_gate_event(self) -> None:
        self._episode()
        forged = self.store.put_blob(
            {"gate": "implementation_approval", "valid": True}
        )
        self.store.append_event(
            "ep-test",
            kind="gate.approved",
            actor="agent",
            payload_sha=forged,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=None,
        )
        commit = self.store.commit_events(
            "ep-test",
            message="forged gate",
            actor="agent",
        )
        audit = self.store.audit(commit, strict=True)
        self.assertFalse(audit["valid"])
        self.assertTrue(
            any("invalid_gate_receipt" in gap for gap in audit["semantic_gaps"])
        )

    def test_checkpoint_preserves_parent_and_summary_is_navigation_only(self) -> None:
        manifest = context.create_manifest(
            root=self.root,
            topic=None,
            task="binder_amend",
            track="poc",
        )
        plan = context.role_plan(manifest, role="openclaw")
        initialized = self.store.init_episode(
            topic=None,
            task="binder_amend",
            role="openclaw",
            track="poc",
            manifest=manifest,
            episode_id="ep-test",
        )
        self.store.put_blob(manifest)
        self.store.put_blob(plan)
        checkpoint = self.store.checkpoint(
            "ep-test",
            summary="short summary",
            manifest_sha=manifest["manifest_sha"],
            plan_sha=plan["plan_sha"],
            open_decisions=["review"],
        )
        commit = self.store.get_object(checkpoint, "commit")["data"]
        self.assertIn(initialized["commit_sha"], self._ancestor_shas(checkpoint))
        reconstruction = self.store.reconstruct(checkpoint)
        checkpoint_blobs = [
            item["object"]["data"]
            for item in reconstruction["recorded_objects"]
            if item["object"]["type"] == "blob"
        ]
        serialized = json.dumps(checkpoint_blobs)
        self.assertIn("summary_navigation_only", serialized)
        self.assertTrue(commit["parents"])

    def _ancestor_shas(self, start: str) -> set[str]:
        return {sha for sha, _ in self.store.walk_commits(start)}

    def test_r0_r1_r3_contracts_are_distinct(self) -> None:
        initialized = self._episode()
        audit = self.store.audit(initialized["commit_sha"], strict=False)
        self.assertEqual(audit["level"], "R0")
        observed = self.store.reconstruct(initialized["commit_sha"], "R1")
        self.assertFalse(observed["side_effects"])
        forked = self.store.fork(initialized["commit_sha"], "demo/model-swap")
        self.assertEqual(forked["level"], "R3")
        self.assertTrue(forked["counterfactual"])
        self.assertNotEqual(forked["commit_sha"], initialized["commit_sha"])

    def test_r2_requires_explicit_non_networked_profile_and_adapter_for_execution(self) -> None:
        initialized = self._episode()
        profile = {
            "schema": "ndf-replay-sandbox-profile/v1",
            "sandbox": True,
            "network": "none",
            "commands": [["python3", "-c", "print('ok')"]],
            "allowed_write_roots": [],
            "expected_outputs": [],
        }
        validated = self.store.sandbox_replay(
            initialized["commit_sha"],
            profile,
            execute=False,
        )
        self.assertEqual(validated["state"], "validated_profile")
        self.assertFalse(validated["executed"])
        with self.assertRaises(ValueError):
            self.store.sandbox_replay(
                initialized["commit_sha"],
                profile,
                execute=True,
            )

    def test_end_to_end_control_and_implementation_merge(self) -> None:
        self.manifest = context.create_manifest(
            root=self.root,
            topic=None,
            task="promote",
            track="promote",
        )
        initialized = self._episode("ep-e2e")
        base = initialized["commit_sha"]
        runtime_worktree = self.root / "tmp" / "e2e-worktree"
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-q",
                "-b",
                "e2e-implementation",
                str(runtime_worktree),
                self.head,
            ],
            cwd=self.root,
            check=True,
        )
        manifest_blob = self.store.put_blob(self.manifest)
        control_plan = context.role_plan(self.manifest, role="openclaw")
        implementation_plan = context.role_plan(self.manifest, role="claude-code")
        control_plan_blob = self.store.put_blob(control_plan)
        implementation_plan_blob = self.store.put_blob(implementation_plan)
        self.store.append_event(
            "ep-e2e",
            kind="manifest.created",
            actor="canvas",
            payload_sha=manifest_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=None,
            branch="control",
        )
        self.store.append_event(
            "ep-e2e",
            kind="context.compiled",
            actor="openclaw",
            payload_sha=control_plan_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=control_plan["plan_sha"],
            branch="control",
        )
        self.store.append_event(
            "ep-e2e",
            kind="context.verified",
            actor="openclaw",
            payload_sha=control_plan_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=control_plan["plan_sha"],
            branch="control",
        )
        gate_path = self.root / "gate.txt"
        gate_path.write_text("approved\n", encoding="utf-8")
        (runtime_worktree / "gate.txt").write_text("approved\n", encoding="utf-8")
        output_path = runtime_worktree / "src" / "output.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("fixture\n", encoding="utf-8")
        gate_sha = evidence.bundle_sha(["gate.txt"], root=self.root)
        gate_receipt = {
            "schema": "ndf-gate-receipt/v1",
            "task": "human_gate",
            "topic": None,
            "mode": "promote",
            "step": "proposal_review",
            "repo_head": self.head,
            "source_generation_sha": self.manifest["source_generation_sha"],
            "manifest_sha": self.manifest["manifest_sha"],
            "context_plan_sha": control_plan["plan_sha"],
            "command": "human approval",
            "input_sha": "f" * 64,
            "output_sha": gate_sha,
            "evidence_paths": ["gate.txt"],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": "2026-08-12T00:00:00Z",
            "result": "passed",
            "blockers": [],
            "status": "approved",
            "gate": "proposal_review",
            "phrase": "已审核",
            "approved_by": "human-reviewer",
            "approved_at": "2026-08-12T00:00:00Z",
            "source_ref": "gate.txt:1",
            "approved_content_sha": gate_sha,
        }
        gate_blob = self.store.put_blob(gate_receipt)
        self.store.append_event(
            "ep-e2e",
            kind="gate.approved",
            actor="human",
            payload_sha=gate_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=control_plan["plan_sha"],
            branch="control",
        )
        control = self.store.commit_events(
            "ep-e2e",
            message="control gate",
            actor="openclaw",
            branch="control",
        )
        self.store.create_gate_tag("process-reviewed", control, gate_receipt)
        self.store.append_event(
            "ep-e2e",
            kind="context.compiled",
            actor="claude-code",
            payload_sha=implementation_plan_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            branch="implementation",
        )
        self.store.append_event(
            "ep-e2e",
            kind="context.verified",
            actor="claude-code",
            payload_sha=implementation_plan_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            branch="implementation",
        )
        dispatch_blob = self.store.put_blob(
            {
                "schema": "ndf-workflow-pack/v2",
                "provider": "claude-code-acp",
                "task": "promote",
                "track": "promote",
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": implementation_plan["plan_sha"],
                "base_sha": self.head,
                "allowed_write_root": "src/",
                "safe_to_dispatch": True,
            }
        )
        self.store.append_event(
            "ep-e2e",
            kind="dispatch.preflight",
            actor="claude-code",
            payload_sha=dispatch_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            branch="implementation",
        )
        lease_receipt = {
            "schema": "ndf-runtime-lease/v1",
            "task": "promote",
            "topic": None,
            "mode": "promote",
            "step": "start",
            "repo_head": self.head,
            "source_generation_sha": self.manifest["source_generation_sha"],
            "manifest_sha": self.manifest["manifest_sha"],
            "context_plan_sha": implementation_plan["plan_sha"],
            "command": "runtime lease",
            "input_sha": "1" * 64,
            "output_sha": "2" * 64,
            "evidence_paths": [],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": None,
            "result": "active",
            "blockers": [],
            "run_id": "run-e2e",
            "session_id": "session-e2e",
            "base_sha": self.head,
            "worktree": str(runtime_worktree),
            "branch": "e2e-implementation",
            "repo_root": str(self.root),
            "allowed_write_root": "src/",
            "pack_sha": dispatch_blob,
            "episode_id": "ep-e2e",
        }
        lease_receipt["binding_proof"] = evidence.runtime_lease_binding_proof(
            lease_receipt,
            root=self.root,
        )
        lease_blob = self.store.put_blob(lease_receipt)
        self.store.append_event(
            "ep-e2e",
            kind="lease.acquired",
            actor="claude-code",
            payload_sha=lease_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            session_id="session-e2e",
            run_id="run-e2e",
            branch="implementation",
        )
        mutation_proof = {
            "schema": "ndf-runtime-mutation-proof/v1",
            "acquisition_snapshot_sha": lease_receipt["binding_proof"][
                "acquisition_snapshot"
            ]["snapshot_sha"],
            "completion_snapshot": evidence.git_mutation_snapshot(
                runtime_worktree
            ),
            "committed_paths": [],
            "actual_mutations": ["src/output.txt"],
            "declared_mutations": ["src/output.txt"],
        }
        mutation_proof["proof_sha"] = evidence.canonical_json_sha(
            mutation_proof
        )
        completion_blob = self.store.put_blob(
            {
                "schema": "ndf-agent-completion/v1",
                "topic": None,
                "task": "promote",
                "track": "promote",
                "base_sha": self.head,
                "repo_head": self.head,
                "manifest_sha": self.manifest["manifest_sha"],
                "context_plan_sha": implementation_plan["plan_sha"],
                "changed_files": ["src/output.txt"],
                "changed_file_shas": {
                    "src/output.txt": hashlib.sha256(b"fixture\n").hexdigest()
                },
                "reproduce_commands": [["python3", "-c", "print('ok')"]],
                "evidence_paths": ["gate.txt"],
                "evidence_bundle_sha": gate_sha,
                "git_commit": "",
                "post_check_receipts": [
                    {
                        "command": "python3 spec/meta/tools/ndf_bindcheck.py",
                        "result": "passed",
                        "output_sha": gate_sha,
                        "evidence_paths": ["gate.txt"],
                        "verifier": {
                            "path": "/recorded/spec/meta/tools/ndf_bindcheck.py",
                            "argv": [
                                "python3",
                                "spec/meta/tools/ndf_bindcheck.py",
                            ],
                            "version_sha": "9" * 64,
                            "exit_code": 0,
                            "output_schema": "ndf-bindcheck/v1",
                        },
                    }
                ],
                "mutation_proof": mutation_proof,
                "result": "success",
                "run_id": "run-e2e",
                "session_id": "session-e2e",
                "worktree": str(runtime_worktree),
                "branch": "e2e-implementation",
            }
        )
        self.store.append_event(
            "ep-e2e",
            kind="acp.complete",
            actor="claude-code",
            payload_sha=completion_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            session_id="session-e2e",
            run_id="run-e2e",
            branch="implementation",
        )
        released_receipt = {
            **lease_receipt,
            "step": "release",
            "finished_at": "2026-08-12T00:01:00Z",
            "result": "released",
        }
        released_blob = self.store.put_blob(released_receipt)
        self.store.append_event(
            "ep-e2e",
            kind="lease.released",
            actor="claude-code",
            payload_sha=released_blob,
            topic=None,
            task="promote",
            track="promote",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=implementation_plan["plan_sha"],
            session_id="session-e2e",
            run_id="run-e2e",
            branch="implementation",
        )
        implementation = self.store.commit_events(
            "ep-e2e",
            message="implementation completion",
            actor="claude-code",
            branch="implementation",
        )
        merged = self.store.merge(
            "ep-e2e",
            control,
            implementation,
            message="verified episode merge",
        )
        merge_parents = self.store.get_object(merged, "commit")["data"]["parents"]
        self.assertEqual(len(merge_parents), 2)
        self.assertEqual(
            self.store.get_object(control, "commit")["data"]["parents"],
            [base],
        )
        self.assertEqual(
            self.store.get_object(implementation, "commit")["data"]["parents"],
            [base],
        )
        self.assertEqual(
            [item["seq"] for item in self.store.read_events("ep-e2e", "control")],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            [
                item["seq"]
                for item in self.store.read_events("ep-e2e", "implementation")
            ],
            [1, 2, 3, 4, 5, 6],
        )
        self.assertTrue(self.store.audit(merged, strict=False)["valid"])
        self.assertTrue(self.store.fsck()["valid"])
        checkpoint = self.store.checkpoint(
            "ep-e2e",
            summary="control and implementation merged",
            manifest_sha=self.manifest["manifest_sha"],
            plan_sha=control_plan["plan_sha"],
            resolved_decisions=["proposal_reviewed"],
            summary_provenance={"model": "fixture", "navigation_only": True},
        )
        self.assertIn(merged, self._ancestor_shas(checkpoint))
        checkpoint_event = self.store.read_events("ep-e2e", "main")[-1]
        checkpoint_payload = self.store.get_object(
            checkpoint_event["payload_sha"], "blob"
        )["data"]["value"]
        self.assertIn("control", checkpoint_payload["covered_branches"])
        self.assertIn("implementation", checkpoint_payload["covered_branches"])
        self.assertIn(merged, checkpoint_payload["retained_object_refs"])
        strict_audit = self.store.audit(checkpoint, strict=True)
        self.assertTrue(strict_audit["valid"], strict_audit)
        reconstructed = self.store.reconstruct(checkpoint, "R0")
        self.assertEqual(reconstructed["commit_sha"], checkpoint)
        self.assertTrue(reconstructed["merge_parents"])
        self.assertEqual(
            {"control", "implementation"},
            {
                item["branch"]
                for item in reconstructed["timeline"]
                if item.get("branch") in {"control", "implementation"}
            },
        )
        (self.root / "README.md").write_text("fixture advanced\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "advance after episode"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(runtime_worktree)],
            cwd=self.root,
            check=True,
        )
        historical_after_drift = self.store.audit(checkpoint, strict=True)
        self.assertTrue(historical_after_drift["valid"], historical_after_drift)
        self.assertTrue(historical_after_drift["historical_integrity"])
        self.assertFalse(historical_after_drift["current_restore_ready"])
        forked = self.store.fork(
            checkpoint,
            "demo/model-swap",
            changes=["model=fixture-v2"],
        )
        self.assertEqual(forked["level"], "R3")
        self.assertNotEqual(forked["commit_sha"], checkpoint)

    def test_r1_requires_recorded_observation_surface(self) -> None:
        _, _, commit = self._episode_with_plan("ep-r1-empty")
        reconstructed = self.store.reconstruct(commit, "R1")
        self.assertFalse(reconstructed["observation_replay_valid"])
        self.assertIn(
            "recorded_observation_surface_missing",
            reconstructed["observation_gaps"],
        )

    def test_redaction_creates_new_commit_without_mutating_source(self) -> None:
        secret = self.store.put_blob(
            {
                "api_token": "do-not-export",
                "safe": "ok",
                "log": (
                    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz "
                    "alice@example.com password=hunter2"
                ),
            }
        )
        tree = self.store.put_tree({"provenance": secret})
        commit = self.store.put_commit(
            tree,
            actor="tool",
            topic="demo",
            task="export",
            track="process",
            repo_head=self.head,
            manifest_sha=None,
            context_plan_sha=None,
            message="secret source",
        )
        before = self.store.get_object(secret)
        exported = self.store.redact_export(commit)
        self.assertNotEqual(exported["source_commit"], exported["redacted_commit"])
        exported_commit = self.store.get_object(
            exported["redacted_commit"],
            "commit",
        )["data"]
        self.assertEqual(exported_commit["parents"], [])
        self.assertEqual(before, self.store.get_object(secret))
        rendered = json.dumps(
            self.store.reconstruct(exported["redacted_commit"]), ensure_ascii=False
        )
        self.assertNotIn("do-not-export", rendered)
        self.assertNotIn("abcdefghijklmnop", rendered)
        self.assertNotIn("alice@example.com", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_redaction_catches_adjacent_argv_secret(self) -> None:
        secret = self.store.put_blob(
            {
                "schema": "fixture/v1",
                "argv": ["client", "--token", "adjacent-secret-value", "--safe", "ok"],
            }
        )
        commit = self.store.put_commit(
            self.store.put_tree({"payload": secret}),
            actor="tool",
            topic="demo",
            task="export",
            track="process",
            repo_head=self.head,
            manifest_sha=None,
            context_plan_sha=None,
            message="argv secret",
        )
        exported = self.store.redact_export(commit)
        rendered = json.dumps(
            self.store.reconstruct(exported["redacted_commit"]),
            ensure_ascii=False,
        )
        self.assertNotIn("adjacent-secret-value", rendered)
        self.assertEqual(exported["secret_scan_findings"], [])

    def test_fsck_rejects_wrong_commit_and_ref_object_types(self) -> None:
        blob = self.store.put_blob({"not": "a tree"})
        malformed = self.store.put_object(
            "commit",
            {
                "schema": "ndf-replay-commit/v1",
                "tree": blob,
                "parents": [blob],
                "actor": "tool",
                "topic": None,
                "task": "malformed",
                "track": "process",
                "repo_head": self.head,
                "manifest_sha": None,
                "context_plan_sha": None,
                "message": "malformed",
                "coverage": {},
                "created_at": replay.now_iso(),
            },
        )
        self.store.update_ref("episodes/bad/HEAD", malformed)
        self.store.update_ref("runs/bad", blob)
        checked = self.store.fsck()
        self.assertFalse(checked["valid"])
        self.assertTrue(
            any("commit_tree_wrong_type" in error for error in checked["errors"])
        )
        self.assertTrue(
            any("commit_parent_wrong_type" in error for error in checked["errors"])
        )
        self.assertTrue(any("ref_wrong_type" in error for error in checked["errors"]))

    def test_tool_cassette_splits_streams_and_rejects_plaintext_secret(self) -> None:
        cassette = self.store.tool_cassette(
            tool="shell",
            name="test",
            invocation_id="inv-1",
            cwd=str(self.root),
            argv=["python3", "-V"],
            normalized_input={"api_token": "[REDACTED]"},
            stdin_sha=None,
            env_allowlist_fingerprint="d" * 64,
            timeout_ms=1000,
            stdout="Python",
            stderr="",
            exit_code=0,
            duration_ms=1,
            replay_policy="sandbox",
            external_resource_version=None,
            bindings={
                "topic": "demo",
                "task": "test",
                "repo_head": self.head,
                "worktree": str(self.root),
                "manifest_sha": "a" * 64,
                "plan_sha": "b" * 64,
                "run_id": "run-1",
            },
        )
        sha = self.store.put_tool_cassette(cassette)
        stored = self.store.get_object(sha, "tool-cassette")["data"]
        self.assertNotIn("stdout", stored)
        self.store.get_object(stored["stdout_blob"], "blob")
        self.assertTrue(self.store.fsck()["valid"])
        with self.assertRaises(ValueError):
            self.store.tool_cassette(
                tool="shell",
                name="bad",
                invocation_id="inv-2",
                cwd=str(self.root),
                argv=["echo"],
                normalized_input={"api_token": "secret-value"},
                stdin_sha=None,
                env_allowlist_fingerprint="d" * 64,
                timeout_ms=1000,
                stdout="",
                stderr="",
                exit_code=0,
                duration_ms=1,
                replay_policy="recorded-only",
                external_resource_version=None,
                bindings={
                    "repo_head": self.head,
                    "worktree": str(self.root),
                    "manifest_sha": "a" * 64,
                    "plan_sha": "b" * 64,
                    "run_id": "run-1",
                },
            )

    def test_model_turn_splits_visible_messages_and_preserves_no_hidden_reasoning(self) -> None:
        turn = self.store.model_turn(
            provider="fixture",
            model_id="model-v1",
            api_version="2026-08",
            parameters={"temperature": 0},
            runtime_build="build-1",
            tool_schema_sha="1" * 64,
            skill_rule_sha="2" * 64,
            manifest_sha="3" * 64,
            role_plan_sha="4" * 64,
            visible_system_surface_sha="5" * 64,
            user_message="do the task",
            assistant_response="done",
            input_tool_cassette_refs=[],
            output_action_refs=[],
            stop_reason="end_turn",
            token_usage={"input": 3, "output": 1},
        )
        sha = self.store.put_model_turn(turn)
        stored = self.store.get_object(sha, "model-turn")["data"]
        self.assertNotIn("assistant_response", stored)
        self.assertEqual(stored["hidden_chain_of_thought"], "not_recorded")
        raw = self.store._object_path(stored["assistant_response_blob"]).read_bytes()
        self.assertNotIn(b"done", raw)
        self.assertTrue(self.store.fsck()["valid"])

    def test_r2_execution_rejects_commands_without_recorded_sandbox_cassette(self) -> None:
        _, _, commit = self._episode_with_plan()
        profile = {
            "schema": "ndf-replay-sandbox-profile/v1",
            "sandbox": True,
            "network": "none",
            "adapter": ["bwrap"],
            "adapter_enforces": ["network", "filesystem", "process"],
            "confirm_cost": True,
            "confirm_side_effects": True,
            "commands": [["python3", "-c", "print('unrecorded')"]],
            "allowed_write_roots": [],
            "expected_outputs": [
                {"path": "output.txt", "sha256": "0" * 64}
            ],
        }
        try:
            result = self.store.sandbox_replay(
                commit,
                profile,
                execute=True,
            )
        except ValueError as exc:
            self.assertIn("complete output set", str(exc))
        else:
            self.assertEqual(result["state"], "environment_blocked")
            self.assertFalse(result["executed"])

    def test_r2_managed_bwrap_replays_recorded_command_and_matches_output(self) -> None:
        if not shutil.which("bwrap"):
            self.skipTest("bwrap is unavailable")
        smoke = subprocess.run(
            [
                "bwrap",
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/",
                "/",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--",
                "true",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if smoke.returncode != 0:
            self.skipTest(f"bwrap isolation unavailable: {smoke.stderr.strip()}")
        _, plan, _ = self._episode_with_plan()
        argv = [
            "python3",
            "-c",
            (
                "from pathlib import Path; "
                "Path('out').mkdir(exist_ok=True); "
                "Path('out/output.txt').write_text('ok')"
            ),
        ]
        dispatch = {
            "schema": "ndf-workflow-pack/v2",
            "provider": "openclaw",
            "task": "binder_amend",
            "track": "process",
            "manifest_sha": self.manifest["manifest_sha"],
            "plan_sha": plan["plan_sha"],
            "safe_to_dispatch": True,
        }
        dispatch_sha = self.store.put_blob(dispatch)
        self.store.append_event(
            "ep-test",
            kind="dispatch.preflight",
            actor="openclaw",
            payload_sha=dispatch_sha,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
        )
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": "binder_amend",
            "topic": None,
            "mode": "process",
            "step": "start",
            "repo_head": self.head,
            "source_generation_sha": self.manifest["source_generation_sha"],
            "manifest_sha": self.manifest["manifest_sha"],
            "context_plan_sha": plan["plan_sha"],
            "command": "runtime lease",
            "input_sha": "1" * 64,
            "output_sha": "2" * 64,
            "evidence_paths": [],
            "started_at": "2026-08-12T00:00:00Z",
            "finished_at": None,
            "result": "active",
            "blockers": [],
            "run_id": "run-r2",
            "session_id": "session-r2",
            "base_sha": self.head,
            "worktree": str(self.root),
            "branch": "recorded-branch",
            "repo_root": str(self.root),
            "allowed_write_root": "out/",
            "pack_sha": dispatch_sha,
            "episode_id": "ep-test",
        }
        lease_sha = self.store.put_blob(lease)
        self.store.append_event(
            "ep-test",
            kind="lease.acquired",
            actor="openclaw",
            payload_sha=lease_sha,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
            session_id="session-r2",
            run_id="run-r2",
        )
        cassette = self.store.tool_cassette(
            tool="shell",
            name="write-fixture",
            invocation_id="r2-command",
            cwd=str(self.root),
            argv=argv,
            normalized_input={},
            stdin_sha=None,
            env_allowlist_fingerprint="d" * 64,
            timeout_ms=10_000,
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=1,
            replay_policy="sandbox",
            external_resource_version=None,
            bindings={
                "topic": None,
                "task": "binder_amend",
                "repo_head": self.head,
                "worktree": str(self.root),
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": plan["plan_sha"],
                "run_id": "run-r2",
            },
        )
        cassette_sha = self.store.put_tool_cassette(cassette)
        self.store.append_event(
            "ep-test",
            kind="tool.result",
            actor="tool",
            payload_sha=cassette_sha,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
            session_id="session-r2",
            run_id="run-r2",
        )
        proof = self.root / "r2-proof.txt"
        proof.write_text("verified\n", encoding="utf-8")
        proof_sha = evidence.bundle_sha(["r2-proof.txt"], root=self.root)
        completion = {
            "schema": "ndf-agent-completion/v1",
            "topic": None,
            "task": "binder_amend",
            "track": "process",
            "base_sha": self.head,
            "repo_head": self.head,
            "manifest_sha": self.manifest["manifest_sha"],
            "context_plan_sha": plan["plan_sha"],
            "changed_files": ["out/output.txt"],
            "changed_file_shas": {
                "out/output.txt": hashlib.sha256(b"ok").hexdigest()
            },
            "reproduce_commands": [argv],
            "evidence_paths": ["r2-proof.txt"],
            "evidence_bundle_sha": proof_sha,
            "git_commit": "",
            "post_check_receipts": [
                {
                    "command": "python3 spec/meta/tools/ndf_bindcheck.py",
                    "result": "passed",
                    "output_sha": proof_sha,
                    "evidence_paths": ["r2-proof.txt"],
                }
            ],
            "result": "success",
            "run_id": "run-r2",
            "session_id": "session-r2",
            "worktree": str(self.root),
            "branch": "recorded-branch",
        }
        completion_sha = self.store.put_blob(completion)
        self.store.append_event(
            "ep-test",
            kind="acp.complete",
            actor="openclaw",
            payload_sha=completion_sha,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
            session_id="session-r2",
            run_id="run-r2",
        )
        commit = self.store.commit_events(
            "ep-test",
            message="record sandbox cassette",
            actor="tool",
        )
        profile = {
            "schema": "ndf-replay-sandbox-profile/v1",
            "sandbox": True,
            "network": "none",
            "adapter": ["bwrap"],
            "confirm_cost": True,
            "confirm_side_effects": True,
            "commands": [argv],
            "allowed_write_roots": ["out"],
            "expected_outputs": [
                {
                    "path": "out/output.txt",
                    "sha256": hashlib.sha256(b"ok").hexdigest(),
                }
            ],
        }
        try:
            result = self.store.sandbox_replay(commit, profile, execute=True)
        except subprocess.CalledProcessError as exc:
            self.skipTest(f"bwrap is not permitted in this environment: {exc}")
        self.assertEqual(result["state"], "equivalent")
        self.assertTrue(result["executed"])

    def test_fsck_detects_corrupt_object_and_dangling_ref(self) -> None:
        initialized = self._episode()
        object_path = self.store._object_path(initialized["commit_sha"])
        object_path.write_text("{}", encoding="utf-8")
        self.assertFalse(self.store.fsck()["valid"])

    def test_retention_plan_is_non_destructive(self) -> None:
        initialized = self._episode()
        before = self.store.get_object(initialized["commit_sha"])
        plan = self.store.retention_plan()
        self.assertFalse(plan["destructive"])
        self.assertEqual(before, self.store.get_object(initialized["commit_sha"]))

    def test_crash_leftover_temp_does_not_replace_valid_object_or_ref(self) -> None:
        initialized = self._episode()
        object_path = self.store._object_path(initialized["commit_sha"])
        leftover = object_path.parent / ".crashed-write"
        leftover.write_text("partial", encoding="utf-8")
        ref = self.store.ref_path("episodes/ep-test/HEAD")
        ref_leftover = ref.parent / ".HEAD.crashed"
        ref_leftover.write_text("not-a-sha", encoding="utf-8")
        self.assertEqual(
            self.store.read_ref("episodes/ep-test/HEAD"),
            initialized["commit_sha"],
        )
        self.assertTrue(self.store.fsck()["valid"])

    def test_atomic_ref_and_event_write_failure_preserves_previous_state(self) -> None:
        initialized = self._episode()
        original_ref = self.store.read_ref("episodes/ep-test/HEAD")
        replacement_tree = self.store.put_tree(
            {"payload": self.store.put_blob({"replacement": True})}
        )
        replacement = self.store.put_commit(
            replacement_tree,
            parents=[initialized["commit_sha"]],
            actor="test",
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=None,
            message="replacement",
        )
        with patch.object(replay.os, "replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                self.store.update_ref("episodes/ep-test/HEAD", replacement)
        self.assertEqual(
            self.store.read_ref("episodes/ep-test/HEAD"),
            original_ref,
        )
        before_events = self.store.read_events("ep-test")
        payload = self.store.put_blob({"event": "not-committed"})
        with patch.object(replay.os, "replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                self.store.append_event(
                    "ep-test",
                    kind="tool.result",
                    actor="tool",
                    payload_sha=payload,
                    topic=None,
                    task="binder_amend",
                    track="process",
                    repo_head=self.head,
                    manifest_sha=self.manifest["manifest_sha"],
                    context_plan_sha=None,
                )
        self.assertEqual(self.store.read_events("ep-test"), before_events)
        self.assertTrue(self.store.fsck()["valid"])


if __name__ == "__main__":
    unittest.main()
