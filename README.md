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
[Tailwind CSS](https://tailwindcss.com) v4. **The application ships no JavaScript** -
pages are plain server-rendered HTML.

Tailwind v4 is CSS-first, so `src/expense_tracker/static/src/input.css` is the config;
there is no `tailwind.config.js`. The compiled `static/css/app.css` **is committed**, so
running the app needs no build step at all - `pixi install && pixi run serve` serves a
styled page on a fresh clone. That means: **after editing a template, run
`pixi run css-build` and commit the result** - CI's `css-check` fails on stale CSS.

### Why Tailwind is an npm dependency

Tailwind is pinned in `package.json` with a committed `package-lock.json`, and
`pixi run css-install` restores it with `npm ci`. Node comes from pixi (`nodejs` in the
dev feature), so there is no system prerequisite beyond pixi itself.

This is a build-time dev dependency only: `prod` has no Node and no `node_modules`, and
nothing from npm reaches the browser. The reason for npm rather than the standalone
Tailwind binary is **version drift**. Editors run Tailwind's language server, which
resolves `tailwindcss` from `node_modules`; with only a standalone binary it cannot find
one and silently falls back to a bundled copy of a different version, so completions
describe a Tailwind you are not compiling with and `@source` paths stop resolving. One
npm pin means the compiler and the editor load the identical version by construction.

### Editor setup

`.zed/settings.json` swaps the CSS language server for Tailwind's, so the v4 at-rules in
`input.css` (`@import "tailwindcss"`, `@source`) are understood instead of flagged as
errors, and pins the v4 stylesheet entry point. Run `pixi run css-install` once so the
language server can load the pinned Tailwind. Templates are left as plain HTML on
purpose, which is what keeps Tailwind class completion working in them - the file
explains the trade-off. Other editors need their own equivalent; nothing here affects
the build.

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
| `pixi run css-install` | Restore the pinned Tailwind toolchain (`npm ci`) |
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
