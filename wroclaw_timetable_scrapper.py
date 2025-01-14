import json
import re
from collections import defaultdict

from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from driver import Driver


class WroclawTimetableScrapper(Driver):
    def __init__(self):
        super().__init__()
        self.url = 'https://airport.wroclaw.pl/pasazer/odlatuje/rozklad-lotow/'
        self.cookie_accept_button_locator = (By.ID, "js_agree_cookies")
        self.arrivals_div_locator = (By.ID, 'n-flights-arrivals')
        self.departures_div_locator = (By.ID, 'n-flights-departures')
        self.flight_data_locator = (By.CSS_SELECTOR, '.n-flights__data-wrap.n-flights__data-regular.desktop')
        self.port_locator = (By.CLASS_NAME, 'port')
        self.departure_locator = (By.CLASS_NAME, 'departure')
        self.arrival_locator = (By.CLASS_NAME, 'arrival')
        self.days_locator = (By.CLASS_NAME, 'days')
        self.period_locator = (By.CLASS_NAME, 'period')

        self.iata_regex = r'\[(\w{3})\]'

    def get_timetable(self, element: WebElement) -> dict[str, list[dict[str, str]]]:
        flight_data_divs = element.find_elements(*self.flight_data_locator)
        timetable = defaultdict(list)

        for div in tqdm(flight_data_divs):
            port = div.find_element(*self.port_locator).text
            if not port:
                continue
            iata_code_match = re.search(self.iata_regex, port)
            iata_code = iata_code_match[1]
            start_time = div.find_element(*self.departure_locator).text.strip()
            landing_time = div.find_element(*self.arrival_locator).text.strip()

            days_element = div.find_element(*self.days_locator)
            weekdays = [day.text.strip() for day in days_element.find_elements(By.TAG_NAME, 'span') if day.text.strip()]

            period = div.find_element(*self.period_locator).text.strip()
            start_date, end_date = period.split(' - ')

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
        arrivals_timetable = self.get_timetable(arrivals_div)
        departures_div = wait.until(lambda x: x.find_element(*self.departures_div_locator))
        departures_timetable = self.get_timetable(departures_div)

        driver.close()

        return dict(arrivals=arrivals_timetable, departures=departures_timetable)


if __name__ == '__main__':
    timetable = WroclawTimetableScrapper().get_full_timetable()
    with open('wroclaw_timetable.json', 'wt', encoding='utf-8') as f:
        json.dump(timetable, f, indent=2, ensure_ascii=False)
