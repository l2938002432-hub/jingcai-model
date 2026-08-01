"""Fetch the official feed locally and dispatch the validated cloud workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from jingcai.providers.sporttery import fetch_sporttery_payload  # noqa: E402
from jingcai.snapshot_relay import encode_snapshot  # noqa: E402


def _github_cli() -> str:
    if executable := shutil.which("gh"):
        return executable
    installed = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if installed.exists():
        return str(installed)
    raise RuntimeError("GitHub CLI is not installed")


def dispatch(
    *,
    repository: str,
    branch: str = "main",
    snapshot_json: Path | None = None,
    runner: object = subprocess.run,
) -> str:
    return dispatch_details(
        repository=repository,
        branch=branch,
        snapshot_json=snapshot_json,
        runner=runner,
    )["message"]


def dispatch_details(
    *,
    repository: str,
    branch: str = "main",
    snapshot_json: Path | None = None,
    runner: object = subprocess.run,
) -> dict[str, object]:
    """Dispatch a snapshot and return only safe operational metadata.

    The snapshot itself deliberately never appears in stdout: it can contain
    the complete official pool.  The content hash is enough to correlate the
    local relay with the cloud workflow and audit records.
    """
    payload = (
        json.loads(snapshot_json.read_text(encoding="utf-8"))
        if snapshot_json is not None
        else fetch_sporttery_payload()
    )
    encoded, digest = encode_snapshot(payload)
    canonical_size = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    try:
        completed = runner(
            [
                _github_cli(), "workflow", "run", "daily.yml", "--repo", repository,
                "--ref", branch,
                "--raw-field", f"snapshot_gzip_base64={encoded}",
                "--raw-field", f"snapshot_sha256={digest}",
            ],
            text=True, capture_output=True, check=True, cwd=PROJECT_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "GitHub dispatch failed").strip()
        raise RuntimeError(f"GitHub workflow dispatch failed: {detail}") from exc
    message = str(getattr(completed, "stdout", "")).strip() or "cloud workflow dispatched"
    matches = payload.get("value", {}).get("matchInfoList", [])
    return {
        "event": "relay_dispatched",
        "repository": repository,
        "ref": branch,
        "snapshot_sha256": digest,
        "snapshot_bytes": canonical_size,
        "fixture_count": len(matches) if isinstance(matches, list) else None,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo", default="l2938002432-hub/jingcai-model",
        help="GitHub repository receiving the validated public snapshot",
    )
    parser.add_argument("--ref", default="main")
    parser.add_argument(
        "--snapshot-json", type=Path,
        help="Use a locally fetched official JSON snapshot instead of Python network access",
    )
    parser.add_argument(
        "--diagnostic-json",
        action="store_true",
        help="Emit safe dispatch metadata for the scheduled relay wrapper",
    )
    args = parser.parse_args()
    details = dispatch_details(repository=args.repo, branch=args.ref, snapshot_json=args.snapshot_json)
    if args.diagnostic_json:
        print(json.dumps(details, ensure_ascii=False, sort_keys=True))
    else:
        print(details["message"] or "cloud workflow dispatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
