import json
import logging
import platform
import re
from dataclasses import dataclass
from datetime import date, datetime

from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm


@dataclass(slots=True, frozen=True)
class FlightInfo:
    start: str
    start_name: str
    end: str
    end_name: str
    date: date
    price: int


class KiwiScrapper:
    def __init__(self, start_month: str, end_month: str, start_iata_airports: list[str]):
        self.start_month = start_month
        self.end_month = end_month
        self.start_iata_airports = start_iata_airports
        self.iata_to_name = self.load_iata_to_city_name()

        self.url = 'https://www.kiwi.com/pl/'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        self.month_button_locator = (By.XPATH, "//button[@data-test='DatepickerMonthButton']")
        self.cookies_button_locator = (By.CLASS_NAME, "orbit-button-primitive-content")
        self.discard_cookies_locator = (By.XPATH, "//p[contains(text(), 'Zapisz ustawienia')]")
        self.direction_button_locator = (By.XPATH, "//button[.//div[contains(text(), 'W obie strony')]]")
        self.one_way_ticket_locator = (By.XPATH, "//span[contains(text(), 'W jedną stronę')]")
        self.remove_start_airport_locator = (By.CSS_SELECTOR, "div[data-test='PlacePickerInputPlace-close']")
        self.choose_start_airport_locator = (By.CSS_SELECTOR, "input[data-test='SearchField-input']")
        self.remove_dst_airport_locator = (
            By.CSS_SELECTOR,
            'div[data-test="SearchFieldItem-destination"] div[data-test="PlacePickerInputPlace-close"]')
        self.start_airport_locator = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
        self.destination_locator = (
            By.CSS_SELECTOR, "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']")
        self.destination_airport_locator = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
        self.destination_airport_eng_locator = (By.XPATH, "//div[contains(text(), 'Airport')]")
        self.date_input_locator = (By.CSS_SELECTOR, "input[data-test='SearchFieldDateInput']")
        self.calendar_day_locator = (By.XPATH, "//div[@data-test='CalendarDay']")
        self.price_span_locator = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']/span")
        self.price_div_locator = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']")
        self.next_button_locator = (By.XPATH, "//button[@data-test='CalendarMoveNextButton']")
        self.origin_input_debug_locator = (
            By.CSS_SELECTOR, 'div[data-test="SearchPlaceField-origin"] input[data-test="SearchField-input"]'
        )
        self.place_picker_rows_debug_locator = (By.CSS_SELECTOR, 'div[data-test^="PlacePickerRow-"]')

        self.timeout = 60 * 5

    @staticmethod
    def load_iata_to_city_name() -> dict[str, str]:
        with open('iata_to_city.txt', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def click_element(wait: WebDriverWait, element: tuple[str, str]) -> None:
        button = wait.until(EC.element_to_be_clickable(element))
        button.click()
        logging.debug(f'Clicked: {element=}')

    def get_month_name(self, wait: WebDriverWait) -> str:
        # time.sleep(10)
        month_button = wait.until(EC.element_to_be_clickable(self.month_button_locator))
        return month_button.text.lower()

    @staticmethod
    def read_iata_codes(file_path: str) -> list[str]:
        with open(file_path, 'rt') as f:
            iata_codes: list[str] = f.read().split('\n')
        return [iata.strip() for iata in iata_codes]

    @staticmethod
    def extract_price(s: str) -> int:
        return int(match.group()) if (match := re.search(r'\d+', s)) else None

    def debug_get_origin_input_value(self, driver: webdriver.Chrome) -> None:
        try:
            # Locate the input field within the specified div
            origin_input = driver.find_element(*self.origin_input_debug_locator)
            logging.debug(origin_input.get_attribute('value'))
        except NoSuchElementException:
            logging.error("Origin input field not found.")
            raise

    def debug_print_all_place_picker_text(self, driver: webdriver.Chrome) -> None:
        try:
            # Locate all the div elements containing the text to print
            place_picker_rows = driver.find_elements(*self.place_picker_rows_debug_locator)
            for row in place_picker_rows:
                logging.debug(row.text)
        except NoSuchElementException:
            logging.error("PlacePickerRow elements not found.")
            raise

    def gather_flight_info(
            self, wait: WebDriverWait, start_airport: str, start_airport_name: str, destination_airport: str,
            destination_airport_name: str
    ) -> list[FlightInfo]:
        flight_info_list: list[FlightInfo] = []
        self.click_element(wait, self.date_input_locator)

        click_count = 0
        while self.start_month not in self.get_month_name(wait)and click_count < 12:
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
                    logging.error("Element not found, here is the HTML of the current element:", day.get_attribute('outerHTML'))
                    raise
                try:
                    price = self.extract_price(price_div.text)
                except ValueError:
                    logging.error("Incorrect price", price_div.text, "HTML: ", price_div.get_attribute('outerHTML'))
                    raise

                flight_info = FlightInfo(
                    start_airport, start_airport_name, destination_airport, destination_airport_name, date_value, price
                )
                flight_info_list.append(flight_info)
            click_count += 1
            self.click_element(wait, self.next_button_locator)

        date_input = wait.until(EC.element_to_be_clickable(self.date_input_locator))
        date_input.send_keys(Keys.ESCAPE)
        return flight_info_list

    def get_flights(self,  wait: WebDriverWait, direction: str) -> list[FlightInfo]:
        date_price_list: list[FlightInfo] = []
        start_airports_names = [self.iata_to_name[iata_airport] for iata_airport in self.start_iata_airports]
        for start_airport_code, start_airport_name in zip(self.start_iata_airports, start_airports_names):
            self.click_element(wait, self.remove_start_airport_locator)
            self.click_element(wait, self.choose_start_airport_locator)
            choose_start_airport = wait.until(EC.element_to_be_clickable(self.choose_start_airport_locator))
            # time.sleep(10)
            try:
                choose_start_airport.send_keys(start_airport_code)
            except:
                self.debug_get_origin_input_value(wait._driver)
                self.debug_print_all_place_picker_text(wait._driver)
                raise

            self.click_element(wait, self.start_airport_locator)

            iata_codes: list[str] = self.read_iata_codes(f'{start_airport_code.lower()}_iata_codes.txt')
            for dst_airport_code in tqdm(iata_codes, desc=start_airport_name):
                destination = wait.until(EC.element_to_be_clickable(self.destination_locator))
                destination.click()
                destination.send_keys(dst_airport_code)
                try:
                    destination_airport: WebElement = wait.until(
                        EC.element_to_be_clickable(self.destination_airport_locator))
                except TimeoutException:
                    destination_airport = wait.until(EC.element_to_be_clickable(self.destination_airport_eng_locator))
                destination_airport_name = destination_airport.text
                destination_airport.click()

                if direction == 'poland_to_anywhere':
                    date_price_list.extend(
                        self.gather_flight_info(wait, start_airport_code, start_airport_name, dst_airport_code,
                                                destination_airport_name)
                    )
                else:
                    date_price_list.extend(
                        self.gather_flight_info(wait, dst_airport_code, destination_airport_name, start_airport_code,
                                                start_airport_name)
                    )

                destination = wait.until(EC.element_to_be_clickable(self.destination_locator))
                destination.click()
                remove_dst_airport: WebElement = wait.until(EC.element_to_be_clickable(self.remove_dst_airport_locator))
                remove_dst_airport.click()

        return date_price_list

    @staticmethod
    def get_driver() -> webdriver.Chrome:
        system = platform.system()
        if system not in {"Windows", "Linux"}:
            raise ValueError("This driver only works on Windows and Linux systems.")

        browser = 'chrome' if system == "Linux" else 'edge'

        options = webdriver.ChromeOptions() if browser == 'chrome' else webdriver.EdgeOptions()
        options.add_argument("window-size=1000,1080")
        options.add_argument("--disk-cache-size=10485760")
        # options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--incognito")

        if browser == 'chrome':
            options.binary_location = "/usr/bin/chromium-browser"
        # Disable loading images for better performance
        prefs = {"profile.managed_default_content_settings.images": 2}
        options.add_experimental_option("prefs", prefs)
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/2b7c7"
        )

        # Set language to Polish
        options.add_argument("--lang=pl-PL")

        # Set geolocation to Poland (latitude and longitude for Warsaw)
        params = {
            "latitude": 52.2297,
            "longitude": 21.0122,
            "accuracy": 100
        }
        if browser == "chrome":
            driver = webdriver.Chrome(options, Service(executable_path="/usr/bin/chromedriver"))
        else:
            driver = webdriver.Edge(options=options)

        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", params)
        return driver

    def webscrap_flights(self) -> dict[str, list[FlightInfo]]:
        driver = self.get_driver()
        driver.get(self.url)
        wait: WebDriverWait = WebDriverWait(driver, self.timeout)

        # Accept cookies
        self.click_element(wait, self.cookies_button_locator)
        self.click_element(wait, self.discard_cookies_locator)

        # Choose one way ticket
        self.click_element(wait, self.direction_button_locator)
        self.click_element(wait, self.one_way_ticket_locator)



        poland_to_anywhere = self.get_flights(wait, 'poland_to_anywhere')
        anywhere_to_poland = self.get_flights(wait, 'anywhere_to_poland')

        flights_data = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
        # Dump list to JSON
        with open('date_price_list.json', 'wt', encoding='utf-8') as f:
            json.dump(flights_data, f, ensure_ascii=False, indent=2)

        driver.close()
        return flights_data
