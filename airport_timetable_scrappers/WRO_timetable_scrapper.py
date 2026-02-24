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

    def _wait_for_table(self, page: Page, div_id: str, timeout: int = 40_000) -> None:
        """Wait until the tbody inside the given div has at least one row."""
        page.wait_for_selector(f"#{div_id} table tbody tr", state="attached", timeout=timeout)

    def _get_tbody_html(self, page: Page, div_id: str) -> str:
        """Return the outerHTML of the tbody inside the given div."""
        tbody = page.locator(f"#{div_id} table tbody").first
        tbody.wait_for(state="attached", timeout=10_000)
        return tbody.evaluate("el => el.outerHTML")

    def _scrape_and_save(self, page: Page, div_id: str, output_path: Path) -> None:
        self._wait_for_table(page, div_id)
        html = self._get_tbody_html(page, div_id)
        pretty_html = pretty_format_html(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty_html, encoding="utf-8")
        logger.info(f"Saved {div_id} -> {output_path} ({len(pretty_html)} characters)")

    def scrape(self) -> None:
        """Main method — scrape arrivals and departures and save HTML files."""
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                page.goto(self.url, wait_until="load")

                self._scrape_and_save(page, self._ARRIVALS_DIV_ID, ARRIVALS_OUTPUT)
                self._scrape_and_save(page, self._DEPARTURES_DIV_ID, DEPARTURES_OUTPUT)

            finally:
                browser.close()


if __name__ == "__main__":
    setup_logging()
    WROTimetableScraper().scrape()

