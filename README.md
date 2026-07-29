# expense-tracker

A small Flask application. The source lives in `src/expense_tracker/` (a
`create_app()` application factory) and tests in `tests/`.

## Prerequisites

- [pixi](https://pixi.sh) - manages the Python toolchain and dependencies. Running
  `pixi install` (or any `pixi run` task) provisions everything from `pixi.toml`.

## Quickstart

```sh
pixi install          # set up the environment (installs the app editable)
pixi run serve        # start the dev server on http://localhost:5000
```

Visit http://localhost:5000/ and you should see `Hello, World!` on a styled page.
The same greeting is served as plain text at http://localhost:5000/api/hello.

## Frontend

Server-rendered Jinja templates in `src/expense_tracker/templates/`, styled with
[Tailwind CSS](https://tailwindcss.com) v4. **No JavaScript and no Node toolchain** -
Tailwind runs as a standalone binary that `pixi run css-install` fetches into
`bin/tailwindcss` (version- and sha256-pinned in `scripts/install-tailwind.sh`).

Tailwind v4 is CSS-first, so `src/expense_tracker/static/src/input.css` is the config;
there is no `tailwind.config.js`. The compiled `static/css/app.css` **is committed**, so
running the app needs no Tailwind binary. That means: **after editing a template, run
`pixi run css-build` and commit the result** - CI's `css-check` fails on stale CSS.

### Editor setup

`.zed/settings.json` configures [Zed](https://zed.dev) for this frontend: it treats
`templates/*.html` as Jinja2, keeps Tailwind class completion working there, and swaps
the CSS language server for Tailwind's so v4 at-rules (`@import "tailwindcss"`,
`@source`) are understood instead of flagged as errors. The `jinja2` extension is
auto-installed on opening the project. Other editors need their own equivalent; nothing
here affects the build.

## Development tasks

| Command | What it does |
| --- | --- |
| `pixi run serve` | Run the dev server (reloader + debugger) |
| `pixi run test` | Run the test suite with coverage |
| `pixi run lint` | Lint with ruff |
| `pixi run fix` | Auto-fix lint issues |
| `pixi run format` | Format with ruff |
| `pixi run format-check` | Check formatting without writing changes |
| `pixi run typecheck` | Type-check with basedpyright (strict) |
| `pixi run css-install` | Fetch the pinned standalone Tailwind CLI into `bin/` |
| `pixi run css-build` | Compile `input.css` to the committed `static/css/app.css` |
| `pixi run css-watch` | Rebuild CSS on change while developing |
| `pixi run css-check` | Fail if the committed CSS is stale (used by CI) |

CI runs `lint`, `format-check`, `typecheck`, `test`, and `css-check` on every pull
request.

## Configuration

Config is read from `FLASK_`-prefixed environment variables. **Production must set
`FLASK_SECRET_KEY`** (used to sign CSRF tokens) to a real, stable secret. The
`serve` and `test` tasks supply a dev-only value automatically.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit,
and squash-merge rules.
