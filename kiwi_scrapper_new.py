import json
import logging
import pickle
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from tqdm import tqdm

from new_driver import Driver


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
        self.interesting_iatas = self.load_interesting_iatas()
        self.iata_to_name = self.load_iata_to_city_name()
        self.price_span_locator = "div[data-test='NewDatepickerPrice'] span"
        self.price_div_locator = "div[data-test='NewDatepickerPrice']"

    @staticmethod
    def load_interesting_iatas() -> set[str]:
        with open('interesting_iatas.txt', 'rt') as f:
            return set(f.read().split('\n'))

    @staticmethod
    def load_iata_to_city_name() -> dict[str, str]:
        with open('iata_to_city.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def read_iata_codes(file_path: Path) -> list[str]:
        with open(file_path, 'rt') as f:
            iata_codes: list[str] = f.read().split('\n')
        return [iata.strip() for iata in iata_codes]

    @staticmethod
    def extract_price(s: str) -> int | None:
        return int(match.group()) if (match := re.search(r'\d+', s)) else None

    @staticmethod
    def get_week_number(date_obj: date) -> int:
        if date_obj.weekday() == 0:
            date_obj -= timedelta(days=1)
        return date_obj.isocalendar()[1]

    def gather_flight_info(
            self, page: Page, start_airport: str, start_airport_name: str, destination_airport: str,
            destination_airport_name: str
    ) -> list[FlightInfo]:
        flight_info_list: list[FlightInfo] = []
        page.locator(self.date_input_locator).click()

        click_count = 0
        while self.start_month not in self.get_month_name(page) and click_count < 12:
            click_count += 1
            page.locator(self.next_button_locator).click()

        click_count = 0
        while self.end_month not in self.get_month_name(page) and click_count < 12:
            try:
                page.locator(self.price_span_locator).first.wait_for(timeout=10000)
            except PlaywrightTimeoutError:
                logging.warning('Timeout while waiting for price elements')
                break

            # Wait for calendar to be stable
            page.wait_for_selector(self.calendar_day_locator, state='visible')

            calendar_days = page.locator(self.calendar_day_locator).all()
            if click_count == 0:
                # In the first month view, some days from the previous month might be shown.
                # The original implementation skipped the first one, this is a more robust way.
                current_month_found = False
                temp_calendar_days = []
                for day in calendar_days:
                    if day.get_attribute('data-pika-day'): # Heuristic for active month days
                        current_month_found = True
                    if current_month_found:
                        temp_calendar_days.append(day)
                calendar_days = temp_calendar_days


            for day in calendar_days:
                date_value_str: str | None = day.get_attribute('data-value')
                if not date_value_str:
                    continue
                try:
                    date_value: date = datetime.strptime(date_value_str, '%Y-%m-%d').date()
                except ValueError:
                    continue

                price_text = ""
                try:
                    price_span = day.locator(self.price_span_locator)
                    price_div = day.locator(self.price_div_locator)

                    if price_span.is_visible():
                        price_text = price_span.inner_text()
                    elif price_div.is_visible():
                        price_text = price_div.inner_text()
                        if price_text == '-':
                            continue
                    else:
                        continue
                except Exception:
                    logging.error(f"Price element not found for date {date_value_str}. HTML: {day.inner_html()}")
                    continue

                price = self.extract_price(price_text)
                if price is None:
                    if price_text.strip(): # Log only if there was text that couldn't be parsed
                        logging.warning(f"Could not extract price from '{price_text}' for date {date_value_str}")
                    continue

                flight_info = FlightInfo(
                    start_airport, start_airport_name, destination_airport, destination_airport_name, date_value, price,
                    self.get_week_number(date_value), None, None
                )
                flight_info_list.append(flight_info)
            click_count += 1
            page.locator(self.next_button_locator).click()

        page.keyboard.press('Escape')
        return flight_info_list

    def get_flights(self, page: Page, direction: str, desc: str) -> list[FlightInfo]:
        date_price_list: list[FlightInfo] = []
        start_airports_names = [self.iata_to_name[iata_airport] for iata_airport in self.start_iata_airports]

        for start_airport_code, start_airport_name in zip(self.start_iata_airports, start_airports_names):
            iatas_dir = Path(f'airport_iata_codes/{start_airport_code.upper()}_iata_codes.txt')
            iata_codes: list[str] = self.read_iata_codes(iatas_dir)
            iata_codes = list(set(iata_codes) & self.interesting_iatas)
            for dst_airport_code in tqdm(iata_codes, desc=f'{desc} {start_airport_name}'):
                if direction == 'poland_to_anywhere':
                    logging.debug(f'{start_airport_name} -> {dst_airport_code}')
                    self.choose_start_airport(page, start_airport_code)
                    destination_airport_name = self.choose_destination_airport(page, dst_airport_code)
                    date_price_list.extend(
                        self.gather_flight_info(
                            page, start_airport_code, start_airport_name, dst_airport_code, destination_airport_name
                        )
                    )
                else:
                    logging.debug(f'{dst_airport_code} -> {start_airport_name}')
                    self.choose_start_airport(page, dst_airport_code)
                    destination_airport_name = self.choose_destination_airport(page, start_airport_code)
                    date_price_list.extend(
                        self.gather_flight_info(
                            page, dst_airport_code, destination_airport_name, start_airport_code, start_airport_name
                        )
                    )

                page.locator(self.destination_locator).click()
                page.locator(self.remove_dst_airport_locator).click()

        return date_price_list

    def webscrap_flights(self) -> OrderedDict[str, list[FlightInfo]]:
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            page.goto(self.url)
            self.setup_main_page(page)

            poland_to_anywhere = self.get_flights(page, 'poland_to_anywhere', 'From')
            with open('poland_to_anywhere.pkl', 'wb') as f:
                pickle.dump(poland_to_anywhere, f, pickle.HIGHEST_PROTOCOL)

            anywhere_to_poland = self.get_flights(page, 'anywhere_to_poland', 'To')

            flights_data = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
            with open('date_price_list.pkl', 'wb') as f:
                pickle.dump(flights_data, f, pickle.HIGHEST_PROTOCOL)

            browser.close()
            return OrderedDict(sorted(flights_data.items()))
