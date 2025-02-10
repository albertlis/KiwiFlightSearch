import json
import re
from collections import defaultdict

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from tqdm import tqdm

from driver import Driver


class WroclawTimetableScrapper(Driver):
    def __init__(self):
        super().__init__()
        self.url = 'https://airport.wroclaw.pl/pasazer/odlatuje/rozklad-lotow/'
        self.cookie_accept_button_locator = (By.ID, "js_agree_cookies")
        self.departures_button_locator = (By.CSS_SELECTOR, "div.n-flights__top-button[data-id='n-flights-departures']")
        self.arrivals_div_locator = (By.ID, 'n-flights-arrivals')
        self.departures_div_locator = (By.ID, 'n-flights-departures')

        self.iata_regex = r'\[(\w{3})\]'

    def get_timetable(self, soup: BeautifulSoup) -> dict[str, list[dict[str, str]]]:
        timetable = defaultdict(list)
        flight_data_divs = soup.select('.n-flights__data-wrap.n-flights__data-regular.desktop')

        for div in tqdm(flight_data_divs):
            try:
                port = div.select_one('.port').text
                if not port:
                    continue
                iata_code_match = re.search(self.iata_regex, port)
                iata_code = iata_code_match.group(1) if iata_code_match else None
                start_time = div.select_one('.departure').text.strip()
                landing_time = div.select_one('.arrival').text.strip()
                days_elements = div.select('.days span')
                weekdays = [
                    day.text.strip() for day in days_elements
                    if 'on' in day.get('class', []) and day.text.strip()
                ]

                period = div.select_one('.period').text.strip()
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
        driver, wait = self.get_driver()
        driver.get(self.url)

        self.click_element(wait, self.cookie_accept_button_locator)

        arrivals_div = wait.until(lambda x: x.find_element(*self.arrivals_div_locator))
        soup_arrivals = BeautifulSoup(arrivals_div.get_attribute('outerHTML'), 'html.parser')

        self.click_element(wait, self.departures_button_locator)
        departures_div = wait.until(lambda x: x.find_element(*self.departures_div_locator))
        soup_departures = BeautifulSoup(departures_div.get_attribute('outerHTML'), 'html.parser')
        driver.close()

        arrivals_timetable = self.get_timetable(soup_arrivals)
        departures_timetable = self.get_timetable(soup_departures)

        return dict(arrivals=arrivals_timetable, departures=departures_timetable)


if __name__ == '__main__':
    timetable = WroclawTimetableScrapper().get_full_timetable()
    with open('timetables/WRO_timetable.json', 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
