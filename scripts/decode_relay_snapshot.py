"""Decode a workflow-dispatch snapshot without placing its value on a command line."""

from __future__ import annotations

import os
from pathlib import Path

from jingcai.providers.sporttery import save_snapshot
from jingcai.snapshot_relay import decode_snapshot


def main() -> int:
    encoded = os.environ.get("SPORTTERY_SNAPSHOT_GZIP_BASE64", "")
    sha256 = os.environ.get("SPORTTERY_SNAPSHOT_SHA256", "")
    output = Path(os.environ.get("SPORTTERY_SNAPSHOT_OUTPUT", "data/snapshots/relay.json"))
    save_snapshot(decode_snapshot(encoded, sha256), output)
    print(f"validated relayed snapshot written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
