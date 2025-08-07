import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date, time
from pathlib import Path
from typing import TypeAlias

import dacite

from kiwi_scrapper import FlightInfo

TripsDict: TypeAlias = dict[str, list[dict[str, FlightInfo | int]]]


@dataclass(frozen=True, slots=True)
class FlightTimetable:
    """Represents the timetable for a specific flight route."""
    start_time: time
    landing_time: time
    weekdays: list[int]
    start_date: date
    end_date: date


class BaseFlightProcessor(ABC):
    """
    An abstract base class for processing flight information.

    It handles loading flight timetables, parsing data, and filtering flights
    based on various criteria like price. Subclasses must implement the

    `process_flights_info` method.
    """
    def __init__(self, price_limit: int, iata_list: list[str]):
        """
        Initializes the BaseFlightProcessor.

        Args:
            price_limit: The maximum price for a flight to be considered.
            iata_list: A list of IATA codes for which to load timetables.
        """
        super().__init__()
        self.price_limit = price_limit
        self.timetables: dict[str, dict[str, dict[str, list[FlightTimetable]]]] = {}
        timetables_path = Path('timetables')
        for iata in iata_list:
            timetable_file = timetables_path / f'{iata.upper()}_timetable.json'
            with open(timetable_file, 'rt', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.timetables[iata] = self._parse_timetable(loaded_data)

    @staticmethod
    def _parse_date(date_str: str, formats: list[str] | None = None) -> date:
        """
        Parses a date string into a date object.

        Args:
            date_str: The date string to parse.
            formats: A list of possible date formats. Defaults to ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"].

        Returns:
            A date object.

        Raises:
            ValueError: If the date string cannot be parsed with any of the provided formats.
        """
        if formats is None:
            formats = ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"]

        for date_format in formats:
            try:
                return datetime.strptime(date_str, date_format).date()
            except ValueError:
                continue

        raise ValueError(f"Date string '{date_str}' is not in a recognized format. Supported formats: {formats}")

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """
        Parses a time string into a time object.

        An empty string defaults to '23:59'.

        Args:
            time_str: The time string to parse (HH:MM).

        Returns:
            A time object.

        Raises:
            ValueError: If the time string is not in the 'HH:MM' format.
        """
        if not time_str:
            time_str = '23:59'
        try:
            time_format = "%H:%M"
            return datetime.strptime(time_str, time_format).time()
        except ValueError as e:
            raise ValueError(f"Time string '{time_str}' is not in the correct format 'HH:MM'.") from e

    @staticmethod
    def _parse_to_weekday_number(weekdays: list[str | int]) -> list[int]:
        """
        Converts a list of weekday representations to integer weekdays (Monday=0, Sunday=6).

        Args:
            weekdays: A list of weekdays (e.g., ["PN", "WT", 3]).

        Returns:
            A list of integer representations of weekdays.

        Raises:
            ValueError: If an unknown weekday representation is provided.
        """
        weekday_map = {
            "PN": 0, "Pn": 0, 1: 0,  # Monday
            "WT": 1, "Wt": 1, 2: 1,  # Tuesday
            "ŚR": 2, "Śr": 2, 3: 2,  # Wednesday
            "CZ": 3, "Cz": 3, 4: 3,  # Thursday
            "PT": 4, "Pt": 4, 5: 4,  # Friday
            "SB": 5, "So": 5, 6: 5,  # Saturday
            "NDZ": 6, "Nd": 6, 7: 6,  # Sunday
        }
        parsed_weekdays = []
        for day in weekdays:
            weekday = weekday_map.get(day)
            if weekday is None:
                raise ValueError(f"Unknown weekday: {day}")
            parsed_weekdays.append(weekday)
        return parsed_weekdays

    def _parse_timetable(self, loaded_data: dict) -> dict[str, dict[str, list[FlightTimetable]]]:
        """
        Parses timetable data from a dictionary into FlightTimetable objects.

        Args:
            loaded_data: The dictionary containing timetable information.

        Returns:
            A nested dictionary with flight timetables.
            Structure: {way_type: {iata: [FlightTimetable, ...]}}
        """
        flights_info = {}
        for way_type, timetables in loaded_data.items():
            one_way_info: dict[str, list[FlightTimetable]] = defaultdict(list)
            for iata, timetable in timetables.items():
                for flight in timetable:
                    data_to_parse = dict(
                        end_date=self._parse_date(flight['end_date']),
                        start_date=self._parse_date(flight['start_date']),
                        start_time=self._parse_time(flight['start_time']),
                        landing_time=self._parse_time(flight['landing_time']),
                        weekdays=self._parse_to_weekday_number(flight['weekdays']),
                    )
                    one_way_info[iata].append(dacite.from_dict(data=data_to_parse, data_class=FlightTimetable))
            flights_info[way_type] = dict(one_way_info)
        return flights_info

    @staticmethod
    def filter_by_price(data: list[FlightInfo], price_limit: int) -> list[FlightInfo]:
        """
        Filters a list of flights by price.

        Args:
            data: A list of FlightInfo objects.
            price_limit: The maximum price allowed.

        Returns:
            A list of FlightInfo objects with price less than the limit.
        """
        return [item for item in data if item.price < price_limit]

    def filter_by_total_price_flights(self, available_trips: TripsDict) -> TripsDict:
        """
        Filters a dictionary of trips by total price against the instance's price_limit.

        Args:
            available_trips: A dictionary of trips, where each trip has a 'total_price'.

        Returns:
            A dictionary of trips with total price less than the instance's price_limit.
        """
        filtered: TripsDict = defaultdict(list)
        for iata, trips in available_trips.items():
            for trip in trips:
                if trip['total_price'] < self.price_limit:
                    filtered[iata].append(trip)
        return filtered

    @staticmethod
    def group_flights_by_key(data: list, key: str) -> dict:
        """
        Groups a list of objects by a specified attribute key.

        Args:
            data: A list of objects.
            key: The attribute name to group by.

        Returns:
            A dictionary where keys are attribute values and values are lists of objects.
        """
        grouped = defaultdict(list)
        for item in data:
            grouped[getattr(item, key)].append(item)
        return dict(grouped)

    @staticmethod
    def _convert_price_to_int(price: str | int) -> int:
        """
        Converts a price from string or int to int.

        Args:
            price: The price to convert.

        Returns:
            The price as an integer.

        Raises:
            ValueError: If the price is not a string or an integer.
        """
        if isinstance(price, int):
            return price
        if isinstance(price, str):
            return int(price)
        raise ValueError(f'Wrong type of price [{type(price)}]')

    def convert_prices(self, data: list[FlightInfo]) -> list[FlightInfo]:
        """
        Converts the 'price' attribute of each FlightInfo object in a list to an integer.

        Args:
            data: A list of FlightInfo objects.

        Returns:
            The list of FlightInfo objects with prices converted to integers.
        """
        for flight in data:
            flight.price = self._convert_price_to_int(flight.price)
        return data

    def get_flight_time(self, flight: FlightInfo, flight_type: str = 'departures') -> time | None:
        """
        Gets the scheduled start time for a flight based on its date and route.

        Args:
            flight: The FlightInfo object.
            flight_type: The type of flight, either 'departures' or 'arrivals'.

        Returns:
            The scheduled start time of the flight, or None if not found in the timetable.
        """
        start_iata = flight.start if flight_type == 'departures' else flight.end
        end_iata = flight.end if flight_type == 'departures' else flight.start
        timetable = self.timetables[start_iata][flight_type][end_iata]
        for flight_info in timetable:
            if (flight_info.start_date <= flight.date <= flight_info.end_date and
                    flight.date.weekday() in flight_info.weekdays):
                return flight_info.start_time
        logging.error(f'No flight found for {flight}, weekdays: {flight.date.strftime("%A")}')
        return None

    @abstractmethod
    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        """
        Processes flight information and returns a formatted string.

        This method must be implemented by subclasses.

        Args:
            data: A dictionary containing lists of flights, keyed by 'departures' and 'arrivals'.

        Returns:
            A formatted string with the processed flight information.
        """
        raise NotImplementedError
