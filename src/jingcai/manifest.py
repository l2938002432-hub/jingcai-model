"""Versioned, reproducible manifests for imported datasets.

The manifest deliberately uses only the standard library.  It records the
*exact bytes* used by an experiment, rather than attempting to infer a schema
or parse every source format.  Callers may provide a record counter when a
format-specific count is useful; no unsafe automatic CSV/JSON parsing occurs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


SCHEMA_VERSION = 1
RecordCounter = Callable[[Path], int | None]


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading the full dataset into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_timestamp(value: str | datetime | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        value = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("generated_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_object(value: Mapping[str, Any] | None, *, field: str) -> dict[str, Any]:
    result = dict(value or {})
    try:
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    return result


def _relative_path(path: Path, base: Path | None) -> str:
    if base is None:
        return path.name
    try:
        return path.relative_to(base).as_posix()
    except ValueError as exc:
        raise ValueError(f"dataset file is outside base_dir: {path}") from exc


@dataclass(frozen=True)
class DatasetFile:
    """An immutable fingerprint of one dataset input."""

    path: str
    sha256: str
    bytes: int
    records: int | None = None

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DatasetManifest:
    """The minimum evidence required to reproduce a training dataset."""

    generated_at: str
    code_revision: str
    filters: Mapping[str, Any]
    files: tuple[DatasetFile, ...]
    schema_version: int = SCHEMA_VERSION
    algorithm: str = "sha256"

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm,
            "generated_at": self.generated_at,
            "code_revision": self.code_revision,
            "filters": dict(self.filters),
            "files": [entry.to_record() for entry in self.files],
        }

    @property
    def sha256(self) -> str:
        return manifest_sha256(self.to_record())

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "DatasetManifest":
        required = {"generated_at", "code_revision", "filters", "files"}
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"dataset manifest missing fields: {', '.join(missing)}")
        filters = record["filters"]
        if not isinstance(filters, Mapping) or not isinstance(record["files"], list):
            raise ValueError("dataset manifest filters/files have invalid types")
        entries = []
        for item in record["files"]:
            if not isinstance(item, Mapping):
                raise ValueError("dataset manifest file entry must be an object")
            try:
                path = str(item["path"])
                digest = str(item["sha256"])
                size = int(item["bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("dataset manifest file entry is invalid") from exc
            count = item.get("records")
            if count is not None:
                try:
                    count = int(count)
                except (TypeError, ValueError) as exc:
                    raise ValueError("dataset manifest records must be an integer or null") from exc
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
                raise ValueError("dataset manifest sha256 is invalid")
            relative = Path(path)
            if not path or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("dataset manifest file path must be a safe relative path")
            if size < 0 or count is not None and count < 0:
                raise ValueError("dataset manifest bytes/records cannot be negative")
            entries.append(DatasetFile(path=path, sha256=digest, bytes=size, records=count))
        return cls(
            generated_at=_utc_timestamp(str(record["generated_at"])),
            code_revision=str(record["code_revision"]),
            filters=_json_object(filters, field="filters"),
            files=tuple(entries),
            schema_version=int(record.get("schema_version", SCHEMA_VERSION)),
            algorithm=str(record.get("algorithm", "sha256")),
        )


def build_dataset_manifest(
    paths: Iterable[str | Path],
    *,
    base_dir: str | Path | None = None,
    code_revision: str,
    filters: Mapping[str, Any] | None = None,
    generated_at: str | datetime | None = None,
    record_counter: RecordCounter | None = None,
) -> DatasetManifest:
    """Create a manifest, rejecting absent, duplicate, or ambiguous inputs."""
    base = Path(base_dir).resolve() if base_dir is not None else None
    entries: list[DatasetFile] = []
    seen: set[str] = set()
    for supplied in paths:
        path = Path(supplied).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        name = _relative_path(path, base)
        if name in seen:
            raise ValueError(f"duplicate dataset path: {name}")
        seen.add(name)
        count = record_counter(path) if record_counter is not None else None
        if count is not None and (not isinstance(count, int) or count < 0):
            raise ValueError("record_counter must return a non-negative integer or None")
        entries.append(DatasetFile(name, sha256_file(path), path.stat().st_size, count))
    if not entries:
        raise ValueError("dataset manifest requires at least one input file")
    entries.sort(key=lambda entry: entry.path)
    return DatasetManifest(
        generated_at=_utc_timestamp(generated_at),
        code_revision=str(code_revision),
        filters=_json_object(filters, field="filters"),
        files=tuple(entries),
    )


def validate_dataset_manifest(
    manifest: DatasetManifest | Mapping[str, Any], *, base_dir: str | Path,
    record_counter: RecordCounter | None = None,
) -> DatasetManifest:
    """Fail closed unless every recorded input still has identical bytes and size.

    Record counts are additionally checked only when the same explicit,
    format-aware ``record_counter`` is supplied.  This keeps validation safe
    for opaque files while allowing callers to verify row counts when needed.
    """
    expected = manifest if isinstance(manifest, DatasetManifest) else DatasetManifest.from_record(manifest)
    base = Path(base_dir).resolve()
    actual = build_dataset_manifest(
        [base / entry.path for entry in expected.files],
        base_dir=base,
        code_revision=expected.code_revision,
        filters=expected.filters,
        generated_at=expected.generated_at,
        record_counter=record_counter,
    )
    expected_fingerprints = tuple((entry.path, entry.sha256, entry.bytes) for entry in expected.files)
    actual_fingerprints = tuple((entry.path, entry.sha256, entry.bytes) for entry in actual.files)
    if actual_fingerprints != expected_fingerprints:
        raise ValueError("dataset manifest validation failed: input files changed")
    if record_counter is not None and actual.files != expected.files:
        raise ValueError("dataset manifest validation failed: record counts changed")
    return expected


def build_manifest(paths: Iterable[str | Path], *, base_dir: str | Path | None = None) -> dict[str, object]:
    """Backward-compatible lightweight file fingerprint helper."""
    base = Path(base_dir).resolve() if base_dir is not None else None
    entries = []
    for supplied in paths:
        path = Path(supplied).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        entries.append({"path": _relative_path(path, base), "size": path.stat().st_size, "sha256": sha256_file(path)})
    entries.sort(key=lambda item: str(item["path"]))
    return {"algorithm": "sha256", "files": entries}


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
