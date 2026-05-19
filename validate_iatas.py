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
IATA_TO_COUNTRY_FILE = ROOT / "data" / "iata_to_country.json"


def load_mapping_iatas() -> set[str]:
    """Return the set of IATA codes present in airports_to_iata_mapping.json."""
    with MAPPING_FILE.open("r", encoding="utf-8") as f:
        city_to_iata: dict[str, str] = json.load(f)
    # Normalize to uppercase to avoid case mismatches
    return {v.upper() for v in city_to_iata.values()}


def load_all_airport_iatas() -> dict[str, set[str]]:
    """Return {filename: set_of_iata_codes} for every *_iata_codes.txt file."""
    result: dict[str, set[str]] = {}
    for path in sorted(IATA_CODES_DIR.glob("*_iata_codes.txt")):
        # Normalize codes to uppercase to be consistent with mapping files
        codes = {line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
        result[path.name] = codes
    return result


def load_iata_to_country_iatas() -> set[str]:
    """Return the set of IATA codes present as keys in iata_to_country.json.

    If the file is missing, return an empty set (the caller will handle reporting).
    """
    if not IATA_TO_COUNTRY_FILE.exists():
        return set()
    with IATA_TO_COUNTRY_FILE.open("r", encoding="utf-8") as f:
        iata_map: dict[str, str] = json.load(f)
    return {k.upper() for k in iata_map}


def _report_missing(mapping_path: Path, missing: dict[str, set[str]], example_msg: str, label: str) -> None:
    """Log a nicely formatted report for missing IATA codes.

    Separated out to keep `main()` small and reduce branching complexity.
    """
    if not missing:
        return

    unique_missing = sorted(set().union(*missing.values()))

    logger.warning(f"⚠️  Missing IATA codes found in {mapping_path.relative_to(ROOT)}!")
    for filename, codes in sorted(missing.items()):
        logger.warning(f"  {filename}:")
        for code in sorted(codes):
            logger.warning(f"    - {code}")

    logger.warning(f"Total unique missing codes in {label}: {len(unique_missing)}  ({', '.join(unique_missing)})")
    logger.warning(example_msg)


def main() -> int:
    setup_logging()

    if not MAPPING_FILE.exists():
        logger.error(f"Mapping file not found: {MAPPING_FILE}")
        return 1

    known_iatas = load_mapping_iatas()
    country_iatas = load_iata_to_country_iatas()
    if not country_iatas:
        logger.warning(
            f"Warning: {IATA_TO_COUNTRY_FILE.relative_to(ROOT)} not found or empty — country coverage check will be skipped."
        )

    airport_files = load_all_airport_iatas()

    # Build missing mappings with comprehensions to reduce branching inside main().
    all_missing_mapping = {
        filename: (codes - known_iatas) for filename, codes in airport_files.items() if (codes - known_iatas)
    }

    all_missing_country = (
        {filename: (codes - country_iatas) for filename, codes in airport_files.items() if (codes - country_iatas)}
        if country_iatas
        else {}
    )

    if not all_missing_mapping and not all_missing_country:
        logger.info("✅ All IATA codes from airport_iata_codes/ are present in mapping and country data.")
        return 0

    if all_missing_mapping:
        _report_missing(
            MAPPING_FILE,
            all_missing_mapping,
            'Please add the missing city→IATA entries to data/airports_to_iata_mapping.json\nExample entry:  "City Name": "IATA"',
            "mapping",
        )

    if all_missing_country:
        _report_missing(
            IATA_TO_COUNTRY_FILE,
            all_missing_country,
            "Please add the missing IATA→country entries to data/iata_to_country.json",
            "country mapping",
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
