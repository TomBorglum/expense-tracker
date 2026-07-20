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

Visit http://localhost:5000/ and you should see `Hello, World!`.

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

CI runs `lint`, `format-check`, `typecheck`, and `test` on every pull request.

## Configuration

Config is read from `FLASK_`-prefixed environment variables. **Production must set
`FLASK_SECRET_KEY`** (used to sign CSRF tokens) to a real, stable secret. The
`serve` and `test` tasks supply a dev-only value automatically.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit,
and squash-merge rules.
