import json
import re
from collections import defaultdict

from bs4 import BeautifulSoup


class WroclawTimetableScrapper:
    def __init__(self):
        super().__init__()
        self.iata_regex = r'\[(\w{3})\]'

    def parse_html(self, file_path: str) -> dict[str, list[dict[str, str]]]:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')

        timetable = defaultdict(list)
        flight_data_divs = soup.select('.flights__data.desktop')

        for div in flight_data_divs:
            try:
                port_div = div.select_one('.port .port_name')
                if not port_div:
                    continue
                port = port_div.text
                iata_code_match = re.search(self.iata_regex, port)
                iata_code = iata_code_match[1] if iata_code_match else None
                start_time = div.select_one('.departure div:last-child').text.strip()
                landing_time = div.select_one('.arrival div:last-child').text.strip()
                days_elements = div.select('.days .day span')
                weekdays = [
                    day.text.strip() for day in days_elements
                    if 'on' in day.get('class', []) and day.text.strip()
                ]

                period = div.select_one('.period div:last-child').text.strip()
                start_date, end_date = period.split(' - ')
            except Exception as e:
                print('Error:', e)
                continue

            if iata_code:
                timetable[iata_code].append(
                    dict(
                        start_time=start_time,
                        landing_time=landing_time,
                        weekdays=weekdays,
                        start_date=start_date,
                        end_date=end_date
                    )
                )
        return timetable

    def get_full_timetable(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        arrivals = self.parse_html('../html_for_scrapping/WRO_timetable_arrivals.html')
        departures = self.parse_html('../html_for_scrapping/WRO_timetable_departures.html')
        return {
            'arrivals': arrivals,
            'departures': departures
        }


if __name__ == '__main__':
    timetable = WroclawTimetableScrapper().get_full_timetable()
    with open('../timetables/WRO_timetable.json', 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
