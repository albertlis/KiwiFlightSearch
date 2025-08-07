import json
import logging
import platform
import time
from functools import wraps

from selenium import webdriver
from selenium.common import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


def retry_on_stale(max_retries: int = 3, delay: int = 1):
    def decorator(func):
        @wraps(func)
        def wrapper(wait: WebDriverWait, element: tuple[str, str], *args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(wait, element, *args, **kwargs)
                except Exception:
                    if i == max_retries - 1:
                        logging.debug(f"Failed to click after {max_retries} attempts.")
                        time.sleep(60 * 10)
                        raise
                    logging.warning(f"Exception, retrying {i}")
                    time.sleep(delay)
            logging.error(f"Failed to click after {max_retries} attempts.")

        return wrapper

    return decorator


class Driver:
    def __init__(self):
        self.failing_iatas_to_names = self.load_failing_iatas()
        self.url = 'https://www.kiwi.com/pl/'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        self.timeout = 30

        self.month_button_locator = (By.XPATH, "//button[@data-test='DatepickerMonthButton']")
        self.cookies_button_locator = (By.CLASS_NAME, "orbit-button-primitive-content")
        self.discard_cookies_locator = (By.XPATH, "//p[contains(text(), 'Zapisz ustawienia')]")
        self.booking_label_locator = (By.CSS_SELECTOR, ".orbit-checkbox-icon-container")
        self.direction_button_locator = (
            By.XPATH, "//div[contains(@class, 'orbit-button-primitive-content') and contains(text(), 'W obie strony')]"
        )
        self.one_way_ticket_locator = (By.XPATH, "//span[contains(text(), 'W jedną stronę')]")

        self.remove_start_airport_locator = (
            By.CSS_SELECTOR, "div[data-test='SearchFieldItem-origin'] div[data-test='PlacePickerInputPlace-close']"
        )
        # self.choose_start_airport_locator = (By.CSS_SELECTOR, "input[data-test='SearchField-input']")
        self.remove_dst_airport_locator = (
            By.CSS_SELECTOR,
            'div[data-test="SearchFieldItem-destination"] div[data-test="PlacePickerInputPlace-close"]')
        self.destination_airport_locator = self.start_airport_locator = (
            By.XPATH, "//div[contains(text(), 'Port lotniczy') or contains(text(), 'Airport')]"
        )
        self.destination_locator = (
            By.CSS_SELECTOR, "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']"
        )
        self.start_locator = (
            By.CSS_SELECTOR, "div[data-test='PlacePickerInput-origin'] input[data-test='SearchField-input']"
        )
        self.destination_airport_eng_locator = (By.XPATH, "//div[contains(text(), 'Airport')]")
        self.date_input_locator = (By.CSS_SELECTOR, "input[data-test='SearchFieldDateInput']")
        self.calendar_day_locator = (By.XPATH, "//div[@data-test='CalendarDay']")
        self.origin_input_debug_locator = (
            By.CSS_SELECTOR, 'div[data-test="SearchPlaceField-origin"] input[data-test="SearchField-input"]'
        )
        self.place_picker_rows_debug_locator = (By.CSS_SELECTOR, 'div[data-test^="PlacePickerRow-"]')
        self.next_button_locator = (By.XPATH, "//button[@data-test='CalendarMoveNextButton']")

    def get_driver(self) -> tuple[webdriver.Chrome, WebDriverWait]:
        system = platform.system()
        if system not in {"Windows", "Linux"}:
            raise ValueError("This driver only works on Windows and Linux systems.")

        browser = 'chrome' # if system == "Linux" else 'edge'

        options = webdriver.ChromeOptions() if browser == 'chrome' else webdriver.EdgeOptions()
        options.add_argument("window-size=1000,1080")
        options.add_argument("--disk-cache-size=10485760")
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--log-level=3')
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--incognito")
        # user_data_dir = tempfile.mkdtemp()
        # options.add_argument(f"--user-data-dir={user_data_dir}")
        # if browser == 'chrome':
        #     options.binary_location = "/usr/bin/chromium-browser"
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
            # driver = webdriver.Chrome(options, Service(executable_path="/usr/bin/chromedriver"))
            driver = webdriver.Chrome(options=options)
        else:
            driver = webdriver.Edge(options=options)
            # driver = webdriver.Chrome(options=options)

        driver.execute_cdp_cmd("Emulation.setGeolocationOverride", params)
        wait = WebDriverWait(driver, self.timeout)
        return driver, wait

    @staticmethod
    def load_failing_iatas() -> dict[str, str]:
        with open('failing_iatas.json', 'rt', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    @retry_on_stale(max_retries=5, delay=2)
    def click_element(wait: WebDriverWait, element: tuple[str, str]) -> tuple[WebElement, str]:
        logging.debug(f'Trying to click: {element=}')
        button = wait.until(EC.element_to_be_clickable(element))
        # time.sleep(0.5)
        text = button.text
        logging.debug(f'Clicked: {element=}, {text}')
        button.click()
        return button, text

    @retry_on_stale(max_retries=5, delay=2)
    def get_month_name(self, wait: WebDriverWait) -> str:
        month_button = wait.until(EC.visibility_of_element_located(self.month_button_locator))
        month = month_button.text.strip().lower()
        logging.debug(f'Month name: {month}')
        return month

    def setup_main_page(self, wait: WebDriverWait) -> None:
        # Accept cookies
        self.click_element(wait, self.cookies_button_locator)
        self.click_element(wait, self.discard_cookies_locator)

        # Choose one way ticket
        self.click_element(wait, self.direction_button_locator)
        self.click_element(wait, self.one_way_ticket_locator)

        self.click_element(wait, self.booking_label_locator)

    def choose_start_airport(self, wait: WebDriverWait, airport_iata: str) -> None:
        self.click_element(wait, self.remove_start_airport_locator)
        choose_start_airport, _ = self.click_element(wait, self.start_locator)
        airport_iata_or_name = self.failing_iatas_to_names[airport_iata] \
            if airport_iata in self.failing_iatas_to_names else airport_iata
        try:
            choose_start_airport.send_keys(airport_iata_or_name)
            time.sleep(2)
        except:
            self.debug_get_origin_input_value(wait._driver)
            self.debug_print_all_place_picker_text(wait._driver)
            raise

        # start_airport_locator = (
        #     self.start_airport_locator[0],
        #     self.start_airport_locator[1].replace('IATA_PLACEHOLDER', airport_iata)
        # )
        _, text = self.click_element(wait, self.start_airport_locator)
        assert airport_iata in text, f"Airport IATA code {airport_iata} not found in {text}"

    def choose_destination_airport(self, wait: WebDriverWait, airport_iata: str) -> str:
        destination = wait.until(EC.element_to_be_clickable(self.destination_locator))
        destination.click()
        airport_iata_or_name = self.failing_iatas_to_names[airport_iata] \
            if airport_iata in self.failing_iatas_to_names else airport_iata
        destination.send_keys(airport_iata_or_name)
        time.sleep(2)
        try:
            destination_airport: WebElement = wait.until(
                EC.element_to_be_clickable(self.destination_airport_locator))
        except TimeoutException:
            destination_airport = wait.until(EC.element_to_be_clickable(self.destination_airport_eng_locator))
        destination_airport_name = destination_airport.text
        destination_airport.click()
        logging.debug(f'Chosen destination airport {destination_airport_name}')
        assert airport_iata in destination_airport_name, \
            f"Airport IATA code {airport_iata} not found in {destination_airport_name}"
        return destination_airport_name

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
