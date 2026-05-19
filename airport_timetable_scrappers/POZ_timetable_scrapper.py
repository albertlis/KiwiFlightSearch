import logging
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from kiwiflight.logging_config import setup_logging
from kiwiflight.scraping.base_driver import BasePlaywrightDriver, pretty_format_html

logger = logging.getLogger(__name__)

TIMETABLE_URL = "https://poznanairport.pl/loty/rozklad-lotow/"

ARRIVALS_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "POZ_timetable_arrivals.html"
DEPARTURES_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "POZ_timetable_departures.html"

_FLIGHTS_TABLE_SELECTOR = "div.flightsTable__table"
_ARRIVALS_LABEL = "label[for='form-cat-arrival']"
_DEPARTURES_LABEL = "label[for='form-cat-departure']"


class POZTimetableScraper(BasePlaywrightDriver):
    """POZ (Poznań) timetable scraper — arrivals and departures.

    The page is a Vue app with radio-button tabs:
      label[for='form-cat-arrival']   → Przyloty
      label[for='form-cat-departure'] → Odloty
    Clicking a label triggers Vue reactivity and re-renders the table.
    """

    url: str = TIMETABLE_URL

    @staticmethod
    def _wait_for_table(page: Page, timeout: int = 20_000) -> None:
        page.wait_for_selector(_FLIGHTS_TABLE_SELECTOR, state="visible", timeout=timeout)

    @staticmethod
    def _click_tab_label(page: Page, label_selector: str) -> None:
        label = page.locator(label_selector).first
        label.wait_for(state="visible", timeout=10_000)
        label.click()
        logger.info(f"Clicked tab label: {label_selector}")

    @staticmethod
    def _get_table_html(page: Page) -> str:
        table = page.locator(_FLIGHTS_TABLE_SELECTOR).first
        table.wait_for(state="visible", timeout=10_000)
        return table.evaluate("el => el.outerHTML")

    def _scrape_tab(self, page: Page, label_selector: str, output_path: Path, label: str) -> None:
        self._click_tab_label(page, label_selector)
        # Wait for Vue to re-render — a brief stabilisation pause
        page.wait_for_timeout(1_000)
        self._wait_for_table(page)
        html = self._get_table_html(page)
        pretty_html = pretty_format_html(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty_html, encoding="utf-8")
        logger.info(f"Saved {label} -> {output_path} ({len(pretty_html)} characters)")

    def scrape(self) -> None:
        """Main method — scrape arrivals and departures and save HTML files."""
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                logger.info(f"Navigating to {self.url} ...")
                page.goto(self.url, wait_until="domcontentloaded", timeout=60_000)
                self._wait_for_table(page)

                self._scrape_tab(page, _ARRIVALS_LABEL, ARRIVALS_OUTPUT, "arrivals")
                self._scrape_tab(page, _DEPARTURES_LABEL, DEPARTURES_OUTPUT, "departures")

            finally:
                browser.close()


if __name__ == "__main__":
    setup_logging()
    POZTimetableScraper().scrape()
