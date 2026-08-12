#!/usr/bin/env python3
"""Shared, read-mostly evidence primitives for NDF workflow tools.

The only write helper in this module appends runtime leases to a caller-selected
path below ``<repo>/tmp``.  It never writes NDF or project state.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


RECEIPT_SCHEMAS = frozenset(
    {
        "ndf-projection-receipt/v2",
        "ndf-close-evidence/v1",
        "ndf-runtime-lease/v1",
    }
)
COMMON_RECEIPT_FIELDS = (
    "schema",
    "task",
    "topic",
    "mode",
    "step",
    "repo_head",
    "source_generation_sha",
    "context_plan_sha",
    "command",
    "input_sha",
    "output_sha",
    "evidence_paths",
    "started_at",
    "finished_at",
    "result",
    "blockers",
)
SHA256_LEN = 64


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 representation used by workflow hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha(value: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact, UTF-8, no NaN)."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha(path: str | os.PathLike[str]) -> str:
    """SHA-256 of exact file bytes. Missing/non-files are errors."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if not _inside(resolved, resolved_root):
        raise ValueError(f"path escapes workspace: {path}")
    return resolved.relative_to(resolved_root).as_posix()


def bundle_sha(
    paths: Iterable[str | os.PathLike[str]],
    *,
    root: str | os.PathLike[str],
) -> str:
    """Hash an exact, path-bound file bundle.

    Files are deduplicated and sorted by workspace-relative POSIX path.  Every
    file is required.  The byte stream is ``path NUL content NUL`` per file,
    matching the established gate-bundle convention.
    """
    repo = Path(root)
    entries: dict[str, Path] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        rel = _relative_path(path, repo)
        if rel in entries and entries[rel].read_bytes() != path.read_bytes():
            raise ValueError(f"duplicate bundle path has different content: {rel}")
        entries[rel] = path
    if not entries:
        raise ValueError("bundle must contain at least one file")
    digest = hashlib.sha256()
    for rel, path in sorted(entries.items()):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def safe_tmp_report_path(
    path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str],
) -> Path:
    """Resolve a report path and require it to remain below ``root/tmp``."""
    repo = Path(root).resolve()
    tmp = (repo / "tmp").resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo / candidate
    candidate = candidate.resolve(strict=False)
    if candidate == tmp or not _inside(candidate, tmp):
        raise ValueError(f"report path must be below {tmp}: {candidate}")
    # Existing symlinked parents must not redirect writes outside tmp.
    parent = candidate.parent
    while parent != tmp and not parent.exists():
        parent = parent.parent
    if parent.exists() and not _inside(parent.resolve(), tmp):
        raise ValueError(f"report parent escapes tmp: {parent}")
    return candidate


def workspace_truth(
    binding: Mapping[str, Any] | None,
    persisted: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare current workspace binding with persisted project state.

    ``persisted`` may be either the workspace object or the containing state
    object.  File existence alone is intentionally not accepted as binding.
    """
    expected = dict(binding or {})
    raw = dict(persisted or {})
    actual = raw.get("workspace") if isinstance(raw.get("workspace"), Mapping) else raw
    actual = dict(actual or {})
    mismatches: list[dict[str, Any]] = []
    for field in ("repo_root", "active_topic"):
        want = expected.get(field)
        got = actual.get(field)
        if want is not None and want != got:
            mismatches.append({"field": field, "expected": want, "actual": got})
    want_head = expected.get("repo_head") or expected.get("bound_sha")
    got_head = actual.get("repo_head") or actual.get("bound_sha")
    if want_head is not None and want_head != got_head:
        mismatches.append({"field": "repo_head", "expected": want_head, "actual": got_head})
    required = ("repo_root", "repo_head", "active_topic")
    missing = [name for name in required if not (actual.get(name) or (name == "repo_head" and actual.get("bound_sha")))]
    bound = bool(expected and actual and not mismatches and not missing)
    return {
        "workspace_bound": bound,
        "state": "bound" if bound else "unbound",
        "mismatches": mismatches,
        "missing": missing,
        "binding": expected,
        "persisted_workspace": actual,
    }


def _is_full_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LEN
        and all(char in "0123456789abcdef" for char in value)
    )


def _is_git_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and all(char in "0123456789abcdef" for char in value)
    )


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one supported workflow receipt without trusting its claims."""
    errors: list[str] = []
    schema = receipt.get("schema")
    if schema not in RECEIPT_SCHEMAS:
        errors.append(f"unsupported_schema:{schema}")
    for field in COMMON_RECEIPT_FIELDS:
        if field not in receipt:
            errors.append(f"missing:{field}")
    if receipt.get("repo_head") is not None and not _is_git_sha(receipt.get("repo_head")):
        errors.append("invalid_git_sha:repo_head")
    for field in ("source_generation_sha", "context_plan_sha", "input_sha", "output_sha"):
        value = receipt.get(field)
        if value is not None and not _is_full_sha(value):
            errors.append(f"invalid_sha256:{field}")
    for field in ("evidence_paths", "blockers"):
        value = receipt.get(field)
        if value is not None and not isinstance(value, list):
            errors.append(f"not_list:{field}")
    if schema == "ndf-runtime-lease/v1":
        for field in ("run_id", "session_id", "base_sha", "worktree", "allowed_write_root"):
            if not receipt.get(field):
                errors.append(f"missing:{field}")
        state = receipt.get("result")
        if state not in {"active", "released", "expired", "failed"}:
            errors.append(f"invalid_lease_result:{state}")
    elif schema == "ndf-close-evidence/v1":
        if receipt.get("mode") not in {"promote", "partial", "reject", "bug", "refactor", "rollback"}:
            errors.append(f"invalid_close_mode:{receipt.get('mode')}")
    elif schema == "ndf-projection-receipt/v2":
        if not receipt.get("projection_sha") and not receipt.get("snapshot_sha_after"):
            errors.append("missing:projection_sha")
    return {"valid": not errors, "schema": schema, "errors": errors}


def read_lease_jsonl(
    path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str],
    strict: bool = True,
) -> list[dict[str, Any]]:
    """Read validated runtime leases from a guarded tmp JSONL file."""
    target = safe_tmp_report_path(path, root=root)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if strict:
                raise ValueError(f"invalid JSONL at line {line_no}: {exc}") from exc
            continue
        validation = validate_receipt(value) if isinstance(value, Mapping) else {"valid": False}
        if not validation["valid"] or value.get("schema") != "ndf-runtime-lease/v1":
            if strict:
                raise ValueError(
                    f"invalid runtime lease at line {line_no}: {validation.get('errors', [])}"
                )
            continue
        records.append(dict(value))
    return records


def append_runtime_lease(
    path: str | os.PathLike[str],
    lease: Mapping[str, Any],
    *,
    root: str | os.PathLike[str],
) -> Path:
    """Append one validated lease as canonical JSON below ``root/tmp``."""
    validation = validate_receipt(lease)
    if lease.get("schema") != "ndf-runtime-lease/v1" or not validation["valid"]:
        raise ValueError(f"invalid runtime lease: {validation['errors']}")
    target = safe_tmp_report_path(path, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as stream:
        stream.write(canonical_json_bytes(dict(lease)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return target


# Concise aliases for callers that use lease terminology.
read_leases = read_lease_jsonl
append_lease = append_runtime_lease
