#!/usr/bin/env python3
"""Canonical POC gate review slices (META-010).

Review slices bind human-approved contract content while leaving mutable
measurement/evidence sections outside gate SHA churn.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[3]

BEGIN_RE = re.compile(
    r"^\s*<!--\s*ndf:gate-slice\s+begin=([a-z][a-z0-9_-]*)\s*-->\s*$"
)
END_RE = re.compile(
    r"^\s*<!--\s*ndf:gate-slice\s+end=([a-z][a-z0-9_-]*)\s*-->\s*$"
)

CORE_SLICES = {
    "topic_contract": "TOPIC.md",
    "design_contract": "DESIGN.md",
    "perf_bind": "PERF_BASELINE.md",
    "delta_hypothesis": "DELTA.md",
    "interface_contract": "INTERFACE.md",
}
GATE_SLICE_IDS = {
    "topic_review": ("topic_contract",),
    "design_review": ("topic_contract", "design_contract"),
    "implementation_approval": (
        "topic_contract",
        "design_contract",
        "perf_bind",
        "delta_hypothesis",
        "interface_contract",
    ),
}
MUTABLE_SECTIONS = (
    "topic_runtime_headers",
    "perf_numbers",
    "delta_rounds",
    "evidence",
    "commits",
    "gates",
)
REQUIRED_GATE_COLUMNS = (
    "gate",
    "phrase",
    "approved_by",
    "approved_at",
    "approved_content_sha",
    "source_ref",
    "status",
)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _canonical_json_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def parse_gates_table(text: str) -> list[dict[str, str]]:
    """Parse append-only GATES.md tables by header name (7-col or 9-col)."""
    lines = text.splitlines()
    rows: list[dict[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.lstrip().startswith("|"):
            index += 1
            continue
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        normalized = [
            re.sub(r"[^a-z_]", "", cell.lower().replace(" ", "_")) for cell in cols
        ]
        if not all(name in normalized for name in REQUIRED_GATE_COLUMNS):
            index += 1
            continue
        if index + 1 >= len(lines):
            break
        cursor = index + 2
        while cursor < len(lines):
            row_line = lines[cursor]
            if not row_line.lstrip().startswith("|"):
                break
            values = [
                cell.strip().strip("`")
                for cell in row_line.strip().strip("|").split("|")
            ]
            if len(values) < len(cols):
                values.extend([""] * (len(cols) - len(values)))
            row = dict(zip(normalized, values))
            if row.get("gate") and set(row["gate"]) - {"-", ":"}:
                rows.append(row)
            cursor += 1
        index = max(cursor, index + 1)
    return rows


def legacy_bundle_sha(paths: Iterable[Path], *, root: Path = ROOT) -> str | None:
    existing = sorted({path.resolve() for path in paths if path.is_file()}, key=str)
    if not existing:
        return None
    digest = hashlib.sha256()
    for path in existing:
        digest.update(_rel(path, root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def parse_review_slices(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": _rel(path, root),
            "has_markers": False,
            "slices": {},
            "errors": [{"kind": "missing_file", "path": _rel(path, root)}],
        }
    slices: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    active_id: str | None = None
    active_start = 0
    content: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    marker_count = 0
    for line_no, line in enumerate(lines, start=1):
        begin = BEGIN_RE.match(line.rstrip("\r\n"))
        end = END_RE.match(line.rstrip("\r\n"))
        if begin:
            marker_count += 1
            slice_id = begin.group(1)
            if active_id is not None:
                errors.append(
                    {
                        "kind": "nested_gate_slice",
                        "path": _rel(path, root),
                        "line": line_no,
                        "active": active_id,
                        "nested": slice_id,
                    }
                )
                continue
            if slice_id in slices:
                errors.append(
                    {
                        "kind": "duplicate_gate_slice",
                        "path": _rel(path, root),
                        "line": line_no,
                        "slice_id": slice_id,
                    }
                )
            active_id = slice_id
            active_start = line_no
            content = []
            continue
        if end:
            marker_count += 1
            slice_id = end.group(1)
            if active_id is None:
                errors.append(
                    {
                        "kind": "unmatched_gate_slice_end",
                        "path": _rel(path, root),
                        "line": line_no,
                        "slice_id": slice_id,
                    }
                )
                continue
            if slice_id != active_id:
                errors.append(
                    {
                        "kind": "mismatched_gate_slice_end",
                        "path": _rel(path, root),
                        "line": line_no,
                        "expected": active_id,
                        "actual": slice_id,
                    }
                )
                active_id = None
                content = []
                continue
            raw = "".join(content).encode("utf-8")
            if slice_id not in slices:
                slices[slice_id] = {
                    "slice_id": slice_id,
                    "path": _rel(path, root),
                    "content_sha": hashlib.sha256(raw).hexdigest(),
                    "content_bytes": raw,
                    "start_line": active_start + 1,
                    "end_line": line_no - 1,
                }
            active_id = None
            content = []
            continue
        if active_id is not None:
            content.append(line)
    if active_id is not None:
        errors.append(
            {
                "kind": "unterminated_gate_slice",
                "path": _rel(path, root),
                "slice_id": active_id,
                "line": active_start,
            }
        )
    return {
        "path": _rel(path, root),
        "has_markers": marker_count > 0,
        "slices": slices,
        "errors": errors,
    }


def review_bundle_sha(records: Iterable[dict[str, Any]]) -> str | None:
    ordered = sorted(records, key=lambda item: (item["slice_id"], item["path"]))
    if not ordered:
        return None
    digest = hashlib.sha256()
    for item in ordered:
        digest.update(str(item["slice_id"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes(item["content_bytes"]))
        digest.update(b"\0")
    return digest.hexdigest()


def slice_content_fingerprints(path: Path, *, root: Path = ROOT) -> list[dict[str, str]]:
    """Contract-slice identity for a binder file, excluding mutable sections."""
    parsed = parse_review_slices(path, root=root)
    if not parsed.get("has_markers"):
        return []
    return [
        {"slice_id": str(record["slice_id"]), "content_sha": str(record["content_sha"])}
        for record in sorted(
            parsed.get("slices", {}).values(),
            key=lambda item: str(item.get("slice_id") or ""),
        )
    ]


def gate_spec_content_identity(spec: Mapping[str, Any] | None) -> tuple[Any, ...]:
    """Identity used to decide whether a gate *contract* changed.

    expected_content_sha + bundle_mode + slice content_sha. slice_manifest_sha
    is diagnostic and MUST NOT enter this tuple.
    """
    spec = spec or {}
    slices = []
    for item in spec.get("slices") or []:
        if not isinstance(item, Mapping):
            continue
        slices.append(
            (item.get("slice_id"), item.get("path"), item.get("content_sha"))
        )
    return (spec.get("expected_content_sha"), spec.get("bundle_mode"), tuple(slices))


def review_slice_mode_aligned(
    *,
    receipt_bundle_mode: str | None,
    expected_bundle_mode: str | None,
    receipt_slice_manifest_sha: str | None,
    expected_slice_manifest_sha: str | None,
    approved_content_sha: str | None,
    expected_content_sha: str | None,
) -> bool:
    """True when receipt bundle mode matches expected.

    review_slice identity is expected_content_sha. Manifest SHA may drift
    after line-number-only edits or semantic-manifest migration; tolerate
    that when content SHAs already match and both sides are review_slice.
    """
    receipt_mode = receipt_bundle_mode or "legacy_whole_file"
    expected_mode = expected_bundle_mode or "legacy_whole_file"
    if receipt_mode != expected_mode:
        return False
    if expected_mode != "review_slice":
        return True
    if receipt_slice_manifest_sha == expected_slice_manifest_sha:
        return True
    return bool(
        expected_content_sha
        and approved_content_sha
        and expected_content_sha == approved_content_sha
        and receipt_mode == "review_slice"
    )


def receipt_mode_aligned(receipt: Mapping[str, Any]) -> bool:
    return review_slice_mode_aligned(
        receipt_bundle_mode=receipt.get("receipt_bundle_mode")
        or receipt.get("bundle_mode"),
        expected_bundle_mode=receipt.get("expected_bundle_mode"),
        receipt_slice_manifest_sha=receipt.get("receipt_slice_manifest_sha")
        or receipt.get("slice_manifest_sha"),
        expected_slice_manifest_sha=receipt.get("expected_slice_manifest_sha"),
        approved_content_sha=receipt.get("approved_content_sha"),
        expected_content_sha=receipt.get("expected_content_sha"),
    )


def gate_bundle_specs(
    topic_dir: Path,
    *,
    root: Path = ROOT,
    proposal_paths: Iterable[Path] = (),
) -> dict[str, dict[str, Any]]:
    ndf = topic_dir / "ndf"
    legacy_paths = {
        "topic_review": [ndf / "TOPIC.md", *proposal_paths],
        "design_review": [ndf / "TOPIC.md", ndf / "DESIGN.md"],
        "implementation_approval": [
            ndf / "TOPIC.md",
            ndf / "DESIGN.md",
            ndf / "PERF_BASELINE.md",
            ndf / "DELTA.md",
            ndf / "INTERFACE.md",
        ],
    }
    parsed = {
        name: parse_review_slices(ndf / filename, root=root)
        for name, filename in CORE_SLICES.items()
    }
    proposal_records = [
        parse_review_slices(path, root=root) for path in proposal_paths
    ]
    has_markers = any(item["has_markers"] for item in parsed.values()) or any(
        item["has_markers"] for item in proposal_records
    )
    if not has_markers:
        return {
            gate: {
                "bundle_mode": "legacy_whole_file",
                "expected_content_sha": (
                    legacy_bundle_sha(paths, root=root)
                    if paths and all(path.is_file() for path in paths)
                    else None
                ),
                "bundle_paths": [_rel(path, root) for path in paths if path.is_file()],
                "slices": [],
                "slice_manifest_sha": None,
                "errors": [
                    {"kind": "missing_file", "path": _rel(path, root)}
                    for path in paths
                    if not path.is_file()
                ],
                "mutable_sections": list(MUTABLE_SECTIONS),
            }
            for gate, paths in legacy_paths.items()
        }

    global_errors: list[dict[str, Any]] = []
    for item in [*parsed.values(), *proposal_records]:
        global_errors.extend(
            error
            for error in item["errors"]
            if error.get("kind") != "missing_file"
        )

    core_by_id = {
        slice_id: parsed[slice_id]["slices"].get(slice_id)
        for slice_id in CORE_SLICES
    }
    proposal_slices: list[dict[str, Any]] = []
    for item in proposal_records:
        record = item["slices"].get("proposal_contract")
        if record:
            proposal_slices.append(record)
        else:
            global_errors.append(
                {
                    "kind": "missing_gate_slice",
                    "path": item["path"],
                    "slice_id": "proposal_contract",
                }
            )

    specs: dict[str, dict[str, Any]] = {}
    for gate, required_ids in GATE_SLICE_IDS.items():
        records = [core_by_id[slice_id] for slice_id in required_ids if core_by_id[slice_id]]
        if gate == "topic_review":
            records.extend(proposal_slices)
        missing = [
            {
                "kind": "missing_gate_slice",
                "path": _rel(ndf / CORE_SLICES[slice_id], root),
                "slice_id": slice_id,
            }
            for slice_id in required_ids
            if not core_by_id[slice_id]
        ]
        errors = [*global_errors, *missing]
        public_records = [
            {
                key: value
                for key, value in record.items()
                if key != "content_bytes"
            }
            for record in records
        ]
        # Manifest identity is semantic only. start_line/end_line stay on
        # public_records for UI/diagnostics but MUST NOT enter the hash —
        # inserting runtime headers (e.g. selected_decision) shifts lines
        # without changing contract bytes and must not invalidate gates.
        semantic_records = [
            {
                "slice_id": record["slice_id"],
                "path": record["path"],
                "content_sha": record["content_sha"],
            }
            for record in records
        ]
        slice_manifest = {
            "schema": "ndf-gate-slice-manifest/v1",
            "bundle_mode": "review_slice",
            "gate": gate,
            "slices": semantic_records,
        }
        specs[gate] = {
            "bundle_mode": "review_slice",
            "expected_content_sha": review_bundle_sha(records) if not errors else None,
            "bundle_paths": sorted({record["path"] for record in records}),
            "slices": public_records,
            "slice_manifest_sha": _canonical_json_sha(slice_manifest),
            "errors": errors,
            "mutable_sections": list(MUTABLE_SECTIONS),
        }
    return specs

