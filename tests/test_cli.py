import unittest
from argparse import Namespace

from jingcai.__main__ import _load_history


class CliTests(unittest.TestCase):
    def test_utc_history_import_does_not_require_tzdata(self) -> None:
        args = Namespace(
            csv="tests/fixtures/football_data.csv",
            season="2025-26",
            competition=None,
            source_timezone="UTC",
        )
        self.assertEqual(2, len(_load_history(args)))


if __name__ == "__main__":
    unittest.main()
