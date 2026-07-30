# expense-tracker

A small Flask application serving a React + Tailwind CSS v4 frontend. The backend
lives in `src/expense_tracker/` (a `create_app()` application factory), the frontend
in `frontend/`, and tests in `tests/`.

## Prerequisites

- [pixi](https://pixi.sh) - manages the Python toolchain, Node, and dependencies.
  Running `pixi install` (or any `pixi run` task) provisions everything from
  `pixi.toml`.

## Quickstart

```sh
pixi install          # set up the environment (installs the app editable)
pixi run web-install  # install frontend dependencies (npm ci)
pixi run web-build    # build the frontend into src/expense_tracker/static/
pixi run serve        # start the dev server on http://localhost:5000
```

Visit http://localhost:5000/ and you should see `Hello, World!`.

## Frontend

The frontend is a React 19 SPA built by vite, styled with Tailwind CSS v4 (configured
in CSS via `frontend/src/styles/app.css` - there is no `tailwind.config.js`).

`src/expense_tracker/static/` is **generated output and is committed**, so the wheel
is self-contained and the lean `prod` environment never needs Node. Rebuild it with
`pixi run web-build` and commit the result whenever you change `frontend/` or
`src/expense_tracker/greeting.json`; `pixi run web-verify` (also run in CI) fails if
the committed bundle has drifted.

The greeting is baked into the bundle at build time from
`src/expense_tracker/greeting.json`, which Flask reads too. That one file is the
single source of truth, and it is why the app exposes no greeting API - the rendered
page is the only public surface.

For frontend-only work, `npm run dev` gives you vite's dev server with hot reload.

## Editor setup (Zed)

`.zed/settings.json` pins the Tailwind and TypeScript language servers to the copies
in `node_modules`, so Zed **reports** exactly what CI enforces. Zed would otherwise
install its own always-latest copies. Run `pixi run web-install` before opening the
project, or those paths do not exist yet and the language servers will not start.

The file is deliberately minimal and does not enable `format_on_save` - that is left
to your own Zed settings. Formatting is applied by `pixi run web-format` and gated in
CI by `pixi run web-format-check`, the same way `ruff format` works on the Python
side. If you do turn `format_on_save` on, Zed picks up the pinned `prettier` from
`node_modules` rather than its bundled copy, so the result still matches CI - but note
that combining it with an `autosave.after_delay` reformats continuously as you type.

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
| `pixi run web-install` | Install frontend dependencies (`npm ci`) |
| `pixi run web-build` | Build the frontend into `src/expense_tracker/static/` |
| `pixi run web-check` | Type-check the frontend with tsc |
| `pixi run web-format` | Format the frontend with prettier |
| `pixi run web-format-check` | Check frontend formatting without writing changes |
| `pixi run web-verify` | Rebuild and fail if the committed bundle has drifted |

CI runs `lint`, `format-check`, `typecheck`, `test`, `web-format-check`, `web-check`,
and `web-verify` on every pull request.

## Configuration

Config is read from `FLASK_`-prefixed environment variables. **Production must set
`FLASK_SECRET_KEY`** (used to sign CSRF tokens) to a real, stable secret. The
`serve` and `test` tasks supply a dev-only value automatically.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit,
and squash-merge rules.
