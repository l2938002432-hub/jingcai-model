from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class AppendOnlyJsonlStore:
    """Small append-only store used by the free local/cloud MVP."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: Mapping[str, Any]) -> str:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        envelope = {"sha256": digest, "record": dict(record)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n")
        return digest

    def read_verified(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            envelope = json.loads(line)
            record = envelope["record"]
            payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            actual = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if actual != envelope["sha256"]:
                raise ValueError(f"checksum mismatch at line {line_number}")
            result.append(record)
        return result


def manifest_hash(records: Iterable[Mapping[str, Any]]) -> str:
    canonical = "\n".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for item in records
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

