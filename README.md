# KiwiFlightSearch

Flight deal scraper & processor for Kiwi (weekend and duration trips).

## Dependency Management (Astral uv)
This project has been migrated from Pipenv to [Astral uv](https://github.com/astral-sh/uv). The `Pipfile` / `Pipfile.lock` are now legacy and will be removed; rely on `pyproject.toml` + `uv`.

### Install uv
Unix / macOS:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Windows (PowerShell):
```
irm https://astral.sh/uv/install.ps1 | iex
```
Verify:
```
uv --version
```

### Create / Sync Environment
Create (or update) the virtual environment in `.venv` and install runtime + dev deps:
```
uv sync --all-groups
```
Runtime only:
```
uv sync
```

### Running the CLI
```
uv run kiwiflight   # runs kiwiflight.pipeline:main_cli
```
(You can also `source .venv/bin/activate` or on Windows `.venv\Scripts\activate` and run `kiwiflight` directly.)

### Adding Dependencies
Runtime:
```
uv add package-name
```
Dev (lint/format/test tools, goes to the `dev` dependency group):
```
uv add --group dev black
```

### Updating Dependencies
```
uv lock --upgrade          # refresh resolved versions (creates/updates uv.lock once generated)
uv sync                    # apply changes
```


### Environment Variables
Place secrets / config in a `.env` file (loaded via python-dotenv) – do **not** commit it.

## License
MIT
