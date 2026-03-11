from dataclasses import dataclass
from datetime import date, time


@dataclass(slots=True)
class FlightInfo:
    """Domain model representing single directional flight price info on a given date.

    start / end represent IATA codes; *_name keep human-readable city / airport names.
    start_time / back_time are enriched later by processors based on static timetable JSONs.
    week is an adjusted ISO week number used for grouping weekend trips (Monday shifted to previous week).
    """
    start: str
    start_name: str
    end: str
    end_name: str
    date: date
    price: int
    week: int
    start_time: time | None
    back_time: time | None


@dataclass(frozen=True, slots=True)
class ScrapeError:
    """Represents a route that could not be scraped due to repeated timeouts."""
    start_iata: str
    start_name: str
    dst_iata: str
    dst_name: str
    direction: str  # 'poland_to_anywhere' or 'anywhere_to_poland'
    failed_month: str  # month name where the consecutive timeout occurred


@dataclass(frozen=True, slots=True)
class AirportLookupError:
    """Represents an airport IATA code that could not be selected on Kiwi.com.

    Recorded when neither the IATA code nor the fallback city name produced
    a selectable result in the Kiwi search field.
    """
    iata: str
    city_name: str | None  # city name used for fallback (None if no mapping existed)
    role: str  # 'origin' or 'destination'
    direction: str  # 'poland_to_anywhere' or 'anywhere_to_poland'


@dataclass(frozen=True, slots=True)
class FlightTimetable:
    """Static timetable definition for a route within a season.

    weekdays: list[int] uses Python weekday numbering (Mon=0, Sun=6).
    """
    start_time: time
    landing_time: time
    weekdays: list[int]
    start_date: date
    end_date: date
