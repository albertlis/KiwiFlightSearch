import logging
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup


def pretty_format_html(html: str) -> str:
    """Return a pretty-formatted HTML string using BeautifulSoup with the 'lxml' parser.

    No fallbacks: if BeautifulSoup or the 'lxml' parser is not available this will raise an
    ImportError / ValueError so the caller knows a required dependency is missing.
    """
    if not html:
        return html
    soup = BeautifulSoup(html, "lxml")
    return soup.prettify()


class BasePlaywrightDriver:
    """Headless Chromium driver with anti-bot stealth applied."""

    url: str = "about:blank"
    timeout: int = 30 * 1000

    def _get_browser_args(self) -> list[str]:
        return [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--window-size=800,800",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
        ]

    def get_page(self, playwright):
        """Create and return a (browser, page) tuple with stealth applied."""
        browser = playwright.chromium.launch(
            headless=False,
            args=self._get_browser_args(),
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            geolocation={"latitude": 52.2297, "longitude": 21.0122},
            permissions=["geolocation"],
            viewport={"width": 800, "height": 800},
            screen={"width": 800, "height": 800},
            color_scheme="light",
            has_touch=False,
            java_script_enabled=True,
            extra_http_headers={
                "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Skip loading images to speed up scraping
        context.route(
            "**/*.{png,jpg,jpeg,webp,svg,gif}",
            lambda route: route.abort(),
        )

        # Mask headless-mode fingerprints via JS overrides
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['pl-PL', 'pl', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.set_default_timeout(self.timeout)
        logging.debug("Browser page created with stealth applied.")
        return browser, page

    def run(self, *args, **kwargs):
        """Override in subclasses. Called inside a sync_playwright context."""
        raise NotImplementedError

    def execute(self):
        """Entry point: opens playwright, calls run(), closes browser."""
        with sync_playwright() as p:
            browser, page = self.get_page(p)
            try:
                return self.run(browser, page)
            finally:
                browser.close()
