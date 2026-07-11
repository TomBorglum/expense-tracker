# expense-tracker

A small application for tracking expenses. Expenses live in CSV files committed to
this repository (the source of truth). On startup those CSV files are projected
into an ephemeral SQLite database, and a Python (Flask) web server renders a
read-only dashboard from it.

## How it works

```
data/*.csv  ->  loader  ->  SQLite (ephemeral, gitignored)  ->  Flask  ->  server-rendered HTML
```

- **Source of truth:** the CSV files under [`data/`](data/). Add or edit expenses
  by editing these files and committing them.
- **Query layer:** [`loader.py`](src/expense_tracker/loader.py) rebuilds
  `expenses.sqlite` from the CSV files on every run. The database is never
  committed and can be deleted at any time.
- **Backend:** a [Flask](https://flask.palletsprojects.com/) server renders the
  dashboard **entirely server-side** with Jinja2. There is no JSON API and no
  client-side JavaScript - filtering is a plain HTML `<form method="get">` that
  reloads the page.
- **Frontend:** HTML styled with [Tailwind CSS](https://tailwindcss.com/) v4,
  compiled by the standalone Tailwind CLI (no Node required).
- **Orchestration:** every command is a [Pixi](https://pixi.sh/) task.

## Project layout

```
data/expenses.csv            # committed expenses (source of truth)
src/expense_tracker/         # Python package
  loader.py                  # CSV -> SQLite projection
  queries.py                 # pure query functions
  server.py                  # Flask app (server-rendered dashboard)
templates/index.html         # dashboard template
static/src/input.css         # Tailwind entry stylesheet
tests/                       # pytest suite
```

## CSV format

Each file under `data/` has the header `date,amount,category,description`:

```csv
date,amount,category,description
2026-07-01,42.50,Groceries,Weekly shop
```

- `date` - ISO `YYYY-MM-DD`
- `amount` - decimal with a dot separator, at most two decimal places
- `category` - non-empty text
- `description` - free text

Multiple CSV files are supported (for example one per month); they are all
concatenated. Amounts are stored internally as integer cents so totals are exact.

## Prerequisites

[Pixi](https://pixi.sh/) is the only prerequisite - it manages the exact Python
and dependency versions. Install it with:

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

## First-time setup

```bash
pixi install          # create the environment (Python, Flask, pytest)
pixi run setup-tailwind   # download the pinned standalone Tailwind CLI (needs network)
```

`setup-tailwind` fetches the Tailwind binary into `tools/tailwindcss` (gitignored)
and only needs to be run once.

## Build

Compile the Tailwind stylesheet to `static/css/tailwind.css`:

```bash
pixi run build-css        # one-off, minified build
pixi run watch-css        # rebuild on change while developing
```

## Test

```bash
pixi run test             # run the pytest suite
```

## Run

```bash
pixi run serve            # build CSS, rebuild the DB from data/*.csv, then serve
```

Then open <http://127.0.0.1:8000>. The `serve` task depends on `build-css`, so it
always serves the current stylesheet. To rebuild only the database without
starting the server:

```bash
pixi run load
```

### Configuration

The server reads a few optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `EXPENSE_HOST` | `127.0.0.1` | Bind host |
| `EXPENSE_PORT` | `8000` | Bind port |
| `EXPENSE_DATA_DIR` | `data/` | Directory of CSV files |
| `EXPENSE_DB_PATH` | `expenses.sqlite` | Ephemeral SQLite location |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the branch, Conventional Commit, and
release rules. In short: never push to `main`, open a PR with a Conventional
Commit title, let the SonarCloud check pass, and squash-merge.
