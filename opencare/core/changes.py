"""Reversible change sets — OpenCare's undo backbone.

Every fix records what it did into a ChangeSet before acting. A ChangeSet is a folder
under history/<id>/ holding changeset.json plus any backup payloads (exported registry
subtrees, quarantined files). ChangeStore lists them and restores one by replaying its
operations in reverse order through registered restore handlers.

Built-in reversible kinds: reg_tree, reg_value, quarantine_file, service_start_type,
startup_entry, tweak. Register more with register_restore_handler().
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from opencare.core import paths
from opencare.core.env import Environment, RegValue, split_root
from opencare.core.fmt import now_iso

log = logging.getLogger(__name__)


@dataclass
class Operation:
    kind: str
    description: str
    data: dict[str, Any] = field(default_factory=dict)
    restored: bool = False


@dataclass
class ChangeSet:
    id: str
    title: str
    created: str
    operations: list[Operation] = field(default_factory=list)
    bytes_freed: int = 0
    items: int = 0
    _dir: Path | None = None
    _env: Environment | None = None

    # ---- recording helpers (called by engines during fix) ----
    def _payload_dir(self) -> Path:
        d = self._dir / "payload"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def record(self, kind: str, description: str, data: dict[str, Any]) -> None:
        self.operations.append(Operation(kind, description, data))

    def backup_reg_value(self, path: str, value: RegValue) -> None:
        self.record(
            "reg_value",
            f"Restore value {value.name or '(default)'} in {path}",
            {"path": path, "name": value.name, "value": _encode_regval(value.value), "type": value.type},
        )

    def backup_reg_tree(self, path: str) -> None:
        """Snapshot a registry subtree (values + descendants) so it can be recreated."""
        env = self._env
        snapshot = _export_tree(env, path)
        fname = f"reg_{uuid.uuid4().hex}.json"
        (self._payload_dir() / fname).write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
        self.record("reg_tree", f"Restore registry key {path}", {"path": path, "file": fname})

    def quarantine_file(self, path: str) -> Path:
        """Move a file into the change set; returns the new location."""
        src = Path(path)
        dest = self._payload_dir() / f"{uuid.uuid4().hex}_{src.name}"
        shutil.move(str(src), str(dest))
        self.record("quarantine_file", f"Restore file {path}", {"original": str(src), "stored": dest.name})
        return dest

    def record_service_start_type(self, name: str, old_value: int) -> None:
        self.record("service_start_type", f"Restore start type of service {name}", {"name": name, "start": old_value})

    def record_startup_entry(self, data: dict[str, Any]) -> None:
        self.record("startup_entry", f"Restore startup entry {data.get('name', '')}", data)

    def record_tweak(self, tweak_id: str, path: str, name: str, old: RegValue | None) -> None:
        self.record(
            "tweak",
            f"Revert tweak {tweak_id}",
            {"path": path, "name": name, "old": _encode_regval(old.value) if old else None, "type": old.type if old else None, "existed": old is not None},
        )

    def save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        doc = {
            "id": self.id,
            "title": self.title,
            "created": self.created,
            "bytes_freed": self.bytes_freed,
            "items": self.items,
            "operations": [asdict(o) for o in self.operations],
        }
        (self._dir / "changeset.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    @property
    def is_empty(self) -> bool:
        return not self.operations


def _encode_regval(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _decode_regval(value: Any) -> Any:
    if isinstance(value, dict) and "__bytes__" in value:
        return bytes.fromhex(value["__bytes__"])
    return value


def _export_tree(env: Environment, path: str) -> dict:
    node: dict[str, Any] = {"path": path, "values": [], "subkeys": []}
    for v in env.reg.values(path):
        node["values"].append({"name": v.name, "value": _encode_regval(v.value), "type": v.type})
    for child in env.reg.subkeys(path):
        node["subkeys"].append(_export_tree(env, path + "\\" + child))
    return node


def _import_tree(env: Environment, node: dict) -> None:
    path = node["path"]
    env.reg.create_key(path)
    for v in node.get("values", []):
        env.reg.set_value(path, v["name"], _decode_regval(v["value"]), v["type"])
    for child in node.get("subkeys", []):
        _import_tree(env, child)


# ---- restore handlers ----
RestoreHandler = Callable[[Environment, Operation, Path], None]
_HANDLERS: dict[str, RestoreHandler] = {}


def register_restore_handler(kind: str, fn: RestoreHandler) -> None:
    _HANDLERS[kind] = fn


def _restore_reg_value(env: Environment, op: Operation, payload: Path) -> None:
    d = op.data
    env.reg.set_value(d["path"], d["name"], _decode_regval(d["value"]), d["type"])


def _restore_reg_tree(env: Environment, op: Operation, payload: Path) -> None:
    snapshot = json.loads((payload / op.data["file"]).read_text(encoding="utf-8"))
    _import_tree(env, snapshot)


def _restore_quarantine(env: Environment, op: Operation, payload: Path) -> None:
    src = payload / op.data["stored"]
    dest = Path(op.data["original"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dest))


def _restore_tweak(env: Environment, op: Operation, payload: Path) -> None:
    d = op.data
    if d.get("existed"):
        env.reg.set_value(d["path"], d["name"], _decode_regval(d["old"]), d["type"])
    else:
        try:
            env.reg.delete_value(d["path"], d["name"])
        except OSError:
            pass


register_restore_handler("reg_value", _restore_reg_value)
register_restore_handler("reg_tree", _restore_reg_tree)
register_restore_handler("quarantine_file", _restore_quarantine)
register_restore_handler("tweak", _restore_tweak)
# service_start_type and startup_entry handlers are registered by their engines.


class ChangeStore:
    def __init__(self, env: Environment | None = None, root: Path | None = None):
        self.env = env or Environment.real()
        self.root = root or paths.history_dir()

    def new_change_set(self, title: str) -> ChangeSet:
        cid = f"{now_iso().replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:6]}"
        cs = ChangeSet(id=cid, title=title, created=now_iso())
        cs._dir = self.root / cid
        cs._env = self.env
        return cs

    def list(self) -> list[ChangeSet]:
        out: list[ChangeSet] = []
        for d in sorted(self.root.glob("*"), reverse=True):
            doc_file = d / "changeset.json"
            if not doc_file.exists():
                continue
            try:
                doc = json.loads(doc_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            cs = ChangeSet(
                id=doc["id"], title=doc["title"], created=doc["created"],
                bytes_freed=doc.get("bytes_freed", 0), items=doc.get("items", 0),
                operations=[Operation(**o) for o in doc.get("operations", [])],
            )
            cs._dir = d
            cs._env = self.env
            out.append(cs)
        return out

    def get(self, change_id: str) -> ChangeSet | None:
        for cs in self.list():
            if cs.id == change_id:
                return cs
        return None

    def restore(self, change_id: str, progress=None) -> tuple[int, int]:
        """Replay a change set in reverse. Returns (restored, failed)."""
        cs = self.get(change_id)
        if not cs:
            raise KeyError(change_id)
        payload = cs._dir / "payload"
        restored = failed = 0
        ops = list(enumerate(cs.operations))
        for n, (i, op) in enumerate(reversed(ops)):
            if op.restored:
                continue
            handler = _HANDLERS.get(op.kind)
            if not handler:
                log.warning("no restore handler for %s", op.kind)
                failed += 1
                continue
            try:
                handler(self.env, op, payload)
                op.restored = True
                restored += 1
            except Exception:  # noqa: BLE001
                log.exception("restore failed: %s", op.description)
                failed += 1
            if progress:
                progress((n + 1) / max(1, len(ops)), op.description)
        cs.save()
        return restored, failed

    def delete(self, change_id: str) -> None:
        cs = self.get(change_id)
        if cs and cs._dir.exists():
            shutil.rmtree(cs._dir, ignore_errors=True)

    def prune(self, keep_days: int) -> int:
        import datetime as dt

        cutoff = dt.datetime.now() - dt.timedelta(days=keep_days)
        removed = 0
        for cs in self.list():
            try:
                created = dt.datetime.fromisoformat(cs.created)
            except ValueError:
                continue
            if created < cutoff:
                self.delete(cs.id)
                removed += 1
        return removed
