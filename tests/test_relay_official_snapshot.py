import json
import unittest
from unittest.mock import MagicMock, patch

from scripts.relay_official_snapshot import dispatch


class RelayOfficialSnapshotTests(unittest.TestCase):
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
        self.assertIn("--json", command)
        body = json.loads(runner.call_args.kwargs["input"])
        self.assertEqual("encoded", body["snapshot_gzip_base64"])
        self.assertEqual("a" * 64, body["snapshot_sha256"])
        self.assertTrue(runner.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
