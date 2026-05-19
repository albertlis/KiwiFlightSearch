"""Playwright based scraper for Kiwi flight date/price grid.

Consolidates logic previously in new_driver.py + kiwi_scrapper_new.py.
"""

import json
import logging
import pickle
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from tqdm import tqdm

from ..models import AirportLookupError, FlightInfo, ScrapeError
from .base_driver import BasePlaywrightDriver
from kiwiflight.config import settings

# Project data directory (root/data)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class AirportSelectionError(Exception):
    """Raised when an airport cannot be found on Kiwi.com by IATA or city name."""

    def __init__(self, iata: str, fallback_name: str | None):
        self.iata = iata
        self.fallback_name = fallback_name
        super().__init__(
            f"Airport '{iata}' not found on Kiwi.com" + (f" (also tried '{fallback_name}')" if fallback_name else "")
        )


class _PlaywrightDriver(BasePlaywrightDriver):
    def __init__(self):
        self.url = "https://www.kiwi.com/pl/?currency=PLN"

        self.month_button_locator = "button[data-test='DatepickerMonthButton']"
        self.cookies_button_locator = "button[data-test='ModalCloseButton']"
        self.discard_cookies_locator = "button[data-test='CookiesPopup-Settings-save']"
        self.booking_label_locator = ".orbit-checkbox-icon-container"
        self.direction_button_locator = (
            "//div[contains(@class, 'orbit-button-primitive-content') and contains(text(), 'W obie strony')]"
        )
        self.one_way_ticket_locator = "//span[contains(text(), 'W jedną stronę')]"
        self.remove_start_airport_locator = (
            "div[data-test='SearchFieldItem-origin'] div[data-test='PlacePickerInputPlace-close']"
        )
        self.remove_dst_airport_locator = (
            "div[data-test='SearchFieldItem-destination'] div[data-test='PlacePickerInputPlace-close']"
        )
        self.start_airport_locator = "div[data-test^='PlacePickerRow-']"
        self.destination_airport_locator = "div[data-test^='PlacePickerRow-']"
        self.destination_locator = "div[data-test='PlacePickerInput-destination'] input[data-test='SearchField-input']"
        self.start_locator = "div[data-test='PlacePickerInput-origin'] input[data-test='SearchField-input']"
        self.date_input_locator = "input[data-test='SearchFieldDateInput']"
        self.calendar_day_locator = "div[data-test='CalendarDay']"
        self.next_button_locator = "button[data-test='CalendarMoveNextButton']"
        self.origin_input_debug_locator = (
            "div[data-test='SearchPlaceField-origin'] input[data-test='SearchField-input']"
        )
        self.place_picker_rows_debug_locator = "div[data-test^='PlacePickerRow-']"

    def get_page(self, playwright):
        """Extends base get_page with Kiwi-specific PLN currency cookies."""
        browser, page = super().get_page(playwright)
        page.context.add_cookies(
            [
                {"name": "currency", "value": "PLN", "domain": ".kiwi.com", "path": "/"},
                {"name": "kw_currency", "value": "PLN", "domain": ".kiwi.com", "path": "/"},
            ]
        )

        return browser, page

    def setup_main_page(self, page: Page) -> None:
        btn = page.locator(self.cookies_button_locator)
        self._highlight(btn)
        btn.click()
        try:
            # Triple the timeout – the privacy-settings modal can be slow to render
            discard = page.locator(self.discard_cookies_locator)
            discard.wait_for(state="visible", timeout=self.timeout)
            self._highlight(discard)
            discard.click()
            logging.info("Cookie settings dismissed via save-settings button.")
        except PlaywrightTimeoutError:  # type: ignore[name-defined]
            logging.info("No secondary cookie banner.")

        # Safety guard: wait for the privacy-settings modal to fully disappear
        # before interacting with the main search form.
        privacy_modal_locator = "div[aria-label='Ustawienia prywatności']"
        try:
            page.locator(privacy_modal_locator).wait_for(state="hidden", timeout=self.timeout)
        except PlaywrightTimeoutError:
            logging.warning("Privacy modal still visible – pressing Escape to dismiss.")
            page.keyboard.press("Escape")
            try:
                page.locator(privacy_modal_locator).wait_for(state="hidden", timeout=self.timeout)
            except PlaywrightTimeoutError:
                logging.warning("Privacy modal persists after Escape – proceeding anyway.")

        direction_btn = page.locator(self.direction_button_locator).first
        self._highlight(direction_btn)
        direction_btn.click()
        one_way = page.locator(self.one_way_ticket_locator)
        self._highlight(one_way)
        one_way.click()
        booking = page.locator(self.booking_label_locator).first
        self._highlight(booking)
        booking.click()

    def _try_select_airport(
        self, page: Page, input_locator: str, row_locator: str, airport_iata: str, fallback_name: str | None
    ) -> str:
        """Try to select an airport in the Kiwi search field with IATA→name fallback.

        1. Type the IATA code and look for a matching picker row.
        2. If that times out and a *fallback_name* is available, clear the field,
           type the city name, and try again.

        Returns:
            The inner text of the selected picker row.

        Raises:
            AirportSelectionError: when neither IATA nor fallback name produced a
            selectable result.
        """
        input_el = page.locator(input_locator)
        self._highlight(input_el)
        input_el.click()

        # --- attempt 1: search by IATA code ---
        input_el.fill(airport_iata)
        row = page.locator(row_locator, has_text=airport_iata).first
        try:
            row.wait_for(state="visible", timeout=self.timeout)
            self._highlight(row)
            name = row.inner_text()
            row.click()
            return name
        except PlaywrightTimeoutError:
            logging.info(f"IATA '{airport_iata}' not found on Kiwi – trying fallback city name")

        # --- attempt 2: search by city/airport name ---
        if fallback_name:
            try:
                input_el.fill("", timeout=5000)
                input_el.fill(fallback_name, timeout=self.timeout)
            except Exception:
                logging.warning(f"Could not fill fallback name '{fallback_name}' for IATA '{airport_iata}'")
            else:
                row = page.locator(row_locator, has_text=airport_iata).first
                try:
                    row.wait_for(state="visible", timeout=self.timeout)
                    self._highlight(row)
                    name = row.inner_text()
                    row.click()
                    return name
                except PlaywrightTimeoutError:
                    logging.warning(f"Fallback name '{fallback_name}' also failed for IATA '{airport_iata}'")

        # Both attempts failed – try to clean up, then signal failure
        # Escape FIRST to close any open dropdown, then clear the input
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        except Exception:
            pass
        try:
            input_el.fill("", timeout=5_000)
        except Exception:
            pass
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        except Exception:
            pass
        raise AirportSelectionError(airport_iata, fallback_name)

    def _dismiss_open_pickers(self, page: Page, attempts: int = 3, wait_ms: int = 300) -> None:
        """Press Escape multiple times to close any open dropdowns/pickers."""
        for _ in range(attempts):
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(wait_ms)
            except Exception:
                break

    def _reload_search_page(self, page: Page) -> None:
        """Reload the search page and restore the search form settings."""
        logging.info("Reloading search page…")
        page.goto(self.url, wait_until="domcontentloaded")
        # Cookies may not reappear – try anyway
        for locator_str in [self.cookies_button_locator, self.discard_cookies_locator]:
            try:
                el = page.locator(locator_str)
                el.wait_for(state="visible", timeout=4_000)
                el.click()
            except Exception:
                pass
        # Restore "one-way" mode
        try:
            direction_btn = page.locator(self.direction_button_locator).first
            direction_btn.wait_for(state="visible", timeout=15_000)
            direction_btn.click()
            page.locator(self.one_way_ticket_locator).click()
        except Exception:
            logging.warning("Failed to restore 'one-way' mode after reload")
        # Restore booking checkbox
        try:
            booking = page.locator(self.booking_label_locator).first
            booking.wait_for(state="visible", timeout=5_000)
            booking.click()
        except Exception:
            pass
        logging.info("Page reloaded and form restored.")

    def choose_start_airport(self, page: Page, airport_iata: str, fallback_name: str | None = None) -> str:
        # Zamknij wszelkie otwarte pickery zanim klikniemy przycisk X przy origin
        self._dismiss_open_pickers(page)
        remove = page.locator(self.remove_start_airport_locator)
        try:
            remove.wait_for(state="visible", timeout=5_000)
            self._highlight(remove)
            remove.click(timeout=self.timeout // 2)
        except Exception:
            # Przycisk X nie odpowiada (overlay?) lub nie istnieje (puste pole po błędzie)
            logging.warning(f"Nie można kliknąć X przy origin (airport={airport_iata}) – przeładowuję stronę…")
            self._reload_search_page(page)
        return self._try_select_airport(
            page,
            self.start_locator,
            self.start_airport_locator,
            airport_iata,
            fallback_name,
        )

    def choose_destination_airport(self, page: Page, airport_iata: str, fallback_name: str | None = None) -> str:
        return self._try_select_airport(
            page,
            self.destination_locator,
            self.destination_airport_locator,
            airport_iata,
            fallback_name,
        )

    def get_month_name(self, page: Page) -> str:
        return page.locator(self.month_button_locator).last.inner_text().strip().lower()

    @staticmethod
    def _highlight(locator, duration_ms: int = 600) -> None:
        """Briefly highlight an element with a red outline for visual debugging."""
        try:
            locator.evaluate(
                f"""el => {{
                    const prev = el.style.outline;
                    el.style.outline = '3px solid red';
                    setTimeout(() => {{ el.style.outline = prev; }}, {duration_ms});
                }}"""
            )
        except Exception:
            pass


class PlaywrightScraper(_PlaywrightDriver):
    def __init__(self, start_month: str, end_month: str, start_iata_airports: list[str], all_iatas: bool = False):
        super().__init__()
        self.start_month = start_month
        self.end_month = end_month
        self.start_iata_airports = start_iata_airports
        self.all_iatas = all_iatas
        self.interesting_iatas = self._load_interesting_iatas()
        self.iata_to_name = self._load_iata_to_city_name()
        self.price_span_locator = "div[data-test='NewDatepickerPrice'] span"
        self.price_div_locator = "div[data-test='NewDatepickerPrice']"

    @staticmethod
    def _load_interesting_iatas() -> set[str]:
        path = DATA_DIR / "interesting_iatas.txt"
        with open(path, "rt", encoding="utf-8") as f:
            return set(filter(None, f.read().split("\n")))

    @staticmethod
    def _load_iata_to_city_name() -> dict[str, str]:
        path = DATA_DIR / "airports_to_iata_mapping.json"
        with open(path, "rt", encoding="utf-8") as f:
            city_to_iata = json.load(f)
        # Invert to IATA -> city. If duplicates exist, the last occurrence wins.
        iata_to_city: dict[str, str] = {iata: city for city, iata in city_to_iata.items()}
        return iata_to_city

    @staticmethod
    def _read_iata_codes(file_path: Path) -> list[str]:
        # If relative path passed (PosixPath with no anchor), resolve against project root
        if not file_path.is_absolute():
            file_path = Path(__file__).resolve().parents[2] / file_path
        with open(file_path, "rt", encoding="utf-8") as f:
            return [iata.strip() for iata in f.read().split("\n") if iata.strip()]

    @staticmethod
    def _extract_price(text: str):
        m = re.search(r"\d+", text)
        return int(m.group()) if m else None

    @staticmethod
    def _week_number(d: date) -> int:
        if d.weekday() == 0:
            d -= timedelta(days=1)
        return d.isocalendar()[1]

    def _wait_for_prices(self, page: Page):
        try:
            page.wait_for_function(
                """() => {const spans = document.querySelectorAll('div[data-test="NewDatepickerPrice"] span');
                    return spans.length>0 && Array.from(spans).every(s=>{const t=s.innerText.trim();return t && t!== 'Ładowanie';});}""",
                timeout=self.timeout,
            )
        except PlaywrightTimeoutError:
            logging.warning(f"Prices loading timed out after {self.timeout}")

    def _gather_route_prices(
        self, page: Page, start_code: str, start_name: str, dst_code: str, dst_name: str
    ) -> tuple[list[FlightInfo], str | None]:
        """Gather date/price data for a single route.

        Returns:
            Tuple of (flights_list, failed_month_or_None).
            If failed_month is not None the route was aborted due to two
            consecutive month timeouts – the value is the month where the
            second timeout occurred.
        """
        flights: list[FlightInfo] = []
        page.locator(self.date_input_locator).click()
        clicks = 0
        while self.start_month not in self.get_month_name(page) and clicks < 12:
            clicks += 1
            page.locator(self.next_button_locator).first.click()
        clicks = 0
        consecutive_timeouts = 0
        while True:
            current_month = self.get_month_name(page)
            is_end_month = self.end_month in current_month

            # --- try loading prices for the current month ---
            try:
                self._wait_for_prices(page)
                page.wait_for_selector(self.calendar_day_locator, state="attached", timeout=self.timeout)
            except PlaywrightTimeoutError:
                consecutive_timeouts += 1
                logging.warning(
                    f"Timeout loading prices for {start_code}→{dst_code} in month '{current_month}' (consecutive: {consecutive_timeouts})"
                )
                if consecutive_timeouts >= 2:
                    # Two consecutive months timed out – abort this route
                    logging.error(
                        f"Aborting route {start_code}→{dst_code} after 2 consecutive timeouts (month: {current_month})"
                    )
                    page.keyboard.press("Escape")
                    return flights, current_month
                # First timeout – skip to next month
                if is_end_month or clicks >= 12:
                    break
                clicks += 1
                page.locator(self.next_button_locator).click()
                continue

            # Prices loaded successfully – reset consecutive counter
            consecutive_timeouts = 0

            days = page.locator(self.calendar_day_locator).all()
            if clicks == 0:
                days = days[1:]
            for day in days:
                date_str = day.get_attribute("data-value")
                if not date_str:
                    continue
                try:
                    d_val = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                price_text = ""
                try:
                    ps = day.locator(self.price_span_locator)
                    pd = day.locator(self.price_div_locator)
                    if ps.is_visible():
                        price_text = ps.inner_text()
                    elif pd.is_visible():
                        price_text = pd.inner_text()
                        if price_text == "-":
                            continue
                    else:
                        continue
                except Exception:
                    logging.debug(f"Missing price element for {date_str}")
                    continue
                price = self._extract_price(price_text)
                if price is None:
                    continue
                flights.append(
                    FlightInfo(
                        start_code, start_name, dst_code, dst_name, d_val, price, self._week_number(d_val), None, None
                    )
                )
            if is_end_month or clicks >= 12:
                break
            clicks += 1
            page.locator(self.next_button_locator).click()
        page.keyboard.press("Escape")
        return flights, None

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self, direction: str) -> Path:
        return settings.data_pickle.with_name(f"checkpoint_{direction}.pkl")

    def _save_checkpoint(
        self,
        direction: str,
        start_code: str,
        done_iatas: set[str],
        collected: list[FlightInfo],
        errors: list[ScrapeError],
        lookup_errors: list[AirportLookupError],
    ) -> None:
        data = dict(
            start_code=start_code,
            done_iatas=done_iatas,
            collected=collected,
            errors=errors,
            lookup_errors=lookup_errors,
        )
        path = self._checkpoint_path(direction)
        with open(path, "wb") as f:
            pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
        logging.debug(f"Checkpoint saved: {path} ({len(done_iatas)} routes done)")

    def _load_checkpoint(self, direction: str) -> dict | None:
        path = self._checkpoint_path(direction)
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
            logging.info(
                f"Resuming '{direction}' from checkpoint: "
                f"{len(data['done_iatas'])} route(s) already done for start={data['start_code']}"
            )
            return data
        return None

    def _delete_checkpoint(self, direction: str) -> None:
        path = self._checkpoint_path(direction)
        if path.exists():
            path.unlink()
            logging.info(f"Checkpoint deleted: {path}")

    # ------------------------------------------------------------------

    def _collect_direction(
        self, page: Page, direction: str, desc: str
    ) -> tuple[list[FlightInfo], list[ScrapeError], list[AirportLookupError]]:
        # --- restore checkpoint if available ---
        checkpoint = self._load_checkpoint(direction)
        if checkpoint:
            collected: list[FlightInfo] = checkpoint["collected"]
            errors: list[ScrapeError] = checkpoint["errors"]
            lookup_errors: list[AirportLookupError] = checkpoint["lookup_errors"]
            resume_start_code: str | None = checkpoint["start_code"]
            done_iatas: set[str] = checkpoint["done_iatas"]
        else:
            collected = []
            errors = []
            lookup_errors = []
            resume_start_code = None
            done_iatas = set()

        start_airports_names = [self.iata_to_name.get(i, i) for i in self.start_iata_airports]
        for start_code, start_name in zip(self.start_iata_airports, start_airports_names):
            # skip start airports that were fully finished before the crash
            if resume_start_code is not None and start_code != resume_start_code:
                # check if this start_code was already completed in a previous run
                # (resume_start_code is the one that was in-progress; earlier ones were done)
                if self.start_iata_airports.index(start_code) < self.start_iata_airports.index(resume_start_code):
                    logging.info(f"Skipping already completed start airport: {start_code}")
                    continue

            iatas_file = Path(f"airport_iata_codes/{start_code.upper()}_iata_codes.txt")
            all_codes = set(self._read_iata_codes(iatas_file))
            iata_codes = list(all_codes if self.all_iatas else all_codes & self.interesting_iatas)

            # when switching to a new start airport, reset done_iatas
            if start_code != resume_start_code:
                done_iatas = set()
            # clear resume_start_code after first use so subsequent start airports work normally
            resume_start_code = None

            remaining = [c for c in iata_codes if c not in done_iatas]
            skipped = len(iata_codes) - len(remaining)
            if skipped:
                logging.info(f"Skipping {skipped} already-scraped route(s) for {start_code}")

            if not remaining:
                logging.info(f"All routes for {start_code} already done, skipping.")
                continue

            # Select the fixed start airport once per start_code (not on every dst iteration)
            start_fallback = self.iata_to_name.get(start_code)
            if direction == "poland_to_anywhere":
                try:
                    self.choose_start_airport(page, start_code, fallback_name=start_fallback)
                except AirportSelectionError as e:
                    logging.error(f"Skipping all routes for start airport: {e}")
                    lookup_errors.append(AirportLookupError(start_code, start_fallback, "origin", direction))
                    # mark all iatas as done so checkpoint reflects this
                    done_iatas.update(iata_codes)
                    self._save_checkpoint(direction, start_code, done_iatas, collected, errors, lookup_errors)
                    continue

            for dst_code in tqdm(remaining, desc=f"{desc} {start_name}", initial=skipped, total=len(iata_codes)):
                dst_fallback = self.iata_to_name.get(dst_code)
                try:
                    if direction == "poland_to_anywhere":
                        try:
                            dst_name = self.choose_destination_airport(page, dst_code, fallback_name=dst_fallback)
                        except AirportSelectionError as e:
                            logging.error(f"Skipping route: destination airport {e}")
                            lookup_errors.append(AirportLookupError(dst_code, dst_fallback, "destination", direction))
                            done_iatas.add(dst_code)
                            self._save_checkpoint(direction, start_code, done_iatas, collected, errors, lookup_errors)
                            continue
                        route_flights, failed_month = self._gather_route_prices(
                            page, start_code, start_name, dst_code, dst_name
                        )
                        if failed_month is not None:
                            errors.append(
                                ScrapeError(start_code, start_name, dst_code, dst_name, direction, failed_month)
                            )
                    else:
                        try:
                            self.choose_start_airport(page, dst_code, fallback_name=dst_fallback)
                        except AirportSelectionError as e:
                            logging.error(f"Skipping route: origin airport {e}")
                            lookup_errors.append(AirportLookupError(dst_code, dst_fallback, "origin", direction))
                            done_iatas.add(dst_code)
                            self._save_checkpoint(direction, start_code, done_iatas, collected, errors, lookup_errors)
                            continue
                        try:
                            dst_name = self.choose_destination_airport(page, start_code, fallback_name=start_fallback)
                        except AirportSelectionError as e:
                            logging.error(f"Skipping route: destination airport {e}")
                            lookup_errors.append(
                                AirportLookupError(start_code, start_fallback, "destination", direction)
                            )
                            done_iatas.add(dst_code)
                            self._save_checkpoint(direction, start_code, done_iatas, collected, errors, lookup_errors)
                            continue
                        route_flights, failed_month = self._gather_route_prices(
                            page, dst_code, dst_fallback or dst_code, start_code, start_name
                        )
                        if failed_month is not None:
                            errors.append(
                                ScrapeError(
                                    dst_code, dst_fallback or dst_code, start_code, start_name, direction, failed_month
                                )
                            )
                    collected.extend(route_flights)
                    page.locator(self.destination_locator).click()
                    page.locator(self.remove_dst_airport_locator).click()
                    # Zamknij picker po usunięciu celu, żeby nie blokował kolejnej iteracji
                    self._dismiss_open_pickers(page, attempts=2, wait_ms=200)
                except Exception:
                    label = f"{direction}_{start_code}_to_{dst_code}"
                    self._dump_page_html(page, label=label)
                    logging.exception(f"Unexpected error on route {start_code}→{dst_code} ({direction}) – skipping")

                done_iatas.add(dst_code)
                self._save_checkpoint(direction, start_code, done_iatas, collected, errors, lookup_errors)

        self._delete_checkpoint(direction)
        return collected, errors, lookup_errors

    # ------------------------------------------------------------------
    # HTML failure dump helper
    # ------------------------------------------------------------------

    @staticmethod
    def _dump_page_html(page: "Page", label: str = "") -> Path:
        """Save the current page HTML to a fixed file in the data directory.

        Always writes to ``data/failure_dump.html``, overwriting any previous
        dump.  The optional *label* is only included in the log message for
        context.  Returns the path where the dump was written.
        """
        dump_path = DATA_DIR / "failure_dump.html"
        try:
            html_content = page.content()
            dump_path.write_text(html_content, encoding="utf-8")
            logging.error(f"[HTML DUMP] Page HTML saved to: {dump_path}" + (f" (label: {label})" if label else ""))
        except Exception as dump_err:
            logging.error(f"[HTML DUMP] Could not save page HTML: {dump_err}")
        return dump_path

    def webscrap_flights(self):  # retains legacy name for compatibility
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                page.goto(self.url)
                self.setup_main_page(page)
                poland_to_anywhere, errors_pta, lookup_pta = self._collect_direction(page, "poland_to_anywhere", "From")
                # Zamknij ewentualnie otwarty picker po ostatniej trasie poland_to_anywhere
                self._dismiss_open_pickers(page)
                # save intermediate pickle next to configured data pickle
                poland_pickle = settings.data_pickle.with_name("poland_to_anywhere.pkl")
                with open(poland_pickle, "wb") as f:
                    pickle.dump(poland_to_anywhere, f, pickle.HIGHEST_PROTOCOL)
                anywhere_to_poland, errors_atp, lookup_atp = self._collect_direction(page, "anywhere_to_poland", "To")
                scrape_errors = errors_pta + errors_atp
                lookup_errors = lookup_pta + lookup_atp
                flights = dict(poland_to_anywhere=poland_to_anywhere, anywhere_to_poland=anywhere_to_poland)
                # save final pickle to configured location
                with open(settings.data_pickle, "wb") as f:
                    pickle.dump(flights, f, pickle.HIGHEST_PROTOCOL)
                # save scrape errors pickle alongside data
                errors_pickle = settings.data_pickle.with_name("scrape_errors.pkl")
                with open(errors_pickle, "wb") as f:
                    pickle.dump(scrape_errors, f, pickle.HIGHEST_PROTOCOL)
                # save lookup errors pickle alongside data
                lookup_errors_pickle = settings.data_pickle.with_name("lookup_errors.pkl")
                with open(lookup_errors_pickle, "wb") as f:
                    pickle.dump(lookup_errors, f, pickle.HIGHEST_PROTOCOL)
                if scrape_errors:
                    logging.warning(f"Scraping finished with {len(scrape_errors)} route error(s):")
                    for err in scrape_errors:
                        logging.warning(
                            f"  {err.start_iata}→{err.dst_iata} ({err.direction}) failed at month '{err.failed_month}'"
                        )
                if lookup_errors:
                    logging.warning(f"Scraping finished with {len(lookup_errors)} airport lookup error(s):")
                    for err in lookup_errors:
                        logging.warning(
                            f"  IATA '{err.iata}' (city: {err.city_name or '?'}) not found as {err.role} ({err.direction})"
                        )
            except Exception:
                self._dump_page_html(page, label="webscrap_flights")
                raise
            finally:
                browser.close()
            return OrderedDict(sorted(flights.items())), scrape_errors, lookup_errors
