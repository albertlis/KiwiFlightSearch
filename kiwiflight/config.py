"""Configuration utilities.

Central place to load environment driven settings (email credentials, defaults, etc.).
Avoids scattering os.getenv calls around the codebase.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env once on module import
load_dotenv()

# Root of the project (parent of the kiwiflight/ package directory)
_PROJECT_ROOT = Path(__file__).parent.parent

# Default travel cost (PLN) per Polish origin/destination airport.
# Override via AIRPORT_PENALTY_MAP env var as JSON, e.g. '{"WRO":0,"KTW":150,"POZ":60}'
_DEFAULT_PENALTY_MAP: dict[str, int] = {"WRO": 0, "KTW": 150, "POZ": 60}


def _load_penalty_map() -> dict[str, int]:
    raw = os.getenv("AIRPORT_PENALTY_MAP")
    if raw:
        try:
            return {k: int(v) for k, v in json.loads(raw).items()}
        except (json.JSONDecodeError, ValueError):
            pass
    return dict(_DEFAULT_PENALTY_MAP)


@dataclass(slots=True)
class Settings:
    src_mail: str | None = os.getenv("SRC_MAIL")
    src_pwd: str | None = os.getenv("SRC_PWD")
    dst_mail: str | None = os.getenv("DST_MAIL")
    data_pickle: Path = Path(os.getenv("DATA_PICKLE", str(_PROJECT_ROOT / "data" / "date_price_list.pkl")))
    output_html: Path = Path(os.getenv("OUTPUT_HTML", str(_PROJECT_ROOT / "data" / "index.html")))
    nginx_dir: Path = Path(os.getenv("NGINX_DIR", "/var/www/kiwi"))
    public_url: str | None = os.getenv("PUBLIC_URL")
    airport_penalty_map: dict[str, int] = field(default_factory=_load_penalty_map)

    def email_configured(self) -> bool:
        return all([self.src_mail, self.src_pwd, self.dst_mail])

    def airport_penalty(self, start_iata: str, end_iata: str) -> int:
        """Return total travel penalty (PLN) for a round trip: departure + return airport."""
        return self.airport_penalty_map.get(start_iata, 0) + self.airport_penalty_map.get(end_iata, 0)


settings = Settings()
