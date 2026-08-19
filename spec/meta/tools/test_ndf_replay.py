import json
import concurrent.futures
import hashlib
import os
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

    def test_project_control_human_events_reject_agent_actors(self) -> None:
        self.assertIn("proposal.reviewed", replay.EVENT_KINDS)
        self.assertTrue(replay.event_actor_valid("proposal.confirmed", "human-reviewer"))
        self.assertTrue(replay.event_actor_valid("proposal.reviewed", "human-reviewer"))
        self.assertFalse(replay.event_actor_valid("proposal.confirmed", "openclaw"))
        self.assertFalse(replay.event_actor_valid("proposal.reviewed", "canvas"))

    def test_project_control_flow_requires_verified_context_and_stage_write_set(self) -> None:
        identity = {
            "proposal_id": "meta-managed",
            "flow_id": "flow-managed",
            "hop": "confirm_land",
            "manifest_sha": "a" * 64,
            "context_plan_sha": "b" * 64,
        }
        valid = replay.validate_project_control_flow(
            [
                ({"kind": "proposal.confirmed", "actor": "human-reviewer", **identity}, identity),
                ({"kind": "context.compiled", "actor": "context-compiler", **identity}, identity),
                ({"kind": "context.verified", "actor": "context-compiler", **identity}, identity),
                ({"kind": "dispatch.preflight", "actor": "project-control", **identity}, identity),
                (
                    {"kind": "openclaw.request", "actor": "openclaw", **identity},
                    {**identity, "request_id": "request-1", "attempt": 1},
                ),
                (
                    {"kind": "openclaw.response", "actor": "openclaw", **identity},
                    {**identity, "request_id": "request-1", "attempt": 1},
                ),
                (
                    {"kind": "filesystem.changed", "actor": "project-control", **identity},
                    {
                        **identity,
                        "changed_files": [
                            "spec/meta/process.md",
                            "spec/meta/open/proposal-meta-managed.md",
                        ],
                        "allowed_write_roots": [
                            "spec/meta/process.md",
                            "spec/meta/open/proposal-meta-managed.md",
                        ],
                    },
                ),
            ]
        )
        self.assertEqual(valid, [])

        invalid = replay.validate_project_control_flow(
            [
                ({"kind": "context.compiled", "actor": "context-compiler", **identity}, identity),
                ({"kind": "dispatch.preflight", "actor": "project-control", **identity}, identity),
                (
                    {"kind": "filesystem.changed", "actor": "project-control", **identity},
                    {
                        **identity,
                        "changed_files": ["src/forbidden.cpp"],
                        "allowed_write_roots": ["spec/meta/process.md"],
                    },
                ),
            ]
        )
        self.assertIn("dispatch_without_context_verify", invalid)
        self.assertIn("project_control_mutation_mismatch", invalid)

    def test_control_child_episodes_are_immutable_per_stage(self) -> None:
        parent = self.store.ensure_control_parent(
            flow_id="flow-managed",
            proposal_id="meta-managed",
            role="openclaw",
            track="process",
        )
        first = self.store.ensure_control_child(
            flow_id="flow-managed",
            stage="confirm_land",
            requested_episode_id="ep-land",
            manifest=self.manifest,
            topic=None,
            task="binder_amend",
            role="openclaw",
            track="process",
            proposal_id="meta-managed",
            proposal_sha="c" * 64,
        )
        again = self.store.ensure_control_child(
            flow_id="flow-managed",
            stage="confirm_land",
            requested_episode_id="ep-land",
            manifest=self.manifest,
            topic=None,
            task="binder_amend",
            role="openclaw",
            track="process",
            proposal_id="meta-managed",
            proposal_sha="c" * 64,
        )
        self.assertEqual(first["parent_episode_id"], parent)
        self.assertEqual(again["episode_id"], "ep-land")
        self.assertFalse(again["created"])
        with self.assertRaisesRegex(ValueError, "already bound for stage"):
            self.store.ensure_control_child(
                flow_id="flow-managed",
                stage="confirm_land",
                requested_episode_id="ep-other",
                manifest=self.manifest,
                topic=None,
                task="binder_amend",
                role="openclaw",
                track="process",
                proposal_id="meta-managed",
                proposal_sha="c" * 64,
            )
        with self.assertRaisesRegex(ValueError, "proposal rebind"):
            self.store.ensure_control_child(
                flow_id="flow-managed",
                stage="confirm_land",
                requested_episode_id="ep-land",
                manifest=self.manifest,
                topic=None,
                task="binder_amend",
                role="openclaw",
                track="process",
                proposal_id="meta-managed",
                proposal_sha="d" * 64,
            )
        review = self.store.ensure_control_child(
            flow_id="flow-managed",
            stage="review",
            requested_episode_id="ep-review",
            manifest=self.manifest,
            topic=None,
            task="binder_amend",
            role="openclaw",
            track="process",
            proposal_id="meta-managed",
            proposal_sha="c" * 64,
        )
        self.assertEqual(review["episode_id"], "ep-review")
        self.assertNotEqual(review["episode_id"], first["episode_id"])
        with self.assertRaisesRegex(ValueError, "another control stage"):
            self.store.ensure_control_child(
                flow_id="flow-managed",
                stage="draft",
                requested_episode_id="ep-land",
                manifest=self.manifest,
                topic=None,
                task="binder_amend",
                role="openclaw",
                track="process",
                proposal_id="meta-managed",
            )

    def test_project_control_mutation_requires_exact_declared_set(self) -> None:
        self.assertEqual(
            replay.validate_project_control_mutation(
                {
                    "changed_files": ["spec/meta/process.md"],
                    "declared_files": ["spec/meta/process.md"],
                    "allowed_write_roots": ["spec/meta/process.md"],
                }
            ),
            [],
        )
        self.assertIn(
            "project_control_mutation_mismatch",
            replay.validate_project_control_mutation(
                {
                    "changed_files": ["spec/meta/process.md"],
                    "declared_files": [
                        "spec/meta/process.md",
                        "spec/meta/open/proposal-meta-managed.md",
                    ],
                }
            ),
        )

    def test_dispatch_pack_lease_eligible_accepts_static_ready(self) -> None:
        self.assertTrue(
            replay.dispatch_pack_lease_eligible({"safe_to_dispatch": True})
        )
        self.assertTrue(
            replay.dispatch_pack_lease_eligible(
                {
                    "safe_to_dispatch": False,
                    "static_preflight_passed": True,
                }
            )
        )
        self.assertTrue(
            replay.dispatch_pack_lease_eligible(
                {
                    "safe_to_dispatch": False,
                    "safe_to_delegate": True,
                }
            )
        )
        self.assertFalse(
            replay.dispatch_pack_lease_eligible(
                {
                    "safe_to_dispatch": False,
                    "static_preflight_passed": False,
                    "safe_to_delegate": False,
                }
            )
        )

    def test_audit_accepts_static_ready_dispatch_preflight(self) -> None:
        _, plan, _ = self._episode_with_plan()
        dispatch = {
            "schema": "ndf-workflow-pack/v2",
            "provider": "claude-code-acp",
            "task": "binder_amend",
            "track": "process",
            "manifest_sha": self.manifest["manifest_sha"],
            "plan_sha": plan["plan_sha"],
            "safe_to_delegate": True,
            "static_preflight_passed": True,
            "safe_to_dispatch": False,
            "runtime_dispatch_ready": False,
        }
        blob = self.store.put_blob(dispatch)
        self.store.append_event(
            "ep-test",
            kind="dispatch.preflight",
            actor="claude-code-acp",
            payload_sha=blob,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=plan["plan_sha"],
            branch="implementation",
        )
        commit = self.store.commit_events(
            "ep-test",
            message="lease-prep dispatch",
            actor="claude-code-acp",
        )
        audit = self.store.audit(commit, strict=True)
        self.assertFalse(
            any("invalid_dispatch" in gap for gap in audit["semantic_gaps"]),
            audit["semantic_gaps"],
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

    def test_isolate_observe_uses_other_worktree_and_leaves_live_tree(self) -> None:
        _, _, commit = self._episode_with_plan("ep-isolate")
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        result = self.store.isolate_observe(commit, episode_id="ep-isolate")
        isolation = result["isolation"]
        self.assertTrue(result["valid"])
        self.assertEqual(result["schema"], "ndf-replay-isolate-proof/v1")
        self.assertFalse(isolation["same_checkout"])
        self.assertNotEqual(isolation["sandbox_toplevel"], isolation["live_toplevel"])
        self.assertTrue(isolation["live_head_unchanged"])
        self.assertTrue(isolation["live_tracked_unchanged"])
        self.assertTrue(isolation["sandbox_marker_absent_from_live_root"])
        self.assertFalse(isolation["bwrap_used"])
        self.assertFalse(result["reconstruct"]["side_effects"])
        self.assertFalse(result["execute"]["attempted"])
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), readme)
        self.assertFalse((self.root / "NDF_ISOLATE_PROOF").exists())
        self.assertTrue(Path(result["proof_path"]).is_file())

    def test_guest_run_vm_blocks_without_hypervisor(self) -> None:
        _, _, commit = self._episode_with_plan("ep-guest-block")
        with patch.object(
            replay,
            "probe_vm_hypervisor",
            return_value={
                "kvm": False,
                "qemu": None,
                "firecracker": None,
                "available": False,
                "blocker": "no_/dev/kvm",
            },
        ):
            result = self.store.guest_run(
                commit,
                episode_id="ep-guest-block",
                adapter="vm",
            )
        self.assertEqual(result["schema"], "ndf-replay-guest-proof/v1")
        self.assertEqual(result["state"], "environment_blocked")
        self.assertFalse(result["valid"])
        self.assertIn("environment_blocked", result["proof_errors"])
        self.assertFalse((self.root / "NDF_GUEST_MARKER").exists())

    def test_guest_environment_probe_schema(self) -> None:
        result = replay.guest_environment_probe(self.root)
        self.assertEqual(result["schema"], "ndf-replay-guest-probe/v1")
        self.assertEqual(result["default_adapter"], "vm")
        self.assertIn("next_actions", result)
        self.assertFalse(result["image_ready"])
        self.assertIn("guest_image", result["next_actions"])

    def test_guest_run_vm_blocks_without_image(self) -> None:
        _, _, commit = self._episode_with_plan("ep-guest-no-image")
        with patch.object(
            replay,
            "probe_vm_hypervisor",
            return_value={
                "kvm": True,
                "qemu": "/usr/bin/qemu-system-x86_64",
                "firecracker": None,
                "available": True,
                "blocker": None,
            },
        ):
            result = self.store.guest_run(
                commit,
                episode_id="ep-guest-no-image",
                adapter="vm",
            )
        self.assertEqual(result["state"], "environment_blocked")
        self.assertEqual(result["environment_blocker"], "vm_adapter_requires_guest_image")
        self.assertFalse(result["valid"])

    def test_guest_run_fake_vm_keeps_writes_off_live_tree(self) -> None:
        _, _, commit = self._episode_with_plan("ep-guest-ok")
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        porcelain_before = self.store._live_porcelain()
        result = self.store.guest_run(
            commit,
            episode_id="ep-guest-ok",
            adapter="fake-vm",
        )
        isolation = result["isolation"]
        self.assertEqual(result["schema"], "ndf-replay-guest-proof/v1")
        self.assertTrue(result["valid"], result.get("proof_errors"))
        self.assertFalse(isolation["same_checkout"])
        self.assertNotEqual(isolation["guest_toplevel"], isolation["host_toplevel"])
        self.assertTrue(isolation["host_tracked_unchanged"])
        self.assertTrue(isolation["sandbox_marker_absent_from_live_root"])
        self.assertFalse(isolation["bwrap_used"])
        self.assertEqual(isolation["adapter"], "fake-vm")
        self.assertFalse(result["reconstruct"]["side_effects"])
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), readme)
        self.assertFalse((self.root / "NDF_GUEST_MARKER").exists())
        self.assertEqual(self.store._live_porcelain(), porcelain_before)
        self.assertEqual(replay.validate_guest_proof(result), [])

    def test_validate_guest_proof_rejects_same_checkout_or_missing_fields(self) -> None:
        bad = {
            "schema": "ndf-replay-guest-proof/v1",
            "state": "guest_observe",
            "isolation": {
                "adapter": "fake-vm",
                "guest_id": "g1",
                "image_sha": "a" * 64,
                "guest_toplevel": "/live/repo",
                "host_toplevel": "/live/repo",
                "same_checkout": True,
                "host_tracked_unchanged": True,
                "host_head_unchanged": True,
                "sandbox_marker_absent_from_live_root": True,
                "bwrap_used": False,
            },
            "reconstruct": {"side_effects": False},
        }
        errors = replay.validate_guest_proof(bad)
        self.assertIn("same_checkout", errors)
        missing = {
            "schema": "ndf-replay-guest-proof/v1",
            "state": "guest_observe",
            "isolation": {
                "adapter": "vm",
                "same_checkout": False,
                "host_tracked_unchanged": True,
                "host_head_unchanged": True,
                "sandbox_marker_absent_from_live_root": True,
                "bwrap_used": False,
            },
            "reconstruct": {"side_effects": False},
        }
        missing_errors = replay.validate_guest_proof(missing)
        self.assertTrue(any(item.startswith("missing:") for item in missing_errors))

    def test_guest_run_cube_blocks_without_api(self) -> None:
        _, _, commit = self._episode_with_plan("ep-cube-block")
        with patch.dict(os.environ, {}, clear=False):
            for key in (
                "NDF_CUBE_API_URL",
                "E2B_API_URL",
                "NDF_CUBE_TEMPLATE_ID",
                "CUBE_TEMPLATE_ID",
            ):
                os.environ.pop(key, None)
            result = self.store.guest_run(
                commit,
                episode_id="ep-cube-block",
                adapter="cube",
            )
        self.assertEqual(result["state"], "environment_blocked")
        self.assertFalse(result["valid"])
        self.assertEqual(result["isolation"]["adapter"], "vm")
        self.assertEqual(result["isolation"]["hypervisor_backend"], "cube")

    def test_guest_run_cube_rejects_host_mount_of_live_root(self) -> None:
        _, _, commit = self._episode_with_plan("ep-cube-mount")
        client = replay.MockCubeSandboxClient(self.root)
        result = self.store.guest_run(
            commit,
            episode_id="ep-cube-mount",
            adapter="cube",
            cube_client=client,
            cube_template_id="tpl-test",
            host_mount=str(self.root),
        )
        self.assertEqual(result["state"], "environment_blocked")
        self.assertIn("host_mount", result["environment_blocker"])
        self.assertFalse(result["valid"])
        self.assertTrue(result["isolation"]["host_mount_used"])

    def test_guest_run_cube_mock_injects_without_touching_live_tree(self) -> None:
        _, _, commit = self._episode_with_plan("ep-cube-ok")
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        porcelain_before = self.store._live_porcelain()
        client = replay.MockCubeSandboxClient(self.root)
        result = self.store.guest_run(
            commit,
            episode_id="ep-cube-ok",
            adapter="cube",
            cube_client=client,
            cube_template_id="tpl-test",
        )
        isolation = result["isolation"]
        self.assertTrue(result["valid"], result.get("proof_errors"))
        self.assertEqual(isolation["adapter"], "vm")
        self.assertEqual(isolation["hypervisor_backend"], "cube")
        self.assertFalse(isolation["same_checkout"])
        self.assertFalse(isolation["host_mount_used"])
        self.assertTrue(isolation["host_tracked_unchanged"])
        self.assertTrue(isolation["sandbox_marker_absent_from_live_root"])
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), readme)
        self.assertFalse((self.root / "NDF_GUEST_MARKER").exists())
        self.assertEqual(self.store._live_porcelain(), porcelain_before)
        self.assertEqual(replay.validate_guest_proof(result), [])

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

    def test_diff_returns_six_semantic_facets(self) -> None:
        initialized, _, commit = self._episode_with_plan("ep-diff-facets")
        result = self.store.diff(initialized["commit_sha"], commit)
        self.assertEqual(
            set(result["facets"]),
            {
                "manifest",
                "context",
                "events",
                "observations",
                "results",
                "verification",
            },
        )
        self.assertTrue(result["facets"]["context"]["added"])
        self.assertTrue(result["facets"]["events"]["added"])
        self.assertIn("change_classification", result)
        self.assertIn(
            "contract_slice_changed", result["change_classification"]
        )
        self.assertIn(
            "manifest_formula_changed", result["change_classification"]
        )
        self.assertIn(
            "mutable_evidence_changed", result["change_classification"]
        )

    def test_diff_contract_change_uses_content_sha_not_manifest(self) -> None:
        slices = [
            {
                "slice_id": "topic_contract",
                "path": "poc/demo/ndf/TOPIC.md",
                "content_sha": "c" * 64,
            }
        ]

        def spec(*, content: str, manifest: str) -> dict:
            return {
                "bundle_mode": "review_slice",
                "expected_content_sha": content,
                "slices": slices,
                "slice_manifest_sha": manifest,
            }

        def commit_with(specs: dict, message: str) -> str:
            manifest = dict(self.manifest)
            gates = dict(manifest.get("human_gates") or {})
            gates["bundle_specs"] = specs
            manifest["human_gates"] = gates
            manifest["manifest_sha"] = context.canonical_json_sha(
                {
                    key: value
                    for key, value in manifest.items()
                    if key != "manifest_sha"
                }
            )
            blob = self.store.put_blob(manifest)
            tree = self.store.put_tree({"manifest": blob})
            return self.store.put_commit(
                tree,
                actor="tool",
                topic=None,
                task="binder_amend",
                track="process",
                repo_head=self.head,
                manifest_sha=manifest["manifest_sha"],
                context_plan_sha=None,
                message=message,
            )

        formula_left = commit_with(
            {"topic_review": spec(content="a" * 64, manifest="1" * 64)},
            "formula left",
        )
        formula_right = commit_with(
            {"topic_review": spec(content="a" * 64, manifest="2" * 64)},
            "formula right",
        )
        formula = self.store.diff(formula_left, formula_right)["change_classification"]
        self.assertEqual(formula["contract_slice_changed"], [])
        self.assertEqual(formula["manifest_formula_changed"], ["topic_review"])

        content_right = commit_with(
            {"topic_review": spec(content="b" * 64, manifest="1" * 64)},
            "content right",
        )
        content = self.store.diff(formula_left, content_right)["change_classification"]
        self.assertEqual(content["contract_slice_changed"], ["topic_review"])
        self.assertEqual(content["manifest_formula_changed"], [])

    def test_r2_profile_rejects_wrong_role_plan_target(self) -> None:
        _, plan, commit = self._episode_with_plan("ep-r2-wrong-role")
        profile = {
            "schema": "ndf-replay-sandbox-profile/v1",
            "sandbox": True,
            "network": "none",
            "adapter": ["bwrap"],
            "commands": [],
            "allowed_write_roots": [],
            "expected_outputs": [],
            "target": {
                "run_id": "run",
                "role": "claude-code",
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": plan["plan_sha"],
                "env_allowlist_fingerprint": "d" * 64,
                "cwd": str(self.root),
                "tool_runtime_version": "fixture",
            },
        }
        with self.assertRaisesRegex(ValueError, "role does not match"):
            self.store.sandbox_replay(commit, profile, execute=False)

    def test_r2_rejects_current_repo_drift_before_execution(self) -> None:
        _, plan, commit = self._episode_with_plan("ep-r2-drift")
        (self.root / "README.md").write_text("advanced\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "advance"], cwd=self.root, check=True
        )
        profile = {
            "schema": "ndf-replay-sandbox-profile/v1",
            "sandbox": True,
            "network": "none",
            "adapter": ["bwrap"],
            "confirm_cost": True,
            "confirm_side_effects": True,
            "commands": [["/bin/true"]],
            "allowed_write_roots": [],
            "expected_outputs": [{"path": "out", "sha256": "0" * 64}],
            "target": {
                "run_id": "run",
                "role": "openclaw",
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": plan["plan_sha"],
                "env_allowlist_fingerprint": "d" * 64,
                "cwd": str(self.root),
                "tool_runtime_version": "fixture",
            },
        }
        with (
            patch.object(replay.shutil, "which", return_value="/usr/bin/bwrap"),
            self.assertRaisesRegex(ValueError, "current restore is not ready"),
        ):
            self.store.sandbox_replay(commit, profile, execute=True)

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
        _, plan, commit = self._episode_with_plan()
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
            "target": {
                "run_id": "missing-run",
                "role": "openclaw",
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": plan["plan_sha"],
                "env_allowlist_fingerprint": "d" * 64,
                "cwd": str(self.root),
                "tool_runtime_version": "python-fixture",
            },
        }
        try:
            result = self.store.sandbox_replay(
                commit,
                profile,
                execute=True,
            )
        except ValueError as exc:
            message = str(exc)
            self.assertTrue(
                "complete output set" in message
                or "isolation adapter is unavailable" in message
                or "requires managed adapter" in message,
                message,
            )
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
            external_resource_version="python-fixture",
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
            "target": {
                "run_id": "run-r2",
                "role": "openclaw",
                "manifest_sha": self.manifest["manifest_sha"],
                "plan_sha": plan["plan_sha"],
                "env_allowlist_fingerprint": "d" * 64,
                "cwd": str(self.root),
                "tool_runtime_version": "python-fixture",
            },
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

    def test_canvas_index_and_ledger_are_read_only_of_heads(self) -> None:
        first = self._episode("ep-canvas-a")
        second = self._episode("ep-canvas-b")
        fat = self.store.put_blob(
            {
                "schema": "ndf-agent-message/v1",
                "message": "P" * 4000,
                "manifest_sha": "a" * 64,
                "task": "binder_amend",
            }
        )
        self.store.append_event(
            "ep-canvas-a",
            kind="openclaw.request",
            actor="openclaw",
            payload_sha=fat,
            topic=None,
            task="binder_amend",
            track="process",
            repo_head=self.head,
            manifest_sha=self.manifest["manifest_sha"],
            context_plan_sha=None,
        )
        before = self.store.episode_head_map()
        index = self.store.canvas_index(write_cache=True)
        ids = {item["id"] for item in index["episodes"]}
        self.assertEqual(ids, {"ep-canvas-a", "ep-canvas-b"})
        for card in index["episodes"]:
            self.assertNotIn("assembledPrompt", card)
            self.assertNotIn("timeline", card)
            self.assertNotIn("dispatchedPrompt", card)
        ledger = self.store.canvas_ledger("ep-canvas-a", write_cache=True)
        self.assertEqual(ledger["id"], "ep-canvas-a")
        self.assertTrue(ledger["dispatchedPrompt"]["text"])
        self.assertLessEqual(
            len(str(ledger["dispatchedPrompt"]["text"])),
            replay.CANVAS_PROMPT_LIMIT,
        )
        self.assertEqual(self.store.episode_head_map(), before)
        self.assertEqual(before["ep-canvas-a"], first["commit_sha"])
        self.assertEqual(before["ep-canvas-b"], second["commit_sha"])
        chosen = replay.pick_canvas_focused_id(index["episodes"], "ep-canvas-b", None)
        self.assertEqual(chosen, "ep-canvas-b")


class ReplayProjectionHelpersTest(unittest.TestCase):
    def test_event_space_and_plane(self) -> None:
        self.assertEqual(replay.event_space("gate.confirmed"), "human")
        self.assertEqual(replay.event_space("context.verified"), "ndf")
        self.assertEqual(replay.event_space("filesystem.changed"), "result")
        self.assertEqual(replay.event_plane("openclaw.request"), "meta")
        self.assertEqual(replay.event_plane("acp.start"), "project")
        self.assertEqual(
            replay.episode_plane(
                episode_id="meta-014--confirm-land",
                track="process",
                task="project_control",
                kinds=["openclaw.request"],
            ),
            "meta",
        )
        self.assertEqual(
            replay.episode_plane(
                episode_id="ep-poc-run",
                track="poc",
                task="implement",
                kinds=["acp.start", "filesystem.changed"],
            ),
            "project",
        )

    def test_payload_preview_and_dispatch_leak(self) -> None:
        preview = replay.payload_preview(
            kind="gate.confirmed",
            payload={"human_phrase": "已确认", "approved_by": "human"},
            actor="human",
        )
        self.assertEqual(preview["space"], "human")
        self.assertEqual(preview["humanUtterance"], "已确认")
        self.assertNotIn("token", json.dumps(preview).lower())

        assembled = replay.assembled_context_summary(
            manifest={
                "intent": "land process proposal",
                "task": "project_control",
                "clause_seeds": ["META-014"],
                "shared_graph_closure": {"nodes": ["META-014"]},
            },
            plan={
                "role": "openclaw",
                "task": "project_control",
                "human_phrase": "已确认",
                "ordered_reads": [{"path": "spec/meta/process.md"}],
                "privileges": {"allowed_write_roots": ["spec/meta/"]},
            },
        )
        self.assertEqual(assembled["role"], "openclaw")
        self.assertEqual(assembled["orderedReads"], ["spec/meta/process.md"])
        self.assertIsNone(assembled["readWhyMissing"])

        self.assertTrue(
            replay.detect_dispatch_leak(
                human_utterance="已确认",
                dispatch_payloads=[{"message": "已确认"}],
            )
        )
        self.assertFalse(
            replay.detect_dispatch_leak(
                human_utterance="已确认",
                dispatch_payloads=[
                    {
                        "manifest_sha": "a" * 64,
                        "plan_sha": "b" * 64,
                        "message": "Execute bound Context Plan for confirm_land",
                    }
                ],
            )
        )

        assembled_prompt = replay.assembled_prompt_view(
            manifest={
                "intent": "land process proposal",
                "task": "project_control",
                "clause_seeds": ["META-014"],
                "shared_graph_closure": {"nodes": ["META-014"]},
            },
            plan={
                "role": "openclaw",
                "task": "project_control",
                "human_phrase": "已确认",
                "ordered_reads": [{"path": "spec/meta/process.md"}],
                "privileges": {"allowed_write_roots": ["spec/meta/"]},
            },
            plan_sha="c" * 64,
            plan_blob_found=True,
        )
        self.assertEqual(assembled_prompt["source"], "context-plan")
        self.assertIn("spec/meta/process.md", assembled_prompt["text"] or "")
        self.assertIn("不得把人口令当成主任务正文", assembled_prompt["text"] or "")
        self.assertIsNone(assembled_prompt["whyMissing"])

        manifest_only = replay.assembled_prompt_view(
            manifest={"intent": "x", "clause_seeds": ["META-014"], "shared_graph_closure": {"nodes": ["a"]}},
            plan=None,
            plan_sha=None,
            plan_blob_found=False,
        )
        self.assertIsNone(manifest_only["text"])
        self.assertEqual(manifest_only["source"], "manifest-only")
        self.assertIn("不能拼出完整下达 Prompt", manifest_only["whyMissing"] or "")

        dispatched = replay.dispatched_prompt_view(
            [
                {
                    "schema": "ndf-agent-message/v1",
                    "message": "Execute bound Context Plan for confirm_land",
                    "manifest_sha": "a" * 64,
                    "context_plan_sha": "b" * 64,
                    "task": "project_control",
                    "topic": None,
                    "pipeline": "control",
                }
            ]
        )
        self.assertEqual(dispatched["source"], "openclaw.request")
        self.assertIn("Execute bound Context Plan", dispatched["text"] or "")

        empty_dispatch = replay.dispatched_prompt_view([])
        self.assertIsNone(empty_dispatch["text"])
        self.assertIn("没有 openclaw.request", empty_dispatch["whyMissing"] or "")

        drift = replay.prompt_drift_view(
            assembled=assembled_prompt,
            dispatched=dispatched,
            dispatch_leak=False,
            dispatch_payloads=[
                {
                    "manifest_sha": "a" * 64,
                    "plan_sha": "b" * 64,
                    "message": "Execute bound Context Plan for confirm_land",
                }
            ],
        )
        self.assertFalse(drift["mismatch"])

        leak_drift = replay.prompt_drift_view(
            assembled=assembled_prompt,
            dispatched={"text": "已确认", "whyMissing": None, "source": "dispatch"},
            dispatch_leak=True,
            dispatch_payloads=[{"message": "已确认"}],
        )
        self.assertTrue(leak_drift["mismatch"])
        self.assertIn("dispatch_human_leak", leak_drift["reasons"])
        secret_preview = replay.payload_preview(
            kind="tool.result",
            payload={"name": "shell", "argv": ["echo", "api_key=secret-value"]},
            actor="tool",
        )
        self.assertIn("[redacted]", secret_preview["summary"])
        self.assertNotIn("secret-value", secret_preview["summary"])

    def test_manifest_then_plan_keeps_ordered_reads(self) -> None:
        """manifest.created arrives first; Plan reads must still win."""
        manifest_payload = {
            "schema": "ndf-task-manifest/v1",
            "intent": "confirm land",
            "task": "project_control",
            "clause_seeds": ["META-014"],
            "shared_graph_closure": {"nodes": ["META-014", "META-013"]},
        }
        plan_payload = {
            "schema": "ndf-context-plan/v1",
            "role": "openclaw",
            "task": "project_control",
            "plan_sha": "c" * 64,
            "ordered_reads": [
                {"path": "spec/meta/process.md"},
                {"path": "spec/meta/README.md"},
            ],
            "privileges": {"allowed_write_roots": ["spec/meta/open/"]},
        }
        first = replay.classify_compile_payload("manifest.created", manifest_payload)
        second = replay.classify_compile_payload("context.compiled", plan_payload)
        self.assertIsNotNone(first["manifest"])
        self.assertIsNone(first["plan"])
        self.assertIsNone(second["manifest"])
        self.assertIsNotNone(second["plan"])

        event_manifest = first["manifest"]
        event_plan = second["plan"]
        assembled = replay.assembled_context_summary(
            manifest=event_manifest,
            plan=event_plan,
            plan_sha="c" * 64,
            plan_blob_found=True,
        )
        self.assertEqual(
            assembled["orderedReads"],
            ["spec/meta/process.md", "spec/meta/README.md"],
        )
        self.assertEqual(assembled["graphNodes"], 2)
        self.assertIsNone(assembled["readWhyMissing"])

        # Old bug: treating Manifest as the only compile hit drops reads.
        wrong = replay.assembled_context_summary(
            manifest=event_manifest,
            plan=None,
            plan_sha=None,
            plan_blob_found=False,
        )
        self.assertEqual(wrong["orderedReads"], [])
        self.assertIn("Manifest", wrong["readWhyMissing"] or "")

    def test_read_why_missing_reasons(self) -> None:
        self.assertIsNone(
            replay.read_why_missing(
                ordered_reads=["spec/meta/process.md"],
                plan={"ordered_reads": [{"path": "spec/meta/process.md"}]},
                plan_sha="a" * 64,
                plan_blob_found=True,
            )
        )
        self.assertIn(
            "找不到 Plan",
            replay.read_why_missing(
                ordered_reads=[],
                plan=None,
                plan_sha="a" * 64,
                plan_blob_found=False,
            )
            or "",
        )
        self.assertIn(
            "只装了 Manifest",
            replay.read_why_missing(
                ordered_reads=[],
                plan=None,
                plan_sha=None,
                plan_blob_found=False,
                manifest={"clause_seeds": ["META-014"]},
            )
            or "",
        )

    def test_episode_matches_agent_includes_compiler_participation(self) -> None:
        self.assertTrue(
            replay.episode_matches_agent(
                needle="context-compiler",
                agent="openclaw",
                participants=["context-compiler", "openclaw"],
                kinds=["intent.received", "context.compiled"],
            )
        )
        self.assertTrue(
            replay.episode_matches_agent(
                needle="context-compiler",
                agent="openclaw",
                participants=["openclaw"],
                kinds=["manifest.created", "context.compiled"],
            )
        )
        self.assertFalse(
            replay.episode_matches_agent(
                needle="claude-code",
                agent="openclaw",
                participants=["openclaw"],
                kinds=["context.compiled"],
            )
        )

    def test_episode_title(self) -> None:
        self.assertEqual(
            replay.episode_title(
                episode_id="ep-x",
                proposal_id="meta-ndf-control-closed-loop",
                stage="confirm_land",
                happened_at="2026-08-17T12:00:00Z",
            ),
            "meta-ndf-control-closed-loop · 确认落地 · 2026-08-17",
        )


if __name__ == "__main__":
    unittest.main()
