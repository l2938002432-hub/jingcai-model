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
    def test_dispatch_sends_snapshot_via_stdin_not_command_line(
        self, _fetch: MagicMock, _encode: MagicMock, _gh: MagicMock
    ) -> None:
        runner = MagicMock()
        runner.return_value.stdout = "https://example.invalid/run"
        result = dispatch(repository="owner/repo", runner=runner)
        self.assertEqual("https://example.invalid/run", result)
        command = runner.call_args.args[0]
        self.assertNotIn("encoded", command)
        self.assertEqual("api", command[1])
        self.assertIn("--input", command)
        body = json.loads(runner.call_args.kwargs["input"])
        self.assertEqual("encoded", body["inputs"]["snapshot_gzip_base64"])
        self.assertEqual("a" * 64, body["inputs"]["snapshot_sha256"])
        self.assertEqual("main", body["ref"])
        self.assertTrue(runner.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
