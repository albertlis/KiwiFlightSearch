"""High-level orchestration for fetching flight data and producing reports.

Usage patterns:

1. Re-scan (scrape) data then process:
   run_pipeline(mode="duration", scrape=True, ...)

2. Reuse previously pickled data (default) for faster iteration:
   run_pipeline(mode="weekend")
"""
import argparse
import logging
import pickle
from pathlib import Path
from typing import Literal, Sequence

from kiwiflight.config import settings
from kiwiflight.emailer import send_email
from kiwiflight.processing.duration import FlightProcessorDuration
from kiwiflight.processing.weekends import FlightProcessorWeekends
from kiwiflight.scraping.playwright_scraper import PlaywrightScraper

ProcessorMode = Literal["weekend", "duration"]


def _load_or_scrape(scrape: bool, start_month: str, end_month: str, iatas: Sequence[str]):
    if scrape:
        logging.info("Starting scraping via Playwright (%s -> %s) for %s", start_month, end_month, iatas)
        scraper = PlaywrightScraper(start_month, end_month, list(iatas))
        return scraper.webscrap_flights()
    # Load existing pickle
    if not settings.data_pickle.exists():
        raise FileNotFoundError(f"Pickle file {settings.data_pickle} not found. Run with --scrape first.")
    with open(settings.data_pickle, "rb") as f:
        logging.info("Loading existing flights pickle %s", settings.data_pickle)
        return pickle.load(f)


def run_pipeline(
        mode: ProcessorMode,
        iatas: Sequence[str],
        scrape: bool = False,
        start_month: str = "sierpień",
        end_month: str = "październik",
        duration_min_days: int = 4,
        duration_max_days: int = 8,
        duration_start_date: str | None = None,
        duration_end_date: str | None = None,
        weekend_min_hours: int = 10,
        weekend_max_start_hour: int = 11,
        email: bool = False,
) -> Path:
    flights_data = _load_or_scrape(scrape, start_month, end_month, iatas)

    if mode == "duration":
        processor = FlightProcessorDuration(
            price_limit=settings.price_limit,
            min_trip_days=duration_min_days,
            max_trip_days=duration_max_days,
            iata_list=list(iatas),
            start_date=duration_start_date,
            end_date=duration_end_date,
        )
    else:
        processor = FlightProcessorWeekends(
            price_limit=settings.price_limit,
            min_trip_hours=weekend_min_hours,
            max_start_hour=weekend_max_start_hour,
            iata_list=list(iatas),
        )

    logging.info("Processing flights using '%s' mode", mode)
    html = processor.process_flights_info(flights_data)
    settings.output_html.write_text(html, encoding="utf-8")
    logging.info("Output written to %s", settings.output_html)

    if email:
        send_email(subject="Loty Kiwi", html_body=html)

    return settings.output_html


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kiwi flight deals pipeline")
    p.add_argument("--mode", choices=["weekend", "duration"], default="duration")
    p.add_argument("--iata", nargs="+", default=["WRO", "POZ", "KTW"], help="Origin airport IATA codes")
    p.add_argument("--scrape", action="store_true", help="Scrape fresh data instead of using pickle")
    p.add_argument("--start-month", default="sierpień")
    p.add_argument("--end-month", default="październik")
    # Duration mode specific
    p.add_argument("--min-days", type=int, default=4)
    p.add_argument("--max-days", type=int, default=8)
    p.add_argument("--start-date", help="dd.mm.YYYY (duration mode)")
    p.add_argument("--end-date", help="dd.mm.YYYY (duration mode)")
    # Weekend mode specific
    p.add_argument("--min-hours", type=int, default=10, help="Minimum hours for same-day return weekend trips")
    p.add_argument("--max-start-hour", type=int, default=11)
    # Misc
    p.add_argument("--email", action="store_true", help="Send email if credentials configured")
    p.add_argument("--log-level", default="INFO")
    return p


def main_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        run_pipeline(
            mode=args.mode,
            iatas=args.iata,
            scrape=args.scrape,
            start_month=args.start_month,
            end_month=args.end_month,
            duration_min_days=args.min_days,
            duration_max_days=args.max_days,
            duration_start_date=args.start_date,
            duration_end_date=args.end_date,
            weekend_min_hours=args.min_hours,
            weekend_max_start_hour=args.max_start_hour,
            email=args.email,
        )
    except Exception:  # noqa: BLE001
        logging.exception("Pipeline failed")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main_cli())
