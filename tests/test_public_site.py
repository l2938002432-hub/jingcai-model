import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_public_site import build_public_site


PUBLIC_REPORT = {
    "schema_version": 1,
    "release_id": "run-123",
    "release_hash": "abc123",
    "report_date": "2026-07-26",
    "generated_at": "2026-07-26T10:30:00+08:00",
    "source_as_of": "2026-07-26T10:20:00+08:00",
    "fixtures": 8,
    "candidates": 2,
    "fixture_details": [],
    "candidate_details": [],
    "model_state": "PAPER_ONLY",
    "html": "report-2026-07-26.html",
    "raw_snapshot": "sporttery-2026-07-26.json",
    "personal_budget": 10000,
    "webhook": "secret",
}


class PublicSiteTests(unittest.TestCase):
    def _inputs(self, root: Path, report: dict | None = None) -> tuple[Path, Path]:
        html_path = root / "daily.html"
        json_path = root / "daily.json"
        html_path.write_text("<!doctype html><html><body>日报</body></html>", encoding="utf-8")
        json_path.write_text(json.dumps(report or PUBLIC_REPORT, ensure_ascii=False), encoding="utf-8")
        return html_path, json_path

    def test_builds_latest_dated_release_and_history_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path, json_path = self._inputs(root)
            site = root / "site"
            dated = build_public_site(html_path, json_path, site, "run-123")
            self.assertEqual(site / "reports" / "2026-07-26" / "run-123", dated)
            for path in (
                site / "index.html", site / "report.json",
                site / "matches" / "index.html", site / "candidates" / "index.html", site / "review" / "index.html",
                dated / "index.html", dated / "report.json",
                site / "reports" / "index.html", site / "reports" / "index.json",
            ):
                self.assertTrue(path.exists(), path)
            self.assertIn("2026-07-26/run-123/", (site / "reports" / "index.html").read_text(encoding="utf-8"))
            self.assertIn("收益复盘", (site / "review" / "index.html").read_text(encoding="utf-8"))

    def test_public_metadata_uses_a_strict_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path, json_path = self._inputs(root, dict(PUBLIC_REPORT, release_id="7"))
            site = root / "site"
            site.mkdir()
            (site / "raw-snapshot.json").write_text('{"raw":"leak"}', encoding="utf-8")
            (site / ".notification-dedupe.json").write_text('["leak"]', encoding="utf-8")
            (root / ".notification-dedupe.json").write_text('["secret"]', encoding="utf-8")
            (root / "sporttery-2026-07-26.json").write_text('{"raw":"secret"}', encoding="utf-8")
            build_public_site(html_path, json_path, site, "7")
            public = json.loads((site / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "schema_version", "release_id", "release_hash", "report_date",
                    "generated_at", "source_as_of", "fixtures", "candidates",
                    "fixture_details", "candidate_details", "model_state", "historical_path",
                },
                set(public),
            )
            serialized = json.dumps(public)
            for forbidden in ("personal_budget", "webhook", "raw_snapshot", "secret"):
                self.assertNotIn(forbidden, serialized)
            published_names = {path.name for path in site.rglob("*") if path.is_file()}
            self.assertNotIn(".notification-dedupe.json", published_names)
            self.assertNotIn("sporttery-2026-07-26.json", published_names)
            self.assertNotIn("raw-snapshot.json", published_names)

    def test_preserves_previous_releases_when_output_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path, json_path = self._inputs(root, dict(PUBLIC_REPORT, release_id="first"))
            site = root / "site"
            build_public_site(html_path, json_path, site, "first")
            html_path, json_path = self._inputs(root, dict(PUBLIC_REPORT, release_id="second"))
            build_public_site(html_path, json_path, site, "second")
            history = json.loads((site / "reports" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual({"first", "second"}, {row["release_id"] for row in history["reports"]})
            self.assertTrue((site / "reports" / "2026-07-26" / "first" / "index.html").exists())

    def test_rejects_unsafe_release_id_and_invalid_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path, json_path = self._inputs(root)
            with self.assertRaisesRegex(ValueError, "release_id"):
                build_public_site(html_path, json_path, root / "site", "../escape")
            invalid = dict(PUBLIC_REPORT, report_date="../../secret")
            html_path, json_path = self._inputs(root, invalid)
            with self.assertRaisesRegex(ValueError, "report_date"):
                build_public_site(html_path, json_path, root / "site", "safe")


if __name__ == "__main__":
    unittest.main()
