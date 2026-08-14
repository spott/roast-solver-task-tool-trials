"""Synthetic-fixture loader. No values here are empirical calibration."""
from pathlib import Path
import json

def load_synthetic_fixture(path=None):
    path=Path(path) if path else Path(__file__).parents[2]/"fixtures"/"synthetic_calibration.json"
    data=json.loads(path.read_text())
    if data.get("provenance")!="synthetic": raise ValueError("fixture must be explicitly synthetic")
    return data
