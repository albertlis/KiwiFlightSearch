import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from datetime import datetime, timedelta
from io import StringIO

import schedule
import yagmail
import yaml
from easydict import EasyDict
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

PRICE_LIMIT = 200
START_WEEKDAYS = {4, 5}  # Friday, Saturday
END_WEEKDAYS = {5, 6, 0}  # Saturday, Sunday, Monday

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

    def to_dict(self) -> dict[str, str | int]:
        return {
            'start': self.start,
            'end': self.end,
            'end_name': self.end_name,
            'date': self.date.isoformat(),
            'price': self.price
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
        for dst_airport_code in tqdm(iata_codes, desc=start_airport_name):
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


def load_data(file_path: str) -> dict:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_dates(data: list) -> None:
    for item in data:
        item['date'] = datetime.strptime(item['date'], '%Y-%m-%d')


def filter_by_weekdays(data: list, weekdays: set) -> list:
    return [item for item in data if item['date'].weekday() in weekdays]


def filter_by_price(data: list, price_limit: int) -> list:
    return [item for item in data if item['price'] < price_limit]


def get_week_number(date: datetime) -> int:
    if date.weekday() == 0:
        date -= timedelta(days=1)
    return date.isocalendar()[1]


def add_week_number(data: list) -> None:
    for item in data:
        item['week'] = get_week_number(item['date'])


def group_flights_by_key(data: list, key: str) -> dict:
    grouped = defaultdict(list)
    for item in data:
        grouped[item[key]].append(item)
    return dict(grouped)


def find_available_trips(poland_to_anywhere: dict, anywhere_to_poland: dict) -> dict:
    possible_iatas = set(poland_to_anywhere).intersection(anywhere_to_poland)
    available_trips = defaultdict(list)
    for iata in possible_iatas:
        start_flights = poland_to_anywhere[iata]
        back_flights = anywhere_to_poland[iata]
        available_weekends = {flight['week'] for flight in start_flights}.intersection(
            (flight['week'] for flight in back_flights)
        )

        for weekend in available_weekends:
            weekend_start_flights = [flight for flight in start_flights if flight['week'] == weekend]
            weekend_back_flights = [flight for flight in back_flights if flight['week'] == weekend]

            for start_flight in weekend_start_flights:
                for back_flight in weekend_back_flights:
                    trip = {
                        'start_flight': start_flight,
                        'back_flight': back_flight,
                        'total_price': start_flight['price'] + back_flight['price']
                    }
                    if trip not in available_trips[iata]:
                        available_trips[iata].append(trip)

    # Sort the trips by total price
    for value in available_trips.values():
        value.sort(key=lambda x: x['total_price'])

    return available_trips


def print_flights_grouped_by_weekend(trips: dict) -> str:
    printed_destinations = set()
    print_data = StringIO()
    for iata, flights in trips.items():
        if flights:
            destination_name = flights[0]['start_flight']['end_name']  # Assuming end_name exists
            if destination_name not in printed_destinations:
                print(f"\nDestination: {destination_name} ({iata})", file=print_data)
                print("-" * 40, file=print_data)
                printed_destinations.add(destination_name)

                weekends = defaultdict(list)
                for flight in flights:
                    week = flight['start_flight']['week']
                    weekends[week].append(flight)

                for week, weekend_flights in weekends.items():
                    print(f"  Week {week}:", file=print_data)
                    weekend_flights = list(
                        {str(flight): flight for flight in weekend_flights}.values())  # Remove duplicates
                    for flight_info in sorted(weekend_flights, key=lambda x: x['total_price']):
                        start_flight = flight_info['start_flight']
                        back_flight = flight_info['back_flight']
                        total_price = flight_info['total_price']

                        start_date_str = start_flight['date'].strftime("%Y-%m-%d (%A)")
                        back_date_str = back_flight['date'].strftime("%Y-%m-%d (%A)")

                        print(
                            f"    Start Date: {start_date_str} from {back_flight['end_name']} ({start_flight['start']}), "
                            f"Return Date: {back_date_str} to {start_flight['end_name']} ({back_flight['start']}), "
                            f"Total Price: {total_price}", file=print_data
                        )
                        print("    " + "-" * 30, file=print_data)


def convert_price_to_int(price: str | int) -> int:
    if isinstance(price, int):
        return price
    if isinstance(price, str):
        return int(price)
    raise ValueError(f'Wrong type of price [{type(price)}]')


def convert_prices(data: list) -> list:
    for flight in data:
        flight['price'] = convert_price_to_int(flight['price'])
    return data


def webscrap_flights() -> None:
    driver: webdriver.Chrome = get_driver()
    driver.get(URL)
    wait: WebDriverWait = WebDriverWait(driver, 60)

    # Accept cookies
    click_element(wait, COOKIES_BUTTON)
    click_element(wait, DISCARD_COOKIES)

    # Choose one way ticket
    click_element(wait, DIRECTION_BUTTON)
    click_element(wait, ONE_WAY_TICKET)

    start_airports = ['POZ', 'WRO', ]
    start_airports_names = ['Poznań', 'Wrocław', ]

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


def process_flights_info() -> str:
    data = load_data('date_price_list.json')

    poland_to_anywhere = data['poland_to_anywhere']
    anywhere_to_poland = data['anywhere_to_poland']

    convert_prices(poland_to_anywhere)
    convert_prices(anywhere_to_poland)

    parse_dates(poland_to_anywhere)
    parse_dates(anywhere_to_poland)

    poland_to_anywhere_filtered = filter_by_weekdays(poland_to_anywhere, START_WEEKDAYS)
    anywhere_to_poland_filtered = filter_by_weekdays(anywhere_to_poland, END_WEEKDAYS)

    poland_to_anywhere_filtered = filter_by_price(poland_to_anywhere_filtered, PRICE_LIMIT)
    anywhere_to_poland_filtered = filter_by_price(anywhere_to_poland_filtered, PRICE_LIMIT)

    add_week_number(poland_to_anywhere_filtered)
    add_week_number(anywhere_to_poland_filtered)

    grouped_poland_to_anywhere = group_flights_by_key(poland_to_anywhere_filtered, 'end')
    grouped_anywhere_to_poland = group_flights_by_key(anywhere_to_poland_filtered, 'start')

    available_trips = find_available_trips(grouped_poland_to_anywhere, grouped_anywhere_to_poland)

    return print_flights_grouped_by_weekend(available_trips)


def send_mail(print_info: str) -> None:
    with open('secrets.yml', 'rt') as f:
        secrets = EasyDict(yaml.safe_load(f))
    email_subject = 'Loty Kiwi'
    yag = yagmail.SMTP(secrets.src_mail, secrets.src_pwd, port=587, smtp_starttls=True, smtp_ssl=False)
    yag.send(to=secrets.dst_mail, subject=email_subject, contents=(print_info, 'text'))


def main() -> None:
    webscrap_flights()
    print_info = process_flights_info()
    send_mail(print_info)


if __name__ == '__main__':
    logging.basicConfig(filename='error.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
    schedule.every().saturday.at("09:00").do(main)
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logging.exception("An error occurred:")
            print(e)
            time.sleep(60 * 60)
        time.sleep(1)
    # main()
