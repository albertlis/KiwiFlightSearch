import json
import re
from collections import defaultdict
from bs4 import BeautifulSoup

class PoznanTimetableScrapper:
    def __init__(self):
        self.city_flights_group_class = 'flightsTable__group'
        self.airport_name_class = 'flightsTable__text--bold'
        self.flight_item_class = 'flightsTable__item'
        self.start_time_label = 'Godzina startu'
        self.landing_time_label = 'Godzina lądowania'
        self.weekdays_label = 'Dni tygodnia'
        self.start_date_label = 'Od'
        self.end_date_label = 'Do'

        self.iata_regex = r'\((\w{3})\)'

    def parse_html(self, file_path: str) -> dict[str, list[dict[str, str]]]:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup = BeautifulSoup(file, 'html.parser')

        timetable = defaultdict(list)
        for group_div in soup.find_all('div', class_=self.city_flights_group_class):
            airport_name = group_div.find('div', class_=self.airport_name_class).get_text(strip=True)
            iata_code_match = re.search(self.iata_regex, airport_name)
            iata_code = iata_code_match[1] if iata_code_match else 'Unknown'

            flights_div = group_div.find_all('div', class_=self.flight_item_class)

            for f_div in flights_div:
                start_time = f_div.find('span', string=self.start_time_label).find_next_sibling(string=True).strip()
                landing_time = f_div.find('span', string=self.landing_time_label).find_next_sibling(string=True).strip()

                weekdays = f_div.find('span', string=self.weekdays_label).find_next_sibling(string=True).strip().split(', ')
                start_date = f_div.find('span', string=self.start_date_label).find_next_sibling(string=True).strip()
                end_date = f_div.find('span', string=self.end_date_label).find_next_sibling(string=True).strip()

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
        arrivals = self.parse_html('../html_for_scrapping/POZ_timetable_arrivals.html')
        departures = self.parse_html('../html_for_scrapping/POZ_timetable_departures.html')
        return {
            'arrivals': arrivals,
            'departures': departures
        }


if __name__ == '__main__':
    timetable = PoznanTimetableScrapper().get_full_timetable()
    with open('../timetables/POZ_timetable.json', 'w', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
