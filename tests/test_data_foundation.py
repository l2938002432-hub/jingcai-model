from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path

from jingcai.identity import AmbiguousMatchError, MatchNotFoundError, TeamAliases, resolve_match
from jingcai.manifest import (
    build_dataset_manifest,
    build_manifest,
    manifest_sha256,
    sha256_file,
    validate_dataset_manifest,
)
from jingcai.providers.football_data import FootballDataError, load_football_data_csv
from jingcai.providers.manual import ManualImportError, load_manual_json

FIXTURES = Path(__file__).parent / "fixtures"


class FootballDataTests(unittest.TestCase):
    def test_imports_unified_schema(self) -> None:
        rows = list(load_football_data_csv(FIXTURES / "football_data.csv", season="2025/26", source_timezone=timezone(timedelta(hours=1))))
        self.assertEqual(rows[0], {
            "provider_match_id": "E0:2025/26:16/08/2025:Liverpool:Bournemouth",
            "competition": "E0", "season": "2025/26", "kickoff_utc": "2025-08-16T11:30:00Z",
            "home_team": "Liverpool", "away_team": "Bournemouth", "home_goals": 2, "away_goals": 1,
        })

    def test_missing_result_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            path.write_text("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/01/2025,A,B,,1\n", encoding="utf-8")
            with self.assertRaises(FootballDataError):
                list(load_football_data_csv(path, season="2024/25"))


class ManualTests(unittest.TestCase):
    def test_json_import(self) -> None:
        row = list(load_manual_json(FIXTURES / "manual.json"))[0]
        self.assertEqual(row["provider_match_id"], "jc-1")

    def test_non_utc_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('[{"provider_match_id":"1","competition":"x","season":"s","kickoff_utc":"2025-01-01T00:00:00+08:00","home_team":"a","away_team":"b","home_goals":0,"away_goals":0}]', encoding="utf-8")
            with self.assertRaises(ManualImportError):
                list(load_manual_json(path))


class IdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aliases = TeamAliases({"Liverpool": ["利物浦"], "Bournemouth": ["伯恩茅斯"]})
        self.target = {"competition": "EPL", "kickoff_utc": "2025-08-16T11:30:00Z", "home_team": "利物浦", "away_team": "伯恩茅斯"}
        self.candidate = {"provider_match_id": "fd-1", "competition": "EPL", "kickoff_utc": "2025-08-16T11:32:00Z", "home_team": "Liverpool", "away_team": "Bournemouth"}

    def test_triple_match_with_aliases(self) -> None:
        self.assertIs(resolve_match(self.target, [self.candidate], aliases=self.aliases), self.candidate)

    def test_wrong_competition_is_not_a_match(self) -> None:
        bad = dict(self.candidate, competition="FAC")
        with self.assertRaises(MatchNotFoundError):
            resolve_match(self.target, [bad], aliases=self.aliases)

    def test_ambiguity_is_rejected(self) -> None:
        duplicate = dict(self.candidate, provider_match_id="fd-2")
        with self.assertRaises(AmbiguousMatchError):
            resolve_match(self.target, [self.candidate, duplicate], aliases=self.aliases)

    def test_alias_collision_is_rejected(self) -> None:
        with self.assertRaises(AmbiguousMatchError):
            TeamAliases({"A": ["same"], "B": ["same"]})


class ManifestTests(unittest.TestCase):
    def test_file_and_manifest_hashes_are_stable(self) -> None:
        path = FIXTURES / "manual.json"
        self.assertEqual(sha256_file(path), hashlib.sha256(path.read_bytes()).hexdigest())
        one = build_manifest([path], base_dir=FIXTURES)
        two = build_manifest([path], base_dir=FIXTURES)
        self.assertEqual(one, two)
        self.assertEqual(manifest_sha256(one), manifest_sha256(two))
        self.assertEqual(one["files"][0]["path"], "manual.json")

    def test_versioned_manifest_records_provenance_and_detects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "matches.jsonl"
            path.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
            manifest = build_dataset_manifest(
                [path], base_dir=root, code_revision="abc123", filters={"season": "2025/26"},
                generated_at="2026-08-01T00:00:00Z", record_counter=lambda p: len(p.read_text(encoding="utf-8").splitlines()),
            )
            self.assertEqual(manifest.files[0].bytes, path.stat().st_size)
            self.assertEqual(manifest.files[0].records, 2)
            self.assertEqual(manifest.code_revision, "abc123")
            validate_dataset_manifest(manifest, base_dir=root)
            path.write_text('{"id": 1}\n{"id": 3}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input files changed"):
                validate_dataset_manifest(manifest, base_dir=root)

    def test_versioned_manifest_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "matches.csv"
            path.write_text("a\n", encoding="utf-8")
            manifest = build_dataset_manifest(
                [path], base_dir=root, code_revision="abc123", generated_at="2026-08-01T00:00:00Z",
            )
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                validate_dataset_manifest(manifest, base_dir=root)


if __name__ == "__main__":
    unittest.main()
