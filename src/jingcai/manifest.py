"""Reproducible file manifests for imported datasets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(paths: Iterable[str | Path], *, base_dir: str | Path | None = None) -> dict[str, object]:
    base = Path(base_dir).resolve() if base_dir is not None else None
    entries = []
    for supplied in paths:
        path = Path(supplied).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        name = path.relative_to(base).as_posix() if base is not None else path.name
        entries.append({"path": name, "size": path.stat().st_size, "sha256": sha256_file(path)})
    entries.sort(key=lambda item: str(item["path"]))
    return {"algorithm": "sha256", "files": entries}


def manifest_sha256(manifest: dict[str, object]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
