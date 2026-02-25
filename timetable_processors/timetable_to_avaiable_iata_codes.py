import json
import logging
from pathlib import Path
from typing import Set, List

from kiwiflight.logging_config import setup_logging

# --- Configuration ---
SOURCE_IATA_CODES: List[str] = ['POZ', 'KTW', 'WRO']
TIMETABLES_DIR: Path = Path('../timetables')
OUTPUT_DIR: Path = Path('../airport_iata_codes')

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def extract_unique_iata_codes(timetable_path: Path) -> Set[str]:
    """
    Reads a timetable JSON file and extracts a set of unique IATA codes.

    Args:
        timetable_path: The path to the timetable JSON file.

    Returns:
        A set of unique IATA codes from arrivals and departures, or an empty set if an error occurs.
    """
    try:
        with timetable_path.open('r', encoding='utf-8') as f:
            timetable = json.load(f)
        arrivals = set(timetable.get('arrivals', []))
        departures = set(timetable.get('departures', []))
        return arrivals | departures
    except FileNotFoundError:
        logging.warning("Timetable file not found: %s", timetable_path)
    except json.JSONDecodeError:
        logging.error("Error decoding JSON from file: %s", timetable_path)
    return set()


def save_iata_codes(iata_codes: Set[str], output_path: Path) -> None:
    """
    Saves a sorted list of IATA codes to a text file.

    Args:
        iata_codes: A set of IATA codes to save.
        output_path: The path to the output text file.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('w', encoding='utf-8') as f:
            for code in sorted(iata_codes):
                f.write(f"{code}\n")
        logging.info("Successfully saved %d IATA codes to %s", len(iata_codes), output_path)
    except IOError as e:
        logging.error("Could not write to file %s: %s", output_path, e)


def main():
    """
    Main function to process timetables for a list of source IATA codes.
    """
    setup_logging()
    for iata in SOURCE_IATA_CODES:
        logging.info("Processing IATA code: %s", iata)
        timetable_file = TIMETABLES_DIR / f"{iata}_timetable.json"
        if unique_iata_codes := extract_unique_iata_codes(timetable_file):
            output_file = OUTPUT_DIR / f"{iata}_iata_codes.txt"
            save_iata_codes(unique_iata_codes, output_file)


if __name__ == '__main__':
    main()
