import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.relay_official_snapshot import dispatch


class RelayOfficialSnapshotTests(unittest.TestCase):
    @patch("scripts.relay_official_snapshot._github_cli", return_value="gh")
    @patch("scripts.relay_official_snapshot.encode_snapshot", return_value=("encoded", "b" * 64))
    @patch("scripts.relay_official_snapshot.fetch_sporttery_payload")
    def test_dispatch_can_use_a_local_official_snapshot(
        self, fetch: MagicMock, encode: MagicMock, _gh: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.return_value.stdout = "dispatched"
        payload = {"success": True, "value": {"matchInfoList": []}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                "dispatched",
                dispatch(repository="owner/repo", snapshot_json=path, runner=runner),
            )
        fetch.assert_not_called()
        encode.assert_called_once_with(payload)

    @patch("scripts.relay_official_snapshot._github_cli", return_value="gh")
    @patch("scripts.relay_official_snapshot.encode_snapshot", return_value=("encoded", "a" * 64))
    @patch(
        "scripts.relay_official_snapshot.fetch_sporttery_payload",
        return_value={"success": True, "value": {"matchInfoList": []}},
    )
    def test_dispatch_passes_public_snapshot_as_workflow_input(
        self, _fetch: MagicMock, _encode: MagicMock, _gh: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.return_value.stdout = "https://example.invalid/run"
        result = dispatch(repository="owner/repo", runner=runner)
        self.assertEqual("https://example.invalid/run", result)
        command = runner.call_args.args[0]
        self.assertEqual(["workflow", "run", "daily.yml"], command[1:4])
        self.assertIn("snapshot_gzip_base64=encoded", command)
        self.assertIn(f"snapshot_sha256={'a' * 64}", command)
        self.assertNotIn("input", runner.call_args.kwargs)
        self.assertTrue(runner.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
