"""Playwright based scraper for Kiwi flight date/price grid.

Consolidates logic previously in new_driver.py + kiwi_scrapper_new.py.
"""

import json
import logging
import pickle
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from tqdm import tqdm

from ..models import FlightInfo


class _PlaywrightDriver:
    def __init__(self):
        self.failing_iatas_to_names = self.load_failing_iatas()
        self.url = 'https://www.kiwi.com/pl/'
        self.timeout = 30 * 1000
        # Locators
        self.month_button_locator = "button[data-test='DatepickerMonthButton']"
        self.cookies_button_locator = "button[data-test='CookiesPopup-Accept']"
        self.discard_cookies_locator = "button[data-test='CookiesPopup-Settings-save']"
        self.booking_label_locator = ".orbit-checkbox-icon-container"
        self.direction_button_locator = "//div[contains(@class, 'orbit-button-primitive-content') and contains(text(), 'W obie strony')]"
        self.one_way_ticket_locator = "//span[contains(text(), 'W jedną stronę')]"
        self.remove_start_airport_locator = "div[data-test='SearchFieldItem-origin'] div[data-test='PlacePickerInputPlace-close']"
        self.remove_dst_airport_locator = "div[data-test='SearchFieldItem-destination'] div[data-test='PlacePickerInputPlace-close']"
        self.start_airport_locator = "div[data-test^='PlacePickerRow-']"
        self.destination_airport_locator = "div[data-test^='PlacePickerRow-']"
        self.destination_locator = "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']"
        self.start_locator = "div[data-test='PlacePickerInput-origin'] input[data-test='SearchField-input']"
        self.date_input_locator = "input[data-test='SearchFieldDateInput']"
        self.calendar_day_locator = "div[data-test='CalendarDay']"
        self.next_button_locator = "button[data-test='CalendarMoveNextButton']"
        self.origin_input_debug_locator = "div[data-test='SearchPlaceField-origin'] input[data-test='SearchField-input']"
        self.place_picker_rows_debug_locator = "div[data-test^='PlacePickerRow-']"

    @staticmethod
    def load_failing_iatas() -> dict[str, str]:
        with open('../failing_iatas.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    def get_page(self, playwright):  # type: ignore[no-untyped-def]
        browser = playwright.chromium.launch(headless=True, args=["--window-size=800,800"])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            locale="pl-PL", geolocation={"latitude": 52.2297, "longitude": 21.0122}, permissions=["geolocation"],
            viewport={"width": 800, "height": 800},
        )
        context.route("**/*.{png,jpg,jpeg,webp,svg}", lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(self.timeout)
        return browser, page

    def setup_main_page(self, page: Page) -> None:
        page.locator(self.cookies_button_locator).click()
        try:
            page.locator(self.discard_cookies_locator).click(timeout=5000)
        except PlaywrightTimeoutError:  # type: ignore[name-defined]
            logging.info("No secondary cookie banner.")
        page.locator(self.direction_button_locator).first.click()
        page.locator(self.one_way_ticket_locator).click()
        page.locator(self.booking_label_locator).first.click()

    def choose_start_airport(self, page: Page, airport_iata: str) -> None:
        page.locator(self.remove_start_airport_locator).click()
        start_input = page.locator(self.start_locator)
        start_input.click()
        start_input.fill(self.failing_iatas_to_names.get(airport_iata, airport_iata))
        airport_option = page.locator(self.start_airport_locator, has_text=airport_iata).first
        airport_option.wait_for(state="visible", timeout=5000)
        airport_option.click()

    def choose_destination_airport(self, page: Page, airport_iata: str) -> str:
        destination_input = page.locator(self.destination_locator)
        destination_input.click()
        destination_input.fill(self.failing_iatas_to_names.get(airport_iata, airport_iata))
        destination_airport = page.locator(self.destination_airport_locator, has_text=airport_iata).first
        destination_airport.wait_for(state="visible", timeout=5000)
        name = destination_airport.inner_text()
        destination_airport.click()
        return name

    def get_month_name(self, page: Page) -> str:
        return page.locator(self.month_button_locator).last.inner_text().strip().lower()


class PlaywrightScraper(_PlaywrightDriver):
    def __init__(self, start_month: str, end_month: str, start_iata_airports: list[str]):
        super().__init__()
        self.start_month = start_month
        self.end_month = end_month
        self.start_iata_airports = start_iata_airports
        self.interesting_iatas = self._load_interesting_iatas()
        self.iata_to_name = self._load_iata_to_city_name()
        self.price_span_locator = "div[data-test='NewDatepickerPrice'] span"
        self.price_div_locator = "div[data-test='NewDatepickerPrice']"

    @staticmethod
    def _load_interesting_iatas() -> set[str]:
        with open('../interesting_iatas.txt', 'rt') as f:
            return set(filter(None, f.read().split('\n')))

    @staticmethod
    def _load_iata_to_city_name() -> dict[str, str]:
        with open('../iata_to_city.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _read_iata_codes(file_path: Path) -> list[str]:
        with open(file_path, 'rt') as f:
            return [iata.strip() for iata in f.read().split('\n') if iata.strip()]

    @staticmethod
    def _extract_price(text: str):
        m = re.search(r'\d+', text)
        return int(m.group()) if m else None

    @staticmethod
    def _week_number(d: date) -> int:
        if d.weekday() == 0:
            d -= timedelta(days=1)
        return d.isocalendar()[1]

    def _wait_for_prices(self, page: Page, timeout: int = 15):
        try:
            page.wait_for_function(
                '''() => {const spans = document.querySelectorAll('div[data-test="NewDatepickerPrice"] span');
                    return spans.length>0 && Array.from(spans).every(s=>{const t=s.innerText.trim();return t && t!== 'Ładowanie';});}''',
                timeout=timeout * 1000
            )
        except PlaywrightTimeoutError:
            logging.warning("Prices loading timed out after %ss", timeout)

    def _gather_route_prices(self, page: Page, start_code: str, start_name: str, dst_code: str, dst_name: str) -> List[
        FlightInfo]:
        flights: list[FlightInfo] = []
        page.locator(self.date_input_locator).click()
        clicks = 0
        while self.start_month not in self.get_month_name(page) and clicks < 12:
            clicks += 1;
            page.locator(self.next_button_locator).click()
        clicks = 0
        while self.end_month not in self.get_month_name(page) and clicks < 12:
            self._wait_for_prices(page)
            page.wait_for_selector(self.calendar_day_locator, state='attached', timeout=10000)
            days = page.locator(self.calendar_day_locator).all()
            if clicks == 0:
                days = days[1:]
            for day in days:
                date_str = day.get_attribute('data-value')
                if not date_str:
                    continue
                try:
                    d_val = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    continue
                price_text = ''
                try:
                    ps = day.locator(self.price_span_locator)
                    pd = day.locator(self.price_div_locator)
                    if ps.is_visible():
                        price_text = ps.inner_text()
                    elif pd.is_visible():
                        price_text = pd.inner_text()
                        if price_text == '-':
                            continue
                    else:
                        continue
                except Exception:
                    logging.debug("Missing price element for %s", date_str)
                    continue
                price = self._extract_price(price_text)
                if price is None:
                    continue
                flights.append(
                    FlightInfo(start_code, start_name, dst_code, dst_name, d_val, price, self._week_number(d_val), None,
                               None))
            clicks += 1
            page.locator(self.next_button_locator).click()
        page.keyboard.press('Escape')
        return flights

    def _collect_direction(self, page: Page, direction: str, desc: str) -> list[FlightInfo]:
        collected: list[FlightInfo] = []
        start_airports_names = [self.iata_to_name[i] for i in self.start_iata_airports]
        for start_code, start_name in zip(self.start_iata_airports, start_airports_names):
            iatas_file = Path(f'../airport_iata_codes/{start_code.upper()}_iata_codes.txt')
            iata_codes = list(set(self._read_iata_codes(iatas_file)) & self.interesting_iatas)
            for dst_code in tqdm(iata_codes, desc=f'{desc} {start_name}'):
                if direction == 'poland_to_anywhere':
                    self.choose_start_airport(page, start_code)
                    dst_name = self.choose_destination_airport(page, dst_code)
                    collected.extend(self._gather_route_prices(page, start_code, start_name, dst_code, dst_name))
                else:
                    self.choose_start_airport(page, dst_code)
                    dst_name = self.choose_destination_airport(page, start_code)
                    collected.extend(self._gather_route_prices(page, dst_code, dst_name, start_code, start_name))
                page.locator(self.destination_locator).click()
                page.locator(self.remove_dst_airport_locator).click()
        return collected

    def webscrap_flights(self):  # retains legacy name for compatibility
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            page.goto(self.url)
            self.setup_main_page(page)
            poland_to_anywhere = self._collect_direction(page, 'poland_to_anywhere', 'From')
            with open('poland_to_anywhere.pkl', 'wb') as f:
                pickle.dump(poland_to_anywhere, f, pickle.HIGHEST_PROTOCOL)
            anywhere_to_poland = self._collect_direction(page, 'anywhere_to_poland', 'To')
            flights = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
            with open('date_price_list.pkl', 'wb') as f:
                pickle.dump(flights, f, pickle.HIGHEST_PROTOCOL)
            browser.close()
            return OrderedDict(sorted(flights.items()))
