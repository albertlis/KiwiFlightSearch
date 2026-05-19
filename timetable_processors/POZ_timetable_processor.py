import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from kiwiflight.logging_config import setup_logging

logger = logging.getLogger(__name__)


class PoznanTimetableScrapper:
    def __init__(self):
        self.city_flights_group_class = "flightsTable__group"
        self.airport_name_class = "flightsTable__text--bold"
        self.flight_item_class = "flightsTable__item"
        self.start_time_label = "Godzina startu"
        self.landing_time_label = "Godzina lądowania"
        self.weekdays_label = "Dni tygodnia"
        self.start_date_label = "Od"
        self.end_date_label = "Do"

        self.iata_regex = r"\((\w{3})\)"

    def parse_html(self, file_path: str) -> dict[str, list[dict[str, str]]]:
        logger.info(f"Parsing HTML file: {file_path}")
        # use Path.open() per linter recommendations and to avoid builtin-open warnings
        path = Path(file_path)
        with path.open(encoding="utf-8") as file:
            soup = BeautifulSoup(file, "html.parser")

        timetable = defaultdict(list)
        groups = soup.find_all("div", class_=self.city_flights_group_class)
        for group_div in groups:
            airport_name = group_div.find("div", class_=self.airport_name_class).get_text(strip=True)
            iata_code_match = re.search(self.iata_regex, airport_name)
            iata_code = iata_code_match[1] if iata_code_match else "Unknown"
            logger.debug(f"Processing flights for: {airport_name} ({iata_code})")

            flights_div = group_div.find_all("div", class_=self.flight_item_class)

            for f_div in flights_div:
                # Safely extract adjacent text nodes; helper handles missing elements/whitespace
                start_time = self._get_label_value(f_div, self.start_time_label)
                landing_time = self._get_label_value(f_div, self.landing_time_label)

                weekdays_str = self._get_label_value(f_div, self.weekdays_label)
                weekdays = weekdays_str.split(", ") if weekdays_str else []

                start_date = self._get_label_value(f_div, self.start_date_label)
                end_date = self._get_label_value(f_div, self.end_date_label)

                timetable[iata_code].append(
                    {
                        "start_time": start_time,
                        "landing_time": landing_time,
                        "weekdays": weekdays,
                        "start_date": start_date,
                        "end_date": end_date,
                    }
                )
        logger.info(f"Processed {len(groups)} groups, found {len(timetable)} unique IATA codes")
        return timetable

    def get_full_timetable(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        logger.info("Starting full timetable processing for POZ")
        arrivals = self.parse_html("../html_for_scrapping/POZ_timetable_arrivals.html")
        departures = self.parse_html("../html_for_scrapping/POZ_timetable_departures.html")
        return {"arrivals": arrivals, "departures": departures}

    def _get_label_value(self, container: Tag, label: str) -> str:
        """Find a <span> whose .string equals `label` and return the stripped text
        of the next meaningful sibling. Returns empty string if not found.
        """
        if container is None:
            return ""

        # container.find may return Tag, NavigableString or None
        # After pretty-printing the HTML contains surrounding whitespace in span text,
        # so use a regex that allows optional whitespace around the label.
        label_tag: Tag | NavigableString | None = container.find(
            "span", string=re.compile(r"^\s*" + re.escape(label) + r"\s*$")
        )
        if not label_tag:
            return ""

        # Prefer next_sibling traversal to capture plain text nodes and skip
        # whitespace-only nodes.
        sib = label_tag.next_sibling
        # walk forward until we find a non-empty string or a Tag
        while sib is not None:
            if isinstance(sib, NavigableString):
                text = str(sib).strip()
                if text:
                    return text
            elif isinstance(sib, Tag):
                text = sib.get_text(strip=True)
                if text:
                    return text
            sib = getattr(sib, "next_sibling", None)

        # fallback to find_next_sibling(text=True)
        text_node = label_tag.find_next_sibling(text=True)
        return str(text_node).strip() if text_node else ""


if __name__ == "__main__":
    setup_logging()
    logger.info("Starting POZ timetable processing")
    timetable = PoznanTimetableScrapper().get_full_timetable()
    output_path = Path("../timetables/POZ_timetable.json")
    # write using Path.open to satisfy linters
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved processed timetable to {output_path}")
