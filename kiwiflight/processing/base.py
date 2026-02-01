import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from typing import TypeAlias

import dacite

from ..models import FlightInfo, FlightTimetable

TripsDict: TypeAlias = dict[str, list[dict[str, FlightInfo | int]]]


class BaseFlightProcessor(ABC):
    """Common helpers for concrete flight processors."""
    def __init__(self, price_limit: int, iata_list: list[str]):
        self.price_limit = price_limit
        self.timetables: dict[str, dict[str, dict[str, list[FlightTimetable]]]] = {}
        timetables_path = Path('timetables')  # keep relative to project root
        for iata in iata_list:
            timetable_file = timetables_path / f'{iata.upper()}_timetable.json'
            with open(timetable_file, 'rt', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.timetables[iata] = self._parse_timetable(loaded_data)

    # ---------------- Parsing helpers -----------------
    @staticmethod
    def _parse_date(date_str: str, formats: list[str] | None = None) -> date:
        if formats is None:
            formats = ["%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"]
        for date_format in formats:
            try:
                return datetime.strptime(date_str, date_format).date()
            except ValueError:
                continue
        raise ValueError(f"Date string '{date_str}' not in formats {formats}")

    @staticmethod
    def _parse_time(time_str: str) -> time:
        if not time_str:
            time_str = '23:59'
        return datetime.strptime(time_str, "%H:%M").time()

    @staticmethod
    def _parse_to_weekday_number(weekdays: list[str | int]) -> list[int]:
        weekday_map = {"PN":0,"Pn":0,1:0,"WT":1,"Wt":1,2:1,"ŚR":2,"Śr":2,3:2,"CZ":3,"Cz":3,4:3,
                       "PT":4,"Pt":4,5:4,"SB":5,"So":5,6:5,"NDZ":6,"Nd":6,7:6}
        parsed = []
        for day in weekdays:
            if (val := weekday_map.get(day)) is None:
                raise ValueError(f"Unknown weekday: {day}")
            parsed.append(val)
        return parsed

    def _parse_timetable(self, loaded_data: dict) -> dict[str, dict[str, list[FlightTimetable]]]:
        flights_info = {}
        for way_type, timetables in loaded_data.items():
            one_way: dict[str, list[FlightTimetable]] = defaultdict(list)
            for iata, timetable in timetables.items():
                for flight in timetable:
                    data_to_parse = dict(
                        end_date=self._parse_date(flight['end_date']),
                        start_date=self._parse_date(flight['start_date']),
                        start_time=self._parse_time(flight['start_time']),
                        landing_time=self._parse_time(flight['landing_time']),
                        weekdays=self._parse_to_weekday_number(flight['weekdays']),
                    )
                    one_way[iata].append(dacite.from_dict(data=data_to_parse, data_class=FlightTimetable))
            flights_info[way_type] = dict(one_way)
        return flights_info

    # ---------------- Filtering / grouping -----------------
    @staticmethod
    def filter_by_price(data: list[FlightInfo], price_limit: int) -> list[FlightInfo]:
        return [f for f in data if f.price < price_limit]

    def filter_by_total_price_flights(self, available_trips: TripsDict) -> TripsDict:
        filtered: TripsDict = defaultdict(list)
        for iata, trips in available_trips.items():
            for trip in trips:
                if trip['total_price'] < self.price_limit:
                    filtered[iata].append(trip)
        return filtered

    @staticmethod
    def filter_non_direct_flights(available_trips: TripsDict) -> TripsDict:
        filtered: TripsDict = defaultdict(list)
        for iata, trips in available_trips.items():
            for trip in trips:
                if trip['start_flight'].start_time and trip['back_flight'].back_time:
                    filtered[iata].append(trip)
        return filtered

    @staticmethod
    def group_flights_by_key(data: list, key: str) -> dict:
        grouped = defaultdict(list)
        for item in data:
            grouped[getattr(item, key)].append(item)
        return dict(grouped)

    @staticmethod
    def _convert_price_to_int(price: str | int) -> int:
        if isinstance(price, int):
            return price
        if isinstance(price, str):
            return int(price)
        raise ValueError(f'Wrong price type {type(price)}')

    def convert_prices(self, data: list[FlightInfo]) -> list[FlightInfo]:
        for flight in data:
            flight.price = self._convert_price_to_int(flight.price)
        return data

    def get_flight_time(self, flight: FlightInfo, flight_type: str = 'departures') -> time | None:
        start_iata = flight.start if flight_type == 'departures' else flight.end
        end_iata = flight.end if flight_type == 'departures' else flight.start
        timetable = self.timetables[start_iata][flight_type][end_iata]
        for flight_info in timetable:
            if flight_info.start_date <= flight.date <= flight_info.end_date and flight.date.weekday() in flight_info.weekdays:
                return flight_info.start_time
        logging.error('No timetable flight match for %s (%s)', flight, flight.date.strftime('%A'))
        return None

    @abstractmethod
    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:  # pragma: no cover
        raise NotImplementedError
