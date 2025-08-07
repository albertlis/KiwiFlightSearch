import json
import logging
from typing import Tuple

from playwright.sync_api import sync_playwright, Page, Browser, Playwright, Locator, expect, TimeoutError


class Driver:
    def __init__(self):
        self.failing_iatas_to_names = self.load_failing_iatas()
        self.url = 'https://www.kiwi.com/pl/'
        self.timeout = 30 * 1000  # Playwright uses milliseconds

        # Locators
        self.month_button_locator = "button[data-test='DatepickerMonthButton']"
        self.cookies_button_locator = "button[data-test='CookiesPopup-Accept']"
        self.discard_cookies_locator = "button[data-test='CookiesPopup-Settings-save']"
        self.booking_label_locator = ".orbit-checkbox-icon-container"
        self.direction_button_locator = "div[data-test='TripTypeSwitch-tripType']"
        self.one_way_ticket_locator = "div[data-test='TripTypeSwitch-oneWay']"
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

    def get_page(self, playwright: Playwright) -> Tuple[Browser, Page]:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            locale="pl-PL",
            geolocation={"latitude": 52.2297, "longitude": 21.0122},
            permissions=["geolocation"]
        )
        # Block images for performance
        context.route("**/*.{png,jpg,jpeg,webp,svg}", lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(self.timeout)
        return browser, page

    @staticmethod
    def load_failing_iatas() -> dict[str, str]:
        with open('failing_iatas.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def click_element(locator: Locator) -> str:
        logging.debug(f'Trying to click: {locator}')
        text = locator.inner_text()
        locator.click()
        logging.debug(f'Clicked: {locator}, text: {text}')
        return text

    def get_month_name(self, page: Page) -> str:
        month_button = page.locator(self.month_button_locator)
        month = month_button.inner_text().strip().lower()
        logging.debug(f'Month name: {month}')
        return month

    def setup_main_page(self, page: Page) -> None:
        # Accept cookies
        page.locator(self.cookies_button_locator).click()
        # The second cookie banner might not appear, so we handle it gracefully.
        try:
            page.locator(self.discard_cookies_locator).click(timeout=5000)
        except TimeoutError:
            logging.info("Second cookie banner not found or did not need clicking.")

        # Choose one way ticket
        page.locator(self.direction_button_locator).click()
        page.locator(self.one_way_ticket_locator).click()

        page.locator(self.booking_label_locator).click()

    def choose_start_airport(self, page: Page, airport_iata: str) -> None:
        page.locator(self.remove_start_airport_locator).click()
        start_input = page.locator(self.start_locator)
        start_input.click()
        airport_iata_or_name = self.failing_iatas_to_names.get(airport_iata, airport_iata)
        start_input.fill(airport_iata_or_name)
        
        try:
            airport_option = page.locator(self.start_airport_locator, has_text=airport_iata).first
            airport_option.wait_for(state="visible", timeout=5000)
            airport_option.click()
        except Exception:
            self.debug_get_origin_input_value(page)
            self.debug_print_all_place_picker_text(page)
            raise

    def choose_destination_airport(self, page: Page, airport_iata: str) -> str:
        destination_input = page.locator(self.destination_locator)
        destination_input.click()
        airport_iata_or_name = self.failing_iatas_to_names.get(airport_iata, airport_iata)
        destination_input.fill(airport_iata_or_name)

        destination_airport = page.locator(self.destination_airport_locator, has_text=airport_iata).first
        destination_airport.wait_for(state="visible", timeout=5000)

        destination_airport_name = destination_airport.inner_text()
        destination_airport.click()
        
        logging.debug(f'Chosen destination airport {destination_airport_name}')
        return destination_airport_name

    def debug_get_origin_input_value(self, page: Page) -> None:
        try:
            origin_input = page.locator(self.origin_input_debug_locator)
            value = origin_input.input_value()
            logging.debug(f"Origin input value: {value}")
        except Exception:
            logging.error("Origin input field not found.")
            raise

    def debug_print_all_place_picker_text(self, page: Page) -> None:
        try:
            place_picker_rows = page.locator(self.place_picker_rows_debug_locator)
            count = place_picker_rows.count()
            for i in range(count):
                row_text = place_picker_rows.nth(i).inner_text()
                logging.debug(f"PlacePickerRow {i}: {row_text}")
        except Exception:
            logging.error("PlacePickerRow elements not found.")
            raise
