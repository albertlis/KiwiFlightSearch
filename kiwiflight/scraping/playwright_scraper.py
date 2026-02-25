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
from .base_driver import BasePlaywrightDriver
from kiwiflight.config import settings

# Project data directory (root/data)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class _PlaywrightDriver(BasePlaywrightDriver):
    def __init__(self):
        self.failing_iatas_to_names = self.load_iata_requires_full_name()
        self.url = 'https://www.kiwi.com/pl/?currency=PLN'
        self.timeout = 30 * 1000

        self.month_button_locator = "button[data-test='DatepickerMonthButton']"
        self.cookies_button_locator = "button[data-test='ModalCloseButton']"
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
    def load_iata_requires_full_name() -> dict[str, str]:
        """Load mapping of IATA codes to airport names from iata_requires_full_name.json.

        Some airports are not recognized correctly by Kiwi's search when only the
        IATA code is entered. For those airports the full airport name must be
        used in the search; this method returns a mapping of IATA code ->
        airport display name for such cases.

        Returns:
            dict[str, str]: Mapping from IATA code to airport name for airports
            that require using the full name instead of the IATA code.
        """
        path = DATA_DIR / 'iata_requires_full_name.json'
        with open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)

    def get_page(self, playwright):
        """Extends base get_page with Kiwi-specific PLN currency cookies."""
        browser, page = super().get_page(playwright)
        page.context.add_cookies([
            {"name": "currency",    "value": "PLN", "domain": ".kiwi.com", "path": "/"},
            {"name": "kw_currency", "value": "PLN", "domain": ".kiwi.com", "path": "/"},
        ])

        return browser, page

    def setup_main_page(self, page: Page) -> None:
        btn = page.locator(self.cookies_button_locator)
        self._highlight(btn)
        btn.click()
        try:
            discard = page.locator(self.discard_cookies_locator)
            discard.wait_for(state="visible", timeout=5000)
            self._highlight(discard)
            discard.click()
        except PlaywrightTimeoutError:  # type: ignore[name-defined]
            logging.info("No secondary cookie banner.")
        direction_btn = page.locator(self.direction_button_locator).first
        self._highlight(direction_btn)
        direction_btn.click()
        one_way = page.locator(self.one_way_ticket_locator)
        self._highlight(one_way)
        one_way.click()
        booking = page.locator(self.booking_label_locator).first
        self._highlight(booking)
        booking.click()

    def choose_start_airport(self, page: Page, airport_iata: str) -> None:
        remove = page.locator(self.remove_start_airport_locator)
        self._highlight(remove)
        remove.click()
        start_input = page.locator(self.start_locator)
        self._highlight(start_input)
        start_input.click()
        start_input.fill(self.failing_iatas_to_names.get(airport_iata, airport_iata))
        airport_option = page.locator(self.start_airport_locator, has_text=airport_iata).first
        airport_option.wait_for(state="visible", timeout=5000)
        self._highlight(airport_option)
        airport_option.click()

    def choose_destination_airport(self, page: Page, airport_iata: str) -> str:
        destination_input = page.locator(self.destination_locator)
        self._highlight(destination_input)
        destination_input.click()
        destination_input.fill(self.failing_iatas_to_names.get(airport_iata, airport_iata))
        destination_airport = page.locator(self.destination_airport_locator, has_text=airport_iata).first
        destination_airport.wait_for(state="visible", timeout=5000)
        self._highlight(destination_airport)
        name = destination_airport.inner_text()
        destination_airport.click()
        return name

    def get_month_name(self, page: Page) -> str:
        return page.locator(self.month_button_locator).last.inner_text().strip().lower()

    @staticmethod
    def _highlight(locator, duration_ms: int = 600) -> None:
        """Briefly highlight an element with a red outline for visual debugging."""
        try:
            locator.evaluate(
                f"""el => {{
                    const prev = el.style.outline;
                    el.style.outline = '3px solid red';
                    setTimeout(() => {{ el.style.outline = prev; }}, {duration_ms});
                }}"""
            )
        except Exception:
            pass


class PlaywrightScraper(_PlaywrightDriver):
    def __init__(self, start_month: str, end_month: str, start_iata_airports: list[str], all_iatas: bool = False):
        super().__init__()
        self.start_month = start_month
        self.end_month = end_month
        self.start_iata_airports = start_iata_airports
        self.all_iatas = all_iatas
        self.interesting_iatas = self._load_interesting_iatas()
        self.iata_to_name = self._load_iata_to_city_name()
        self.price_span_locator = "div[data-test='NewDatepickerPrice'] span"
        self.price_div_locator = "div[data-test='NewDatepickerPrice']"

    @staticmethod
    def _load_interesting_iatas() -> set[str]:
        path = DATA_DIR / 'interesting_iatas.txt'
        with open(path, 'rt', encoding='utf-8') as f:
            return set(filter(None, f.read().split('\n')))

    @staticmethod
    def _load_iata_to_city_name() -> dict[str, str]:
        path = DATA_DIR / 'airports_to_iata_mapping.json'
        with open(path, 'rt', encoding='utf-8') as f:
            city_to_iata = json.load(f)
        # Invert to IATA -> city. If duplicates exist, the last occurrence wins.
        iata_to_city: dict[str, str] = {iata: city for city, iata in city_to_iata.items()}
        return iata_to_city

    @staticmethod
    def _read_iata_codes(file_path: Path) -> list[str]:
        # If relative path passed (PosixPath with no anchor), resolve against project root
        if not file_path.is_absolute():
            file_path = Path(__file__).resolve().parents[2] / file_path
        with open(file_path, 'rt', encoding='utf-8') as f:
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
            clicks += 1
            page.locator(self.next_button_locator).first.click()
        clicks = 0
        while True:
            current_month = self.get_month_name(page)
            is_end_month = self.end_month in current_month
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
            if is_end_month or clicks >= 12:
                break
            clicks += 1
            page.locator(self.next_button_locator).click()
        page.keyboard.press('Escape')
        return flights

    def _collect_direction(self, page: Page, direction: str, desc: str) -> list[FlightInfo]:
        collected: list[FlightInfo] = []
        start_airports_names = [self.iata_to_name[i] for i in self.start_iata_airports]
        for start_code, start_name in zip(self.start_iata_airports, start_airports_names):
            iatas_file = Path(f'airport_iata_codes/{start_code.upper()}_iata_codes.txt')
            all_codes = set(self._read_iata_codes(iatas_file))
            iata_codes = list(all_codes if self.all_iatas else all_codes & self.interesting_iatas)
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
            # save intermediate pickle next to configured data pickle
            poland_pickle = settings.data_pickle.with_name('poland_to_anywhere.pkl')
            with open(poland_pickle, 'wb') as f:
                pickle.dump(poland_to_anywhere, f, pickle.HIGHEST_PROTOCOL)
            anywhere_to_poland = self._collect_direction(page, 'anywhere_to_poland', 'To')
            flights = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
            # save final pickle to configured location
            with open(settings.data_pickle, 'wb') as f:
                pickle.dump(flights, f, pickle.HIGHEST_PROTOCOL)
            browser.close()
            return OrderedDict(sorted(flights.items()))
