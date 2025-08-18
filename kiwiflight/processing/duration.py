from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Iterator

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tqdm import tqdm

from .base import BaseFlightProcessor, TripsDict
from ..models import FlightInfo

Trip = dict[str, FlightInfo | int]


class FlightProcessorDuration(BaseFlightProcessor):
    """Find round trips with duration in a chosen day-span window (optionally bounded by date range)."""

    def __init__(self, price_limit: int, min_trip_days: int, max_trip_days: int, iata_list: list[str],
                 start_date: Optional[str] = None, end_date: Optional[str] = None):
        super().__init__(price_limit, iata_list)
        self.min_trip_days = min_trip_days
        self.max_trip_days = max_trip_days
        self.start_date: Optional[date] = datetime.strptime(start_date, "%d.%m.%Y").date() if start_date else None
        self.end_date: Optional[date] = datetime.strptime(end_date, "%d.%m.%Y").date() if end_date else None

    # ---------------- validation helpers -----------------
    def _is_valid_start_flight(self, flight: FlightInfo) -> bool:
        if self.start_date and flight.date < self.start_date:
            return False
        return not self.end_date or flight.date <= self.end_date

    def _is_valid_trip(self, start_flight: FlightInfo, back_flight: FlightInfo) -> bool:
        if start_flight.date >= back_flight.date:
            return False
        if self.start_date and back_flight.date < self.start_date:
            return False
        if self.end_date and back_flight.date > self.end_date:
            return False
        trip_duration = (back_flight.date - start_flight.date).days
        return self.min_trip_days <= trip_duration <= self.max_trip_days

    def _find_trips_for_iata(self, start_flights: list[FlightInfo], back_flights: list[FlightInfo]) -> Iterator[Trip]:
        for start_flight in start_flights:
            if not self._is_valid_start_flight(start_flight):
                continue
            for back_flight in back_flights:
                if self._is_valid_trip(start_flight, back_flight):
                    yield {
                        'start_flight': start_flight,
                        'back_flight': back_flight,
                        'total_price': start_flight.price + back_flight.price
                    }

    # ---------------- core steps -----------------
    def find_available_trips(
            self, poland_to_anywhere: dict[str, list[FlightInfo]], anywhere_to_poland: dict[str, list[FlightInfo]]
    ) -> TripsDict:
        possible_iatas = set(poland_to_anywhere) & set(anywhere_to_poland)
        available_trips: TripsDict = defaultdict(list)
        for iata in tqdm(possible_iatas, desc="Finding trips"):
            start_flights = poland_to_anywhere[iata]
            back_flights = anywhere_to_poland[iata]
            available_trips[iata].extend(self._find_trips_for_iata(start_flights, back_flights))
        for trips in available_trips.values():
            trips.sort(key=lambda x: x['total_price'])
        return available_trips

    def add_flight_times(self, available_trips: TripsDict) -> TripsDict:
        for trips in tqdm(available_trips.values(), desc='Adding flight times', position=0, leave=False):
            for trip in trips:
                s = trip['start_flight']
                b = trip['back_flight']
                s.start_time = self.get_flight_time(s)
                b.back_time = self.get_flight_time(b, 'arrivals')
        return available_trips

    # ---------------- formatting -----------------
    def _format_trips_to_html(self, trips: TripsDict) -> str:
        sorted_destinations = sorted(
            trips.items(),
            key=lambda item: item[1][0]['start_flight'].end_name if item[1] else ""
        )
        formatted = []
        for iata, flights in sorted_destinations:
            if not flights:
                continue
            unique_trips = list({str(f): f for f in flights}.values())
            unique_trips.sort(key=lambda x: x['total_price'])
            if not unique_trips:
                continue
            dest_name = unique_trips[0]['start_flight'].end_name
            lowest = unique_trips[0]['total_price']
            trips_list = []
            for info in unique_trips:
                s = info['start_flight']
                b = info['back_flight']
                duration = (b.date - s.date).days
                trips_list.append({
                    'total_price': info['total_price'],
                    'duration': duration,
                    'start_date': s.date.strftime("%Y-%m-%d (%A)"),
                    'start_name': s.start_name,
                    'start_code': s.start,
                    'start_time': s.start_time.strftime("%H:%M") if s.start_time else "N/A",
                    'back_date': b.date.strftime("%Y-%m-%d (%A)"),
                    'back_name': b.end_name,
                    'back_code': b.end,
                    'back_time': b.back_time.strftime("%H:%M") if b.back_time else "N/A",
                })
            formatted.append({'destination_name': dest_name, 'iata': iata, 'lowest_price': lowest, 'trips': trips_list})

        templates_dir = Path(__file__).resolve().parents[2] / 'templates'
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape(['html', 'xml']))
        tpl = env.get_template('duration_deals.html.j2')
        rendered = tpl.render(destinations=formatted)
        soup = BeautifulSoup(rendered, 'lxml')
        return soup.prettify()

    # ---------------- public API -----------------
    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        poland_to_anywhere = data['poland_to_anywhere']
        anywhere_to_poland = data['anywhere_to_poland']
        self.convert_prices(poland_to_anywhere)
        self.convert_prices(anywhere_to_poland)
        poland_to_anywhere_filtered = self.filter_by_price(poland_to_anywhere, self.price_limit)
        anywhere_to_poland_filtered = self.filter_by_price(anywhere_to_poland, self.price_limit)
        grouped_poland_to_anywhere = self.group_flights_by_key(poland_to_anywhere_filtered, 'end')
        grouped_anywhere_to_poland = self.group_flights_by_key(anywhere_to_pololand_filtered, 'start')
        available_trips = self.find_available_trips(grouped_poland_to_anywhere, grouped_anywhere_to_poland)
        available_trips = self.filter_by_total_price_flights(available_trips)
        available_trips = self.add_flight_times(available_trips)
        return self._format_trips_to_html(available_trips)

