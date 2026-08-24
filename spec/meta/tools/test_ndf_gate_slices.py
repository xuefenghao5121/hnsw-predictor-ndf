import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("ndf_gate_slices.py")
SPEC = importlib.util.spec_from_file_location("ndf_gate_slices", MODULE_PATH)
assert SPEC and SPEC.loader
slices = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = slices
SPEC.loader.exec_module(slices)


class GateSliceTest(unittest.TestCase):
    def _topic(self, root: Path, *, marked: bool = True) -> Path:
        topic = root / "poc" / "demo"
        ndf = topic / "ndf"
        ndf.mkdir(parents=True)
        marker = (
            "<!-- ndf:gate-slice begin=topic_contract -->\n"
            "hypothesis A\n"
            "<!-- ndf:gate-slice end=topic_contract -->\n"
            if marked
            else "hypothesis A\n"
        )
        (ndf / "TOPIC.md").write_text(
            "> baseline_status: stale\n" + marker,
            encoding="utf-8",
        )
        (ndf / "DESIGN.md").write_text(
            "<!-- ndf:gate-slice begin=design_contract -->\n"
            "design A\n"
            "<!-- ndf:gate-slice end=design_contract -->\n"
            "evidence mutable\n",
            encoding="utf-8",
        )
        (ndf / "PERF_BASELINE.md").write_text(
            "<!-- ndf:gate-slice begin=perf_bind -->\n"
            "> vs: bl-a\n> config_id: cfg-a\n"
            "<!-- ndf:gate-slice end=perf_bind -->\n"
            "## Numbers\npending\n",
            encoding="utf-8",
        )
        (ndf / "DELTA.md").write_text(
            "<!-- ndf:gate-slice begin=delta_hypothesis -->\n"
            "hypothesis H1\n"
            "<!-- ndf:gate-slice end=delta_hypothesis -->\n"
            "## Rounds\nR0 pending\n",
            encoding="utf-8",
        )
        (ndf / "INTERFACE.md").write_text(
            "<!-- ndf:gate-slice begin=interface_contract -->\n"
            "interface A\n"
            "<!-- ndf:gate-slice end=interface_contract -->\n",
            encoding="utf-8",
        )
        return topic

    def test_mutable_sections_do_not_change_review_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            before = slices.gate_bundle_specs(topic, root=root)
            ndf = topic / "ndf"
            (ndf / "TOPIC.md").write_text(
                (ndf / "TOPIC.md").read_text().replace("stale", "current"),
                encoding="utf-8",
            )
            with (ndf / "PERF_BASELINE.md").open("a", encoding="utf-8") as stream:
                stream.write("R0: 123 QPS\n")
            with (ndf / "DELTA.md").open("a", encoding="utf-8") as stream:
                stream.write("R1 result\n")
            after = slices.gate_bundle_specs(topic, root=root)
            self.assertEqual(
                {gate: item["expected_content_sha"] for gate, item in before.items()},
                {gate: item["expected_content_sha"] for gate, item in after.items()},
            )

    def test_contract_changes_follow_invalidation_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            ndf = topic / "ndf"
            base = slices.gate_bundle_specs(topic, root=root)

            topic_path = ndf / "TOPIC.md"
            topic_path.write_text(
                topic_path.read_text().replace("hypothesis A", "hypothesis B"),
                encoding="utf-8",
            )
            changed = slices.gate_bundle_specs(topic, root=root)
            self.assertTrue(
                all(
                    base[gate]["expected_content_sha"]
                    != changed[gate]["expected_content_sha"]
                    for gate in base
                )
            )

            topic_path.write_text(
                topic_path.read_text().replace("hypothesis B", "hypothesis A"),
                encoding="utf-8",
            )
            design_path = ndf / "DESIGN.md"
            design_path.write_text(
                design_path.read_text().replace("design A", "design B"),
                encoding="utf-8",
            )
            changed = slices.gate_bundle_specs(topic, root=root)
            self.assertEqual(
                base["topic_review"]["expected_content_sha"],
                changed["topic_review"]["expected_content_sha"],
            )
            self.assertNotEqual(
                base["design_review"]["expected_content_sha"],
                changed["design_review"]["expected_content_sha"],
            )
            self.assertNotEqual(
                base["implementation_approval"]["expected_content_sha"],
                changed["implementation_approval"]["expected_content_sha"],
            )

    def test_legacy_and_partial_marker_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root, marked=False)
            ndf = topic / "ndf"
            # Remove the other markers to make a true legacy topic.
            for name in ("DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md"):
                path = ndf / name
                text = "\n".join(
                    line
                    for line in path.read_text().splitlines()
                    if "ndf:gate-slice" not in line
                ) + "\n"
                path.write_text(text, encoding="utf-8")
            legacy = slices.gate_bundle_specs(topic, root=root)
            self.assertTrue(
                all(item["bundle_mode"] == "legacy_whole_file" for item in legacy.values())
            )

            with (ndf / "TOPIC.md").open("a", encoding="utf-8") as stream:
                stream.write(
                    "<!-- ndf:gate-slice begin=topic_contract -->\n"
                    "new\n"
                    "<!-- ndf:gate-slice end=topic_contract -->\n"
                )
            partial = slices.gate_bundle_specs(topic, root=root)
            self.assertEqual(partial["topic_review"]["bundle_mode"], "review_slice")
            self.assertTrue(partial["design_review"]["errors"])
            self.assertIsNone(partial["design_review"]["expected_content_sha"])

    def test_selected_decision_line_shift_keeps_manifest_and_content_sha(self) -> None:
        """Runtime header insert must not fake-invalidate promote/partial close."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            ndf = topic / "ndf"
            before = slices.gate_bundle_specs(topic, root=root)
            before_lines = {
                gate: [
                    (item["start_line"], item["end_line"])
                    for item in before[gate]["slices"]
                    if item["slice_id"] == "topic_contract"
                ]
                for gate in before
            }
            for mode in ("promote", "partial", "reject"):
                topic_path = ndf / "TOPIC.md"
                body = topic_path.read_text(encoding="utf-8")
                # Strip any prior selected_decision, then insert one line before markers.
                lines = [
                    line
                    for line in body.splitlines(keepends=True)
                    if not line.startswith("> selected_decision:")
                ]
                insert_at = 0
                for index, line in enumerate(lines):
                    if "ndf:gate-slice begin=topic_contract" in line:
                        insert_at = index
                        break
                lines.insert(insert_at, f"> selected_decision: {mode}\n")
                topic_path.write_text("".join(lines), encoding="utf-8")
                after = slices.gate_bundle_specs(topic, root=root)
                self.assertEqual(
                    {gate: item["expected_content_sha"] for gate, item in before.items()},
                    {gate: item["expected_content_sha"] for gate, item in after.items()},
                    msg=f"content sha drifted for selected_decision={mode}",
                )
                self.assertEqual(
                    {gate: item["slice_manifest_sha"] for gate, item in before.items()},
                    {gate: item["slice_manifest_sha"] for gate, item in after.items()},
                    msg=f"manifest sha drifted for selected_decision={mode}",
                )
                after_lines = {
                    gate: [
                        (item["start_line"], item["end_line"])
                        for item in after[gate]["slices"]
                        if item["slice_id"] == "topic_contract"
                    ]
                    for gate in after
                }
                self.assertNotEqual(
                    before_lines["topic_review"],
                    after_lines["topic_review"],
                    msg="line numbers should still shift for diagnostics",
                )

    def test_topic_contract_edit_still_changes_content_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            before = slices.gate_bundle_specs(topic, root=root)
            topic_path = topic / "ndf" / "TOPIC.md"
            topic_path.write_text(
                topic_path.read_text(encoding="utf-8").replace(
                    "hypothesis A", "hypothesis Z"
                ),
                encoding="utf-8",
            )
            after = slices.gate_bundle_specs(topic, root=root)
            self.assertNotEqual(
                before["topic_review"]["expected_content_sha"],
                after["topic_review"]["expected_content_sha"],
            )
            self.assertNotEqual(
                before["topic_review"]["slice_manifest_sha"],
                after["topic_review"]["slice_manifest_sha"],
            )
            self.assertNotEqual(
                before["implementation_approval"]["expected_content_sha"],
                after["implementation_approval"]["expected_content_sha"],
            )

    def test_binder_pointer_stub_does_not_null_expected_sha(self) -> None:
        """Marker-less proposals/ stub must not poison gate expected_content_sha.

        Hotspot-style binders keep a pointer under ndf/proposals/ plus the
        canonical body under spec/open/. Treating the stub as missing_gate_slice
        previously set expected=null for every gate and failed context-verify
        even when GATES receipts already matched live review-slice SHAs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            ndf = topic / "ndf"
            proposals = ndf / "proposals"
            proposals.mkdir()
            (proposals / "proposal-demo.md").write_text(
                "# Stub → product proposal\n\n"
                "Canonical text: `spec/open/proposal-demo.md`\n",
                encoding="utf-8",
            )
            open_dir = root / "spec" / "open"
            open_dir.mkdir(parents=True)
            open_proposal = open_dir / "proposal-demo.md"
            open_proposal.write_text(
                "<!-- ndf:gate-slice begin=proposal_contract -->\n"
                "proposal body\n"
                "<!-- ndf:gate-slice end=proposal_contract -->\n",
                encoding="utf-8",
            )
            with_stub = slices.gate_bundle_specs(
                topic,
                root=root,
                proposal_paths=[proposals / "proposal-demo.md", open_proposal],
            )
            only_open = slices.gate_bundle_specs(
                topic, root=root, proposal_paths=[open_proposal]
            )
            for gate in (
                "topic_review",
                "design_review",
                "implementation_approval",
            ):
                self.assertIsNotNone(with_stub[gate]["expected_content_sha"], gate)
                self.assertEqual(
                    with_stub[gate]["expected_content_sha"],
                    only_open[gate]["expected_content_sha"],
                    gate,
                )
                stub_errors = [
                    err
                    for err in with_stub[gate]["errors"]
                    if err.get("path", "").endswith("proposals/proposal-demo.md")
                ]
                self.assertEqual(stub_errors, [], gate)

    def test_nested_markers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TOPIC.md"
            path.write_text(
                "<!-- ndf:gate-slice begin=topic_contract -->\n"
                "<!-- ndf:gate-slice begin=other -->\n"
                "<!-- ndf:gate-slice end=other -->\n",
                encoding="utf-8",
            )
            parsed = slices.parse_review_slices(path, root=Path(tmp))
            kinds = {item["kind"] for item in parsed["errors"]}
            self.assertIn("nested_gate_slice", kinds)
            self.assertIn("mismatched_gate_slice_end", kinds)

    def test_parse_gates_table_uses_headers_for_seven_and_nine_columns(self) -> None:
        seven = (
            "| gate | phrase | approved_by | approved_at | approved_content_sha |"
            " source_ref | status |\n"
            "|------|--------|-------------|-------------|----------------------|"
            "------------|--------|\n"
            "| topic_review | TOPIC已审核 | human | 2026-08-13T00:00:00Z |"
            " aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |"
            " TOPIC.md | approved |\n"
        )
        nine = (
            "| gate | phrase | approved_by | approved_at | approved_content_sha |"
            " bundle_mode | slice_manifest_sha | source_ref | status |\n"
            "|------|--------|-------------|-------------|----------------------|"
            "-------------|-------------------|------------|--------|\n"
            "| implementation_approval | 可以开始实现 | human | 2026-08-14T10:26:00Z |"
            " bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb |"
            " review_slice | cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc |"
            " TOPIC+DESIGN | approved |\n"
        )
        seven_row = slices.parse_gates_table(seven)[0]
        nine_row = slices.parse_gates_table(nine)[0]
        self.assertEqual(seven_row["status"], "approved")
        self.assertEqual(seven_row["source_ref"], "TOPIC.md")
        self.assertEqual(nine_row["status"], "approved")
        self.assertEqual(nine_row["bundle_mode"], "review_slice")
        self.assertEqual(nine_row["source_ref"], "TOPIC+DESIGN")
        self.assertNotEqual(nine_row["status"], "TOPIC+DESIGN")

    def test_review_slice_mode_aligned_tolerates_manifest_only_drift(self) -> None:
        self.assertTrue(
            slices.review_slice_mode_aligned(
                receipt_bundle_mode="review_slice",
                expected_bundle_mode="review_slice",
                receipt_slice_manifest_sha="d" * 64,
                expected_slice_manifest_sha="e" * 64,
                approved_content_sha="c" * 64,
                expected_content_sha="c" * 64,
            )
        )
        self.assertFalse(
            slices.review_slice_mode_aligned(
                receipt_bundle_mode="review_slice",
                expected_bundle_mode="review_slice",
                receipt_slice_manifest_sha="d" * 64,
                expected_slice_manifest_sha="e" * 64,
                approved_content_sha="c" * 64,
                expected_content_sha="f" * 64,
            )
        )
        self.assertFalse(
            slices.review_slice_mode_aligned(
                receipt_bundle_mode="legacy_whole_file",
                expected_bundle_mode="review_slice",
                receipt_slice_manifest_sha=None,
                expected_slice_manifest_sha="e" * 64,
                approved_content_sha="c" * 64,
                expected_content_sha="c" * 64,
            )
        )

    def test_content_identity_ignores_slice_manifest_sha(self) -> None:
        left = {
            "expected_content_sha": "a" * 64,
            "bundle_mode": "review_slice",
            "slice_manifest_sha": "1" * 64,
            "slices": [
                {
                    "slice_id": "topic_contract",
                    "path": "poc/demo/ndf/TOPIC.md",
                    "content_sha": "c" * 64,
                }
            ],
        }
        right = dict(left)
        right["slice_manifest_sha"] = "2" * 64
        self.assertEqual(
            slices.gate_spec_content_identity(left),
            slices.gate_spec_content_identity(right),
        )
        right["expected_content_sha"] = "b" * 64
        self.assertNotEqual(
            slices.gate_spec_content_identity(left),
            slices.gate_spec_content_identity(right),
        )

    def test_explain_gate_drift_shows_interface_hunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            specs = slices.gate_bundle_specs(topic, root=root)
            sha = specs["bundle_dispatch"]["expected_content_sha"]
            self.assertTrue(sha)
            saved = slices.persist_gate_slice_snapshot(
                topic,
                "bundle_dispatch",
                approved_content_sha=sha,
                root=root,
            )
            self.assertTrue(saved.get("ok"))
            iface = topic / "ndf" / "INTERFACE.md"
            iface.write_text(
                iface.read_text(encoding="utf-8").replace(
                    "interface A", "interface B"
                ),
                encoding="utf-8",
            )
            # Numbers-like mutable append must not appear in slice diff path.
            with (topic / "ndf" / "DELTA.md").open("a", encoding="utf-8") as stream:
                stream.write("R9 numbers only\n")
            explain = slices.explain_gate_drift(
                topic,
                "bundle_dispatch",
                approved_content_sha=sha,
                root=root,
            )
            self.assertTrue(explain["drift"])
            changed_ids = {item["slice_id"] for item in explain["changed_slices"]}
            self.assertEqual(changed_ids, {"interface_contract"})
            blob = "\n".join(item["diff"] for item in explain["slice_diffs"])
            self.assertIn("interface B", blob)
            self.assertNotIn("R9 numbers only", blob)
            self.assertIsNone(explain.get("diff_unavailable"))

    def test_explain_without_snapshot_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = self._topic(root)
            explain = slices.explain_gate_drift(
                topic,
                "bundle_dispatch",
                approved_content_sha="a" * 64,
                root=root,
            )
            self.assertTrue(explain["drift"])
            self.assertEqual(explain["diff_unavailable"], "missing_gate_snapshot")


if __name__ == "__main__":
    unittest.main()
