import json
import re
from collections import defaultdict

from selenium.webdriver.common.by import By
from tqdm import tqdm

from driver import Driver


class PoznanTimetableScrapper(Driver):
    def __init__(self):
        super().__init__()
        self.url_arrivals = 'https://poznanairport.pl/loty/rozklad-lotow/#przyloty'
        self.url_depertuares = 'https://poznanairport.pl/loty/rozklad-lotow/#odloty'
        self.city_flights_group_locator = (By.CLASS_NAME, 'flightsTable__group')
        self.airport_name_locator = (By.CLASS_NAME, 'flightsTable__text--bold')
        self.flighs_locator = (By.CLASS_NAME, 'flightsTable__item')
        self.start_time_locator = (By.XPATH, ".//span[text()='Godzina startu']/parent::div")
        self.landing_time_locator = (By.XPATH, ".//span[text()='Godzina lądowania']/parent::div")
        self.weekdays_locator = (By.XPATH, ".//span[text()='Dni tygodnia']/parent::div")
        self.start_date_locator = (By.XPATH, ".//span[text()='Od']/parent::div")
        self.end_date_locator = (By.XPATH, ".//span[text()='Do']/parent::div")

        self.iata_regex = r'\((\w{3})\)'

    def get_timetable(self, url: str) -> dict[str, list[dict[str, str]]]:
        driver, _ = self.get_driver()
        driver.get(url)

        get_city_flights_divs = driver.find_elements(*self.city_flights_group_locator)
        timetable = defaultdict(list)
        for div in tqdm(get_city_flights_divs):
            airport_name = div.find_element(*self.airport_name_locator).text
            iata_code_match = re.search(r'\((\w{3})\)', airport_name)
            iata_code = iata_code_match[1]

            flights_div = driver.find_elements(*self.flighs_locator)

            for f_div in flights_div:
                start_time_div = f_div.find_element(*self.start_time_locator)
                start_time = start_time_div.text.replace('Godzina startu', '').strip()
                landing_time_div = f_div.find_element(*self.landing_time_locator)
                landing_time = landing_time_div.text.replace('Godzina lądowania', '').strip()

                weekdays_div = f_div.find_element(*self.weekdays_locator)
                weekdays = weekdays_div.text.replace('Dni tygodnia', '').strip()
                weekdays = weekdays.split(', ')
                start_date_div = f_div.find_element(*self.start_date_locator)
                start_date = start_date_div.text.replace('Od', '').strip()

                end_date_div = f_div.find_element(*self.end_date_locator)
                end_date = end_date_div.text.replace('Do', '').strip()

                timetable[iata_code].append(
                    dict(
                        start_time=start_time,
                        landing_time=landing_time,
                        weekdays=weekdays,
                        start_date=start_date,
                        end_date=end_date
                    )
                )

        driver.close()
        return timetable

    def get_full_timetable(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        return {
            'arrivals': self.get_timetable(self.url_arrivals),
            'departures': self.get_timetable(self.url_depertuares)
        }


if __name__ == '__main__':
    timetable = PoznanTimetableScrapper().get_full_timetable()
    with open('timetables/POZ_timetable.json', 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
