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
class FlightTimetable:
    """Static timetable definition for a route within a season.

    weekdays: list[int] uses Python weekday numbering (Mon=0, Sun=6).
    """
    start_time: time
    landing_time: time
    weekdays: list[int]
    start_date: date
    end_date: date
