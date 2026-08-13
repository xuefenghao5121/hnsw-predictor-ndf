#!/usr/bin/env python3
"""Content-addressed Agent Episode recording and bounded replay.

The default store is ``<repo>/.ndf/replay`` and is not an NDF source of truth.
All mutation is explicit through this CLI or the ``ReplayStore`` API.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - deployment guard
    AESGCM = None  # type: ignore[assignment]

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ndf_workflow_evidence import (  # noqa: E402
    canonical_json_bytes,
    canonical_json_sha,
    chained_event,
    validate_evidence_bundle,
    validate_event_chain,
    validate_receipt,
    validate_recorded_runtime_lease_binding,
    validate_runtime_lease_binding,
)

ROOT = Path(__file__).resolve().parents[3]
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
EVENT_KINDS = frozenset(
    {
        "intent.received",
        "manifest.created",
        "context.compiled",
        "context.expanded",
        "context.verified",
        "proposal.confirmed",
        "gate.approved",
        "dispatch.preflight",
        "dispatch.blocked",
        "openclaw.request",
        "openclaw.response",
        "acp.start",
        "lease.acquired",
        "model.request",
        "model.response",
        "tool.invoke",
        "tool.result",
        "filesystem.changed",
        "git.commit",
        "acp.complete",
        "lease.released",
        "verification.completed",
        "close.receipt",
        "action.begin",
        "action.finish",
        "snapshot.embedded",
        "compaction.checkpoint",
        "legacy.import",
    }
)
REPLAY_LEVELS = ("R0", "R1", "R2", "R3")
SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|session[_-]?key|authorization|cookie)",
    re.I,
)
_UNSET = object()
ENCRYPTED_MAGIC = b"NDFE1\0"
AGENT_ACTORS = {
    "agent",
    "openclaw",
    "claude-code",
    "canvas",
    "tool",
    "context-compiler",
    "project-control",
    "model",
    "sandbox",
    "close",
}


def event_actor_valid(kind: str, actor: str) -> bool:
    if kind in {"proposal.confirmed", "gate.approved"}:
        return bool(actor) and actor.lower() not in AGENT_ACTORS
    if kind in {"acp.start", "lease.acquired", "lease.released", "acp.complete"}:
        return actor == "claude-code"
    if kind.startswith("openclaw."):
        return actor == "openclaw"
    if kind in {"manifest.created", "context.compiled", "context.expanded", "context.verified"}:
        return actor in {"context-compiler", "canvas", "openclaw", "claude-code", "project-control"}
    if kind in {"snapshot.embedded", "compaction.checkpoint"}:
        return actor in {"tool", "canvas"}
    return bool(actor)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _assert_no_plaintext_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            secret_marker = child is None or child is False or child is True
            if isinstance(child, str):
                secret_marker = child in {"[REDACTED]", "present", "absent"}
            telemetry_key = str(key).lower() in {
                "token_usage",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            }
            if (
                SECRET_KEY_RE.search(str(key))
                and not telemetry_key
                and not secret_marker
            ):
                raise ValueError(f"plaintext secret-like field is forbidden: {child_path}")
            _assert_no_plaintext_secrets(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_plaintext_secrets(child, f"{path}[{index}]")


class ReplayStore:
    """Small Git-like object store with atomic refs and append-only events."""

    def __init__(self, repo_root: Path = ROOT, store_root: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.root = (store_root or self.repo_root / ".ndf" / "replay").resolve()
        if not _inside(self.root, self.repo_root):
            raise ValueError("replay store must remain inside repository")
        self.objects = self.root / "objects"
        self.refs = self.root / "refs"
        self.events = self.root / "events"

    def initialize(self) -> None:
        for path in (self.objects, self.refs, self.events):
            path.mkdir(parents=True, exist_ok=True)
        config = self.root / "config.json"
        if not config.exists():
            self._atomic_write(
                config,
                canonical_json_bytes(
                    {
                        "schema": "ndf-replay-config/v1",
                        "created_at": now_iso(),
                        "object_hash": "sha256-canonical-json",
                        "default_replay_level": "R0",
                        "storage_security": "encrypted-local",
                        "cipher": "AES-256-GCM",
                        "key_id": self._key_id(),
                        "retention": {
                            "large_tool_blob_hot_days": 90,
                            "sensitive_model_turn_hot_days": 30,
                            "core_evidence": "topic-close-plus-one-archive-cycle",
                            "cold_objects_keep_sha_and_location": True,
                        },
                    }
                )
                + b"\n",
            )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _key_path(self) -> Path:
        override = os.environ.get("NDF_REPLAY_KEY_FILE")
        if override:
            return Path(override).expanduser().resolve()
        repo_id = hashlib.sha256(str(self.repo_root).encode("utf-8")).hexdigest()
        return (
            Path.home()
            / ".local"
            / "share"
            / "ndf-replay"
            / "keys"
            / f"{repo_id}.key"
        )

    def _key(self) -> bytes:
        if AESGCM is None:
            raise RuntimeError("cryptography is required for encrypted Replay objects")
        path = self._key_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._atomic_write(path, os.urandom(32))
            path.chmod(0o600)
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError(f"invalid Replay encryption key: {path}")
        return key

    def _key_id(self) -> str:
        return hashlib.sha256(self._key()).hexdigest()

    def _encrypt_object(self, sha: str, content: bytes) -> bytes:
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key()).encrypt(
            nonce,
            content,
            sha.encode("ascii"),
        )
        return ENCRYPTED_MAGIC + nonce + encrypted

    def _decrypt_object(self, sha: str, content: bytes) -> tuple[bytes, bool]:
        if not content.startswith(ENCRYPTED_MAGIC):
            return content, False
        nonce_start = len(ENCRYPTED_MAGIC)
        nonce = content[nonce_start : nonce_start + 12]
        ciphertext = content[nonce_start + 12 :]
        try:
            plain = AESGCM(self._key()).decrypt(
                nonce,
                ciphertext,
                sha.encode("ascii"),
            )
        except Exception as exc:
            raise ValueError(f"object decryption failed: {sha}") from exc
        return plain, True

    def _object_path(self, sha: str) -> Path:
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid object sha: {sha}")
        return self.objects / sha[:2] / sha[2:]

    def put_object(self, kind: str, data: Mapping[str, Any]) -> str:
        self.initialize()
        envelope = {"type": kind, "data": _json_copy(data)}
        content = canonical_json_bytes(envelope)
        sha = canonical_json_sha(envelope)
        path = self._object_path(sha)
        if path.exists():
            existing, _ = self._decrypt_object(sha, path.read_bytes())
            if existing != content:
                raise ValueError(f"object collision: {sha}")
            return sha
        self._atomic_write(path, self._encrypt_object(sha, content))
        return sha

    def get_object(self, sha: str, expected_type: str | None = None) -> dict[str, Any]:
        path = self._object_path(sha)
        if not path.is_file():
            raise FileNotFoundError(f"missing replay object: {sha}")
        raw, _ = self._decrypt_object(sha, path.read_bytes())
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid replay object: {sha}") from exc
        if canonical_json_sha(value) != sha:
            raise ValueError(f"object hash mismatch: {sha}")
        if expected_type and value.get("type") != expected_type:
            raise ValueError(f"expected {expected_type}, got {value.get('type')}")
        return value

    def find_blob(
        self,
        *,
        schema: str | None,
        schema_prefix: str | None = None,
        semantic_field: str,
        semantic_sha: str,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve one semantic SHA to its content-addressed blob."""
        matches: list[tuple[str, dict[str, Any]]] = []
        if self.objects.is_dir():
            for path in sorted(
                item
                for item in self.objects.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                sha = path.parent.name + path.name
                try:
                    obj = self.get_object(sha, "blob")
                except (FileNotFoundError, ValueError):
                    continue
                value = obj.get("data", {}).get("value")
                if (
                    isinstance(value, dict)
                    and (
                        value.get("schema") == schema
                        if schema is not None
                        else True
                    )
                    and (
                        str(value.get("schema") or "").startswith(schema_prefix)
                        if schema_prefix is not None
                        else True
                    )
                    and value.get(semantic_field) == semantic_sha
                ):
                    matches.append((sha, value))
        if not matches:
            raise ValueError(f"missing {schema or 'semantic'} blob for {semantic_sha}")
        first_sha, first = matches[0]
        if any(value != first for _, value in matches[1:]):
            raise ValueError(f"ambiguous semantic object: {semantic_sha}")
        return first_sha, first

    def put_blob(
        self,
        value: Any,
        *,
        media_type: str = "application/json",
        sensitivity: str = "internal",
    ) -> str:
        if isinstance(value, bytes):
            encoding = "base64"
            payload: Any = base64.b64encode(value).decode("ascii")
        elif isinstance(value, str):
            encoding = "utf-8"
            payload = value
        else:
            encoding = "json"
            payload = _json_copy(value)
        return self.put_object(
            "blob",
            {
                "schema": "ndf-replay-blob/v1",
                "media_type": media_type,
                "encoding": encoding,
                "sensitivity": sensitivity,
                "value": payload,
            },
        )

    def put_tree(self, entries: Mapping[str, str]) -> str:
        normalized: dict[str, str] = {}
        for name, sha in sorted(entries.items()):
            if not name or name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"invalid tree name: {name}")
            self.get_object(sha)
            normalized[name] = sha
        return self.put_object(
            "tree",
            {"schema": "ndf-replay-tree/v1", "entries": normalized},
        )

    def put_commit(
        self,
        tree: str,
        *,
        parents: Iterable[str] = (),
        actor: str,
        topic: str | None,
        task: str,
        track: str,
        repo_head: str | None,
        manifest_sha: str | None,
        context_plan_sha: str | None,
        message: str,
        coverage: Mapping[str, Any] | None = None,
    ) -> str:
        self.get_object(tree, "tree")
        parent_list = list(parents)
        for parent in parent_list:
            self.get_object(parent, "commit")
        return self.put_object(
            "commit",
            {
                "schema": "ndf-replay-commit/v1",
                "tree": tree,
                "parents": parent_list,
                "actor": actor,
                "topic": topic,
                "task": task,
                "track": track,
                "repo_head": repo_head,
                "manifest_sha": manifest_sha,
                "context_plan_sha": context_plan_sha,
                "message": message,
                "coverage": dict(coverage or {}),
                "created_at": now_iso(),
            },
        )

    @staticmethod
    def _validate_ref_name(name: str) -> str:
        clean = name.strip("/")
        if (
            not REF_RE.fullmatch(clean)
            or ".." in Path(clean).parts
            or any(part in {"", ".", ".."} for part in Path(clean).parts)
        ):
            raise ValueError(f"invalid ref name: {name}")
        return clean

    def ref_path(self, name: str) -> Path:
        clean = self._validate_ref_name(name)
        path = (self.refs / clean).resolve(strict=False)
        if not _inside(path, self.refs.resolve(strict=False)):
            raise ValueError(f"ref escapes store: {name}")
        return path

    def read_ref(self, name: str) -> str | None:
        path = self.ref_path(name)
        if not path.is_file():
            return None
        sha = path.read_text(encoding="utf-8").strip()
        if not SHA_RE.fullmatch(sha):
            raise ValueError(f"invalid ref target: {name}")
        return sha

    def update_ref(
        self,
        name: str,
        sha: str,
        *,
        expected_old: str | None | object = _UNSET,
        immutable: bool = False,
    ) -> None:
        self.get_object(sha)
        path = self.ref_path(name)
        lock_path = self.root / "locks" / (
            hashlib.sha256(f"ref:{name}".encode("utf-8")).hexdigest() + ".lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            current = self.read_ref(name)
            if immutable and current is not None and current != sha:
                raise ValueError(f"immutable ref already exists: {name}")
            if expected_old is not _UNSET and current != expected_old:
                raise ValueError(
                    f"ref changed: {name}: expected {expected_old}, got {current}"
                )
            self._atomic_write(path, f"{sha}\n".encode())

    def create_gate_tag(
        self,
        name: str,
        target: str,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create an immutable approval tag only from a human-bound receipt."""
        errors = list(validate_receipt(receipt)["errors"])
        evidence = validate_evidence_bundle(receipt, root=self.repo_root)
        errors.extend(evidence["errors"])
        if receipt.get("status") not in {"approved", "valid"}:
            errors.append("gate_not_approved")
        if not receipt.get("phrase"):
            errors.append("missing:phrase")
        actor = str(receipt.get("approved_by") or "")
        if not actor or actor.lower() in {"agent", "openclaw", "claude-code", "canvas", "tool"}:
            errors.append("approval_actor_not_human")
        for field in (
            "approved_at",
            "source_ref",
            "approved_content_sha",
            "manifest_sha",
            "context_plan_sha",
        ):
            if not receipt.get(field):
                errors.append(f"missing:{field}")
        if not SHA_RE.fullmatch(str(receipt.get("approved_content_sha") or "")):
            errors.append("invalid:approved_content_sha")
        if receipt.get("approved_content_sha") != evidence.get(
            "expected_output_sha"
        ):
            errors.append("approved_content_sha_not_evidence_bundle")
        if errors:
            raise ValueError(f"invalid gate tag receipt: {errors}")
        target_sha = self.read_ref(target) or target
        target_commit = self.get_object(target_sha, "commit")["data"]
        receipt_sha = self.put_blob(dict(receipt))
        tree = self.put_tree(
            {
                "parent-tree": target_commit["tree"],
                "gate-receipt": receipt_sha,
            }
        )
        commit = self.put_commit(
            tree,
            parents=[target_sha],
            actor=actor,
            topic=target_commit.get("topic"),
            task="human_gate",
            track=target_commit.get("track") or "process",
            repo_head=target_commit.get("repo_head"),
            manifest_sha=receipt.get("manifest_sha"),
            context_plan_sha=receipt.get("context_plan_sha"),
            message=f"human gate tag: {name}",
            coverage={"gate_receipt": receipt_sha},
        )
        self.update_ref(f"tags/gates/{name}", commit, immutable=True)
        return {
            "schema": "ndf-replay-gate-tag/v1",
            "tag": f"gates/{name}",
            "commit_sha": commit,
            "receipt_sha": receipt_sha,
        }

    def event_path(self, episode_id: str, branch: str = "main") -> Path:
        clean = self._validate_ref_name(episode_id)
        if "/" in clean:
            raise ValueError("episode id must be a single path segment")
        if branch == "main":
            return self.events / f"{clean}.jsonl"
        branch_name = self._validate_ref_name(branch)
        path = (self.events / clean / f"{branch_name}.jsonl").resolve(strict=False)
        episode_root = (self.events / clean).resolve(strict=False)
        if not _inside(path, episode_root):
            raise ValueError("event branch escapes episode")
        return path

    def read_events(self, episode_id: str, branch: str = "main") -> list[dict[str, Any]]:
        path = self.event_path(episode_id, branch)
        if not path.is_file():
            return []
        events = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event JSON at line {number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"event is not object at line {number}")
            events.append(value)
        return events

    def event_branches(self, episode_id: str) -> list[str]:
        branches: list[str] = []
        if self.event_path(episode_id).is_file():
            branches.append("main")
        branch_root = self.events / self._validate_ref_name(episode_id)
        if branch_root.is_dir():
            branches.extend(
                path.relative_to(branch_root).with_suffix("").as_posix()
                for path in sorted(branch_root.rglob("*.jsonl"))
            )
        return branches

    def read_all_events(self, episode_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            branch: self.read_events(episode_id, branch)
            for branch in self.event_branches(episode_id)
        }

    def append_event(
        self,
        episode_id: str,
        *,
        kind: str,
        actor: str,
        payload_sha: str,
        topic: str | None,
        task: str,
        track: str,
        repo_head: str | None,
        manifest_sha: str | None,
        context_plan_sha: str | None,
        session_id: str | None = None,
        run_id: str | None = None,
        branch: str = "main",
        verified: bool = True,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown replay event kind: {kind}")
        self.get_object(payload_sha)
        self.initialize()
        path = self.event_path(episode_id, branch)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / "locks" / (
            hashlib.sha256(
                f"event:{episode_id}:{branch}".encode("utf-8")
            ).hexdigest()
            + ".lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            events = self.read_events(episode_id, branch)
            chain = validate_event_chain(events)
            if not chain["valid"]:
                raise ValueError(
                    f"cannot append to invalid event chain: {chain['errors']}"
                )
            event = chained_event(
                {
                    "schema": "ndf-replay-event/v1",
                    "seq": len(events) + 1,
                    "episode_id": episode_id,
                    "branch": branch,
                    "timestamp": now_iso(),
                    "kind": kind,
                    "actor": actor,
                    "session_id": session_id,
                    "run_id": run_id,
                    "topic": topic,
                    "task": task,
                    "track": track,
                    "payload_sha": payload_sha,
                    "repo_head": repo_head,
                    "manifest_sha": manifest_sha,
                    "context_plan_sha": context_plan_sha,
                    "semantic_status": (
                        "verified"
                        if verified and event_actor_valid(kind, actor)
                        else "unverified"
                    ),
                },
                previous_sha=chain["tip_sha"],
            )
            existing = path.read_bytes() if path.is_file() else b""
            self._atomic_write(
                path,
                existing + canonical_json_bytes(event) + b"\n",
            )
        return event

    def init_episode(
        self,
        *,
        topic: str | None,
        task: str,
        role: str,
        track: str,
        manifest: Mapping[str, Any] | None = None,
        episode_id: str | None = None,
    ) -> dict[str, Any]:
        identifier = episode_id or f"ep-{uuid.uuid4()}"
        if manifest:
            import ndf_context

            manifest_check = ndf_context.verify_manifest(
                manifest,
                root=self.repo_root,
            )
            if not manifest_check["valid"]:
                raise ValueError(
                    f"episode requires a verified manifest: {manifest_check['errors']}"
                )
            expected_identity = {
                "topic": manifest.get("topic"),
                "task": manifest.get("task"),
                "track": manifest.get("track"),
            }
            actual_identity = {"topic": topic, "task": task, "track": track}
            if actual_identity != expected_identity:
                raise ValueError(
                    "episode identity does not match manifest: "
                    f"expected={expected_identity} actual={actual_identity}"
                )
        payload = {
            "schema": "ndf-replay-episode/v1",
            "episode_id": identifier,
            "topic": topic,
            "task": task,
            "role": role,
            "track": track,
            "manifest_sha": (manifest or {}).get("manifest_sha"),
            "created_at": now_iso(),
        }
        entries = {"episode": self.put_blob(payload)}
        if manifest:
            entries["manifest"] = self.put_blob(dict(manifest))
        tree = self.put_tree(entries)
        commit = self.put_commit(
            tree,
            actor=role,
            topic=topic,
            task=task,
            track=track,
            repo_head=(manifest or {}).get("workspace", {}).get("repo_head"),
            manifest_sha=(manifest or {}).get("manifest_sha"),
            context_plan_sha=None,
            message="episode init",
            coverage={"events": "initialized"},
        )
        self.update_ref(f"episodes/{identifier}/HEAD", commit)
        self.update_ref(f"episodes/{identifier}/BASE", commit, immutable=True)
        self.update_ref(f"branches/{identifier}/main", commit)
        if topic:
            self.update_ref(f"topics/{topic}/current", commit)
        event = self.append_event(
            identifier,
            kind="intent.received",
            actor=role,
            payload_sha=entries["episode"],
            topic=topic,
            task=task,
            track=track,
            repo_head=(manifest or {}).get("workspace", {}).get("repo_head"),
            manifest_sha=(manifest or {}).get("manifest_sha"),
            context_plan_sha=None,
        )
        return {
            "schema": "ndf-replay-episode-init/v1",
            "episode_id": identifier,
            "commit_sha": commit,
            "event_sha": event["event_sha"],
        }

    def commit_events(
        self,
        episode_id: str,
        *,
        message: str,
        actor: str = "tool",
        branch: str = "main",
        coverage: Mapping[str, Any] | None = None,
    ) -> str:
        events = self.read_events(episode_id, branch)
        validation = validate_event_chain(events)
        if not validation["valid"]:
            raise ValueError(f"invalid event chain: {validation['errors']}")
        head_ref = f"episodes/{episode_id}/HEAD"
        branch_ref = f"branches/{episode_id}/{branch}"
        parent = self.read_ref(branch_ref)
        if parent is None:
            parent = self.read_ref(f"episodes/{episode_id}/BASE")
        if parent is None:
            raise ValueError(f"unknown episode: {episode_id}")
        entries: dict[str, str] = {}
        for event in events:
            sequence = int(event["seq"])
            entries[f"event-{sequence:08d}"] = self.put_blob(event)
            entries[f"payload-{sequence:08d}"] = str(event["payload_sha"])
        entries["event-chain"] = self.put_blob(
            {
                "schema": "ndf-replay-event-chain/v1",
                "episode_id": episode_id,
                "branch": branch,
                "count": validation["count"],
                "tip_sha": validation["tip_sha"],
            }
        )
        tree = self.put_tree(entries)
        last = events[-1] if events else {}
        commit = self.put_commit(
            tree,
            parents=[parent],
            actor=actor,
            topic=last.get("topic"),
            task=str(last.get("task") or "unknown"),
            track=str(last.get("track") or "unknown"),
            repo_head=last.get("repo_head"),
            manifest_sha=last.get("manifest_sha"),
            context_plan_sha=last.get("context_plan_sha"),
            message=message,
            coverage={
                "event_count": len(events),
                "event_tip": validation["tip_sha"],
                **dict(coverage or {}),
            },
        )
        self.update_ref(branch_ref, commit, expected_old=self.read_ref(branch_ref))
        if branch == "main":
            self.update_ref(head_ref, commit, expected_old=self.read_ref(head_ref))
        return commit

    def checkpoint(
        self,
        episode_id: str,
        *,
        summary: str,
        manifest_sha: str | None,
        plan_sha: str | None,
        open_decisions: Iterable[str] = (),
        resolved_decisions: Iterable[str] = (),
        summary_provenance: Mapping[str, Any] | None = None,
        branch: str = "main",
    ) -> str:
        if not manifest_sha or not plan_sha:
            raise ValueError("checkpoint requires manifest_sha and plan_sha")
        manifest_blob, manifest = self.find_blob(
            schema="ndf-task-manifest/v1",
            semantic_field="manifest_sha",
            semantic_sha=manifest_sha,
        )
        plan_blob, plan = self.find_blob(
            schema=None,
            schema_prefix="ndf-context-plan",
            semantic_field="plan_sha",
            semantic_sha=plan_sha,
        )
        # Role plan schemas vary, so fall back to a type-neutral scan.
        if (
            plan.get("plan_sha") != plan_sha
            or not str(plan.get("schema") or "").startswith("ndf-context-plan")
        ):
            raise ValueError("checkpoint plan SHA mismatch")
        import ndf_context

        policy = manifest.get("compiler_policy") or {}
        recompiled_manifest = ndf_context.create_manifest(
            root=self.repo_root,
            topic=manifest.get("topic"),
            task=str(manifest.get("task")),
            track=str(manifest.get("track")),
            business_goal=str(manifest.get("business_goal") or ""),
            seed_ids=policy.get("requested_seed_ids", []),
            depth=int(policy.get("depth", 2)),
            node_budget=int(policy.get("node_budget", 80)),
            byte_budget=int(policy.get("byte_budget", 256_000)),
        )
        if recompiled_manifest.get("manifest_sha") != manifest_sha:
            raise ValueError("checkpoint manifest drift; recompile context first")
        recompiled_plan = ndf_context.role_plan(
            recompiled_manifest,
            role=str(plan.get("role")),
        )
        if recompiled_plan.get("plan_sha") != plan_sha:
            raise ValueError("checkpoint role plan drift; recompile context first")
        verification = ndf_context.verify_plan(
            plan,
            root=self.repo_root,
            manifest=manifest,
            require_manifest=True,
        )
        if not verification["valid"]:
            raise ValueError(f"checkpoint context verification failed: {verification['errors']}")
        events = self.read_events(episode_id, branch)
        validation = validate_event_chain(events)
        if not validation["valid"]:
            raise ValueError(f"invalid event chain: {validation['errors']}")
        all_branch_events = self.read_all_events(episode_id)
        branch_coverage = {
            name: validate_event_chain(values)
            for name, values in all_branch_events.items()
        }
        if not branch_coverage or any(
            not value["valid"] for value in branch_coverage.values()
        ):
            raise ValueError("checkpoint requires all Episode branch chains valid")
        retained_branch_heads = [
            value
            for name in all_branch_events
            if (value := self.read_ref(f"branches/{episode_id}/{name}"))
        ]
        summary_blob = self.put_blob(
            summary,
            media_type="text/plain",
            sensitivity="sensitive",
        )
        provenance = {
            "schema": "ndf-summary-provenance/v1",
            "producer": "human-or-tool",
            "model": None,
            **dict(summary_provenance or {}),
        }
        provenance_blob = self.put_blob(provenance)
        previous_checkpoint = next(
            (
                event.get("payload_sha")
                for event in reversed(events)
                if event.get("kind") == "compaction.checkpoint"
            ),
            None,
        )
        checkpoint = {
            "schema": "ndf-replay-checkpoint/v1",
            "episode_id": episode_id,
            "covered_seq": [1, len(events)],
            "covered_branches": {
                name: {
                    "count": value["count"],
                    "tip_sha": value["tip_sha"],
                }
                for name, value in sorted(branch_coverage.items())
            },
            "raw_events_digest": canonical_json_sha(all_branch_events),
            "event_tip_sha": validation["tip_sha"],
            "parent_checkpoint": previous_checkpoint,
            "manifest_sha": manifest_sha,
            "context_plan_sha": plan_sha,
            "recompiled_manifest_sha": recompiled_manifest["manifest_sha"],
            "recompiled_context_plan_sha": recompiled_plan["plan_sha"],
            "retained_object_refs": [
                manifest_blob,
                plan_blob,
                *sorted(set(retained_branch_heads)),
            ],
            "summary_blob": summary_blob,
            "summary_provenance_blob": provenance_blob,
            "summary_navigation_only": True,
            "resolved_decisions": list(resolved_decisions),
            "open_decisions": list(open_decisions),
            "gate_states": manifest.get("human_gates"),
            "context_verification": verification,
            "created_at": now_iso(),
        }
        payload_sha = self.put_blob(checkpoint)
        last = events[-1] if events else {}
        self.append_event(
            episode_id,
            kind="compaction.checkpoint",
            actor="tool",
            payload_sha=payload_sha,
            topic=last.get("topic"),
            task=str(last.get("task") or "checkpoint"),
            track=str(last.get("track") or "process"),
            repo_head=last.get("repo_head"),
            manifest_sha=manifest_sha,
            context_plan_sha=plan_sha,
            branch=branch,
        )
        return self.commit_events(
            episode_id,
            message="compaction checkpoint",
            branch=branch,
            coverage={"checkpoint_context_reverified": True},
        )

    def merge(
        self,
        episode_id: str,
        left: str,
        right: str,
        *,
        message: str,
        actor: str = "tool",
    ) -> str:
        left_sha = self.read_ref(left) or left
        right_sha = self.read_ref(right) or right
        left_commit = self.get_object(left_sha, "commit")["data"]
        right_commit = self.get_object(right_sha, "commit")["data"]
        left_audit = self.audit(left_sha, strict=True)
        right_audit = self.audit(right_sha, strict=True)
        if not left_audit["valid"] or not right_audit["valid"]:
            raise ValueError(
                "merge requires semantically verified parent histories: "
                f"left={left_audit['join_gaps'] + left_audit.get('semantic_gaps', [])}; "
                f"right={right_audit['join_gaps'] + right_audit.get('semantic_gaps', [])}"
            )
        if (
            not left_commit.get("manifest_sha")
            or left_commit.get("manifest_sha") != right_commit.get("manifest_sha")
        ):
            raise ValueError("merge parents must share one manifest_sha")
        tree = self.put_tree(
            {
                "left": left_commit["tree"],
                "right": right_commit["tree"],
                "merge-metadata": self.put_blob(
                    {
                        "schema": "ndf-replay-merge/v1",
                        "left": left_sha,
                        "right": right_sha,
                        "verified_objects_only": True,
                        "left_audit": left_audit["valid"],
                        "right_audit": right_audit["valid"],
                    }
                ),
            }
        )
        commit = self.put_commit(
            tree,
            parents=[left_sha, right_sha],
            actor=actor,
            topic=left_commit.get("topic") or right_commit.get("topic"),
            task="merge",
            track=left_commit.get("track") or right_commit.get("track") or "process",
            repo_head=right_commit.get("repo_head") or left_commit.get("repo_head"),
            manifest_sha=left_commit.get("manifest_sha") or right_commit.get("manifest_sha"),
            context_plan_sha=None,
            message=message,
            coverage={
                "left": left_commit.get("coverage", {}),
                "right": right_commit.get("coverage", {}),
            },
        )
        head_ref = f"episodes/{episode_id}/HEAD"
        self.update_ref(head_ref, commit, expected_old=self.read_ref(head_ref))
        main_ref = f"branches/{episode_id}/main"
        self.update_ref(main_ref, commit, expected_old=self.read_ref(main_ref))
        topic = left_commit.get("topic") or right_commit.get("topic")
        if topic:
            self.update_ref(f"topics/{topic}/current", commit)
        return commit

    def walk_commits(self, start: str) -> list[tuple[str, dict[str, Any]]]:
        sha = self.read_ref(start) or start
        output: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def visit(current: str) -> None:
            if current in seen:
                return
            if current in visiting:
                raise ValueError(f"commit parent cycle: {current}")
            visiting.add(current)
            commit = self.get_object(current, "commit")["data"]
            for parent in commit.get("parents", []):
                visit(str(parent))
            visiting.remove(current)
            seen.add(current)
            output.append((current, commit))

        visit(sha)
        return output

    def diff(self, left: str, right: str) -> dict[str, Any]:
        left_sha = self.read_ref(left) or left
        right_sha = self.read_ref(right) or right
        left_commit = self.get_object(left_sha, "commit")["data"]
        right_commit = self.get_object(right_sha, "commit")["data"]
        left_tree = self.get_object(left_commit["tree"], "tree")["data"]["entries"]
        right_tree = self.get_object(right_commit["tree"], "tree")["data"]["entries"]
        names = sorted(set(left_tree) | set(right_tree))
        facet_names = (
            "manifest",
            "context",
            "events",
            "observations",
            "results",
            "verification",
        )

        def semantic_objects(commit_sha: str) -> dict[str, dict[str, str]]:
            facets: dict[str, dict[str, str]] = {
                name: {} for name in facet_names
            }
            reconstruction = self.reconstruct(commit_sha, "R0")
            for item in reconstruction.get("recorded_objects", []):
                obj = item.get("object", {})
                data = obj.get("data", {})
                value = data.get("value") if obj.get("type") == "blob" else data
                schema = (
                    str(value.get("schema") or "")
                    if isinstance(value, Mapping)
                    else str(data.get("schema") or "")
                )
                facet = None
                semantic_key = item["sha"]
                if schema == "ndf-task-manifest/v1":
                    facet = "manifest"
                    semantic_key = str(value.get("manifest_sha") or item["sha"])
                elif schema.startswith("ndf-context-plan"):
                    facet = "context"
                    semantic_key = str(value.get("plan_sha") or item["sha"])
                elif schema == "ndf-replay-event/v1":
                    facet = "events"
                    semantic_key = str(value.get("event_sha") or item["sha"])
                elif obj.get("type") in {"tool-cassette", "model-turn"}:
                    facet = "observations"
                    semantic_key = str(
                        data.get("invocation_id")
                        or data.get("turn_id")
                        or item["sha"]
                    )
                elif schema in {
                    "ndf-agent-completion/v1",
                    "ndf-runtime-mutation-proof/v1",
                    "ndf-replay-r2-expectations/v1",
                }:
                    facet = "results"
                    semantic_key = str(
                        value.get("run_id") or value.get("proof_sha") or item["sha"]
                    )
                elif schema in {
                    "ndf-replay-sandbox/v1",
                    "ndf-close-evidence/v1",
                    "ndf-projection-receipt/v2",
                    "ndf-context-verification/v1",
                }:
                    facet = "verification"
                    semantic_key = str(
                        value.get("profile_sha")
                        or value.get("output_sha")
                        or value.get("plan_sha")
                        or item["sha"]
                    )
                if facet:
                    facets[facet][semantic_key] = str(item["sha"])
            return facets

        left_facets = semantic_objects(left_sha)
        right_facets = semantic_objects(right_sha)
        facet_diff = {}
        for facet in facet_names:
            left_values = left_facets[facet]
            right_values = right_facets[facet]
            keys = sorted(set(left_values) | set(right_values))
            facet_diff[facet] = {
                "added": [
                    key for key in keys if key not in left_values
                ],
                "removed": [
                    key for key in keys if key not in right_values
                ],
                "changed": [
                    key
                    for key in keys
                    if key in left_values
                    and key in right_values
                    and left_values[key] != right_values[key]
                ],
                "left_shas": left_values,
                "right_shas": right_values,
            }
        return {
            "schema": "ndf-replay-diff/v1",
            "left": left_sha,
            "right": right_sha,
            "added": [name for name in names if name not in left_tree],
            "removed": [name for name in names if name not in right_tree],
            "changed": [
                name
                for name in names
                if name in left_tree
                and name in right_tree
                and left_tree[name] != right_tree[name]
            ],
            "facets": facet_diff,
        }

    def audit(self, commit_or_ref: str, *, strict: bool = True) -> dict[str, Any]:
        fsck = self.fsck()
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        coverage_gaps: list[str] = []
        join_gaps: list[str] = []
        semantic_gaps: list[str] = []
        seen_events: set[str] = set()
        observed_events: list[
            tuple[str, str, dict[str, Any], dict[str, Any], Any]
        ] = []
        if strict:
            import ndf_context
        for commit_sha, historical in self.walk_commits(sha):
            for key, value in historical.get("coverage", {}).items():
                if value is None or (
                    isinstance(value, str)
                    and value in {"unknown", "completion_only", "messages_only"}
                ):
                    coverage_gaps.append(f"{commit_sha}:{key}:{value}")
            manifest_sha = historical.get("manifest_sha")
            plan_sha = historical.get("context_plan_sha")
            manifest: dict[str, Any] | None = None
            plan: dict[str, Any] | None = None
            if manifest_sha:
                try:
                    _, manifest = self.find_blob(
                        schema="ndf-task-manifest/v1",
                        semantic_field="manifest_sha",
                        semantic_sha=str(manifest_sha),
                    )
                    if strict:
                        manifest_check = ndf_context.verify_manifest_recorded(manifest)
                        if not manifest_check["valid"]:
                            semantic_gaps.append(
                                f"{commit_sha}:manifest_invalid:"
                                f"{canonical_json_sha(manifest_check['errors'])}"
                            )
                except ValueError:
                    join_gaps.append(f"{commit_sha}:manifest:{manifest_sha}")
            if plan_sha:
                try:
                    _, plan = self.find_blob(
                        schema=None,
                        schema_prefix="ndf-context-plan",
                        semantic_field="plan_sha",
                        semantic_sha=str(plan_sha),
                    )
                    if not str(plan.get("schema") or "").startswith(
                        "ndf-context-plan"
                    ):
                        raise ValueError("semantic plan object has wrong schema")
                    if manifest_sha and plan.get("manifest_sha") != manifest_sha:
                        join_gaps.append(f"{commit_sha}:plan_manifest_mismatch")
                    if strict and manifest is not None:
                        plan_check = ndf_context.verify_plan_recorded(
                            plan,
                            manifest=manifest,
                        )
                        if not plan_check["valid"]:
                            semantic_gaps.append(
                                f"{commit_sha}:plan_invalid:"
                                f"{canonical_json_sha(plan_check['errors'])}"
                            )
                except ValueError:
                    join_gaps.append(f"{commit_sha}:plan:{plan_sha}")
            if plan_sha and manifest is None:
                join_gaps.append(f"{commit_sha}:plan_without_manifest")
            tree_entries = self.get_object(
                str(historical["tree"]),
                "tree",
            )["data"].get("entries", {})
            for name, event_blob_sha in tree_entries.items():
                if (
                    not re.fullmatch(r"event-\d{8}", str(name))
                    or event_blob_sha in seen_events
                ):
                    continue
                seen_events.add(str(event_blob_sha))
                event_blob = self.get_object(str(event_blob_sha), "blob")["data"]
                replay_event = event_blob.get("value")
                if not isinstance(replay_event, dict):
                    semantic_gaps.append(f"{commit_sha}:{name}:event_not_json")
                    continue
                payload = self.get_object(str(replay_event.get("payload_sha") or ""))
                payload_value = payload.get("data", {}).get("value")
                kind = replay_event.get("kind")
                observed_events.append(
                    (commit_sha, str(name), replay_event, payload, payload_value)
                )
                if not event_actor_valid(str(kind or ""), str(replay_event.get("actor") or "")):
                    semantic_gaps.append(f"{commit_sha}:{name}:invalid_event_actor")
                if replay_event.get("semantic_status") != "verified":
                    semantic_gaps.append(f"{commit_sha}:{name}:unverified_event")
                if kind == "gate.approved":
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-gate-receipt/v1"
                        or not validate_receipt(payload_value)["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_gate_receipt")
                elif kind == "dispatch.preflight":
                    invalid_dispatch = (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("safe_to_dispatch") is not True
                        or payload_value.get("manifest_sha")
                        != replay_event.get("manifest_sha")
                        or payload_value.get("plan_sha")
                        != replay_event.get("context_plan_sha")
                        or payload_value.get("task") != replay_event.get("task")
                        or payload_value.get("track") != replay_event.get("track")
                    )
                    if not invalid_dispatch and replay_event.get(
                        "context_plan_sha"
                    ):
                        try:
                            _, dispatch_plan = self.find_blob(
                                schema=None,
                                schema_prefix="ndf-context-plan",
                                semantic_field="plan_sha",
                                semantic_sha=str(
                                    replay_event["context_plan_sha"]
                                ),
                            )
                            write_root = str(
                                payload_value.get("allowed_write_root") or ""
                            ).strip("/")
                            planned_roots = [
                                str(root).strip("/")
                                for root in dispatch_plan.get(
                                    "privileges", {}
                                ).get("allowed_write_roots", [])
                            ]
                            if write_root and not any(
                                write_root == root
                                or write_root.startswith(f"{root}/")
                                for root in planned_roots
                            ):
                                invalid_dispatch = True
                        except ValueError:
                            invalid_dispatch = True
                    if invalid_dispatch:
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_dispatch_pack")
                elif kind in {"acp.start", "lease.acquired", "lease.released"}:
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-runtime-lease/v1"
                        or not validate_receipt(payload_value)["valid"]
                        or payload_value.get("manifest_sha")
                        != replay_event.get("manifest_sha")
                        or payload_value.get("context_plan_sha")
                        != replay_event.get("context_plan_sha")
                        or not validate_recorded_runtime_lease_binding(
                            payload_value
                        )["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_runtime_lease")
                elif kind == "close.receipt":
                    if (
                        not isinstance(payload_value, Mapping)
                        or payload_value.get("schema") != "ndf-close-evidence/v1"
                        or not validate_receipt(payload_value)["valid"]
                    ):
                        semantic_gaps.append(f"{commit_sha}:{name}:invalid_close_receipt")
                elif kind in {"acp.complete", "openclaw.response"}:
                    if not isinstance(payload_value, Mapping):
                        semantic_gaps.append(f"{commit_sha}:{name}:completion_not_json")
                        continue
                    schema = payload_value.get("schema")
                    if schema == "ndf-agent-message/v1":
                        if any(
                            field not in payload_value
                            for field in (
                                "task",
                                "track",
                                "manifest_sha",
                                "context_plan_sha",
                                "session_id",
                                "run_id",
                                "message",
                            )
                        ):
                            semantic_gaps.append(
                                f"{commit_sha}:{name}:invalid_agent_message"
                            )
                    elif schema == "ndf-agent-completion/v1":
                        required_completion = (
                            "task",
                            "track",
                            "base_sha",
                            "repo_head",
                            "manifest_sha",
                            "context_plan_sha",
                            "changed_files",
                            "changed_file_shas",
                            "reproduce_commands",
                            "evidence_paths",
                            "evidence_bundle_sha",
                            "git_commit",
                            "post_check_receipts",
                            "result",
                            "run_id",
                            "session_id",
                        )
                        changed_files = payload_value.get("changed_files")
                        changed_shas = payload_value.get("changed_file_shas")
                        valid_changed = bool(
                            isinstance(changed_files, list)
                            and isinstance(changed_shas, Mapping)
                            and set(changed_files) == set(changed_shas)
                            and all(
                                SHA_RE.fullmatch(str(value or ""))
                                for value in changed_shas.values()
                            )
                        )
                        event_bound = all(
                            payload_value.get(field) == replay_event.get(event_field)
                            for field, event_field in (
                                ("task", "task"),
                                ("track", "track"),
                                ("manifest_sha", "manifest_sha"),
                                ("context_plan_sha", "context_plan_sha"),
                                ("run_id", "run_id"),
                                ("session_id", "session_id"),
                            )
                        )
                        evidence_valid = bool(
                            SHA_RE.fullmatch(
                                str(payload_value.get("evidence_bundle_sha") or "")
                            )
                            and isinstance(payload_value.get("evidence_paths"), list)
                        )
                        post_checks_valid = bool(
                            isinstance(
                                payload_value.get("post_check_receipts"), list
                            )
                            and payload_value.get("post_check_receipts")
                            and all(
                                isinstance(receipt, Mapping)
                                and receipt.get("result")
                                in {"success", "passed", "completed"}
                                and isinstance(receipt.get("verifier"), Mapping)
                                and Path(
                                    str(receipt["verifier"].get("path") or "")
                                ).is_absolute()
                                and isinstance(
                                    receipt["verifier"].get("argv"), list
                                )
                                and SHA_RE.fullmatch(
                                    str(
                                        receipt["verifier"].get("version_sha")
                                        or ""
                                    )
                                )
                                is not None
                                and receipt["verifier"].get("exit_code") == 0
                                and bool(
                                    receipt["verifier"].get("output_schema")
                                )
                                for receipt in payload_value.get(
                                    "post_check_receipts", []
                                )
                            )
                        )
                        mutation_proof = payload_value.get("mutation_proof")
                        mutation_valid = bool(
                            isinstance(mutation_proof, Mapping)
                            and mutation_proof.get("schema")
                            == "ndf-runtime-mutation-proof/v1"
                            and mutation_proof.get("proof_sha")
                            == canonical_json_sha(
                                {
                                    key: value
                                    for key, value in mutation_proof.items()
                                    if key != "proof_sha"
                                }
                            )
                            and set(mutation_proof.get("actual_mutations", []))
                            == set(payload_value.get("changed_files", []))
                        )
                        if (
                            any(field not in payload_value for field in required_completion)
                            or payload_value.get("result")
                            not in {"success", "passed", "completed"}
                            or not valid_changed
                            or not evidence_valid
                            or not post_checks_valid
                            or not mutation_valid
                            or not event_bound
                        ):
                            semantic_gaps.append(
                                f"{commit_sha}:{name}:invalid_agent_completion"
                            )
                    else:
                        semantic_gaps.append(
                            f"{commit_sha}:{name}:unsupported_agent_response"
                        )
                elif kind == "verification.completed":
                    if (
                        isinstance(payload_value, Mapping)
                        and payload_value.get("schema") == "ndf-replay-sandbox/v1"
                        and payload_value.get("state") == "equivalent"
                        and (
                            payload_value.get("executed") is not True
                            or not payload_value.get("output_checks")
                            or not all(
                                check.get("matches") is True
                                for check in payload_value.get("output_checks", [])
                            )
                            or payload_value.get("write_violations")
                        )
                    ):
                        semantic_gaps.append(
                            f"{commit_sha}:{name}:invalid_r2_equivalence"
                        )
        branch_state: dict[str, dict[str, bool]] = {}
        for commit_sha, name, event, _, _ in sorted(
            observed_events,
            key=lambda item: (
                str(item[2].get("branch") or "main"),
                int(item[2].get("seq") or 0),
            ),
        ):
            branch = str(event.get("branch") or "main")
            state = branch_state.setdefault(
                branch,
                {
                    "compiled": False,
                    "verified": False,
                    "dispatch": False,
                    "lease": False,
                    "completion": False,
                },
            )
            kind = event.get("kind")
            if kind == "context.compiled":
                state["compiled"] = True
            elif kind == "context.verified":
                if not state["compiled"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:context_verified_without_compile"
                    )
                state["verified"] = True
            elif kind in {"dispatch.preflight", "dispatch.blocked"}:
                if kind == "dispatch.preflight" and not state["verified"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:dispatch_without_context_verify"
                    )
                if kind == "dispatch.preflight":
                    state["dispatch"] = True
            elif kind == "lease.acquired":
                if not state["dispatch"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:lease_without_dispatch"
                    )
                state["lease"] = True
            elif kind in {"acp.complete", "openclaw.response"}:
                if kind == "acp.complete" and not state["lease"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:completion_without_acquired_lease"
                    )
                if kind == "acp.complete":
                    state["completion"] = True
            elif kind == "lease.released":
                if not state["completion"]:
                    semantic_gaps.append(
                        f"{commit_sha}:{name}:release_without_completion"
                    )
        for branch, state in branch_state.items():
            if state["compiled"] and not state["verified"]:
                semantic_gaps.append(f"{branch}:compiled_context_not_verified")

        dispatches = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "dispatch.preflight"
            and isinstance(value, Mapping)
            and value.get("safe_to_dispatch") is True
        ]
        leases = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "lease.acquired"
            and isinstance(value, Mapping)
            and value.get("result") == "active"
        ]
        releases = [
            (event, value)
            for _, _, event, _, value in observed_events
            if event.get("kind") == "lease.released"
            and isinstance(value, Mapping)
            and value.get("result") in {"released", "expired", "failed"}
        ]
        for event, lease in leases:
            joined_pack = next(
                (
                    (dispatch_event, pack)
                    for dispatch_event, pack in dispatches
                    if dispatch_event.get("task") == event.get("task")
                    and dispatch_event.get("manifest_sha")
                    == event.get("manifest_sha")
                    and dispatch_event.get("context_plan_sha")
                    == event.get("context_plan_sha")
                    and lease.get("pack_sha")
                    == dispatch_event.get("payload_sha")
                ),
                None,
            )
            if joined_pack is None:
                semantic_gaps.append(
                    f"{event.get('run_id')}:lease_without_dispatch_pack"
                )
                continue
            dispatch_event, pack = joined_pack
            lease_check = validate_recorded_runtime_lease_binding(
                lease,
                expected={
                    "topic": event.get("topic"),
                    "task": event.get("task"),
                    "repo_head": event.get("repo_head"),
                    "base_sha": pack.get("base_sha"),
                    "plan_sha": event.get("context_plan_sha"),
                    "manifest_sha": event.get("manifest_sha"),
                    "allowed_write_root": pack.get("allowed_write_root"),
                    "pack_sha": dispatch_event.get("payload_sha"),
                    "episode_id": event.get("episode_id"),
                    "branch": lease.get("branch"),
                    "repo_root": str(self.repo_root),
                },
            )
            if not lease_check["valid"]:
                semantic_gaps.extend(
                    f"{event.get('run_id')}:lease:{error}"
                    for error in lease_check["errors"]
                )
        for event, released in releases:
            active_pair = next(
                (
                    (active_event, active)
                    for active_event, active in leases
                    if active_event.get("run_id") == event.get("run_id")
                    and active_event.get("session_id") == event.get("session_id")
                    and active_event.get("branch") == event.get("branch")
                    and int(active_event.get("seq") or 0)
                    < int(event.get("seq") or 0)
                ),
                None,
            )
            if active_pair is None or any(
                active_pair[1].get(field) != released.get(field)
                for field in (
                    "task",
                    "topic",
                    "base_sha",
                    "worktree",
                    "branch",
                    "allowed_write_root",
                    "pack_sha",
                    "manifest_sha",
                    "context_plan_sha",
                )
            ):
                semantic_gaps.append(
                    f"{event.get('run_id')}:invalid_lease_release_transition"
                )
        for commit_sha, name, event, _, value in observed_events:
            if event.get("kind") != "acp.complete" or not isinstance(value, Mapping):
                continue
            joined_dispatch = any(
                candidate.get("task") == event.get("task")
                and candidate.get("manifest_sha") == event.get("manifest_sha")
                and candidate.get("context_plan_sha")
                == event.get("context_plan_sha")
                for candidate, _ in dispatches
            )
            joined_lease = any(
                candidate.get("run_id") == event.get("run_id")
                and candidate.get("session_id") == event.get("session_id")
                and candidate.get("task") == event.get("task")
                and candidate.get("manifest_sha") == event.get("manifest_sha")
                and candidate.get("context_plan_sha")
                == event.get("context_plan_sha")
                for candidate, _ in leases
            )
            joined_release = any(
                candidate.get("run_id") == event.get("run_id")
                and candidate.get("session_id") == event.get("session_id")
                and candidate.get("task") == event.get("task")
                for candidate, _ in releases
            )
            if not joined_dispatch:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_dispatch")
            if not joined_lease:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_lease")
            if not joined_release:
                semantic_gaps.append(f"{commit_sha}:{name}:completion_without_lease_release")
        valid = fsck["valid"] and (
            not strict or (not join_gaps and not semantic_gaps)
        )
        current_errors: list[Any] = []
        current_manifest: dict[str, Any] | None = None
        current_plan: dict[str, Any] | None = None
        if strict:
            for _, candidate_commit in reversed(self.walk_commits(sha)):
                candidate_manifest_sha = candidate_commit.get("manifest_sha")
                candidate_plan_sha = candidate_commit.get("context_plan_sha")
                if candidate_manifest_sha and current_manifest is None:
                    try:
                        _, current_manifest = self.find_blob(
                            schema="ndf-task-manifest/v1",
                            semantic_field="manifest_sha",
                            semantic_sha=str(candidate_manifest_sha),
                        )
                    except ValueError:
                        pass
                if candidate_plan_sha and current_plan is None:
                    try:
                        _, current_plan = self.find_blob(
                            schema=None,
                            schema_prefix="ndf-context-plan",
                            semantic_field="plan_sha",
                            semantic_sha=str(candidate_plan_sha),
                        )
                    except ValueError:
                        pass
                if current_manifest is not None and current_plan is not None:
                    break
            if current_manifest is None:
                current_errors.append({"kind": "current_manifest_unavailable"})
            else:
                current_errors.extend(
                    ndf_context.verify_manifest_current(
                        current_manifest,
                        root=self.repo_root,
                    )["errors"]
                )
            if current_plan is None:
                current_errors.append({"kind": "current_plan_unavailable"})
            elif current_manifest is not None:
                current_errors.extend(
                    ndf_context.verify_plan(
                        current_plan,
                        root=self.repo_root,
                        manifest=current_manifest,
                        require_manifest=True,
                    )["errors"]
                )
        return {
            "schema": "ndf-replay-audit/v1",
            "level": "R0",
            "valid": valid,
            "historical_integrity": fsck["valid"],
            "historical_semantics": not join_gaps and not semantic_gaps,
            "current_restore_ready": not current_errors if strict else None,
            "current_dispatch_ready": not current_errors if strict else None,
            "current_readiness_errors": current_errors,
            "commit_sha": sha,
            "commit": commit,
            "coverage_gaps": sorted(set(coverage_gaps)),
            "join_gaps": sorted(set(join_gaps)),
            "semantic_gaps": sorted(set(semantic_gaps)),
            "fsck": fsck,
        }

    def reconstruct(self, commit_or_ref: str, level: str = "R1") -> dict[str, Any]:
        if level not in {"R0", "R1"}:
            raise ValueError("reconstruct supports R0 or R1")
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        commit = self.get_object(sha, "commit")["data"]
        recorded: list[dict[str, Any]] = []
        by_object: dict[str, dict[str, Any]] = {}
        commit_dag: list[dict[str, Any]] = []

        def visit_tree(
            tree_sha: str,
            *,
            commit_sha: str,
            parents: list[str],
            prefix: str = "",
            seen_trees: set[str] | None = None,
        ) -> None:
            local_seen = seen_trees if seen_trees is not None else set()
            if tree_sha in local_seen:
                return
            local_seen.add(tree_sha)
            entries = self.get_object(tree_sha, "tree")["data"]["entries"]
            for name, object_sha in sorted(entries.items()):
                obj = self.get_object(object_sha)
                qualified = f"{prefix}/{name}".strip("/")
                provenance = {
                    "commit_sha": commit_sha,
                    "parents": list(parents),
                    "path": qualified,
                }
                if object_sha not in by_object:
                    item = {
                        "name": qualified,
                        "sha": object_sha,
                        "object": obj,
                        "provenance": [provenance],
                    }
                    by_object[object_sha] = item
                    recorded.append(item)
                else:
                    by_object[object_sha]["provenance"].append(provenance)
                if obj.get("type") == "tree":
                    visit_tree(
                        object_sha,
                        commit_sha=commit_sha,
                        parents=parents,
                        prefix=qualified,
                        seen_trees=local_seen,
                    )

        for historical_sha, historical in self.walk_commits(sha):
            parents = [str(parent) for parent in historical.get("parents", [])]
            commit_dag.append(
                {
                    "commit_sha": historical_sha,
                    "parents": parents,
                    "tree": historical.get("tree"),
                    "actor": historical.get("actor"),
                    "task": historical.get("task"),
                    "manifest_sha": historical.get("manifest_sha"),
                    "context_plan_sha": historical.get("context_plan_sha"),
                }
            )
            visit_tree(
                str(historical["tree"]),
                commit_sha=historical_sha,
                parents=parents,
            )
        observations: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        observation_gaps: list[str] = []
        seen_observations: set[str] = set()
        seen_event_shas: set[str] = set()
        for item in recorded:
            obj = item["object"]
            data = obj.get("data", {})
            if obj.get("type") == "tool-cassette":
                if item["sha"] in seen_observations:
                    continue
                seen_observations.add(item["sha"])
                observations.append(
                    {
                        "kind": "tool",
                        "sha": item["sha"],
                        "cassette": data,
                        "stdout": self.get_object(data["stdout_blob"], "blob")[
                            "data"
                        ].get("value"),
                        "stderr": self.get_object(data["stderr_blob"], "blob")[
                            "data"
                        ].get("value"),
                    }
                )
                if data.get("replay_policy") not in {
                    "recorded-only",
                    "sandbox",
                    "live-readonly",
                }:
                    observation_gaps.append(
                        f"{item['sha']}:invalid_tool_replay_policy"
                    )
                if (
                    data.get("replay_policy") == "live-readonly"
                    and not data.get("external_resource_version")
                ):
                    observation_gaps.append(
                        f"{item['sha']}:unversioned_live_observation"
                    )
            elif obj.get("type") == "model-turn":
                if item["sha"] in seen_observations:
                    continue
                seen_observations.add(item["sha"])
                observations.append(
                    {
                        "kind": "model",
                        "sha": item["sha"],
                        "turn": data,
                        "user_message": self.get_object(
                            data["user_message_blob"], "blob"
                        )["data"].get("value"),
                        "assistant_response": self.get_object(
                            data["assistant_response_blob"], "blob"
                        )["data"].get("value"),
                    }
                )
                if not data.get("visible_system_surface_sha"):
                    observation_gaps.append(
                        f"{item['sha']}:missing_visible_prompt_surface"
                    )
            elif (
                obj.get("type") == "blob"
                and isinstance(data.get("value"), dict)
                and data["value"].get("schema") == "ndf-replay-event/v1"
            ):
                event = data["value"]
                event_sha = str(event.get("event_sha") or "")
                if event_sha and event_sha not in seen_event_shas:
                    seen_event_shas.add(event_sha)
                    timeline.append(event)
        return {
            "schema": "ndf-replay-reconstruction/v1",
            "level": level,
            "commit_sha": sha,
            "side_effects": False,
            "recorded_objects": recorded,
            "commit_dag": commit_dag,
            "merge_parents": [
                item for item in commit_dag if len(item.get("parents", [])) > 1
            ],
            "timeline": sorted(
                timeline,
                key=lambda item: (
                    str(item.get("branch") or ""),
                    int(item.get("seq") or 0),
                    str(item.get("event_sha") or ""),
                ),
            ),
            "observations": observations,
            "observation_replay_valid": (
                not observation_gaps
                and (level == "R0" or bool(observations))
            ),
            "observation_gaps": (
                observation_gaps
                if observations
                else (["recorded_observation_surface_missing"] if level == "R1" else [])
            ),
            "coverage": commit.get("coverage", {}),
        }

    def sandbox_replay(
        self,
        commit_or_ref: str,
        profile: Mapping[str, Any],
        *,
        execute: bool = False,
    ) -> dict[str, Any]:
        """Validate or execute an R2 profile in a disposable git worktree."""
        if not profile.get("sandbox") or profile.get("network") not in {False, "none"}:
            raise ValueError("R2 requires sandbox=true and network=false|none")
        commands = profile.get("commands", [])
        if not isinstance(commands, list) or not all(
            isinstance(command, list)
            and command
            and all(isinstance(part, str) for part in command)
            for command in commands
        ):
            raise ValueError("R2 profile commands must be non-empty argv arrays")
        adapter = profile.get("adapter", [])
        if not isinstance(adapter, list) or not all(isinstance(part, str) for part in adapter):
            raise ValueError("R2 profile adapter must be an argv array")
        if execute and not adapter:
            raise ValueError("R2 execution with network disabled requires an isolation adapter")
        if execute:
            if not profile.get("confirm_cost") or not profile.get(
                "confirm_side_effects"
            ):
                raise ValueError("R2 execution requires explicit cost and side-effect confirmation")
            adapter_name = Path(adapter[0]).name
            if len(adapter) != 1 or adapter_name not in {"bwrap", "bubblewrap"}:
                raise ValueError("R2 execution requires the managed bwrap adapter")
            if not (
                Path(adapter[0]).is_file()
                or shutil.which(adapter[0])
            ):
                raise ValueError("R2 isolation adapter is unavailable")
        sha = self.read_ref(commit_or_ref) or commit_or_ref
        audit = self.audit(sha, strict=execute)
        if execute and not audit["valid"]:
            raise ValueError(
                f"R2 requires a strict verified episode: "
                f"{audit['join_gaps'] + audit.get('semantic_gaps', [])}"
            )
        if execute and audit.get("current_restore_ready") is not True:
            raise ValueError(
                "R2 current restore is not ready: "
                f"{audit.get('current_readiness_errors', [])}"
            )
        commit = self.get_object(sha, "commit")["data"]
        repo_head = commit.get("repo_head")
        if not repo_head:
            raise ValueError("R2 commit has no bound repo_head")
        target = profile.get("target")
        manifest_sha: str | None = None
        plan_sha: str | None = None
        run_id: str | None = None
        role: str | None = None
        manifest: dict[str, Any] | None = None
        plan: dict[str, Any] | None = None
        if execute or target is not None:
            if not isinstance(target, Mapping):
                raise ValueError("R2 profile requires exact target binding")
            required_target = (
                "run_id",
                "role",
                "manifest_sha",
                "plan_sha",
                "env_allowlist_fingerprint",
                "cwd",
                "tool_runtime_version",
            )
            missing_target = [
                field for field in required_target if not target.get(field)
            ]
            if missing_target:
                raise ValueError(f"R2 target missing fields: {missing_target}")
            run_id = str(target["run_id"])
            role = str(target["role"])
            manifest_sha = str(target["manifest_sha"])
            plan_sha = str(target["plan_sha"])
            _, manifest = self.find_blob(
                schema="ndf-task-manifest/v1",
                semantic_field="manifest_sha",
                semantic_sha=manifest_sha,
            )
            _, plan = self.find_blob(
                schema=None,
                schema_prefix="ndf-context-plan",
                semantic_field="plan_sha",
                semantic_sha=plan_sha,
            )
            if plan.get("role") != role:
                raise ValueError("R2 target role does not match recorded plan")
            if plan.get("manifest_sha") != manifest_sha:
                raise ValueError("R2 target manifest does not match recorded plan")
        result: dict[str, Any] = {
            "schema": "ndf-replay-sandbox/v1",
            "level": "R2",
            "commit_sha": sha,
            "repo_head": repo_head,
            "audit": audit,
            "profile_sha": canonical_json_sha(profile),
            "profile": _json_copy(profile),
            "executed": False,
            "state": "validated_profile",
            "commands": [],
            "changed_paths": [],
            "output_checks": [],
        }
        if not execute:
            return result
        adapter_probe = subprocess.run(
            [
                adapter[0],
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
                "--",
                "/bin/true",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        result["adapter_probe"] = {
            "exit_code": adapter_probe.returncode,
            "stdout_sha": canonical_json_sha(adapter_probe.stdout),
            "stderr_sha": canonical_json_sha(adapter_probe.stderr),
        }
        if adapter_probe.returncode != 0:
            result["state"] = "environment_blocked"
            result["environment_blocker"] = adapter_probe.stderr.strip()
            return result
        if not commands:
            raise ValueError("R2 execution requires at least one recorded command")
        expected_outputs = profile.get("expected_outputs", [])
        if not isinstance(expected_outputs, list) or not expected_outputs:
            raise ValueError("R2 equivalence requires at least one expected output")
        assert target is not None
        assert run_id is not None
        assert manifest_sha is not None
        assert plan_sha is not None
        assert manifest is not None
        assert plan is not None
        allowed_roots = [
            str(value).strip("/")
            for value in profile.get("allowed_write_roots", [])
            if str(value).strip("/")
        ]
        planned_roots = [
            str(value).strip("/")
            for value in plan.get("privileges", {}).get("allowed_write_roots", [])
            if str(value).strip("/")
        ]
        if any(
            not any(
                root == planned or root.startswith(f"{planned}/")
                for planned in planned_roots
            )
            for root in allowed_roots
        ):
            raise ValueError("R2 write roots exceed recorded context privileges")
        reconstruction = self.reconstruct(sha, "R1")
        recorded_completions = [
            item["object"]["data"]["value"]
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(item.get("object", {}).get("data", {}).get("value"), dict)
            and item["object"]["data"]["value"].get("schema")
            == "ndf-agent-completion/v1"
        ]
        exact_expectations = {
            str(expected.get("path") or ""): str(expected.get("sha256") or "")
            for expected in expected_outputs
            if expected.get("comparison") != "epsilon"
        }
        matching_completions = [
            completion
            for completion in recorded_completions
            if str(completion.get("run_id") or "") == run_id
            and completion.get("manifest_sha") == manifest_sha
            and completion.get("context_plan_sha") == plan_sha
            and {
                str(path): str(file_sha)
                for path, file_sha in completion.get(
                    "changed_file_shas", {}
                ).items()
            }
            == exact_expectations
        ]
        matching_run_ids = {
            str(completion.get("run_id"))
            for completion in matching_completions
            if completion.get("run_id")
        }
        if matching_run_ids != {run_id}:
            raise ValueError(
                "R2 expected outputs are not the complete output set of one "
                "recorded completion"
            )
        recorded_expectations = [
            (str(value.get("run_id") or ""), expectation)
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(
                item.get("object", {}).get("data", {}).get("value"), dict
            )
            and (
                value := item["object"]["data"]["value"]
            ).get("schema")
            == "ndf-replay-r2-expectations/v1"
            for expectation in value.get("outputs", [])
        ]
        for expected in expected_outputs:
            relative = str(expected.get("path") or "")
            if expected.get("comparison") == "epsilon":
                if not any(
                    run_id in matching_run_ids and expectation == expected
                    for run_id, expectation in recorded_expectations
                ):
                    raise ValueError(
                        f"R2 epsilon expectation is not recorded evidence: {relative}"
                    )
        recorded_leases = [
            value
            for item in reconstruction.get("recorded_objects", [])
            if item.get("object", {}).get("type") == "blob"
            and isinstance(
                item.get("object", {}).get("data", {}).get("value"), dict
            )
            and (
                value := item["object"]["data"]["value"]
            ).get("schema")
            == "ndf-runtime-lease/v1"
            and str(value.get("run_id") or "") in matching_run_ids
        ]
        if not recorded_leases:
            raise ValueError("R2 completion has no joined recorded runtime lease")
        for root in allowed_roots:
            if not any(
                root == str(lease.get("allowed_write_root") or "").strip("/")
                or root.startswith(
                    f"{str(lease.get('allowed_write_root') or '').strip('/')}/"
                )
                for lease in recorded_leases
            ):
                raise ValueError("R2 write roots exceed recorded runtime lease")
        if any(
            not any(
                path == root or path.startswith(f"{root}/")
                for root in allowed_roots
            )
            for path in exact_expectations
        ):
            raise ValueError(
                "R2 recorded changed outputs are outside the replay write roots"
            )
        recorded_commands = {
            tuple(item["cassette"].get("argv", []))
            for item in reconstruction.get("observations", [])
            if item.get("kind") == "tool"
            and item.get("cassette", {}).get("replay_policy") == "sandbox"
            and item.get("cassette", {}).get("manifest_sha") == manifest_sha
            and item.get("cassette", {}).get("plan_sha") == plan_sha
            and item.get("cassette", {}).get("repo_head") == repo_head
            and str(item.get("cassette", {}).get("run_id")) in matching_run_ids
            and item.get("cassette", {}).get("env_allowlist_fingerprint")
            == target.get("env_allowlist_fingerprint")
            and item.get("cassette", {}).get("cwd") == target.get("cwd")
            and item.get("cassette", {}).get("external_resource_version")
            == target.get("tool_runtime_version")
        }
        unrecorded = [argv for argv in commands if tuple(argv) not in recorded_commands]
        if unrecorded:
            raise ValueError(f"R2 commands lack sandbox replay cassettes: {unrecorded}")
        sandbox_root = self.repo_root / "tmp" / "ndf-replay-sandboxes"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        worktree = sandbox_root / f"r2-{uuid.uuid4()}"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), str(repo_head)],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            import ndf_context

            context_check = ndf_context.verify_plan(
                plan,
                root=worktree,
                manifest=manifest,
                require_manifest=True,
            )
            if not context_check["valid"]:
                raise ValueError(
                    f"R2 context/gate drift: {context_check['errors']}"
                )
            result["context_verification"] = context_check
            managed_adapter = [
                adapter[0],
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
                "--chdir",
                str(worktree),
            ]
            for relative in allowed_roots:
                if relative.startswith("/") or ".." in Path(relative).parts:
                    raise ValueError(f"R2 write root escapes sandbox: {relative}")
                writable = worktree / relative
                writable.mkdir(parents=True, exist_ok=True)
                managed_adapter.extend(["--bind", str(writable), str(writable)])
            managed_adapter.append("--")
            command_results = []
            for argv in commands:
                proc = subprocess.run(
                    [*managed_adapter, *argv],
                    cwd=worktree,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=int(profile.get("timeout_seconds", 600)),
                    check=False,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "HOME": "/tmp",
                        "NDF_REPLAY_LEVEL": "R2",
                    },
                )
                command_results.append(
                    {
                        "argv": argv,
                        "exit_code": proc.returncode,
                        "stdout_sha": canonical_json_sha(proc.stdout),
                        "stderr_sha": canonical_json_sha(proc.stderr),
                    }
                )
                if proc.returncode != 0:
                    result["state"] = "command_failed"
                    result["commands"] = command_results
                    return result
            changed = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=worktree,
                text=True,
            ).splitlines()
            changed_paths = [line[3:].strip() for line in changed if len(line) > 3]
            violations = [
                path
                for path in changed_paths
                if not any(path == root or path.startswith(f"{root}/") for root in allowed_roots)
            ]
            checks = []
            for expected in expected_outputs:
                relative = str(expected["path"])
                if relative.startswith("/") or ".." in Path(relative).parts:
                    raise ValueError(f"R2 expected output escapes sandbox: {relative}")
                output = worktree / relative
                if expected.get("comparison") == "epsilon":
                    if not output.is_file():
                        actual_metric = None
                    else:
                        observed = json.loads(output.read_text(encoding="utf-8"))
                        actual_metric = observed.get(str(expected.get("metric")))
                    target = expected.get("expected")
                    epsilon = expected.get("epsilon")
                    matches = bool(
                        isinstance(actual_metric, (int, float))
                        and isinstance(target, (int, float))
                        and isinstance(epsilon, (int, float))
                        and abs(float(actual_metric) - float(target))
                        <= float(epsilon)
                    )
                    checks.append(
                        {
                            "path": relative,
                            "comparison": "epsilon",
                            "metric": expected.get("metric"),
                            "expected": target,
                            "actual": actual_metric,
                            "epsilon": epsilon,
                            "matches": matches,
                        }
                    )
                else:
                    actual = (
                        hashlib.sha256(output.read_bytes()).hexdigest()
                        if output.is_file()
                        else None
                    )
                    checks.append(
                        {
                            "path": relative,
                            "comparison": "sha256",
                            "expected_sha256": expected.get("sha256"),
                            "actual_sha256": actual,
                            "matches": actual == expected.get("sha256"),
                        }
                    )
            result.update(
                {
                    "executed": True,
                    "state": (
                        "equivalent"
                        if checks
                        and not violations
                        and all(item["matches"] for item in checks)
                        else "different"
                    ),
                    "commands": command_results,
                    "changed_paths": changed_paths,
                    "write_violations": violations,
                    "output_checks": checks,
                }
            )
            return result
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=self.repo_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            shutil.rmtree(worktree, ignore_errors=True)

    def fork(
        self,
        start: str,
        branch: str,
        *,
        changes: Iterable[str] = (),
    ) -> dict[str, Any]:
        sha = self.read_ref(start) or start
        source = self.get_object(sha, "commit")["data"]
        change_list = list(changes)
        metadata = self.put_blob(
            {
                "schema": "ndf-replay-counterfactual/v1",
                "source_commit": sha,
                "changes": change_list,
                "historical_reproduction": False,
                "created_at": now_iso(),
            }
        )
        tree = self.put_tree(
            {
                "source-tree": source["tree"],
                "counterfactual": metadata,
            }
        )
        commit = self.put_commit(
            tree,
            parents=[sha],
            actor="fork",
            topic=source.get("topic"),
            task="counterfactual_fork",
            track=source.get("track") or "process",
            repo_head=source.get("repo_head"),
            manifest_sha=source.get("manifest_sha"),
            context_plan_sha=source.get("context_plan_sha"),
            message="R3 counterfactual fork",
            coverage={"counterfactual": True},
        )
        self.update_ref(f"branches/{branch}", commit, expected_old=None)
        return {
            "schema": "ndf-replay-fork/v1",
            "level": "R3",
            "from": sha,
            "branch": branch,
            "commit_sha": commit,
            "changes": change_list,
            "counterfactual": True,
        }

    @staticmethod
    def tool_cassette(
        *,
        tool: str,
        name: str,
        invocation_id: str,
        cwd: str,
        argv: Iterable[str],
        normalized_input: Any,
        stdin_sha: str | None,
        env_allowlist_fingerprint: str,
        timeout_ms: int,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: int,
        replay_policy: str,
        external_resource_version: str | None,
        bindings: Mapping[str, Any],
    ) -> dict[str, Any]:
        cassette = {
            "schema": "ndf-tool-cassette/v1",
            "tool": tool,
            "name": name,
            "invocation_id": invocation_id,
            "cwd": cwd,
            "argv": list(argv),
            "normalized_input": _json_copy(normalized_input),
            "stdin_sha": stdin_sha,
            "env_allowlist_fingerprint": env_allowlist_fingerprint,
            "timeout_ms": timeout_ms,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "replay_policy": replay_policy,
            "external_resource_version": external_resource_version,
            **dict(bindings),
        }
        required = (
            "repo_head",
            "worktree",
            "manifest_sha",
            "plan_sha",
            "run_id",
        )
        missing = [field for field in required if not cassette.get(field)]
        if missing:
            raise ValueError(f"tool cassette missing bindings: {missing}")
        if replay_policy not in {"recorded-only", "sandbox", "live-readonly"}:
            raise ValueError(f"invalid replay policy: {replay_policy}")
        if tool.lower() in {"mcp", "remote", "web"} and replay_policy == "sandbox":
            raise ValueError("remote tools default to recorded-only")
        if replay_policy == "live-readonly" and not external_resource_version:
            raise ValueError("live-readonly requires external_resource_version")
        _assert_no_plaintext_secrets(cassette)
        return cassette

    def put_tool_cassette(self, cassette: Mapping[str, Any]) -> str:
        value = _json_copy(cassette)
        if value.get("schema") != "ndf-tool-cassette/v1":
            raise ValueError("expected ndf-tool-cassette/v1")
        required = (
            "tool",
            "name",
            "invocation_id",
            "cwd",
            "argv",
            "normalized_input",
            "env_allowlist_fingerprint",
            "timeout_ms",
            "exit_code",
            "duration_ms",
            "repo_head",
            "worktree",
            "manifest_sha",
            "plan_sha",
            "run_id",
            "replay_policy",
        )
        missing = [
            field
            for field in required
            if field not in value or value[field] is None or value[field] == ""
        ]
        if missing:
            raise ValueError(f"tool cassette missing fields: {missing}")
        _assert_no_plaintext_secrets(value)
        for stream_name in ("stdout", "stderr"):
            content = str(value.pop(stream_name, ""))
            blob_sha = self.put_blob(content, media_type="text/plain")
            value[f"{stream_name}_blob"] = blob_sha
            value[f"{stream_name}_sha"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
        return self.put_object("tool-cassette", value)

    @staticmethod
    def model_turn(**values: Any) -> dict[str, Any]:
        turn = {"schema": "ndf-model-turn/v1", **_json_copy(values)}
        turn.setdefault("hidden_chain_of_thought", "not_recorded")
        turn.setdefault("visible_surface_coverage", "unknown_hidden_surface")
        _assert_no_plaintext_secrets(turn)
        return turn

    def put_model_turn(self, turn: Mapping[str, Any]) -> str:
        value = _json_copy(turn)
        if value.get("schema") != "ndf-model-turn/v1":
            raise ValueError("expected ndf-model-turn/v1")
        required = (
            "provider",
            "model_id",
            "api_version",
            "parameters",
            "runtime_build",
            "tool_schema_sha",
            "skill_rule_sha",
            "manifest_sha",
            "role_plan_sha",
            "visible_system_surface_sha",
            "user_message",
            "assistant_response",
            "stop_reason",
            "token_usage",
        )
        missing = [field for field in required if field not in value or value[field] is None]
        if missing:
            raise ValueError(f"model turn missing fields: {missing}")
        for field in (
            "tool_schema_sha",
            "skill_rule_sha",
            "manifest_sha",
            "role_plan_sha",
            "visible_system_surface_sha",
        ):
            if not SHA_RE.fullmatch(str(value.get(field) or "")):
                raise ValueError(f"model turn invalid SHA: {field}")
        _assert_no_plaintext_secrets(value)
        for field in ("user_message", "assistant_response"):
            content = str(value.pop(field))
            value[f"{field}_blob"] = self.put_blob(
                content,
                media_type="text/plain",
                sensitivity="sensitive",
            )
            value[f"{field}_sha"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
        for reference in value.get("input_tool_cassette_refs", []):
            self.get_object(str(reference), "tool-cassette")
        return self.put_object("model-turn", value)

    def redact_export(self, commit_or_ref: str) -> dict[str, Any]:
        source_sha = self.read_ref(commit_or_ref) or commit_or_ref
        source = self.get_object(source_sha, "commit")["data"]
        tree = self.get_object(source["tree"], "tree")["data"]["entries"]
        redacted_entries: dict[str, str] = {}
        replacements: list[dict[str, Any]] = []
        object_map: dict[str, str] = {}

        sensitive_value_patterns = (
            (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]", "private_key"),
            (re.compile(r"\b(?:Bearer\s+)?(?:sk|ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{12,}\b", re.I), "[REDACTED_TOKEN]", "secret_value"),
            (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I), "Bearer [REDACTED_TOKEN]", "authorization"),
            (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]", "secret_value"),
            (
                re.compile(
                    r"(?i)\b(password|passwd|token|secret|api[_-]?key|session[_-]?key)"
                    r"(\s*[:=]\s*)([^\s,;\"']+)"
                ),
                r"\1\2[REDACTED]",
                "secret_assignment",
            ),
            (re.compile(r"\b(?:ou|oc|on|cli)_[A-Za-z0-9]{8,}\b"), "[REDACTED_ID]", "service_id"),
            (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[REDACTED_EMAIL]", "pii_email"),
            (
                re.compile(r"(?i)\bhttps?://[^/\s:@]+:[^/\s@]+@"),
                "https://[REDACTED_CREDENTIAL]@",
                "url_credential",
            ),
        )
        secret_argv_flags = {
            "--token",
            "--api-key",
            "--apikey",
            "--password",
            "--passwd",
            "--secret",
            "--authorization",
            "-p",
        }

        def redact(value: Any, path: str = "") -> Any:
            if isinstance(value, dict):
                output = {}
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else key
                    if SECRET_KEY_RE.search(key):
                        output[key] = "[REDACTED]"
                        replacements.append({"path": child_path, "reason": "secret_key"})
                    else:
                        output[key] = redact(child, child_path)
                return output
            if isinstance(value, list):
                output = []
                redact_next = False
                for index, child in enumerate(value):
                    child_path = f"{path}[{index}]"
                    if redact_next:
                        output.append("[REDACTED]")
                        replacements.append(
                            {"path": child_path, "reason": "argv_secret_value"}
                        )
                        redact_next = False
                        continue
                    if isinstance(child, str):
                        flag = child.lower()
                        if flag in secret_argv_flags:
                            output.append(child)
                            redact_next = True
                            continue
                        if any(
                            flag.startswith(f"{secret_flag}=")
                            for secret_flag in secret_argv_flags
                        ):
                            output.append(child.split("=", 1)[0] + "=[REDACTED]")
                            replacements.append(
                                {"path": child_path, "reason": "argv_secret_assignment"}
                            )
                            continue
                        if flag in {"-h", "--header"} and index + 1 < len(value):
                            output.append(child)
                            redact_next = True
                            continue
                    output.append(redact(child, child_path))
                return output
            if isinstance(value, str):
                output = value
                for pattern, replacement, reason in sensitive_value_patterns:
                    revised, count = pattern.subn(replacement, output)
                    if count:
                        replacements.append(
                            {"path": path, "reason": reason, "count": count}
                        )
                    output = revised
                return output
            return value

        def redact_object(object_sha: str, path: str) -> str:
            if object_sha in object_map:
                return object_map[object_sha]
            obj = self.get_object(object_sha)
            kind = obj["type"]
            data = _json_copy(obj["data"])
            if kind == "tree":
                data["entries"] = {
                    name: redact_object(target, f"{path}/{name}")
                    for name, target in data.get("entries", {}).items()
                }
            elif kind == "tool-cassette":
                for field in ("stdout_blob", "stderr_blob"):
                    if data.get(field):
                        data[field] = redact_object(
                            str(data[field]),
                            f"{path}/{field}",
                        )
                data = redact(data, path)
            elif kind == "model-turn":
                for field in ("user_message_blob", "assistant_response_blob"):
                    if data.get(field):
                        data[field] = redact_object(
                            str(data[field]),
                            f"{path}/{field}",
                        )
                data["input_tool_cassette_refs"] = [
                    redact_object(str(target), f"{path}/input-tool-{index}")
                    for index, target in enumerate(
                        data.get("input_tool_cassette_refs", [])
                    )
                ]
                data = redact(data, path)
            else:
                data = redact(data, path)
            redacted_sha = self.put_object(kind, data)
            object_map[object_sha] = redacted_sha
            return redacted_sha

        for name, object_sha in tree.items():
            redacted_entries[name] = redact_object(object_sha, name)
        redaction_map = {
            "schema": "ndf-redaction-map/v1",
            "source_commit": source_sha,
            "replacements": replacements,
            "object_map": object_map,
            "original_objects_unchanged": True,
        }
        redacted_entries["redaction-map"] = self.put_blob(redaction_map)
        redacted_tree = self.put_tree(redacted_entries)
        scanner_findings: list[str] = []
        for original_sha, exported_sha in object_map.items():
            exported = self.get_object(exported_sha)
            serialized = json.dumps(
                exported,
                ensure_ascii=False,
                sort_keys=True,
            )
            scan_text = re.sub(r"\[REDACTED[^\]]*\]", "", serialized)
            for pattern, _, reason in sensitive_value_patterns:
                if pattern.search(scan_text):
                    scanner_findings.append(f"{exported_sha}:{reason}")
            if re.search(
                r'(?i)"(?:token|password|secret|api[_-]?key)"\s*:\s*"[^"]+"',
                scan_text,
            ):
                scanner_findings.append(f"{exported_sha}:secret_key_value")
        if scanner_findings:
            raise ValueError(
                "share-safe export secret scan failed: "
                + ",".join(sorted(set(scanner_findings)))
            )
        commit = self.put_commit(
            redacted_tree,
            # A share-safe export must not make the secret-bearing source
            # history reachable from the exported commit closure.
            parents=[],
            actor="redactor",
            topic=source.get("topic"),
            task="redacted_export",
            track=source.get("track") or "process",
            repo_head=source.get("repo_head"),
            manifest_sha=source.get("manifest_sha"),
            context_plan_sha=source.get("context_plan_sha"),
            message="share-safe redacted export",
            coverage={"redaction_map": redacted_entries["redaction-map"]},
        )
        return {
            "schema": "ndf-replay-export/v1",
            "source_commit": source_sha,
            "redacted_commit": commit,
            "redaction_map_sha": redacted_entries["redaction-map"],
            "secret_scan_findings": [],
        }

    def ledger_entry(self, episode_id: str, *, write: bool = False) -> dict[str, Any]:
        head = self.read_ref(f"episodes/{episode_id}/HEAD")
        if head is None:
            raise ValueError(f"unknown episode: {episode_id}")
        commit = self.get_object(head, "commit")["data"]
        topic = commit.get("topic")
        if not topic:
            raise ValueError("project-level episode has no topic binder ledger")
        branch_events = self.read_all_events(episode_id)
        chains = {
            branch: validate_event_chain(events)
            for branch, events in branch_events.items()
        }
        history = [value for _, value in self.walk_commits(head)]
        manifest_sha = next(
            (value.get("manifest_sha") for value in history if value.get("manifest_sha")),
            None,
        )
        plan_sha = next(
            (
                value.get("context_plan_sha")
                for value in history
                if value.get("context_plan_sha")
            ),
            None,
        )
        runtime_coverage = [
            value.get("coverage", {}).get("runtime_stream")
            for value in history
            if value.get("coverage", {}).get("runtime_stream")
        ]
        line = (
            f"| {now_iso()} | {episode_id} | {commit.get('task')} | "
            f"{manifest_sha or 'missing'} | "
            f"{plan_sha or 'missing'} | {head} | "
            f"R0={'yes' if chains and all(item['valid'] for item in chains.values()) else 'no'}; "
            f"runtime={','.join(str(item) for item in runtime_coverage) or 'unknown'} | "
            f".ndf/replay/ | coverage gaps retained |"
        )
        path = self.repo_root / "poc" / str(topic) / "ndf" / "REPLAYS.md"
        if write:
            if not path.parent.is_dir():
                raise ValueError(f"topic binder missing: {path.parent}")
            if not path.exists():
                path.write_text(
                    "# Agent Episode Replay Ledger\n\n"
                    "> schema: ndf-replay-ledger/v1\n\n"
                    "| recorded_at | episode_id | task | manifest_sha | role_plan_sha | completion_commit | replay_coverage | artifact_location | note |\n"
                    "|---|---|---|---|---|---|---|---|---|\n",
                    encoding="utf-8",
                )
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return {
            "schema": "ndf-replay-ledger-entry/v1",
            "episode_id": episode_id,
            "topic": topic,
            "head": head,
            "line": line,
            "path": path.relative_to(self.repo_root).as_posix(),
            "written": write,
        }

    def retention_plan(self) -> dict[str, Any]:
        """Return a non-destructive hot/cold plan; never deletes evidence."""
        config_path = self.root / "config.json"
        if not config_path.is_file():
            return {
                "schema": "ndf-replay-retention-plan/v1",
                "state": "not_initialized",
                "candidates": [],
            }
        config = json.loads(config_path.read_text(encoding="utf-8"))
        hot_days = int(config.get("retention", {}).get("large_tool_blob_hot_days", 90))
        model_days = int(
            config.get("retention", {}).get("sensitive_model_turn_hot_days", 30)
        )
        referenced: set[str] = set()
        pending: list[str] = []
        if self.refs.is_dir():
            for path in self.refs.rglob("*"):
                if path.is_file():
                    pending.append(path.read_text(encoding="utf-8").strip())
        while pending:
            sha = pending.pop()
            if sha in referenced or not SHA_RE.fullmatch(sha):
                continue
            referenced.add(sha)
            try:
                obj = self.get_object(sha)
            except (FileNotFoundError, ValueError):
                continue
            data = obj.get("data", {})
            if obj.get("type") == "commit":
                pending.extend([data.get("tree"), *data.get("parents", [])])
            elif obj.get("type") == "tree":
                pending.extend(data.get("entries", {}).values())
            elif obj.get("type") == "tool-cassette":
                pending.extend(
                    data.get(field)
                    for field in ("stdout_blob", "stderr_blob")
                    if data.get(field)
                )
        current = datetime.now(timezone.utc).timestamp()
        candidates = []
        if self.objects.is_dir():
            for path in sorted(item for item in self.objects.rglob("*") if item.is_file()):
                sha = path.parent.name + path.name
                age_days = max(0, int((current - path.stat().st_mtime) / 86400))
                try:
                    obj = self.get_object(sha)
                except (FileNotFoundError, ValueError):
                    continue
                threshold = (
                    model_days
                    if obj.get("type") == "model-turn"
                    or obj.get("data", {}).get("sensitivity") in {
                        "sensitive",
                        "secret",
                    }
                    else hot_days
                )
                if age_days >= threshold:
                    candidates.append(
                        {
                            "sha": sha,
                            "age_days": age_days,
                            "hot_days": threshold,
                            "reachable": sha in referenced,
                            "action": (
                                "keep-core"
                                if sha in referenced
                                else "eligible-for-cold-store-after-location-receipt"
                            ),
                        }
                    )
        return {
            "schema": "ndf-replay-retention-plan/v1",
            "state": "planned",
            "hot_days": hot_days,
            "destructive": False,
            "candidates": candidates,
        }

    def fsck(self) -> dict[str, Any]:
        errors: list[str] = []
        object_count = 0
        commits: dict[str, dict[str, Any]] = {}
        config_path = self.root / "config.json"
        if self.root.is_dir():
            if not config_path.is_file():
                errors.append("missing replay config")
            else:
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    if config.get("schema") != "ndf-replay-config/v1":
                        errors.append("invalid replay config schema")
                    if config.get("storage_security") not in {
                        "encrypted-local",
                        "controlled-artifact-store",
                    }:
                        errors.append("uncontrolled replay storage")
                    if (
                        config.get("storage_security") == "encrypted-local"
                        and config.get("key_id") != self._key_id()
                    ):
                        errors.append("replay encryption key mismatch")
                except json.JSONDecodeError:
                    errors.append("invalid replay config")
        if self.objects.is_dir():
            for path in sorted(
                item
                for item in self.objects.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                sha = path.parent.name + path.name
                object_count += 1
                if not path.read_bytes().startswith(ENCRYPTED_MAGIC):
                    errors.append(f"plaintext replay object:{sha}")
                try:
                    obj = self.get_object(sha)
                except (ValueError, FileNotFoundError) as exc:
                    errors.append(str(exc))
                    continue
                data = obj.get("data", {})
                if obj.get("type") == "tree":
                    if not isinstance(data.get("entries"), dict):
                        errors.append(f"invalid tree entries:{sha}")
                        continue
                    for name, target in data.get("entries", {}).items():
                        try:
                            self.get_object(target)
                        except (ValueError, FileNotFoundError):
                            errors.append(f"missing tree object:{sha}:{name}:{target}")
                elif obj.get("type") == "commit":
                    commits[sha] = data
                    try:
                        self.get_object(str(data.get("tree")), "tree")
                    except (ValueError, FileNotFoundError):
                        errors.append(
                            f"commit_tree_wrong_type_or_missing:{sha}:{data.get('tree')}"
                        )
                    for target in data.get("parents", []):
                        try:
                            self.get_object(str(target), "commit")
                        except (ValueError, FileNotFoundError):
                            errors.append(
                                f"commit_parent_wrong_type_or_missing:{sha}:{target}"
                            )
                elif obj.get("type") == "tool-cassette":
                    for field in ("stdout_blob", "stderr_blob"):
                        try:
                            self.get_object(str(data[field]), "blob")
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing cassette stream:{sha}:{field}")
                elif obj.get("type") == "model-turn":
                    for field in ("user_message_blob", "assistant_response_blob"):
                        try:
                            self.get_object(str(data[field]), "blob")
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing model turn message:{sha}:{field}")
                    for target in data.get("input_tool_cassette_refs", []):
                        try:
                            self.get_object(str(target), "tool-cassette")
                        except (ValueError, FileNotFoundError):
                            errors.append(f"missing model turn cassette:{sha}:{target}")
                elif obj.get("type") == "blob":
                    value = data.get("value")
                    if (
                        data.get("encoding") == "json"
                        and isinstance(value, dict)
                        and value.get("schema") == "ndf-redaction-map/v1"
                    ):
                        try:
                            self.get_object(str(value["source_commit"]), "commit")
                            for original, redacted in value.get(
                                "object_map", {}
                            ).items():
                                self.get_object(str(original))
                                self.get_object(str(redacted))
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"invalid redaction lineage:{sha}")
                    if (
                        data.get("encoding") == "json"
                        and isinstance(value, dict)
                        and value.get("schema") == "ndf-replay-event-chain/v1"
                    ):
                        try:
                            count = int(value["count"])
                            events = self.read_events(
                                str(value["episode_id"]),
                                str(value.get("branch") or "main"),
                            )
                            prefix = validate_event_chain(events[:count])
                            if (
                                prefix["count"] != count
                                or prefix["tip_sha"] != value.get("tip_sha")
                            ):
                                errors.append(f"event chain object mismatch:{sha}")
                        except (KeyError, TypeError, ValueError):
                            errors.append(f"invalid event chain object:{sha}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit_commit(current: str) -> None:
            if current in visited:
                return
            if current in visiting:
                errors.append(f"commit_cycle:{current}")
                return
            visiting.add(current)
            for parent in commits.get(current, {}).get("parents", []):
                if parent in commits:
                    visit_commit(parent)
            visiting.remove(current)
            visited.add(current)

        for sha in commits:
            visit_commit(sha)
        ref_count = 0
        if self.refs.is_dir():
            for path in sorted(
                item
                for item in self.refs.rglob("*")
                if item.is_file() and not item.name.startswith(".")
            ):
                ref_count += 1
                sha = path.read_text(encoding="utf-8").strip()
                relative_ref = path.relative_to(self.refs).as_posix()
                try:
                    obj = self.get_object(sha)
                    if (
                        relative_ref.startswith(
                            ("episodes/", "branches/", "topics/", "runs/", "tags/")
                        )
                        and obj.get("type") != "commit"
                    ):
                        errors.append(
                            f"ref_wrong_type:{relative_ref}:{obj.get('type')}"
                        )
                except (ValueError, FileNotFoundError):
                    errors.append(f"dangling_ref:{relative_ref}:{sha}")
        event_count = 0
        if self.events.is_dir():
            for path in sorted(self.events.rglob("*.jsonl")):
                try:
                    relative = path.relative_to(self.events)
                    if len(relative.parts) == 1:
                        episode_id = path.stem
                        branch = "main"
                    else:
                        episode_id = relative.parts[0]
                        branch = Path(*relative.parts[1:]).with_suffix("").as_posix()
                    events = self.read_events(episode_id, branch)
                    validation = validate_event_chain(events)
                    event_count += len(events)
                    errors.extend(f"{path.name}:{error}" for error in validation["errors"])
                    for event in events:
                        if event.get("episode_id") != episode_id:
                            errors.append(
                                f"event_episode_mismatch:{path.name}:{event.get('seq')}"
                            )
                        if event.get("branch") != branch:
                            errors.append(
                                f"event_branch_mismatch:{path.name}:{event.get('seq')}"
                            )
                        try:
                            self.get_object(event["payload_sha"])
                        except (KeyError, ValueError, FileNotFoundError):
                            errors.append(f"missing_event_payload:{path.name}:{event.get('seq')}")
                except ValueError as exc:
                    errors.append(f"{path.name}:{exc}")
        return {
            "schema": "ndf-replay-fsck/v1",
            "valid": not errors,
            "objects": object_count,
            "refs": ref_count,
            "events": event_count,
            "errors": sorted(set(errors)),
        }


def _load_json(path: str | None) -> dict[str, Any]:
    if not path or path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    parser.add_argument("--store", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("episode-init")
    init.add_argument("--topic")
    init.add_argument("--task", required=True)
    init.add_argument("--role", required=True)
    init.add_argument("--track", default="poc")
    init.add_argument("--manifest")
    init.add_argument("--episode")

    record = sub.add_parser("record")
    record.add_argument("--episode", required=True)
    record.add_argument("--kind", required=True, choices=tuple(sorted(EVENT_KINDS)))
    record.add_argument("--payload", required=True)
    record.add_argument("--actor", default="tool")
    record.add_argument("--topic")
    record.add_argument("--task", required=True)
    record.add_argument("--track", default="poc")
    record.add_argument("--repo-head")
    record.add_argument("--manifest-sha")
    record.add_argument("--plan-sha")
    record.add_argument("--session-id")
    record.add_argument("--run-id")
    record.add_argument("--branch", default="main")
    cassette = sub.add_parser("cassette-record")
    cassette.add_argument("--episode", required=True)
    cassette.add_argument("--file", required=True)
    cassette.add_argument("--actor", default="tool")
    cassette.add_argument("--branch", default="main")
    model_turn = sub.add_parser("model-turn-record")
    model_turn.add_argument("--episode", required=True)
    model_turn.add_argument("--file", required=True)
    model_turn.add_argument("--actor", default="model")
    model_turn.add_argument("--branch", default="main")

    commit = sub.add_parser("commit")
    commit.add_argument("--episode", required=True)
    commit.add_argument("--message", required=True)
    commit.add_argument("--actor", default="tool")
    commit.add_argument("--branch", default="main")

    show = sub.add_parser("show")
    show.add_argument("object")
    log = sub.add_parser("log")
    log.add_argument("start")
    diff = sub.add_parser("diff")
    diff.add_argument("left")
    diff.add_argument("right")

    branch = sub.add_parser("branch")
    branch.add_argument("name")
    branch.add_argument("start")
    tag = sub.add_parser("tag")
    tag.add_argument("name")
    tag.add_argument("target")
    gate_tag = sub.add_parser("gate-tag")
    gate_tag.add_argument("--name", required=True)
    gate_tag.add_argument("--target", required=True)
    gate_tag.add_argument("--receipt", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--episode", required=True)
    merge.add_argument("--left", required=True)
    merge.add_argument("--right", required=True)
    merge.add_argument("--message", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--episode", required=True)
    checkpoint.add_argument("--strategy", choices=("context-recompile",), default="context-recompile")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--manifest-sha")
    checkpoint.add_argument("--plan-sha")
    checkpoint.add_argument("--open-decision", action="append", default=[])
    checkpoint.add_argument("--resolved-decision", action="append", default=[])
    checkpoint.add_argument("--summary-provenance")
    checkpoint.add_argument("--branch", default="main")

    audit = sub.add_parser("audit")
    audit.add_argument("--commit", required=True)
    audit.add_argument("--strict", action="store_true")
    reconstruct = sub.add_parser("reconstruct")
    reconstruct.add_argument("--commit", required=True)
    reconstruct.add_argument("--level", choices=("R0", "R1"), default="R1")
    sandbox = sub.add_parser("sandbox")
    sandbox.add_argument("--commit", required=True)
    sandbox.add_argument("--profile", required=True)
    sandbox.add_argument("--execute", action="store_true")
    sandbox.add_argument("--episode")
    fork = sub.add_parser("fork")
    fork.add_argument("--from", dest="start", required=True)
    fork.add_argument("--branch", required=True)
    fork.add_argument("--change", action="append", default=[])
    export = sub.add_parser("export")
    export.add_argument("--commit", required=True)
    export.add_argument("--redact", default="share-safe")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("--episode", required=True)
    ledger.add_argument("--write", action="store_true")
    sub.add_parser("retention-plan")
    sub.add_parser("fsck")

    args = parser.parse_args(argv)
    repo = Path(args.root).resolve()
    store = ReplayStore(repo, Path(args.store).resolve() if args.store else None)
    try:
        if args.command == "episode-init":
            result = store.init_episode(
                topic=args.topic,
                task=args.task,
                role=args.role,
                track=args.track,
                manifest=_load_json(args.manifest) if args.manifest else None,
                episode_id=args.episode,
            )
        elif args.command == "record":
            payload = _load_json(args.payload)
            payload_sha = store.put_blob(payload)
            result = store.append_event(
                args.episode,
                kind=args.kind,
                actor=args.actor,
                payload_sha=payload_sha,
                topic=args.topic,
                task=args.task,
                track=args.track,
                repo_head=args.repo_head,
                manifest_sha=args.manifest_sha,
                context_plan_sha=args.plan_sha,
                session_id=args.session_id,
                run_id=args.run_id,
                branch=args.branch,
                verified=False,
            )
        elif args.command in {"cassette-record", "model-turn-record"}:
            payload = _load_json(args.file)
            expected_schema = (
                "ndf-tool-cassette/v1"
                if args.command == "cassette-record"
                else "ndf-model-turn/v1"
            )
            if payload.get("schema") != expected_schema:
                raise ValueError(f"expected {expected_schema}")
            _assert_no_plaintext_secrets(payload)
            payload_sha = (
                store.put_tool_cassette(payload)
                if args.command == "cassette-record"
                else store.put_model_turn(payload)
            )
            result = store.append_event(
                args.episode,
                kind="tool.result" if args.command == "cassette-record" else "model.response",
                actor=args.actor,
                payload_sha=payload_sha,
                topic=payload.get("topic"),
                task=str(payload.get("task") or args.command),
                track=str(payload.get("track") or "process"),
                repo_head=payload.get("repo_head"),
                manifest_sha=payload.get("manifest_sha"),
                context_plan_sha=payload.get("plan_sha") or payload.get("context_plan_sha"),
                session_id=payload.get("session_id"),
                run_id=payload.get("run_id"),
                branch=args.branch,
            )
        elif args.command == "commit":
            result = {"commit_sha": store.commit_events(args.episode, message=args.message, actor=args.actor, branch=args.branch)}
        elif args.command == "show":
            sha = store.read_ref(args.object) or args.object
            result = {"sha": sha, "object": store.get_object(sha)}
        elif args.command == "log":
            result = {
                "schema": "ndf-replay-log/v1",
                "commits": [{"sha": sha, **value} for sha, value in store.walk_commits(args.start)],
            }
        elif args.command == "diff":
            result = store.diff(args.left, args.right)
        elif args.command == "branch":
            sha = store.read_ref(args.start) or args.start
            store.update_ref(f"branches/{args.name}", sha)
            result = {"branch": args.name, "sha": sha}
        elif args.command == "tag":
            if args.name.startswith("gates/"):
                raise ValueError("gate tags require gate-tag and a verified human receipt")
            sha = store.read_ref(args.target) or args.target
            store.update_ref(f"tags/{args.name}", sha, immutable=True)
            result = {"tag": args.name, "sha": sha}
        elif args.command == "gate-tag":
            result = store.create_gate_tag(
                args.name,
                args.target,
                _load_json(args.receipt),
            )
        elif args.command == "merge":
            result = {"commit_sha": store.merge(args.episode, args.left, args.right, message=args.message)}
        elif args.command == "checkpoint":
            result = {
                "commit_sha": store.checkpoint(
                    args.episode,
                    summary=args.summary,
                    manifest_sha=args.manifest_sha,
                    plan_sha=args.plan_sha,
                    open_decisions=args.open_decision,
                    resolved_decisions=args.resolved_decision,
                    summary_provenance=(
                        _load_json(args.summary_provenance)
                        if args.summary_provenance
                        else None
                    ),
                    branch=args.branch,
                )
            }
        elif args.command == "audit":
            result = store.audit(args.commit, strict=args.strict)
        elif args.command == "reconstruct":
            result = store.reconstruct(args.commit, args.level)
        elif args.command == "sandbox":
            if args.execute and not args.episode:
                raise ValueError("executed R2 replay requires --episode")
            profile = _load_json(args.profile)
            result = store.sandbox_replay(
                args.commit,
                profile,
                execute=args.execute,
            )
            if args.execute and args.episode:
                result_blob = store.put_blob(result)
                source_commit = store.get_object(
                    store.read_ref(args.commit) or args.commit,
                    "commit",
                )["data"]
                event = store.append_event(
                    args.episode,
                    kind="verification.completed",
                    actor="sandbox",
                    payload_sha=result_blob,
                    topic=source_commit.get("topic"),
                    task="r2_sandbox_replay",
                    track=str(source_commit.get("track") or "process"),
                    repo_head=source_commit.get("repo_head"),
                    manifest_sha=source_commit.get("manifest_sha"),
                    context_plan_sha=source_commit.get("context_plan_sha"),
                    branch="replay-r2",
                )
                commit_sha = store.commit_events(
                    args.episode,
                    message=f"R2 sandbox {result.get('state')}",
                    actor="sandbox",
                    branch="replay-r2",
                    coverage={
                        "sandbox_profile": result.get("profile_sha"),
                        "sandbox_outcome": result.get("state"),
                    },
                )
                result["replay"] = {
                    "event_sha": event["event_sha"],
                    "commit_sha": commit_sha,
                }
        elif args.command == "fork":
            result = store.fork(args.start, args.branch, changes=args.change)
        elif args.command == "export":
            if args.redact != "share-safe":
                raise ValueError("only share-safe redaction profile is supported")
            result = store.redact_export(args.commit)
        elif args.command == "ledger":
            result = store.ledger_entry(args.episode, write=args.write)
        elif args.command == "retention-plan":
            result = store.retention_plan()
        else:
            result = store.fsck()
        _emit(result)
        return 0 if result.get("valid", True) else 1
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        _emit({"schema": "ndf-replay-error/v1", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
