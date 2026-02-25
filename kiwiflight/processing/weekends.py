from collections import defaultdict
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tqdm import tqdm

from .base import BaseFlightProcessor, TripsDict
from ..models import FlightInfo


class FlightProcessorWeekends(BaseFlightProcessor):
    """Find short weekend (or near-weekend) round trips subject to timing constraints."""

    def __init__(self, price_limit: int, min_trip_hours: int, max_start_hour: int, iata_list: list[str]):
        super().__init__(price_limit, iata_list)
        self.min_trip_hours = min_trip_hours
        self.start_weekdays = {4, 5}  # Fri, Sat
        self.end_weekdays = {6, 0, 1}  # Sun, Mon, Tue
        self.max_start_hour = time(hour=max_start_hour)

    # ------------- filtering helpers --------------
    @staticmethod
    def _filter_by_weekdays(data: Iterable[FlightInfo], weekdays: set[int]) -> list[FlightInfo]:
        return [f for f in data if f.date.weekday() in weekdays]

    @staticmethod
    def _find_available_trips(
            poland_to_anywhere: dict[str, list[FlightInfo]],
            anywhere_to_poland: dict[str, list[FlightInfo]]
    ) -> TripsDict:
        possible_iatas = set(poland_to_anywhere) & set(anywhere_to_poland)
        available_trips: TripsDict = defaultdict(list)
        for iata in possible_iatas:
            start_flights = poland_to_anywhere[iata]
            back_flights = anywhere_to_poland[iata]
            by_week_start = defaultdict(list)
            by_week_back = defaultdict(list)
            for s in start_flights:
                by_week_start[s.week].append(s)
            for b in back_flights:
                by_week_back[b.week].append(b)
            for week in set(by_week_start) & set(by_week_back):
                for s in by_week_start[week]:
                    for b in by_week_back[week]:
                        if s.date > b.date:
                            continue
                        available_trips[iata].append({
                            'start_flight': s,
                            'back_flight': b,
                            'total_price': s.price + b.price
                        })
        for trips in available_trips.values():
            trips.sort(key=lambda x: x['total_price'])
        return available_trips

    def _filter_and_enrich_trips(self, available_trips: TripsDict) -> TripsDict:
        filtered: TripsDict = defaultdict(list)
        for iata, trips in tqdm(available_trips.items(), desc='Filtering/enriching weekend trips', leave=False):
            for trip in trips:
                s: FlightInfo = trip['start_flight']
                b: FlightInfo = trip['back_flight']
                s_time = self.get_flight_time(s, 'departures')
                b_time = self.get_flight_time(b, 'arrivals')
                s.start_time = s_time
                b.back_time = b_time
                if s_time is None or b_time is None:
                    continue
                if s.date != b.date:
                    filtered[iata].append(trip)
                    continue
                if s_time > self.max_start_hour:
                    continue
                s_dt = datetime.combine(s.date, s_time)
                b_dt = datetime.combine(b.date, b_time)
                if b_dt - s_dt >= timedelta(hours=self.min_trip_hours):
                    filtered[iata].append(trip)
        return filtered

    # ------------- formatting --------------
    def _format_trips_to_html(self, trips: TripsDict) -> str:
        sorted_destinations = sorted(trips.items(), key=lambda it: it[1][0]['start_flight'].end_name if it[1] else '')
        formatted = []
        for iata, fls in sorted_destinations:
            if not fls:
                continue
            dest_name = fls[0]['start_flight'].end_name
            lowest = fls[0]['total_price']
            weeks = []
            by_week: dict[int, list] = {}
            for trip in fls:
                by_week.setdefault(trip['start_flight'].week, []).append(trip)
            for week, trips_list in sorted(by_week.items()):
                unique = list({str(t): t for t in trips_list}.values())
                entries = []
                for info in sorted(unique, key=lambda x: x['total_price']):
                    s = info['start_flight']; b = info['back_flight']
                    duration = (b.date - s.date).days
                    entries.append({
                        'total_price': info['total_price'],
                        'duration': duration,
                        'start_date': s.date.strftime('%Y-%m-%d (%A)'),
                        'start_name': s.start_name,
                        'start_code': s.start,
                        'start_time': s.start_time.strftime('%H:%M'),
                        'back_date': b.date.strftime('%Y-%m-%d (%A)'),
                        'back_name': b.end_name,
                        'back_code': b.end,
                        'back_time': b.back_time.strftime('%H:%M'),
                    })
                weeks.append({'week': week, 'trips': entries})
            formatted.append({'destination_name': dest_name, 'iata': iata, 'lowest_price': lowest, 'weeks': weeks})
        templates_dir = Path(__file__).resolve().parents[2] / 'templates'
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape(['html', 'xml']))
        tpl = env.get_template('weekend_deals.html.j2')
        generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")
        rendered = tpl.render(destinations=formatted, generated_at=generated_at)
        soup = BeautifulSoup(rendered, 'lxml')
        return soup.prettify()

    # ------------- public API --------------
    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        poland_to_anywhere = data['poland_to_anywhere']
        anywhere_to_poland = data['anywhere_to_poland']
        self.convert_prices(poland_to_anywhere)
        self.convert_prices(anywhere_to_poland)
        poland_to_anywhere_filtered = self._filter_by_weekdays(poland_to_anywhere, self.start_weekdays)
        anywhere_to_poland_filtered = self._filter_by_weekdays(anywhere_to_poland, self.end_weekdays)
        poland_to_anywhere_filtered = self.filter_by_price(poland_to_anywhere_filtered, self.price_limit)
        anywhere_to_poland_filtered = self.filter_by_price(anywhere_to_poland_filtered, self.price_limit)
        grouped_poland_to_anywhere = self.group_flights_by_key(poland_to_anywhere_filtered, 'end')
        grouped_anywhere_to_poland = self.group_flights_by_key(anywhere_to_poland_filtered, 'start')
        available_trips = self._find_available_trips(grouped_poland_to_anywhere, grouped_anywhere_to_poland)
        available_trips = self._filter_and_enrich_trips(available_trips)
        available_trips = self.filter_by_total_price_flights(available_trips)
        return self._format_trips_to_html(available_trips)

