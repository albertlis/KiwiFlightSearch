import json
from dataclasses import dataclass
from datetime import datetime, date

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm
from webdriver_manager.chrome import ChromeDriverManager

# Constants
URL = 'https://www.kiwi.com/pl/'
CHROME_DRIVER_PATH = ChromeDriverManager().install()

# XPath and CSS selectors
COOKIES_BUTTON: tuple[str, str] = (By.CLASS_NAME, "orbit-button-primitive-content")
DISCARD_COOKIES: tuple[str, str] = (By.XPATH, "//p[contains(text(), 'Zapisz ustawienia')]")
DIRECTION_BUTTON: tuple[str, str] = (By.XPATH, "//button[.//div[contains(text(), 'W obie strony')]]")
ONE_WAY_TICKET: tuple[str, str] = (By.XPATH, "//span[contains(text(), 'W jedną stronę')]")
REMOVE_START_AIRPORT: tuple[str, str] = (By.CSS_SELECTOR, "div[data-test='PlacePickerInputPlace-close']")
CHOOSE_START_AIRPORT: tuple[str, str] = (By.CSS_SELECTOR, "input[data-test='SearchField-input']")
REMOVE_DST_AIRPORT: tuple[str, str] = (
    By.CSS_SELECTOR, 'div[data-test="SearchFieldItem-destination"] div[data-test="PlacePickerInputPlace-close"]')
START_AIRPORT: tuple[str, str] = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
DESTINATION: tuple[str, str] = (
    By.CSS_SELECTOR, "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']")
DESTINATION_AIRPORT: tuple[str, str] = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
DESTINATION_AIRPORT_ENG: tuple[str, str] = (By.XPATH, "//div[contains(text(), 'Airport')]")
DATE_INPUT: tuple[str, str] = (By.CSS_SELECTOR, "input[data-test='SearchFieldDateInput']")
MONTH_BUTTON: tuple[str, str] = (By.XPATH, "//button[@data-test='DatepickerMonthButton']")
CALENDAR_DAY: tuple[str, str] = (By.XPATH, "//div[@data-test='CalendarDay']")
PRICE_SPAN: tuple[str, str] = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']/span")
PRICE_DIV: tuple[str, str] = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']")
NEXT_BUTTON: tuple[str, str] = (By.XPATH, "//button[@data-test='CalendarMoveNextButton']")


@dataclass(slots=True)
class FlightInfo:
    start: str
    start_name: str
    end: str
    end_name: str
    date: date
    price: int

    def to_dict(self) -> dict[str, str]:
        return {
            'start': self.start,
            'end': self.end,
            'end_name': self.end_name,
            'date': self.date.isoformat(),
            'price': str(self.price)
        }


def get_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("window-size=1000,1080")
    options.add_argument('--headless')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/2b7c7")
    return webdriver.Chrome(service=ChromeService(CHROME_DRIVER_PATH), options=options)


def click_element(wait: WebDriverWait, element: tuple[str, str]) -> None:
    button = wait.until(EC.element_to_be_clickable(element))
    button.click()


def get_month_name(wait: WebDriverWait) -> str:
    month_button = wait.until(EC.element_to_be_clickable(MONTH_BUTTON))
    return month_button.text.lower()


def read_iata_codes(file_path: str) -> list[str]:
    with open(file_path, 'rt') as f:
        iata_codes: list[str] = f.read().split('\n')
    return [iata.strip() for iata in iata_codes]


def gather_flight_info(
        wait: WebDriverWait, start_airport: str, start_airport_name: str, destination_airport: str,
        destination_airport_name: str
) -> list[FlightInfo]:
    flight_info_list: list[FlightInfo] = []
    click_element(wait, DATE_INPUT)

    click_count: int = 0
    while 'listopad' not in get_month_name(wait) and click_count < 12:
        try:
            wait.until(EC.presence_of_all_elements_located(PRICE_SPAN))
        except TimeoutException:
            break

        calendar_days = wait.until(EC.presence_of_all_elements_located(CALENDAR_DAY))
        if click_count == 0:
            calendar_days = calendar_days[1:]

        for day in calendar_days:
            date_value: str = day.get_attribute('data-value')
            try:
                date_value: date = datetime.strptime(date_value, '%Y-%m-%d').date()
            except ValueError:
                continue

            try:
                price_div = day.find_element(*PRICE_SPAN)
            except NoSuchElementException:
                price_div = day.find_element(*PRICE_DIV)
                if price_div.text == '-':
                    continue
                print("Element not found, here is the HTML of the current element:", day.get_attribute('outerHTML'))
                raise
            try:
                price: int = int(price_div.text.split(' ')[0])
            except ValueError:
                print("Incorrect price", price_div.text, "HTML: ", price_div.get_attribute('outerHTML'))
                raise

            flight_info = FlightInfo(
                start_airport, start_airport_name, destination_airport, destination_airport_name, date_value, price
            )
            flight_info_list.append(flight_info)
        click_count += 1
        click_element(wait, NEXT_BUTTON)

    date_input = wait.until(EC.element_to_be_clickable(DATE_INPUT))
    date_input.send_keys(Keys.ESCAPE)
    return flight_info_list


def get_flights(
        wait: WebDriverWait, start_airports: list[str], start_airports_names: list[str], direction: str
) -> list[dict[str, str]]:
    date_price_list: list[FlightInfo] = []
    for start_airport_code, start_airport_name in zip(start_airports, start_airports_names):
        click_element(wait, REMOVE_START_AIRPORT)
        click_element(wait, CHOOSE_START_AIRPORT)
        choose_start_airport = wait.until(EC.element_to_be_clickable(CHOOSE_START_AIRPORT))
        choose_start_airport.send_keys(start_airport_code)
        click_element(wait, START_AIRPORT)

        iata_codes: list[str] = read_iata_codes(f'{start_airport_code}_iata_codes.txt')
        for dst_airport_code in tqdm(iata_codes):
            destination = wait.until(EC.element_to_be_clickable(DESTINATION))
            destination.click()
            destination.send_keys(dst_airport_code)
            try:
                destination_airport: WebElement = wait.until(EC.element_to_be_clickable(DESTINATION_AIRPORT))
            except TimeoutException:
                destination_airport = wait.until(EC.element_to_be_clickable(DESTINATION_AIRPORT_ENG))
            destination_airport_name = destination_airport.text
            destination_airport.click()

            if direction == 'poland_to_anywhere':
                date_price_list.extend(
                    gather_flight_info(wait, start_airport_code, start_airport_name, dst_airport_code,
                                       destination_airport_name)
                )
            else:
                date_price_list.extend(
                    gather_flight_info(wait, dst_airport_code, destination_airport_name, start_airport_code,
                                       start_airport_name)
                )

            destination = wait.until(EC.element_to_be_clickable(DESTINATION))
            destination.click()
            remove_dst_airport: WebElement = wait.until(EC.element_to_be_clickable(REMOVE_DST_AIRPORT))
            remove_dst_airport.click()

    return [info.to_dict() for info in date_price_list]


def main() -> None:
    driver: webdriver.Chrome = get_driver()
    driver.get(URL)
    wait: WebDriverWait = WebDriverWait(driver, 20)

    # Accept cookies
    click_element(wait, COOKIES_BUTTON)
    click_element(wait, DISCARD_COOKIES)

    # Choose one way ticket
    click_element(wait, DIRECTION_BUTTON)
    click_element(wait, ONE_WAY_TICKET)

    start_airports = ['WRO', 'POZ']
    start_airports_names = ['Wrocław', 'Poznań']

    poland_to_anywhere = get_flights(wait, start_airports, start_airports_names, 'poland_to_anywhere')
    anywhere_to_poland = get_flights(wait, start_airports, start_airports_names, 'anywhere_to_poland')

    # Dump list to JSON
    with open('date_price_list.json', 'w', encoding='utf-8') as f:
        json.dump(
            {
                'poland_to_anywhere': poland_to_anywhere,
                'anywhere_to_poland': anywhere_to_poland
            }, f, ensure_ascii=False, indent=2
        )


if __name__ == '__main__':
    main()
