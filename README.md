# ✈️ KiwiFlightSearch

> Automated flight deal finder — scrapes [Kiwi.com](https://www.kiwi.com), filters results by custom criteria and
> delivers a clean HTML report (optionally via e-mail or nginx).

> [!WARNING]
> **This project is under heavy development and is currently unstable.** Breaking changes — including
> backward-incompatible API, CLI, and data-format changes — may be introduced at any time without prior notice.

![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![uv](https://img.shields.io/badge/managed%20by-uv-purple?logo=astral)
![Playwright](https://img.shields.io/badge/scraper-Playwright-orange?logo=playwright)

---

## 📑 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Timetable Pipeline](#timetable-pipeline)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Processing Modes](#processing-modes)
- [Scheduling](#scheduling)
- [Development](#development)
- [License](#license)

---

## 🔍 Overview

KiwiFlightSearch scrapes Kiwi.com for round-trip flights departing from selected Polish airports (**KTW**, **WRO**, *
*POZ**) and automatically finds the best deals matching your travel preferences. Results are rendered into a clean HTML
report and can be sent directly to your inbox or served via nginx.

---

## ✨ Features

| #   | Feature                                                                   |
|-----|---------------------------------------------------------------------------|
| 🕷️ | **Playwright-based scraper** with stealth mode to avoid bot detection     |
| 📅  | **Two search modes**: weekend getaways and flexible duration trips        |
| 🗓️ | Static airport timetable enrichment (departure / arrival times per route) |
| 💰  | Configurable price-limit filtering (default: 500 PLN)                     |
| 📧  | Optional e-mail delivery via `yagmail` (full HTML body or link)           |
| 🌐  | Optional nginx integration — copy report to a web root directory          |
| ⏰   | Built-in **daily scheduler** — run as a daemon with `--schedule-at`       |
| 🧩  | Modular pipeline — reuse cached pickle to iterate without re-scraping     |
| 🖨️ | Jinja2-templated HTML reports                                             |

---

## 🗂️ Project Structure

```
KiwiFlightSearch/
│
├── kiwiflight/                        # 📦 Core package
│   ├── config.py                      #   Settings loaded from .env
│   ├── models.py                      #   Domain models (FlightInfo, FlightTimetable)
│   ├── pipeline.py                    #   High-level orchestration + CLI entry point
│   ├── emailer.py                     #   E-mail delivery (full HTML or link)
│   ├── logging_config.py              #   Logging setup
│   ├── processing/
│   │   ├── base.py                    #   Shared base processor
│   │   ├── weekends.py                #   Weekend trip processor
│   │   └── duration.py                #   Duration trip processor
│   └── scraping/
│       ├── base_driver.py             #   Base Playwright driver
│       └── playwright_scraper.py      #   Kiwi.com scraper (stealth)
│
├── airport_timetable_scrappers/       # 🕸️ Step 1 – scrape airport pages → raw HTML
├── html_for_scrapping/                # 📄 Step 2 – raw HTML timetable files
├── timetable_processors/              # ⚙️ Step 3 – parse HTML → structured JSON
├── timetables/                        # 📋 Step 4 – output JSON timetables per airport
│
├── data/
│   ├── date_price_list.pkl            #   Cached scraping results
│   ├── flights.html                   #   Generated HTML report
│   ├── interesting_iatas.txt          #   Curated list of destination IATA codes
│   └── airports_to_iata_mapping.json  #   Airport → IATA reverse mapping
│
├── templates/                         # 🎨 Jinja2 HTML report templates
│   ├── duration_deals.html.j2
│   └── weekend_deals.html.j2
│
├── validate_iatas.py                  # 🔎 Pre-flight IATA mapping validator
├── pyproject.toml                     # Project metadata & dependencies (uv)
└── .env                               # Secrets (not committed)
```

---

## 🔄 Timetable Pipeline

Airport timetables are prepared through a dedicated, multi-step pipeline:

```
airport_timetable_scrappers/
        │  scrape timetable website → save raw HTML
        ▼
html_for_scrapping/
        │  raw HTML files (e.g. KTW_timetable_departures.html)
        ▼
timetable_processors/
        │  parse HTML with BeautifulSoup → extract routes, times, weekdays, seasons
        │  timetable_to_avaiable_iata_codes.py → update interesting_iatas.txt
        ▼
timetables/
        ├─ KTW_timetable.json
        ├─ WRO_timetable.json
        └─ POZ_timetable.json
```

Each resulting JSON contains **arrivals** and **departures** keyed by IATA code, and is later used by the processing
layer to enrich flight results with real departure/arrival times.

---

## 🚀 Installation

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

### 3. Install Playwright browsers

```bash
uv run playwright install chromium
```

### 4. Validate IATA mappings

Before scraping, make sure every IATA code in `airport_iata_codes/` has a corresponding city→IATA entry in
`data/airports_to_iata_mapping.json`. The mapping is used as a **fallback** when Kiwi.com doesn't recognise a bare IATA
code — if a code is missing, the scraper will skip that route and report it as an `AirportLookupError` in the HTML
report.

Run the validator:

```bash
uv run python validate_iatas.py
```

If any codes are missing, the script prints them and exits with code 1. Add the missing `"City Name": "IATA"` entries to
`data/airports_to_iata_mapping.json` and re-run until the check passes.

---

## ⚙️ Configuration

Create a `.env` file in the project root — it is loaded automatically at startup:

```dotenv
# ── E-mail credentials (required for --email / --email-link flags) ──────────
SRC_MAIL=your_sender@gmail.com
SRC_PWD=your_gmail_app_password
DST_MAIL=your_recipient@gmail.com

# ── File paths (defaults shown) ──────────────────────────────────────────────
DATA_PICKLE=data/date_price_list.pkl
OUTPUT_HTML=data/flights.html

# ── Nginx integration (optional, required for --nginx) ───────────────────────
NGINX_DIR=/var/www/kiwi

# ── Public URL for email-link mode (optional, required for --email-link) ─────
PUBLIC_URL=https://your-server.example.com
```

> ⚠️ **Never commit `.env` to version control.**

---

## 💻 Usage

Run the pipeline via the CLI entry point:

```bash
uv run kiwiflight [OPTIONS]
```

### 🧪 Common examples

```bash
# Weekend deals from WRO and KTW, reuse cached data
uv run kiwiflight --mode weekend --iata WRO KTW

# Duration deals: scrape fresh data, 5–9 day trips, send e-mail
uv run kiwiflight --mode duration --scrape --min-days 5 --max-days 9 --email

# Duration deals within a specific date range
uv run kiwiflight --mode duration --start-date 01.06.2026 --end-date 31.08.2026

# Search all known destinations (not just interesting_iatas.txt)
uv run kiwiflight --mode duration --scrape --all-iatas

# Run once, copy report to nginx, send link by e-mail
uv run kiwiflight --scrape --nginx --email-link

# Run as a daily daemon at 07:30
uv run kiwiflight --scrape --schedule-at 07:30 --nginx --email-link

# Change log verbosity
uv run kiwiflight --log-level DEBUG
```

### 📋 All CLI options

| Option             | Default       | Description                                                |
|--------------------|---------------|------------------------------------------------------------|
| `--mode`           | `duration`    | Search mode: `weekend` or `duration`                       |
| `--iata`           | `WRO POZ KTW` | Origin airport IATA codes (space-separated)                |
| `--scrape`         | `False`       | Scrape fresh data; otherwise loads cached pickle           |
| `--all-iatas`      | `False`       | Search all IATA codes, ignoring `interesting_iatas.txt`    |
| `--start-month`    | `sierpień`    | Month name passed to Kiwi date picker (Polish)             |
| `--end-month`      | `październik` | Month name passed to Kiwi date picker (Polish)             |
| `--min-days`       | `4`           | Minimum trip duration in days *(duration mode)*            |
| `--max-days`       | `8`           | Maximum trip duration in days *(duration mode)*            |
| `--start-date`     | —             | Earliest allowed departure `dd.mm.YYYY` *(duration mode)*  |
| `--end-date`       | —             | Latest allowed return `dd.mm.YYYY` *(duration mode)*       |
| `--min-hours`      | `10`          | Minimum trip length in hours *(weekend mode)*              |
| `--max-start-hour` | `11`          | Latest accepted departure hour *(weekend mode)*            |
| `--price-limit`    | `500`         | Maximum price per deal in PLN                              |
| `--email`          | `False`       | Send full HTML report via e-mail                           |
| `--email-link`     | `False`       | Send e-mail containing a link to the report (`PUBLIC_URL`) |
| `--nginx`          | `False`       | Copy HTML report to `NGINX_DIR`                            |
| `--schedule-at`    | —             | Run pipeline daily at `HH:MM` (daemon mode)                |
| `--log-level`      | `INFO`        | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, …)          |

> **Note:** `--start-month` and `--end-month` accept Polish month names (e.g. `sierpień`, `wrzesień`, `październik`) as
> displayed in Kiwi.com's date picker UI.

---

## 🗺️ Processing Modes

### 🏖️ `weekend`

Finds **short round trips** that start on **Friday or Saturday** and return on **Sunday, Monday or Tuesday**. Filters
by:

- Minimum trip duration (`--min-hours`)
- Latest allowed departure time (`--max-start-hour`)

Ideal for spontaneous weekend city breaks.

### 🧳 `duration`

Finds **round trips** whose length falls within `[--min-days, --max-days]`. Optionally constrained to a specific date
window (`--start-date` / `--end-date`). Ideal for planning longer holidays.

---

## ⏰ Scheduling

The `--schedule-at HH:MM` flag turns the pipeline into a **long-running daemon** that executes once immediately and then
repeats every day at the specified time.

```bash
# Run every day at 07:30, copy to nginx, send link by e-mail
uv run kiwiflight --scrape --schedule-at 07:30 --nginx --email-link
```

To run as a **systemd service** on Linux, create `/etc/systemd/system/kiwiflight.service`:

```ini
[Unit]
Description = KiwiFlightSearch daily deal finder
After = network-online.target

[Service]
ExecStart = uv run kiwiflight --scrape --schedule-at 07:30 --nginx --email-link
WorkingDirectory = /path/to/KiwiFlightSearch
Restart = on-failure

[Install]
WantedBy = multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kiwiflight
```

---

## 🛠️ Development

```bash
# Format code
uv run black .
uv run isort .

# Lint
uv run ruff check .

# Type check
uv run mypy kiwiflight/
```

Dev dependencies are declared in the `dev` group in `pyproject.toml` and installed via:

```bash
uv sync --group dev
```

---

## 📄 License

[MIT](LICENSE)
