"""Input adapters for external and manually supplied match data."""

from .football_data import load_football_data_csv
from .manual import load_manual_csv, load_manual_json

__all__ = ["load_football_data_csv", "load_manual_csv", "load_manual_json"]
