"""Fetch the official feed locally and dispatch the validated cloud workflow."""

from __future__ import annotations

import argparse
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
    payload = (
        json.loads(snapshot_json.read_text(encoding="utf-8"))
        if snapshot_json is not None
        else fetch_sporttery_payload()
    )
    encoded, digest = encode_snapshot(payload)
    workflow_inputs = json.dumps(
        {
            "ref": branch,
            "inputs": {"snapshot_gzip_base64": encoded, "snapshot_sha256": digest},
        },
        separators=(",", ":"),
    )
    completed = runner(
        [
            _github_cli(),
            "api",
            "--method",
            "POST",
            f"repos/{repository}/actions/workflows/daily.yml/dispatches",
            "--input",
            "-",
        ],
        input=workflow_inputs,
        text=True,
        capture_output=True,
        check=True,
        cwd=PROJECT_ROOT,
    )
    return str(getattr(completed, "stdout", "")).strip() or "cloud workflow dispatched"


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
    args = parser.parse_args()
    url = dispatch(repository=args.repo, branch=args.ref, snapshot_json=args.snapshot_json)
    print(url or "cloud workflow dispatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
