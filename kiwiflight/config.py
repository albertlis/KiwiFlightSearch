"""Configuration utilities.

Central place to load environment driven settings (email credentials, defaults, etc.).
Avoids scattering os.getenv calls around the codebase.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env once on module import
load_dotenv()

# Root of the project (parent of the kiwiflight/ package directory)
_PROJECT_ROOT = Path(__file__).parent.parent


@dataclass(slots=True)
class Settings:
    src_mail: str | None = os.getenv("SRC_MAIL")
    src_pwd: str | None = os.getenv("SRC_PWD")
    dst_mail: str | None = os.getenv("DST_MAIL")
    data_pickle: Path = Path(os.getenv("DATA_PICKLE", str(_PROJECT_ROOT / "data" / "date_price_list.pkl")))
    output_html: Path = Path(os.getenv("OUTPUT_HTML", str(_PROJECT_ROOT / "data" / "flights.html")))
    nginx_dir: Path = Path(os.getenv("NGINX_DIR", "/var/www/kiwi"))
    public_url: str | None = os.getenv("PUBLIC_URL")

    def email_configured(self) -> bool:
        return all([self.src_mail, self.src_pwd, self.dst_mail])


settings = Settings()
