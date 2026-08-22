from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Hashable, TypeVar
from urllib.parse import quote

from .authority import load_authority_status
from .source_integrity import validate_current_overlays
from .version_integrity import validate_rule_version_integrity

INDEX_SCHEMA_VERSION = 1
RUNTIME_SCHEMA_VERSION = 1
DEFAULT_CACHE_ENTRIES = 256

# These are the minimum artifacts needed for normal Ask/Search/UI serving.  Source
# update scratch areas and test reports are intentionally excluded from the runtime
# snapshot so their mutation cannot invalidate a long-running read-only server.
RUNTIME_ARTIFACTS: tuple[str, ...] = (
    "data/canonical/core_rules.json",
    "data/canonical/tournament_rules.json",
    "data/canonical/cards.json",
    "data/canonical/semantic_ir.json",
    "data/canonical/compiled_rule_catalog.json",
    "data/canonical/rule_programs.json",
    "data/canonical/supplemental_sources.json",
    "data/canonical/official_errata.json",
    "data/canonical/effective_rule_overrides.json",
    "data/canonical/card_interaction_catalog.json",
    "data/canonical/card_interaction_programs.json",
    "data/index/rules.sqlite",
    "data/source/official_source_manifest.json",
    "data/source/current_authority_overlay.json",
    "data/source/core_rules.pdf",
    "data/source/tournament_rules.pdf",
    "data/source/rule_versions/core/history.json",
    "data/source/rule_versions/tournament/history.json",
)

SCHEMA_VERSION_EXPECTATIONS: dict[str, int] = {
    "data/canonical/compiled_rule_catalog.json": 1,
    "data/canonical/rule_programs.json": 1,
    "data/canonical/supplemental_sources.json": 1,
    "data/canonical/official_errata.json": 1,
    "data/canonical/card_interaction_catalog.json": 1,
    "data/canonical/card_interaction_programs.json": 1,
    "data/source/rule_versions/core/history.json": 1,
    "data/source/rule_versions/tournament/history.json": 1,
}


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync after os.replace.

    POSIX filesystems can durably persist a rename by fsyncing the parent directory.
    Windows does not support opening directories this way, so failure is intentionally
    ignored after the file itself has already been flushed and replaced.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(Path(path), text.encode(encoding))


def atomic_write_json(path: Path, data: Any) -> None:
    # Preserve the project's established canonical JSON byte format while making
    # the replacement crash-safe.  Atomicity must not silently change source/hash
    # semantics (for example by adding a trailing newline to frozen gold inputs).
    atomic_write_text(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def open_readonly_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open a short-lived, explicitly read-only/query-only SQLite connection."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    # quote(..., safe='/') retains path separators while protecting URI syntax.
    uri = "file:" + quote(path.as_posix(), safe="/:_") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA busy_timeout=3000")
    con.execute("PRAGMA temp_store=MEMORY")
    return con


def runtime_artifact_signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    root = Path(root)
    rows: list[tuple[str, int, int]] = []
    for rel in RUNTIME_ARTIFACTS:
        path = root / rel
        if not path.exists():
            rows.append((rel, -1, -1))
            continue
        st = path.stat()
        rows.append((rel, int(st.st_size), int(st.st_mtime_ns)))
    return tuple(rows)


def signature_digest(signature: tuple[tuple[str, int, int], ...]) -> str:
    raw = json.dumps(signature, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_runtime_artifacts(root: Path, *, require_current_authority: bool = True) -> dict[str, Any]:
    root = Path(root)
    errors: list[str] = []
    artifact_rows: list[dict[str, Any]] = []

    for rel in RUNTIME_ARTIFACTS:
        path = root / rel
        exists = path.is_file()
        row = {"path": rel, "exists": exists, "bytes": path.stat().st_size if exists else None}
        artifact_rows.append(row)
        if not exists:
            errors.append(f"missing:{rel}")
        elif path.stat().st_size <= 0:
            errors.append(f"empty:{rel}")

    json_checks: dict[str, Any] = {}
    for rel, expected in SCHEMA_VERSION_EXPECTATIONS.items():
        path = root / rel
        if not path.is_file():
            json_checks[rel] = {"passed": False, "reason": "missing"}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            actual = data.get("schemaVersion") if isinstance(data, dict) else None
            ok = actual == expected
            json_checks[rel] = {"passed": ok, "expected": expected, "actual": actual}
            if not ok:
                errors.append(f"schema_version:{rel}:expected={expected}:actual={actual}")
        except Exception as exc:
            json_checks[rel] = {"passed": False, "reason": f"{type(exc).__name__}:{exc}"}
            errors.append(f"invalid_json:{rel}")

    # Parse the remaining serving-critical JSON too, even when it has no formal
    # schemaVersion field yet.  A truncated JSON file must block startup.
    schema_paths = set(SCHEMA_VERSION_EXPECTATIONS)
    for rel in RUNTIME_ARTIFACTS:
        if not rel.endswith(".json") or rel in schema_paths:
            continue
        path = root / rel
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            errors.append(f"invalid_json:{rel}")

    sqlite_result: dict[str, Any] = {"passed": False}
    db = root / "data/index/rules.sqlite"
    if db.is_file():
        try:
            con = open_readonly_sqlite(db)
            try:
                quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
                user_version = int(con.execute("PRAGMA user_version").fetchone()[0])
                doc_count = int(con.execute("SELECT COUNT(*) FROM docs_meta").fetchone()[0])
                fts_count = int(con.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0])
            finally:
                con.close()
            sqlite_result = {
                "passed": quick == "ok" and user_version == INDEX_SCHEMA_VERSION and doc_count > 0 and fts_count > 0,
                "quickCheck": quick,
                "userVersion": user_version,
                "expectedUserVersion": INDEX_SCHEMA_VERSION,
                "docCount": doc_count,
                "ftsCount": fts_count,
            }
            if quick != "ok":
                errors.append("sqlite_quick_check_failed")
            if user_version != INDEX_SCHEMA_VERSION:
                errors.append(f"sqlite_schema_version:expected={INDEX_SCHEMA_VERSION}:actual={user_version}")
            if doc_count <= 0 or fts_count <= 0:
                errors.append("sqlite_index_empty")
        except Exception as exc:
            sqlite_result = {"passed": False, "reason": f"{type(exc).__name__}:{exc}"}
            errors.append("sqlite_open_or_integrity_failed")

    version_integrity = validate_rule_version_integrity(root)
    if not version_integrity.get("passed"):
        errors.append("rule_version_integrity_failed")
    overlay_integrity = validate_current_overlays(root)
    if not overlay_integrity.get("passed"):
        errors.append("current_overlay_integrity_failed")
    authority = load_authority_status(root)
    if require_current_authority and not authority.get("currentRulesComplete"):
        errors.append("current_authority_incomplete")

    sig = runtime_artifact_signature(root)
    result = {
        "schemaVersion": RUNTIME_SCHEMA_VERSION,
        "passed": not errors,
        "errors": sorted(set(errors)),
        "artifactCount": len(RUNTIME_ARTIFACTS),
        "artifacts": artifact_rows,
        "schemaChecks": json_checks,
        "sqlite": sqlite_result,
        "ruleVersionIntegrity": {"passed": bool(version_integrity.get("passed")), "errors": list(version_integrity.get("errors") or [])},
        "currentOverlayIntegrity": {"passed": bool(overlay_integrity.get("passed")), "errors": list(overlay_integrity.get("errors") or [])},
        "authority": {"currentRulesComplete": bool(authority.get("currentRulesComplete")), "missing": list(authority.get("missing") or [])},
        "snapshotId": signature_digest(sig),
        "networkRequiredForServing": False,
    }
    return result


@dataclass
class RuntimeArtifactGuard:
    root: Path
    require_current_authority: bool = True

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self._lock = threading.RLock()
        report = validate_runtime_artifacts(self.root, require_current_authority=self.require_current_authority)
        if not report.get("passed"):
            raise RuntimeError("runtime integrity failure: " + "; ".join(report.get("errors") or []))
        self._startup_report = report
        self._signature = runtime_artifact_signature(self.root)
        self._snapshot_id = signature_digest(self._signature)

    @property
    def snapshot_id(self) -> str:
        with self._lock:
            return self._snapshot_id

    def unchanged(self) -> bool:
        with self._lock:
            return runtime_artifact_signature(self.root) == self._signature

    def assert_unchanged(self) -> None:
        if not self.unchanged():
            raise RuntimeError("runtime_snapshot_changed")

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            current = runtime_artifact_signature(self.root)
            unchanged = current == self._signature
            return {
                "schemaVersion": RUNTIME_SCHEMA_VERSION,
                "startupValidated": True,
                "snapshotId": self._snapshot_id,
                "snapshotCurrent": unchanged,
                "degraded": not unchanged,
                "networkRequiredForServing": False,
                "sqlite": dict(self._startup_report.get("sqlite") or {}),
                "authority": dict(self._startup_report.get("authority") or {}),
            }


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class BoundedLruCache(Generic[K, V]):
    """Small thread-safe cache for deterministic read-only API results.

    Values are deep-copied on both set and get so callers cannot mutate the cached
    object shared with other threads.  Adjudication/LLM output is intentionally not
    cached by ProductApiService.
    """

    def __init__(self, max_entries: int = DEFAULT_CACHE_ENTRIES):
        if int(max_entries) < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = int(max_entries)
        self._lock = threading.RLock()
        self._items: OrderedDict[K, V] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: K) -> tuple[bool, V | None]:
        with self._lock:
            if key not in self._items:
                self._misses += 1
                return False, None
            self._hits += 1
            value = self._items.pop(key)
            self._items[key] = value
            return True, copy.deepcopy(value)

    def set(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._items:
                self._items.pop(key)
            self._items[key] = copy.deepcopy(value)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
                self._evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "maxEntries": self.max_entries,
                "entries": len(self._items),
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
            }
