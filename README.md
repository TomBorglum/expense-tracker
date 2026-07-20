# expense-tracker

Track expenses imported from CSV files.

**Stack:** Flask (Python) serving server-rendered HTML styled with Tailwind CSS,
backed by SQLite. No JavaScript, no Node at runtime.

## Requirements

[pixi](https://pixi.sh) manages the toolchain, including Python itself. With
[direnv](https://direnv.net) installed, `.envrc` activates the environment on `cd`.

## Getting started

```sh
pixi install                                  # solve and install the environment
pixi run css                                  # fetch tailwindcss, build the stylesheet
pixi run flask --app expense_tracker init-db  # create the SQLite database
pixi run serve                                # http://localhost:5000
```

## Tasks

| Task | What it does |
|---|---|
| `pixi run serve` | Run the development server with debug reloading. |
| `pixi run test` | Run the test suite. |
| `pixi run lint` | Lint with ruff. |
| `pixi run fix` | Lint and apply safe fixes. |
| `pixi run format` | Format with ruff. |
| `pixi run typecheck` | Type-check with basedpyright (strict). |
| `pixi run css` | Build `static/dist/app.css` (installs the binary if missing). |
| `pixi run css-watch` | Rebuild the stylesheet on template changes. |
| `pixi run tailwind-install` | Fetch the pinned tailwindcss binary into `bin/`. |

## Layout

```
expense_tracker/      application package
  __init__.py         create_app() application factory
  config.py           configuration objects
  db.py               sqlite3 helpers and the init-db CLI command
  schema.sql          table definitions
  routes/             blueprints
  templates/          Jinja templates
  static/src/         Tailwind entry point (source)
  static/dist/        compiled CSS (committed)
data/                 CSV expense files
tests/                test suite
scripts/              tooling helpers
```

## Tailwind

Tailwind v4 is CSS-first: there is no `tailwind.config.js`, and template scanning is
declared with `@source` in `expense_tracker/static/src/input.css`.

Tailwind is not packaged on conda-forge, so it cannot be a pixi dependency or enter
`pixi.lock`. It is pinned instead by exact version plus a SHA-256 checksum, both in
`pixi.toml`, and fetched by `scripts/install-tailwind.sh` into a gitignored `bin/`.

The compiled `static/dist/app.css` **is committed**. That is deliberate: it keeps the
Docker image free of any Node or Tailwind toolchain. CI rebuilds the stylesheet and
fails if the result differs from what was committed, so it cannot drift from the
templates. Run `pixi run css` and commit the result after changing template classes.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev` | Session signing key. **Must** be set in production. |
| `DATABASE` | `instance/expense-tracker.sqlite` | Path to the SQLite file. |

## Docker

```sh
docker build -t expense-tracker .
docker run -p 5000:5000 -v expense-data:/app/instance expense-tracker
```

The image installs only the `prod` pixi environment, so test tooling is excluded. The
volume keeps the SQLite database across container restarts.

Note the image currently runs Flask's built-in development server. That is fine for
local use; a real deployment should front it with a WSGI server such as gunicorn or
waitress.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). In short: branch, open a PR with a
Conventional Commit title, wait for checks, squash-merge.
