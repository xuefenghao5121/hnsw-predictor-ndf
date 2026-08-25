#!/usr/bin/env python3
"""Self-check: dispatch closeout succeeds from disk receipt without stdout notify."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[3]
sys.path.insert(0, str(TOOLS))
import ndf_dispatch_send as dispatch  # noqa: E402


def main() -> int:
    pack = {
        "topic": "project-genesis",
        "task": "product_proposal",
        "track": "bootstrap",
        "hop": "genesis_architecture",
        "attempt_id": "architecture-g1",
        "episode_id": "project-genesis",
        "allowed_write_roots": ["spec/open/"],
        "workspace": {"repo_root": str(REPO)},
    }
    rel = dispatch.completion_receipt_path_for_pack(pack)
    assert "genesis_architecture" in rel, rel
    assert rel != "spec/open/.ndf-completion/product_proposal-attempt.json"

    pack["completion_receipt_path"] = rel
    path = REPO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "ndf-agent-completion/v1",
        "status": "completed",
        "result": "success",
        "topic": "project-genesis",
        "task": "product_proposal",
        "hop": "genesis_architecture",
        "episode_id": "project-genesis",
        "attempt_id": "architecture-g1",
        "summary": "disk-first self-check",
    }
    path.write_text(json.dumps(receipt), encoding="utf-8")
    try:
        result, blockers, summary, completion = dispatch._task_outcome_from_transport(
            {"transport_ok": True, "ok": True, "response_text": "no notify here"},
            pack=pack,
            lease_only=False,
        )
        assert result == "succeeded", (result, blockers, summary)
        assert blockers == []
        assert "missing_dispatch_notify" not in blockers
        assert completion is not None
        assert completion["attempt_id"] == "architecture-g1"
    finally:
        if path.is_file():
            path.unlink()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
