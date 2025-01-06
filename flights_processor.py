from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO

from kiwi_scrapper import FlightInfo


class FlightProcessor:
    def __init__(self):
        self.price_limit = 200
        self.start_weekdays = {4, 5}  # Friday, Saturday
        self.end_weekdays = {5, 6, 0}  # Saturday, Sunday, Monday

    @staticmethod
    def parse_dates(data: list) -> None:
        for item in data:
            item['date'] = datetime.strptime(item['date'], '%Y-%m-%d')

    @staticmethod
    def filter_by_weekdays(data: list, weekdays: set) -> list:
        return [item for item in data if item['date'].weekday() in weekdays]

    @staticmethod
    def filter_by_price(data: list, price_limit: int) -> list:
        return [item for item in data if item['price'] < price_limit]

    @staticmethod
    def get_week_number(date: datetime) -> int:
        if date.weekday() == 0:
            date -= timedelta(days=1)
        return date.isocalendar()[1]

    def add_week_number(self, data: list) -> None:
        for item in data:
            item['week'] = self.get_week_number(item['date'])

    @staticmethod
    def group_flights_by_key(data: list, key: str) -> dict:
        grouped = defaultdict(list)
        for item in data:
            grouped[item[key]].append(item)
        return dict(grouped)

    @staticmethod
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

    @staticmethod
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

                    for week, weekend_flights in sorted(weekends.items()):
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
                                f"    Total Price: {total_price}zł, "
                                f"Start Date: {start_date_str} from {start_flight['start_name']} ({start_flight['start']}), "
                                f"Return Date: {back_date_str} to {back_flight['end_name']} ({back_flight['end']}), "
                                , file=print_data
                            )
                            print("    " + "-" * 30, file=print_data)
        return print_data.getvalue()

    @staticmethod
    def convert_price_to_int(price: str | int) -> int:
        if isinstance(price, int):
            return price
        if isinstance(price, str):
            return int(price)
        raise ValueError(f'Wrong type of price [{type(price)}]')

    def convert_prices(self, data: list) -> list:
        for flight in data:
            flight['price'] = self.convert_price_to_int(flight['price'])
        return data

    def process_flights_info(self, data: dict[str, list[FlightInfo]]) -> str:
        poland_to_anywhere = data['poland_to_anywhere']
        anywhere_to_poland = data['anywhere_to_poland']

        self.convert_prices(poland_to_anywhere)
        self.convert_prices(anywhere_to_poland)

        self.parse_dates(poland_to_anywhere)
        self.parse_dates(anywhere_to_poland)

        poland_to_anywhere_filtered = self.filter_by_weekdays(poland_to_anywhere, self.start_weekdays)
        anywhere_to_poland_filtered = self.filter_by_weekdays(anywhere_to_poland, self.end_weekdays)

        poland_to_anywhere_filtered = self.filter_by_price(poland_to_anywhere_filtered, self.price_limit)
        anywhere_to_poland_filtered = self.filter_by_price(anywhere_to_poland_filtered, self.price_limit)

        self.add_week_number(poland_to_anywhere_filtered)
        self.add_week_number(anywhere_to_poland_filtered)

        grouped_poland_to_anywhere = self.group_flights_by_key(poland_to_anywhere_filtered, 'end')
        grouped_anywhere_to_poland = self.group_flights_by_key(anywhere_to_poland_filtered, 'start')

        available_trips = self.find_available_trips(grouped_poland_to_anywhere, grouped_anywhere_to_poland)

        return self.print_flights_grouped_by_weekend(available_trips)
