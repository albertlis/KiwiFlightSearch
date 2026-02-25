import logging
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from kiwiflight.logging_config import setup_logging

from kiwiflight.scraping.base_driver import BasePlaywrightDriver, pretty_format_html

logger = logging.getLogger(__name__)

TIMETABLE_URL = "https://www.katowice-airport.com/pl/dla-pasazera/rozklady-lotow"

ARRIVALS_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "KTW_timetable_arrivals.html"
DEPARTURES_OUTPUT = Path(__file__).resolve().parents[1] / "html_for_scrapping" / "KTW_timetable_departures.html"


class KTWTimetableScraper(BasePlaywrightDriver):
    """KTW timetable scraper — arrivals and departures."""

    url: str = TIMETABLE_URL
    viewport_width: int = 1920
    viewport_height: int = 1080
    _ARRIVALS_LABEL_TEXT = "Przylot"
    _DEPARTURES_LABEL_TEXT = "Odlot"
    _TIMETABLE_ROW_SELECTOR = "div.timetable__row.flight-board__row"
    _SHOW_RESULTS_BUTTON_SELECTOR = "div.filter-timetable__button button"

    def _click_flight_type(self, page: Page, label_text: str) -> None:
        """Click the radio-label for the given tab (Arrivals or Departures)."""
        label = page.locator(
            f"label.radio-button__label",
            has_text=label_text,
        ).first
        label.wait_for(state="visible", timeout=10_000)
        label.click()
        logger.info(f"Clicked flight type button: {label_text}")

    def _click_show_results(self, page: Page) -> None:
        """Click the 'Pokaż wyniki' button to load the timetable."""
        show_results_btn = page.locator(self._SHOW_RESULTS_BUTTON_SELECTOR).first
        show_results_btn.wait_for(state="visible", timeout=10_000)
        show_results_btn.click()
        logger.info("Clicked 'Show results' button")

    def _wait_for_timetable(self, page: Page, timeout: int = 20_000) -> None:
        """Wait until at least one timetable row appears."""
        page.wait_for_selector(self._TIMETABLE_ROW_SELECTOR, state="visible", timeout=timeout)

    def _get_timetable_section_html(self, page: Page) -> str:
        """Return the outerHTML of the direct container of the timetable rows."""
        first_row = page.locator(self._TIMETABLE_ROW_SELECTOR).first
        first_row.wait_for(state="attached", timeout=10_000)
        return first_row.evaluate("el => el.parentElement.outerHTML")


    def _scrape_and_save(self, page: Page, label_text: str, output_path: Path) -> None:
        self._click_flight_type(page, label_text)
        self._click_show_results(page)
        self._wait_for_timetable(page)
        html = self._get_timetable_section_html(page)
        # Pretty-format HTML before saving
        pretty_html = pretty_format_html(html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty_html, encoding="utf-8")
        logger.info(f"Saved {label_text} -> {output_path} ({len(pretty_html)} characters)")

    def scrape(self) -> None:
        """Main method — scrape arrivals and departures and save HTML files."""
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                page.goto(self.url, wait_until="domcontentloaded")

                self._scrape_and_save(page, self._ARRIVALS_LABEL_TEXT, ARRIVALS_OUTPUT)
                self._scrape_and_save(page, self._DEPARTURES_LABEL_TEXT, DEPARTURES_OUTPUT)

            finally:
                browser.close()


if __name__ == "__main__":
    setup_logging()
    KTWTimetableScraper().scrape()
