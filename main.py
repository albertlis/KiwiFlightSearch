import json
from dataclasses import dataclass
from datetime import datetime

from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Constants
URL = 'https://www.kiwi.com/pl/'
CHROME_DRIVER_PATH = ChromeDriverManager().install()

# XPath and CSS selectors
COOKIES_BUTTON = (By.CLASS_NAME, "orbit-button-primitive-content")
DISCARD_COOKIES = (By.XPATH, "//p[contains(text(), 'Zapisz ustawienia')]")
DIRECTION_BUTTON = (By.XPATH, "//button[.//div[contains(text(), 'W obie strony')]]")
ONE_WAY_TICKET = (By.XPATH, "//span[contains(text(), 'W jedną stronę')]")
REMOVE_START_AIRPORT = (By.CSS_SELECTOR, "div[data-test='PlacePickerInputPlace-close']")
CHOOSE_START_AIRPORT = (By.CSS_SELECTOR, "input[data-test='SearchField-input']")
REMOVE_DST_AIRPORT = (
By.CSS_SELECTOR, 'div[data-test="SearchFieldItem-destination"] div[data-test="PlacePickerInputPlace-close"]')
START_AIRPORT = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
DESTINATION = (By.CSS_SELECTOR, "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']")
DESTINATION_AIRPORT = (By.XPATH, "//div[contains(text(), 'Port lotniczy')]")
DESTINATION_AIRPORT_ENG = (By.XPATH, "//div[contains(text(), 'Airport')]")
DATE_INPUT = (By.CSS_SELECTOR, "input[data-test='SearchFieldDateInput']")
MONTH_BUTTON = (By.XPATH, "//button[@data-test='DatepickerMonthButton']")
CALENDAR_DAY = (By.XPATH, "//div[@data-test='CalendarDay']")
PRICE_SPAN = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']/span")
PRICE_DIV = (By.XPATH, ".//div[@data-test='NewDatepickerPrice']")
NEXT_BUTTON = (By.XPATH, "//button[@data-test='CalendarMoveNextButton']")


@dataclass
class FlightInfo:
    start: str
    start_name: str
    end: str
    end_name: str
    date: datetime.date
    price: int

    def to_dict(self):
        return {
            'start': self.start,
            'end': self.end,
            'end_name': self.end_name,
            'date': self.date.isoformat(),  # convert date to string
            'price': self.price
        }


def get_driver() -> webdriver.Chrome:
    op = webdriver.ChromeOptions()
    op.add_argument("window-size=1000,1080")  # Specify resolution
    op.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/2b7c7"
    )
    return webdriver.Chrome(service=ChromeService(CHROME_DRIVER_PATH), options=op)


def click_element(wait, element):
    button = wait.until(EC.element_to_be_clickable(element))
    button.click()


def get_month_name(wait):
    month_button = wait.until(EC.element_to_be_clickable(MONTH_BUTTON))
    return month_button.text.lower()


def main():
    driver = get_driver()
    driver.get(URL)
    wait = WebDriverWait(driver, 20)

    # Accept cookies
    click_element(wait, COOKIES_BUTTON)
    click_element(wait, DISCARD_COOKIES)

    # Choose one way ticket
    click_element(wait, DIRECTION_BUTTON)
    click_element(wait, ONE_WAY_TICKET)

    wro_to_anywhere = get_from_wro_to_anywhere_flights(wait)
    anywhere_to_wro = get_from_anywhere_to_wro_flights(wait)
    # Dump list to JSON
    with open('date_price_list.json', 'w', encoding='utf-8') as f:
        json.dump(
            {
                'wrocław_to_anywhere': wro_to_anywhere,
                'anywhere_to_wrocław': anywhere_to_wro
            }, f, ensure_ascii=False, indent=2
        )


def get_from_wro_to_anywhere_flights(wait: WebDriverWait) -> list[dict]:
    # Choose start airport
    click_element(wait, REMOVE_START_AIRPORT)
    click_element(wait, CHOOSE_START_AIRPORT)
    st_airport = 'WRO'
    choose_start_airport = wait.until(EC.element_to_be_clickable(CHOOSE_START_AIRPORT))
    choose_start_airport.send_keys(st_airport)
    click_element(wait, START_AIRPORT)
    with open('iata_codes.txt', 'rt') as f:
        iata_codes = f.read()
    iata_codes = iata_codes.split('\n')
    iata_codes = [iata.strip() for iata in iata_codes]
    date_price_list = []
    for i, dst_airport in enumerate(iata_codes):
        destination = wait.until(EC.element_to_be_clickable(DESTINATION))
        destination.click()
        destination.send_keys(dst_airport)
        try:
            destination_airport = wait.until(EC.element_to_be_clickable(DESTINATION_AIRPORT))
        except TimeoutException:
            destination_airport = wait.until(EC.element_to_be_clickable(DESTINATION_AIRPORT_ENG))
        destination_airport_name = destination_airport.text
        destination_airport.click()

        click_element(wait, DATE_INPUT)

        click_count = 0
        while 'październik' not in get_month_name(wait) and click_count < 12:
            try:
                wait.until(EC.presence_of_all_elements_located(PRICE_SPAN))
            except TimeoutException:
                break

            calendar_days = wait.until(EC.presence_of_all_elements_located(CALENDAR_DAY))
            if click_count == 0:
                calendar_days = calendar_days[1:]

            for day in calendar_days:
                date_value = day.get_attribute('data-value')
                try:
                    date = datetime.strptime(date_value, '%Y-%m-%d').date()
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
                    price = int(price_div.text.split(' ')[0])
                except ValueError:
                    print("Incorrect price", price_div.text, "HTML: ", price_div.get_attribute('outerHTML'))
                    raise

                info = FlightInfo(st_airport, 'Wrocław', dst_airport, destination_airport_name, date, price)
                date_price_list.append(info)
            click_count += 1
            click_element(wait, NEXT_BUTTON)

        date_input = wait.until(EC.element_to_be_clickable(DATE_INPUT))
        date_input.send_keys(Keys.ESCAPE)

        destination = wait.until(EC.element_to_be_clickable(DESTINATION))
        destination.click()

        remove_dst_airport = wait.until(EC.element_to_be_clickable(REMOVE_DST_AIRPORT))
        remove_dst_airport.click()
    return [info.to_dict() for info in date_price_list]


def get_from_anywhere_to_wro_flights(wait: WebDriverWait) -> list[dict]:
    with open('iata_codes.txt', 'rt') as f:
        iata_codes = f.read()
    iata_codes = iata_codes.split('\n')
    iata_codes = [iata.strip() for iata in iata_codes]

    # Choose start airport
    click_element(wait, REMOVE_START_AIRPORT)
    click_element(wait, DESTINATION)
    st_airport = 'WRO'
    choose_dst_airport = wait.until(EC.element_to_be_clickable(DESTINATION))
    choose_dst_airport.send_keys(st_airport)
    click_element(wait, DESTINATION_AIRPORT)
    date_price_list = []
    for i, src_airport in enumerate(iata_codes):
        origin = wait.until(EC.element_to_be_clickable(CHOOSE_START_AIRPORT))
        origin.click()
        origin.send_keys(src_airport)
        try:
            origin_airport = wait.until(EC.element_to_be_clickable(START_AIRPORT))
        except TimeoutException:
            origin_airport = wait.until(EC.element_to_be_clickable(DESTINATION_AIRPORT_ENG))
        origin_airport_name = origin_airport.text
        origin_airport.click()

        click_element(wait, DATE_INPUT)

        click_count = 0
        while 'październik' not in get_month_name(wait) and click_count < 12:
            try:
                wait.until(EC.presence_of_all_elements_located(PRICE_SPAN))
            except TimeoutException:
                break

            calendar_days = wait.until(EC.presence_of_all_elements_located(CALENDAR_DAY))
            if click_count == 0:
                calendar_days = calendar_days[1:]

            for day in calendar_days:
                date_value = day.get_attribute('data-value')
                try:
                    date = datetime.strptime(date_value, '%Y-%m-%d').date()
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
                    price = int(price_div.text.split(' ')[0])
                except ValueError:
                    print("Incorrect price", price_div.text, "HTML: ", price_div.get_attribute('outerHTML'))
                    raise
                start: str
                end: str
                end_name: str
                date: datetime.date
                price: int
                info = FlightInfo(src_airport, origin_airport_name, st_airport, 'Wrocław', date, price)
                date_price_list.append(info)
            click_count += 1
            click_element(wait, NEXT_BUTTON)

        date_input = wait.until(EC.element_to_be_clickable(DATE_INPUT))
        date_input.send_keys(Keys.ESCAPE)

        origin = wait.until(EC.element_to_be_clickable(CHOOSE_START_AIRPORT))
        origin.click()

        remove_dst_airport = wait.until(EC.element_to_be_clickable(REMOVE_START_AIRPORT))
        remove_dst_airport.click()
    return [info.to_dict() for info in date_price_list]


if __name__ == '__main__':
    main()
