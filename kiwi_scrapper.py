import json
import logging
import pickle
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from pathlib import Path

from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from driver import Driver


@dataclass(slots=True)
class FlightInfo:
    start: str
    start_name: str
    end: str
    end_name: str
    date: date
    price: int
    week: int
    start_time: time | None
    back_time: time | None


class KiwiScrapper(Driver):
    def __init__(self, start_month: str, end_month: str, start_iata_airports: list[str]):
        super().__init__()
        self.start_month = start_month
        self.end_month = end_month
        self.start_iata_airports = start_iata_airports
        self.iata_to_name = self.load_iata_to_city_name()
        self.interesting_iatas = self.load_interesting_iatas()
        self.price_span_locator = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']/span")
        self.price_div_locator = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']")

    @staticmethod
    def load_iata_to_city_name() -> dict[str, str]:
        with open('iata_to_city.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def load_interesting_iatas() -> set[str]:
        with open('interesting_iatas.txt', 'rt') as f:
            return set(f.read().split('\n'))

    @staticmethod
    def read_iata_codes(file_path: Path) -> list[str]:
        with open(file_path, 'rt') as f:
            iata_codes: list[str] = f.read().split('\n')
        return [iata.strip() for iata in iata_codes]

    @staticmethod
    def extract_price(s: str) -> int:
        return int(match.group()) if (match := re.search(r'\d+', s)) else None

    @staticmethod
    def get_week_number(date: datetime.date) -> int:
        if date.weekday() == 0:
            date -= timedelta(days=1)
        return date.isocalendar()[1]

    def gather_flight_info(
            self, wait: WebDriverWait, start_airport: str, start_airport_name: str, destination_airport: str,
            destination_airport_name: str
    ) -> list[FlightInfo]:
        flight_info_list: list[FlightInfo] = []
        self.click_element(wait, self.date_input_locator)

        click_count = 0
        while self.start_month not in self.get_month_name(wait) and click_count < 12:
            click_count += 1
            self.click_element(wait, self.next_button_locator)

        click_count = 0
        while self.end_month not in self.get_month_name(wait) and click_count < 12:
            try:
                wait.until(EC.presence_of_all_elements_located(self.price_span_locator))
            except TimeoutException:
                break

            calendar_days = wait.until(EC.presence_of_all_elements_located(self.calendar_day_locator))
            if click_count == 0:
                calendar_days = calendar_days[1:]

            for day in calendar_days:
                date_value: str = day.get_attribute('data-value')
                try:
                    date_value: date = datetime.strptime(date_value, '%Y-%m-%d').date()
                except ValueError:
                    continue

                try:
                    price_div = day.find_element(*self.price_span_locator)
                except NoSuchElementException:
                    price_div = day.find_element(*self.price_div_locator)
                    if price_div.text == '-':
                        continue
                    logging.error("Element not found, here is the HTML of the current element:",
                                  day.get_attribute('outerHTML'))
                    raise
                try:
                    price = self.extract_price(price_div.text)
                except ValueError:
                    logging.error("Incorrect price", price_div.text, "HTML: ", price_div.get_attribute('outerHTML'))
                    raise

                flight_info = FlightInfo(
                    start_airport, start_airport_name, destination_airport, destination_airport_name, date_value, price,
                    self.get_week_number(date_value), None, None
                )
                flight_info_list.append(flight_info)
            click_count += 1
            self.click_element(wait, self.next_button_locator)

        date_input = wait.until(EC.element_to_be_clickable(self.date_input_locator))
        date_input.send_keys(Keys.ESCAPE)
        return flight_info_list

    def get_flights(self, wait: WebDriverWait, direction: str, desc: str) -> list[FlightInfo]:
        date_price_list: list[FlightInfo] = []
        start_airports_names = [self.iata_to_name[iata_airport] for iata_airport in self.start_iata_airports]
        for start_airport_code, start_airport_name in zip(self.start_iata_airports, start_airports_names):
            iatas_dir = Path(f'airport_iata_codes/{start_airport_code.upper()}_iata_codes.txt')
            iata_codes: list[str] = self.read_iata_codes(iatas_dir)
            iata_codes = list(set(iata_codes) & self.interesting_iatas)
            for dst_airport_code in tqdm(iata_codes, desc=f'{desc} {start_airport_name}'):
                if direction == 'poland_to_anywhere':
                    self.choose_start_airport(wait, start_airport_code)
                    destination_airport_name = self.choose_destination_airport(wait, dst_airport_code)
                    date_price_list.extend(
                        self.gather_flight_info(
                            wait, start_airport_code, start_airport_name, dst_airport_code, destination_airport_name
                        )
                    )
                else:
                    self.choose_start_airport(wait, dst_airport_code)
                    destination_airport_name = self.choose_destination_airport(wait, start_airport_code)
                    date_price_list.extend(
                        self.gather_flight_info(
                            wait, dst_airport_code, destination_airport_name, start_airport_code, start_airport_name
                        )
                    )

                self.click_element(wait, self.destination_locator)
                self.click_element(wait, self.remove_dst_airport_locator)

        return date_price_list

    def webscrap_flights(self) -> OrderedDict[str, list[FlightInfo]]:
        driver, wait = self.get_driver()
        driver.get(self.url)
        self.setup_main_page(wait)

        poland_to_anywhere = self.get_flights(wait, 'poland_to_anywhere', 'From')
        anywhere_to_poland = self.get_flights(wait, 'anywhere_to_poland', 'To')

        flights_data = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
        # Dump list to JSON
        with open('date_price_list.pkl', 'wb') as f:
            pickle.dump(flights_data, f, pickle.HIGHEST_PROTOCOL)

        driver.close()
        return OrderedDict(sorted(flights_data.items()))
