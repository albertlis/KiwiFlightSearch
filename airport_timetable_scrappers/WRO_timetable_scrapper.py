import logging
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from kiwiflight.logging_config import setup_logging
from kiwiflight.scraping.base_driver import BasePlaywrightDriver, pretty_format_html

logger = logging.getLogger(__name__)

TIMETABLE_URL = "https://airport.wroclaw.pl/pasazer/odlatuje/rozklad-lotow/"

ARRIVALS_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "WRO_timetable_arrivals.html"
DEPARTURES_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "WRO_timetable_departures.html"


class WROTimetableScraper(BasePlaywrightDriver):
    """WRO timetable scraper — arrivals and departures."""

    url: str = TIMETABLE_URL
    _ARRIVALS_DIV_ID = "n-flights-arrivals"
    _DEPARTURES_DIV_ID = "n-flights-departures"

    # Selectors
    _ARRIVALS_BUTTON = "[data-id='n-flights-arrivals']"
    _DEPARTURES_BUTTON = "[data-id='n-flights-departures']"
    _TABLE_ROWS = ".n-flights__wrap table tbody tr"
    _PRELOADER = ".preloader-flights"

    def get_page(self, playwright):
        """Override base get_page — use larger viewport and Wrocław geolocation."""
        browser, page = super().get_page(playwright)
        page.context.set_geolocation({"latitude": 51.1025, "longitude": 17.0318})
        page.set_viewport_size({"width": 1280, "height": 900})
        logger.debug("WRO viewport and geolocation applied.")
        return browser, page

    def _wait_for_table(self, page: Page, timeout: int = 20_000) -> None:
        """Wait until the preloader is gone and tbody has at least one row."""
        page.wait_for_selector(self._PRELOADER, state="hidden", timeout=timeout)
        page.wait_for_selector(self._TABLE_ROWS, state="attached", timeout=timeout)

    def _get_tbody_html(self, page: Page) -> str:
        """Return the outerHTML of the tbody inside .n-flights__wrap."""
        tbody = page.locator(".n-flights__wrap table tbody").first
        tbody.wait_for(state="attached", timeout=10_000)
        return tbody.evaluate("el => el.outerHTML")

    def _click_tab_and_scrape(self, page: Page, button_selector: str, output_path: Path) -> None:
        """Click a tab button, wait for data to load, then save the tbody HTML."""
        page.locator(button_selector).click()
        self._wait_for_table(page)
        html = self._get_tbody_html(page)
        pretty_html = pretty_format_html(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty_html, encoding="utf-8")
        logger.info(f"Saved {button_selector} -> {output_path} ({len(pretty_html)} chars)")

    def _dump_debug(self, page: Page, label: str) -> None:
        """Save a screenshot and full page HTML to html_for_scrapping/debug_*."""
        debug_dir = ARRIVALS_OUTPUT.parent
        debug_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = debug_dir / f"debug_{label}.png"
        html_path = debug_dir / f"debug_{label}.html"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info(f"[debug] Screenshot saved: {screenshot_path}")
        except Exception as e:
            logger.warning(f"[debug] Screenshot failed: {e}")
        try:
            html_path.write_text(page.content(), encoding="utf-8")
            logger.info(f"[debug] Page HTML saved: {html_path}")
        except Exception as e:
            logger.warning(f"[debug] HTML dump failed: {e}")

    def _trigger_user_interaction(self, page: Page) -> None:
        """Simulate user interaction to unblock WP Rocket lazy-loaded scripts.

        WP Rocket defers ALL scripts until the first user gesture (mousemove/click/keydown).
        Without this, jQuery and the flights AJAX call never execute in headless mode.
        """
        logger.info("Triggering user interaction to unblock WP Rocket lazy JS...")
        page.mouse.move(640, 450)
        page.mouse.move(641, 451)
        # Click the arrivals tab button — this both triggers WP Rocket AND loads the data
        page.locator(self._ARRIVALS_BUTTON).click()
        logger.info("Arrivals tab clicked — waiting for AJAX...")

    def scrape(self, debug: bool = False) -> None:
        """Main method — scrape arrivals and departures and save HTML files."""
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                logger.info(f"Navigating to {self.url} ...")
                page.goto(self.url, wait_until="domcontentloaded", timeout=60_000)
                logger.info("Page loaded.")
                self._trigger_user_interaction(page)

                if debug:
                    self._dump_debug(page, "after_load")

                try:
                    self._click_tab_and_scrape(page, self._ARRIVALS_BUTTON, ARRIVALS_OUTPUT)
                except Exception as e:
                    logger.error(f"[arrivals] Failed: {e}")
                    if debug:
                        self._dump_debug(page, "arrivals_error")
                    raise

                try:
                    self._click_tab_and_scrape(page, self._DEPARTURES_BUTTON, DEPARTURES_OUTPUT)
                except Exception as e:
                    logger.error(f"[departures] Failed: {e}")
                    if debug:
                        self._dump_debug(page, "departures_error")
                    raise

            finally:
                browser.close()


if __name__ == "__main__":
    setup_logging()
    WROTimetableScraper().scrape(debug=False)

