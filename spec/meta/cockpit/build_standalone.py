#!/usr/bin/env python3
"""Build a self-contained commander page from Vite dist + NDF snapshot."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COCKPIT = Path(__file__).resolve().parent
DIST = COCKPIT / "dist"
SNAPSHOT = ROOT / "tmp" / "ndf-canvas-snapshot.json"
OUTPUT = ROOT / "docs" / "ndf-commander.html"


def main() -> None:
    index = (DIST / "index.html").read_text(encoding="utf-8")
    script_match = re.search(r'<script type="module" crossorigin src="([^"]+)"></script>', index)
    style_match = re.search(r'<link rel="stylesheet" crossorigin href="([^"]+)">', index)
    if not script_match or not style_match:
        raise RuntimeError("Vite output assets not found")

    javascript = (DIST / script_match.group(1).lstrip("/")).read_text(encoding="utf-8")
    # htmlpreview.github.io rewrites every literal "<script" in the fetched
    # document, including occurrences inside bundled JavaScript strings. React
    # DOM contains one such string, which made the hosted page a black screen
    # with `Unexpected identifier 'text'`. Preserve the runtime string while
    # keeping it invisible to that HTML rewriter.
    javascript = re.sub(r"<script", r"\\x3cscript", javascript, flags=re.IGNORECASE)
    css = (DIST / style_match.group(1).lstrip("/")).read_text(encoding="utf-8")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    embedded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="dark" />
  <title>NDF commander · DiskHNSW</title>
  <style>{css}</style>
</head>
<body>
  <div id="root"></div>
  <script>
    window.__NDF_STANDALONE__ = true;
    window.__NDF_SNAPSHOT__ = {embedded};
  </script>
  <script type="module">{javascript}</script>
</body>
</html>
"""
    OUTPUT.write_text(page, encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": "ndf-commander-standalone-build/v1",
                "output": str(OUTPUT.relative_to(ROOT)),
                "bytes": OUTPUT.stat().st_size,
                "snapshotSha": snapshot.get("snapshotSha"),
                "payloadSha": snapshot.get("payloadSha"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
