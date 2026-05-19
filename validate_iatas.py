#!/usr/bin/env python3
"""Validate that all IATA codes from airport_iata_codes/ exist in airports_to_iata_mapping.json.

Run before scraping to catch missing mappings early:

    uv run python validate_iatas.py

If any IATA codes are missing from the mapping, the script prints them and exits
with code 1 — you should add the missing city→IATA entries to
data/airports_to_iata_mapping.json before running the scraper.
"""

import json
import logging
import sys
from pathlib import Path

from kiwiflight.logging_config import setup_logging

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
IATA_CODES_DIR = ROOT / "airport_iata_codes"
MAPPING_FILE = ROOT / "data" / "airports_to_iata_mapping.json"


def load_mapping_iatas() -> set[str]:
    """Return the set of IATA codes present in airports_to_iata_mapping.json."""
    with open(MAPPING_FILE, "rt", encoding="utf-8") as f:
        city_to_iata: dict[str, str] = json.load(f)
    return set(city_to_iata.values())


def load_all_airport_iatas() -> dict[str, set[str]]:
    """Return {filename: set_of_iata_codes} for every *_iata_codes.txt file."""
    result: dict[str, set[str]] = {}
    for path in sorted(IATA_CODES_DIR.glob("*_iata_codes.txt")):
        codes = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
        result[path.name] = codes
    return result


def main() -> int:
    setup_logging()

    if not MAPPING_FILE.exists():
        logger.error("Mapping file not found: %s", MAPPING_FILE)
        return 1

    known_iatas = load_mapping_iatas()
    airport_files = load_all_airport_iatas()

    all_missing: dict[str, set[str]] = {}
    for filename, codes in airport_files.items():
        missing = codes - known_iatas
        if missing:
            all_missing[filename] = missing

    if not all_missing:
        logger.info("✅ All IATA codes from airport_iata_codes/ are present in airports_to_iata_mapping.json.")
        return 0

    # Collect unique missing across all files
    unique_missing = sorted(set().union(*all_missing.values()))

    logger.warning("⚠️  Missing IATA codes found!")
    logger.warning(
        "The following IATA codes appear in airport_iata_codes/ but are NOT in %s",
        MAPPING_FILE.relative_to(ROOT),
    )

    for filename, missing in sorted(all_missing.items()):
        logger.warning("  %s:", filename)
        for code in sorted(missing):
            logger.warning("    - %s", code)

    logger.warning("Total unique missing codes: %d  (%s)", len(unique_missing), ", ".join(unique_missing))
    logger.warning("Please add the missing city→IATA entries to data/airports_to_iata_mapping.json")
    logger.warning("so the scraper can resolve city names for fallback airport selection.")
    logger.warning('Example entry:  "City Name": "IATA"')

    return 1


if __name__ == "__main__":
    sys.exit(main())
