import json
import logging
import pickle
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, date, time
from io import StringIO
from pathlib import Path

import dacite
from tqdm import tqdm

from kiwi_scrapper import FlightInfo

TripsDict = dict[str, list[dict[str, FlightInfo | int]]]


@dataclass(frozen=True, slots=True)
class FlightTimetable:
    start_time: time
    landing_time: time
    weekdays: list[int]
    start_date: date
    end_date: date


class FlightProcessor:
    def __init__(self, price_limit: int, min_trip_hours: int, max_start_hour: int, iata_list: list[str]):
        super().__init__()
        self.price_limit = price_limit
        self.min_trip_hours = min_trip_hours
        self.start_weekdays = {4, 5}  # Friday, Saturday
        self.end_weekdays = {5, 6, 0}  # Saturday, Sunday, Monday
        self.max_start_hour = datetime.strptime(f"{max_start_hour}:00", '%H:%M').time()

        self.timetables = {}
        timetables_path = Path('timetables')
        for iata in iata_list:
            with open(timetables_path / f'{iata.upper()}_timetable.json', 'rt', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.timetables[iata] = self.parse_timetable(loaded_data)
        # self.set_date_locator = (By.CSS_SELECTOR, 'button[data-test="SearchFormDoneButton"]')
        # self.search_button_locator = (By.XPATH, "//div[text()='Wyszukaj']")
        # self.first_trip_timestamp_locator = (By.CSS_SELECTOR, "div[data-test='TripTimestamp'] time")
        # self.kiwi_logo_locator = (By.CSS_SELECTOR, "a[data-test='Logo']")

    @staticmethod
    def parse_date(date_str: str, formats: list[str] = None) -> datetime.date:
        if formats is None:
            formats = ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"]

        # Try each format until one works
        for date_format in formats:
            try:
                return datetime.strptime(date_str, date_format).date()
            except ValueError:
                continue

        raise ValueError(f"Date string '{date_str}' is not in a recognized format. Supported formats: {formats}")

    @staticmethod
    def parse_time(time_str: str) -> datetime.time:
        if not time_str:
            time_str = '23:59'
        try:
            time_format = "%H:%M"
            return datetime.strptime(time_str, time_format).time()
        except ValueError as e:
            raise ValueError(f"Time string '{time_str}' is not in the correct format 'HH:MM'.") from e

    @staticmethod
    def parse_to_weekday_number(weekdays: list[str | int]) -> list[int]:
        weekday_map = {
            "PN": 0, "Pn": 0,  1:0, # Monday
            "WT": 1, "Wt": 1,  2:1, # Tuesday
            "ŚR": 2, "Śr": 2,  3:2, # Wednesday
            "CZ": 3, "Cz": 3,  4:3, # Thursday
            "PT": 4, "Pt": 4,  5:4, # Friday
            "SB": 5, "So": 5,  6:5, # Saturday
            "NDZ": 6, "Nd": 6, 7:6, # Sunday
        }
        return [weekday_map.get(day, -1) for day in weekdays]

    def parse_timetable(self, loaded_data: dict) -> dict[str, dict[str, list[FlightTimetable]]]:
        flights_info = {}
        for way_type, timetables in loaded_data.items():
            one_way_info = defaultdict(list)
            for iata, timetable in timetables.items():
                for flight in timetable:
                    data_to_parse = dict(
                        end_date=self.parse_date(flight['end_date']),
                        start_date=self.parse_date(flight['start_date']),
                        start_time=self.parse_time(flight['start_time']),
                        landing_time=self.parse_time(flight['landing_time']),
                        weekdays=self.parse_to_weekday_number(flight['weekdays']),
                    )
                    one_way_info[iata].append(dacite.from_dict(data=data_to_parse, data_class=FlightTimetable))
            flights_info[way_type] = one_way_info
        return flights_info

    @staticmethod
    def filter_by_weekdays(data: list[FlightInfo], weekdays: set) -> list[FlightInfo]:
        return [item for item in data if item.date.weekday() in weekdays]

    @staticmethod
    def filter_by_price(data: list[FlightInfo], price_limit: int) -> list[FlightInfo]:
        return [item for item in data if item.price < price_limit]

    def filter_by_total_price_flights(self, available_trips: TripsDict) -> TripsDict:
        filtered = defaultdict(list)
        for iata, trips in available_trips.items():
            for trip in trips:
               if trip['total_price'] < self.price_limit:
                   filtered[iata].append(trip)
        return filtered

    @staticmethod
    def group_flights_by_key(data: list, key: str) -> dict:
        grouped = defaultdict(list)
        for item in data:
            grouped[getattr(item, key)].append(item)
        return dict(grouped)

    @staticmethod
    def convert_price_to_int(price: str | int) -> int:
        if isinstance(price, int):
            return price
        if isinstance(price, str):
            return int(price)
        raise ValueError(f'Wrong type of price [{type(price)}]')

    def convert_prices(self, data: list[FlightInfo]) -> list[FlightInfo]:
        for flight in data:
            flight.price = self.convert_price_to_int(flight.price)
        return data

    @staticmethod
    def find_available_trips(
            poland_to_anywhere: dict[str, list[FlightInfo]], anywhere_to_poland: dict[str, list[FlightInfo]]
    ) -> TripsDict:
        possible_iatas = set(poland_to_anywhere).intersection(anywhere_to_poland)
        available_trips = defaultdict(list)
        for iata in possible_iatas:
            start_flights = poland_to_anywhere[iata]
            back_flights = anywhere_to_poland[iata]
            available_weekends = {flight.week for flight in start_flights}.intersection(
                (flight.week for flight in back_flights)
            )

            for weekend in available_weekends:
                weekend_start_flights = [flight for flight in start_flights if flight.week == weekend]
                weekend_back_flights = [flight for flight in back_flights if flight.week == weekend]

                for start_flight in weekend_start_flights:
                    for back_flight in weekend_back_flights:
                        trip: dict[str, FlightInfo | int] = {
                            'start_flight': start_flight,
                            'back_flight': back_flight,
                            'total_price': start_flight.price + back_flight.price
                        }
                        if trip not in available_trips[iata]:
                            available_trips[iata].append(trip)

        # Sort the trips by total price
        for value in available_trips.values():
            value.sort(key=lambda x: x['total_price'])

        return available_trips

    def get_flight_time(self, flight: FlightInfo, type: str = 'departures') -> time | None:
        start_iata = flight.start if type == 'departures' else flight.end
        end_iata = flight.end if type == 'departures' else flight.start
        timetable = self.timetables[start_iata][type][end_iata]
        for flight_info in timetable:
            if flight_info.start_date <= flight.date <= flight_info.end_date and flight.date.weekday() in flight_info.weekdays:
                return flight_info.start_time
        logging.error(f'No flight found for {flight}')
        return None

    def filter_same_day_flights(self, available_trips: TripsDict) -> TripsDict:
        filtered = defaultdict(list)
        # checkpoint = dict(filtered=filtered, last_iata=None)

        # with open('checkpoint.pkl', 'rb') as f:
        #     loaded_checkpoint = pickle.load(f)
        # loaded_checkpoint = None
        for iata, trips in tqdm(available_trips.items(), desc='Filtering same day flights', position=0, leave=False):
            # if loaded_checkpoint and loaded_checkpoint['last_iata'] != iata:
            #     continue
            #
            for trip in trips:
                start_flight = trip['start_flight']
                back_flight = trip['back_flight']
                start_time = self.get_flight_time(start_flight)
                back_time = self.get_flight_time(back_flight, 'arrivals')
                start_flight.start_time = start_time
                back_flight.back_time = back_time
                # Międzylądowanie
                if None in (start_time, back_time):
                    continue

                if start_flight.date != back_flight.date:
                    filtered[iata].append(trip)
                    continue


                if start_time > self.max_start_hour:
                    continue
                start_datetime = datetime.combine(datetime.now(), start_time)
                back_datetime = datetime.combine(datetime.now(), back_time)
                if back_datetime - start_datetime > timedelta(hours=self.min_trip_hours):
                    filtered[iata].append(trip)
        return filtered


    @staticmethod
    def print_flights_grouped_by_weekend(trips: TripsDict) -> str:
        printed_destinations = set()
        print_data = StringIO()
        for iata, flights in trips.items():
            if flights:
                destination_name = flights[0]['start_flight'].end_name  # Assuming end_name exists
                if destination_name not in printed_destinations:
                    print(f"\nDestination: {destination_name} ({iata})", file=print_data)
                    print("-" * 40, file=print_data)
                    printed_destinations.add(destination_name)

                    weekends = defaultdict(list)
                    for flight in flights:
                        week = flight['start_flight'].week
                        weekends[week].append(flight)

                    for week, weekend_flights in sorted(weekends.items()):
                        print(f"  Week {week}:", file=print_data)
                        weekend_flights = list(
                            {str(flight): flight for flight in weekend_flights}.values())  # Remove duplicates
                        for flight_info in sorted(weekend_flights, key=lambda x: x['total_price']):
                            start_flight = flight_info['start_flight']
                            back_flight = flight_info['back_flight']
                            total_price = flight_info['total_price']

                            start_date_str = start_flight.date.strftime("%Y-%m-%d (%A)")
                            back_date_str = back_flight.date.strftime("%Y-%m-%d (%A)")

                            print(
                                f"    Total Price: {total_price}zł, "
                                f"Start Date: {start_date_str} from {start_flight.start_name} ({start_flight.start}) at {start_flight.start_time}, "
                                f"Return Date: {back_date_str} to {back_flight.end_name} ({back_flight.end}) at {back_flight.back_time}, "
                                , file=print_data
                            )
                            print("    " + "-" * 30, file=print_data)
        return print_data.getvalue()

    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        poland_to_anywhere = data['poland_to_anywhere']
        anywhere_to_poland = data['anywhere_to_poland']

        self.convert_prices(poland_to_anywhere)
        self.convert_prices(anywhere_to_poland)

        poland_to_anywhere_filtered = self.filter_by_weekdays(poland_to_anywhere, self.start_weekdays)
        anywhere_to_poland_filtered = self.filter_by_weekdays(anywhere_to_poland, self.end_weekdays)

        poland_to_anywhere_filtered = self.filter_by_price(poland_to_anywhere_filtered, self.price_limit)
        anywhere_to_poland_filtered = self.filter_by_price(anywhere_to_poland_filtered, self.price_limit)

        grouped_poland_to_anywhere = self.group_flights_by_key(poland_to_anywhere_filtered, 'end')
        grouped_anywhere_to_poland = self.group_flights_by_key(anywhere_to_poland_filtered, 'start')

        available_trips = self.find_available_trips(grouped_poland_to_anywhere, grouped_anywhere_to_poland)
        available_trips = self.filter_same_day_flights(available_trips)
        available_trips = self.filter_by_total_price_flights(available_trips)
        return self.print_flights_grouped_by_weekend(available_trips)
