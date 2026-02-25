import json
import logging
import re
from collections import defaultdict

from bs4 import BeautifulSoup

from kiwiflight.logging_config import setup_logging

logger = logging.getLogger(__name__)


class WroclawTimetableScrapper:
    def __init__(self):
        super().__init__()
        self.iata_regex = r'\[(\w{3})\]'

    def parse_html(self, file_path: str) -> dict[str, list[dict[str, str]]]:
        logger.info(f"Parsing HTML file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')

        timetable = defaultdict(list)
        flight_data_divs = soup.select('tr.n-flights__data-wrap.desktop')
        logger.info(f"Found {len(flight_data_divs)} flight data rows")

        for div in flight_data_divs:
            try:
                port_td = div.select_one('td.port')
                if not port_td:
                    continue
                port = port_td.text.strip()
                iata_code_match = re.search(self.iata_regex, port)
                iata_code = iata_code_match[1] if iata_code_match else None
                start_time = div.select_one('td.departure').text.strip()
                landing_time = div.select_one('td.arrival').text.strip()
                days_elements = div.select('td.days span.on.day')
                weekdays = [
                    day.text.strip() for day in days_elements
                    if day.text.strip()
                ]

                period_text = div.select_one('td.period').text.strip()
                period_text = re.sub(r'\s+', ' ', period_text)
                start_date, end_date = [p.strip() for p in period_text.split('-', 1)]
            except Exception as e:
                logger.error(f"Error parsing row: {e}")
                continue

            if iata_code:
                logger.debug(f"Adding flight for IATA: {iata_code}")
                timetable[iata_code].append(
                    dict(
                        start_time=start_time,
                        landing_time=landing_time,
                        weekdays=weekdays,
                        start_date=start_date,
                        end_date=end_date
                    )
                )
            else:
                logger.warning(f"Could not extract IATA code from port: {port}")
        logger.info(f"Finished parsing. Found {len(timetable)} unique IATA codes")
        return timetable

    def get_full_timetable(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        arrivals = self.parse_html('../html_for_scrapping/WRO_timetable_arrivals.html')
        departures = self.parse_html('../html_for_scrapping/WRO_timetable_departures.html')
        return {
            'arrivals': arrivals,
            'departures': departures
        }


if __name__ == '__main__':
    setup_logging()
    logger.info("Starting WRO timetable processing")
    timetable = WroclawTimetableScrapper().get_full_timetable()
    output_path = '../timetables/WRO_timetable.json'
    with open(output_path, 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved processed timetable to {output_path}")
