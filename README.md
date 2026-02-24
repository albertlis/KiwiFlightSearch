# ✈️ KiwiFlightSearch

> Automated flight deal finder — scrapes [Kiwi.com](https://www.kiwi.com), filters results by custom criteria and delivers an HTML report (optionally via e-mail).

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Timetable Pipeline](#timetable-pipeline)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Processing Modes](#processing-modes)
- [Development](#development)
- [License](#license)

---

## Overview

KiwiFlightSearch scrapes Kiwi.com for round-trip flights departing from selected Polish airports (**KTW**, **WRO**, **POZ**) and automatically finds the best deals matching your travel preferences. Results are rendered into a clean HTML report and can be sent directly to your inbox.

---

## Features

- 🕷️ **Playwright-based scraper** with stealth mode to avoid bot detection
- 📅 **Two search modes**: weekend getaways and flexible duration trips
- 🗓️ Static airport timetable enrichment (departure / arrival times per route)
- 💰 Price-limit filtering
- 📧 Optional e-mail delivery via `yagmail`
- 🧩 Modular pipeline — reuse cached data (pickle) to iterate without re-scraping
- 🖨️ Jinja2-templated HTML reports

---

## Project Structure

```
KiwiFlightSearch/
├── kiwiflight/                  # Core package
│   ├── config.py                # Settings loaded from .env
│   ├── models.py                # Domain models (FlightInfo, FlightTimetable)
│   ├── pipeline.py              # High-level orchestration + CLI entry point
│   ├── emailer.py               # E-mail delivery
│   ├── processing/
│   │   ├── base.py              # Shared base processor
│   │   ├── weekends.py          # Weekend trip processor
│   │   └── duration.py          # Duration trip processor
│   └── scraping/
│       ├── playwright_scraper.py
│       └── selenium_scraper.py
│
├── airport_timetable_scrappers/ # Step 1 – scrape airport timetable pages → HTML
├── html_for_scrapping/          # Step 2 – raw HTML timetable files
├── html_timetable_processors/   # Step 3 – parse HTML → structured JSON timetables
├── timetables/                  # Step 4 – output JSON timetables (per airport)
│
├── templates/                   # Jinja2 HTML report templates
├── pyproject.toml               # Project metadata & dependencies (uv)
└── .env                         # Secrets (not committed)
```

---

## Timetable Pipeline

Airport timetables are prepared through a dedicated, multi-step pipeline:

```
airport_timetable_scrappers/
        │  (scrape timetable website → save raw HTML)
        ▼
html_for_scrapping/
        │  (raw HTML files, e.g. KTW_timetable_departures.html)
        ▼
html_timetable_processors/
        │  (parse HTML with BeautifulSoup → extract routes, times, weekdays, seasons)
        ▼
timetables/
        └─ KTW_timetable.json
        └─ WRO_timetable.json
        └─ ...
```

Each resulting JSON contains **arrivals** and **departures** keyed by IATA code, and is later used by the processing layer to enrich flight results with real departure/arrival times.

> Note about POZ airport: due to site protections and dynamic content loading on the airport's website, `POZ_timetable_scrapper.py` could not be reliably automated. In practice, you need to save the timetable page manually from your browser and place the HTML file into the `html_for_scrapping/` folder.
>
> How to do this (simple options):
> - Open the POZ timetable page in your browser and press F12 to open Developer Tools (Inspector).
> - Locate the element containing the timetable (Elements tab). Right-click the relevant node and choose "Save as..." if available, or choose "Copy → OuterHTML" and paste the content into a new HTML file.
> - Save the file into `html_for_scrapping/`, e.g. `POZ_timetable_departures.html` (or `POZ_timetable_arrivals.html`).
> - Then run the processor script in `html_timetable_processors/` to parse that file and generate `timetables/POZ_timetable.json`.

---

## Installation

This project uses [Astral uv](https://github.com/astral-sh/uv) for dependency management.

### 1. Install uv

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
**Windows (PowerShell):**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### 2. Install dependencies

```bash
# Runtime + dev dependencies
uv sync --all-groups

# Runtime only
uv sync
```

---

## Configuration

Create a `.env` file in the project root — it is loaded automatically at startup:

```dotenv
# E-mail credentials (required for --email flag)
SRC_MAIL=your_sender@gmail.com
SRC_PWD=your_app_password
DST_MAIL=your_recipient@gmail.com

# Price ceiling in PLN (default: 500)
PRICE_LIMIT=500

# Paths (defaults shown)
DATA_PICKLE=date_price_list.pkl
OUTPUT_HTML=flights.html
```

> ⚠️ Never commit `.env` to version control.

---

## Usage

Run the pipeline via the CLI entry point:

```bash
uv run kiwiflight [OPTIONS]
```

### Common examples

```bash
# Weekend deals from WRO and KTW, reuse cached data
uv run kiwiflight --mode weekend --iata WRO KTW

# Duration deals: scrape fresh data, 5–9 day trips, send e-mail
uv run kiwiflight --mode duration --scrape --min-days 5 --max-days 9 --email

# Duration deals within a specific date range
uv run kiwiflight --mode duration --start-date 01.06.2026 --end-date 31.08.2026

# Change log verbosity
uv run kiwiflight --log-level DEBUG
```

### All CLI options

| Option | Default | Description |
|---|---|---|
| `--mode` | `duration` | `weekend` or `duration` |
| `--iata` | `WRO POZ KTW` | Origin airport IATA codes (space-separated) |
| `--scrape` | `False` | Scrape fresh data; otherwise loads cached pickle |
| `--start-month` | `sierpień` | Month name passed to Kiwi date picker |
| `--end-month` | `październik` | Month name passed to Kiwi date picker |
| `--min-days` | `4` | Minimum trip duration in days *(duration mode)* |
| `--max-days` | `8` | Maximum trip duration in days *(duration mode)* |
| `--start-date` | — | Earliest allowed departure `dd.mm.YYYY` *(duration mode)* |
| `--end-date` | — | Latest allowed return `dd.mm.YYYY` *(duration mode)* |
| `--min-hours` | `10` | Minimum trip length in hours *(weekend mode)* |
| `--max-start-hour` | `11` | Latest departure hour accepted *(weekend mode)* |
| `--email` | `False` | Send HTML report via e-mail |
| `--log-level` | `INFO` | Logging verbosity |

---

## Processing Modes

### `weekend`
Finds **short round trips** that start on Friday or Saturday and return on Sunday, Monday or Tuesday. Filters by minimum trip duration (hours) and earliest departure time to ensure the trip is actually usable as a weekend escape.

### `duration`
Finds **round trips** whose length falls within `[min-days, max-days]`. Optionally constrained to a specific date window. Ideal for planning longer holidays or city breaks.

---

## Development

### Adding dependencies

```bash
# Runtime
uv add package-name

# Dev tooling (linting, formatting, testing)
uv add --group dev package-name
```

### Updating the lock file

```bash
uv lock --upgrade   # recalculate resolved versions
uv sync             # apply to the virtual environment
```

### Code quality tools

```bash
uv run black .          # format
uv run isort .          # sort imports
uv run ruff check .     # lint
uv run mypy kiwiflight  # type-check
```

---

## License

[MIT](LICENSE)
