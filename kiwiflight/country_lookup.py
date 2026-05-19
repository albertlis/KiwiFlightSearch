"""Utility: look up Polish country name for a given IATA airport code.
The mapping lives in ``data/iata_to_country.json`` so it can be updated
without touching Python code.
"""

from __future__ import annotations
import json
from pathlib import Path

_DATA_FILE = Path(__file__).parent.parent / "data" / "iata_to_country.json"
# Loaded once at import time
_IATA_TO_COUNTRY: dict[str, str] = json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def get_country(iata: str) -> str:
    """Return the Polish country name for *iata*, or an empty string if unknown."""
    return _IATA_TO_COUNTRY.get(iata.upper(), "")
