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


@dataclass(slots=True)
class Settings:
    src_mail: str | None = os.getenv("SRC_MAIL")
    src_pwd: str | None = os.getenv("SRC_PWD")
    dst_mail: str | None = os.getenv("DST_MAIL")
    price_limit: int = int(os.getenv("PRICE_LIMIT", "500"))
    data_pickle: Path = Path(os.getenv("DATA_PICKLE", "date_price_list.pkl"))
    output_html: Path = Path(os.getenv("OUTPUT_HTML", "flights.html"))

    def email_configured(self) -> bool:
        return all([self.src_mail, self.src_pwd, self.dst_mail])


settings = Settings()
