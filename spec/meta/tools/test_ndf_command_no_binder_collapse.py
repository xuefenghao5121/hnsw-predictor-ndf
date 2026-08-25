#!/usr/bin/env python3
"""META-011 command-no-binder-collapse smoke tests (stdlib)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


wf = _load("ndf_workflow_status", TOOLS / "ndf_workflow_status.py")
perf = _load("ndf_perf_baseline", TOOLS / "ndf_perf_baseline.py")


class CommandNoBinderCollapseTests(unittest.TestCase):
    def test_fallback_when_gateway_down(self):
        plan = wf.control_dispatch_plan(
            {"reachable": False, "session_dispatchable": False}
        )
        self.assertTrue(plan["runtime_ready"])
        self.assertEqual(plan["provider"], "in-host")
        self.assertTrue(plan["using_fallback"])
        self.assertEqual(plan["blockers"], [])

    def test_open_topic_binder_pipeline_finds_reviewed_proposal(self):
        prop = wf.reviewed_product_proposal_for_topic("hierarchical-vamana")
        self.assertIsNotNone(prop)
        assert prop is not None
        self.assertTrue(prop.is_file())
        self.assertIn("hierarchical-vamana", prop.name)

    def test_perf_baseline_empty_evidence_status_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            topic = "empty-evidence"
            ndf = Path(tmp) / "poc" / topic / "ndf"
            ndf.mkdir(parents=True)
            (ndf / "TOPIC.md").write_text(
                "> ndf_topic: empty-evidence\n"
                "> status: exploring\n"
                "> perf_baseline: ndf/PERF_BASELINE.md\n"
                "> baseline_trunk_sha: d0ae5dd\n"
                "> baseline_status: pending\n",
                encoding="utf-8",
            )
            (ndf / "PERF_BASELINE.md").write_text(
                "> vs: bl-trunk-d0ae5dd\n"
                "> config_id: cfg-sla-ef100\n"
                "> measure_script: scripts/run_sustained.sh\n"
                "> trunk_sha: d0ae5dd\n"
                "> status: pending\n"
                "> evidence_status:\n\n"
                "## Numbers\n\nPending R0.\n",
                encoding="utf-8",
            )
            (ndf / "DELTA.md").write_text("# DELTA\n", encoding="utf-8")
            old_poc = perf.POC
            old_root = perf.ROOT
            try:
                perf.POC = Path(tmp) / "poc"
                perf.ROOT = Path(tmp)
                view = perf.inspect_topic(topic, require_card=True)
            finally:
                perf.POC = old_poc
                perf.ROOT = old_root
            kinds = {f.kind for f in view.findings}
            self.assertNotIn("unverified_measurement_claim", kinds)


if __name__ == "__main__":
    unittest.main()
