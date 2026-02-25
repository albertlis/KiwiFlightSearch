import json
import logging
from collections import defaultdict

from bs4 import BeautifulSoup

from kiwiflight.logging_config import setup_logging

logger = logging.getLogger(__name__)

WEEKDAY_MAP = {1: 'Pn', 2: 'Wt', 3: 'Śr', 4: 'Cz', 5: 'Pt', 6: 'So', 7: 'Nd'}


class KatowiceTimetableScrapper:
    def __init__(self):
        self.arrivals_html_file = '../html_for_scrapping/KTW_timetable_arrivals.html'
        self.departures_html_file = '../html_for_scrapping/KTW_timetable_departures.html'
        logger.info("Loading airport to IATA mapping...")
        with open('../data/airports_to_iata_mapping.json', 'rt', encoding='utf-8') as f:
            self.airports_to_iata = json.load(f)

    def get_timetable(self, soup: BeautifulSoup) -> dict[str, list[dict[str, str]]]:
        logger.debug("Parsing timetable from soup")
        rows = soup.find_all('div', class_='timetable__row flight-board__row')
        timetable = defaultdict(list)

        for row in rows:
            destination = row.find('div', class_='flight-board__col--1').strong.text.strip()
            departure_time = row.find('div', class_='flight-board__col--3').strong.text.strip()
            arrival_time = row.find('div', class_='flight-board__col--4').strong.text.strip()
            dates = row.find('div', class_='flight-board__col--5').text.strip()
            days_operation_div = row.find('div', class_='flight-timetable__days-operation')
            days_of_operation = [WEEKDAY_MAP[int(strong.text.strip())] for strong in days_operation_div.find_all('strong')]
            start_date, end_date = dates.split(' - ')
            iata_code = self.airports_to_iata[destination]
            logger.debug(f"Processing flight to: {destination} ({iata_code})")
            timetable[iata_code].append(
                dict(
                    start_time=departure_time,
                    landing_time=arrival_time,
                    weekdays=days_of_operation,
                    start_date=start_date,
                    end_date=end_date
                )
            )
        logger.info(f"Processed {len(rows)} flight rows")
        return timetable

    def get_full_timetable(self):
        logger.info("Starting full timetable processing for KTW")
        with open(self.arrivals_html_file, 'rt', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, 'html.parser')
        arrivals_timetable = self.get_timetable(soup)

        with open(self.departures_html_file, 'rt', encoding='utf-8') as f:
            html = f.read()
        soup = BeautifulSoup(html, 'html.parser')
        departures_timetable = self.get_timetable(soup)
        return {
            'arrivals': arrivals_timetable,
            'departures': departures_timetable
        }


if __name__ == '__main__':
    setup_logging()
    logger.info("Starting KTW timetable processing")
    timetable = KatowiceTimetableScrapper().get_full_timetable()
    output_path = '../timetables/KTW_timetable.json'
    with open(output_path, 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved processed timetable to {output_path}")
