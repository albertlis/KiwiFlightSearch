import os
from collections import defaultdict
from datetime import datetime, timedelta, time
from typing import Iterable

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tqdm import tqdm

from base_flights_processor import BaseFlightProcessor, TripsDict
from kiwi_scrapper import FlightInfo


class FlightProcessorWeekends(BaseFlightProcessor):
    """
    Processes flight information to find weekend trips.

    This processor filters flights to find round trips that start on a Friday or
    Saturday and return on a Saturday, Sunday, or Monday of the same week.
    It also filters based on price, trip duration, and departure time.
    """

    def __init__(self, price_limit: int, min_trip_hours: int, max_start_hour: int, iata_list: list[str]):
        """
        Initializes the FlightProcessorWeekends.

        Args:
            price_limit: The maximum total price for a round trip.
            min_trip_hours: The minimum duration of the trip in hours for same-day returns.
            max_start_hour: The latest valid departure hour for a flight.
            iata_list: A list of IATA codes for airports of origin.
        """
        super().__init__(price_limit, iata_list)
        self.min_trip_hours = min_trip_hours
        self.start_weekdays = {4, 5}  # Friday, Saturday
        self.end_weekdays = {6, 0, 1}  # Sunday, Monday, Tuesday
        self.max_start_hour = time(hour=max_start_hour)

    @staticmethod
    def _filter_by_weekdays(data: Iterable[FlightInfo], weekdays: set[int]) -> list[FlightInfo]:
        """
        Filters flights by the day of the week.

        Args:
            data: An iterable of FlightInfo objects.
            weekdays: A set of integer weekdays (Monday=0) to keep.

        Returns:
            A list of flights that occur on the specified weekdays.
        """
        return [item for item in data if item.date.weekday() in weekdays]

    @staticmethod
    def _find_available_trips(
            poland_to_anywhere: dict[str, list[FlightInfo]], anywhere_to_poland: dict[str, list[FlightInfo]]
    ) -> TripsDict:
        """
        Finds possible round trips from the given departure and arrival flights.

        A trip is considered possible if there's a departure and return flight
        to the same destination within the same calendar week.

        Args:
            poland_to_anywhere: Flights from Poland, grouped by destination IATA.
            anywhere_to_poland: Flights to Poland, grouped by origin IATA.

        Returns:
            A dictionary of possible trips, grouped by destination IATA and
            sorted by total price.
        """
        possible_iatas = set(poland_to_anywhere) & set(anywhere_to_poland)
        available_trips: TripsDict = defaultdict(list)

        for iata in possible_iatas:
            start_flights = poland_to_anywhere[iata]
            back_flights = anywhere_to_poland[iata]

            start_flights_by_week = defaultdict(list)
            for flight in start_flights:
                start_flights_by_week[flight.week].append(flight)

            back_flights_by_week = defaultdict(list)
            for flight in back_flights:
                back_flights_by_week[flight.week].append(flight)

            common_weeks = set(start_flights_by_week) & set(back_flights_by_week)

            for week in common_weeks:
                for start_flight in start_flights_by_week[week]:
                    for back_flight in back_flights_by_week[week]:
                        # Ensure return flight is on the same day or after departure
                        if start_flight.date > back_flight.date:
                            continue

                        trip = {
                            'start_flight': start_flight,
                            'back_flight': back_flight,
                            'total_price': start_flight.price + back_flight.price
                        }
                        available_trips[iata].append(trip)

        # Sort the trips by total price
        for iata_trips in available_trips.values():
            iata_trips.sort(key=lambda x: x['total_price'])

        return available_trips

    def _filter_and_enrich_trips(self, available_trips: TripsDict) -> TripsDict:
        """
        Filters trips based on timing constraints and enriches them with time info.

        This method filters out:
        - Trips where flight times cannot be determined.
        - Same-day trips that are shorter than `min_trip_hours`.
        - Same-day trips where the departure is after `max_start_hour`.

        It also adds `start_time` and `back_time` to the flight objects.

        Args:
            available_trips: A dictionary of trips to filter.

        Returns:
            A filtered dictionary of trips.
        """
        filtered: TripsDict = defaultdict(list)
        for iata, trips in tqdm(available_trips.items(), desc='Filtering and enriching trips', position=0, leave=False):
            for trip in trips:
                start_flight = trip['start_flight']
                back_flight = trip['back_flight']

                start_time = self.get_flight_time(start_flight, 'departures')
                back_time = self.get_flight_time(back_flight, 'arrivals')

                # Attach times to flight objects for later use
                start_flight.start_time = start_time
                back_flight.back_time = back_time

                if start_time is None or back_time is None:
                    continue

                if start_flight.date != back_flight.date:
                    filtered[iata].append(trip)
                    continue

                # Logic for same-day return
                if start_time > self.max_start_hour:
                    continue

                start_datetime = datetime.combine(start_flight.date, start_time)
                back_datetime = datetime.combine(back_flight.date, back_time)

                if back_datetime - start_datetime >= timedelta(hours=self.min_trip_hours):
                    filtered[iata].append(trip)
        return filtered

    def _format_trips_to_html(self, trips: TripsDict) -> str:
        # Prepare a serializable structure for the template
        sorted_destinations = sorted(
            trips.items(),
            key=lambda item: item[1][0]['start_flight'].end_name if item[1] else ""
        )
        formatted = []
        for iata, flights in sorted_destinations:
            if not flights:
                continue
            dest_name = flights[0]['start_flight'].end_name
            lowest = flights[0]['total_price']
            weeks = []
            by_week = {}
            for f in flights:
                by_week.setdefault(f['start_flight'].week, []).append(f)
            for week, fls in sorted(by_week.items()):
                # de-dup
                unique = list({str(f): f for f in fls}.values())
                trips_list = []
                for info in sorted(unique, key=lambda x: x['total_price']):
                    s = info['start_flight']
                    b = info['back_flight']
                    duration = (b.date - s.date).days
                    trips_list.append({
                        'total_price': info['total_price'],
                        'duration': duration,
                        'start_date': s.date.strftime("%Y-%m-%d (%A)"),
                        'start_name': s.start_name,
                        'start_code': s.start,
                        'start_time': s.start_time.strftime("%H:%M"),
                        'back_date': b.date.strftime("%Y-%m-%d (%A)"),
                        'back_name': b.end_name,
                        'back_code': b.end,
                        'back_time': b.back_time.strftime("%H:%M"),
                    })
                weeks.append({'week': week, 'trips': trips_list})
            formatted.append({
                'destination_name': dest_name,
                'iata': iata,
                'lowest_price': lowest,
                'weeks': weeks,
            })

        # Load & render Jinja2 template
        base = os.path.dirname(__file__)
        env = Environment(
            loader=FileSystemLoader(os.path.join(base, 'templates')),
            autoescape=select_autoescape(['html', 'xml'])
        )
        tpl = env.get_template('weekend_deals.html.j2')
        rendered = tpl.render(destinations=formatted)

        # Pretty-print via BeautifulSoup
        soup = BeautifulSoup(rendered, 'lxml')
        return soup.prettify()

    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        """
        Orchestrates the processing of flight data to find and format weekend trips.

        Args:
            data: A dictionary containing 'poland_to_anywhere' and 'anywhere_to_poland' flights.

        Returns:
            A formatted string of available weekend trips.
        """
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
