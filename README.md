# expense-tracker

A small FastAPI application serving a React + Tailwind CSS v4 frontend. The backend
lives in `src/expense_tracker/` (a `create_app()` application factory), the frontend
in `frontend/`, and tests in `tests/`.

## Prerequisites

- [direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc`
  runs `use pixi`, so entering the directory provisions the Python toolchain, Node,
  and dependencies from `pixi.toml` - and re-provisions whenever `pixi.toml` changes,
  because the directive watches it. Run `direnv allow` once after cloning; there is
  no separate `pixi install` step.

  The `use pixi` directive is not built into direnv - it comes from the direnv
  library installed by [`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init),
  whose `setup-direnv` action CI uses to activate this same `.envrc`.

## Quickstart

```sh
cd expense-tracker    # direnv provisions the environment on entry
pixi run web-install  # install frontend dependencies (pnpm)
pixi run web-build    # build the frontend into src/expense_tracker/static/
pixi run serve        # start the dev server on http://localhost:8000
```

Visit http://localhost:8000/ and you should see `Hello, World!`.

## Frontend

The frontend is a React 19 SPA built by vite, styled with Tailwind CSS v4 (configured
in CSS via `frontend/src/styles/app.css` - there is no `tailwind.config.js`).

`src/expense_tracker/static/` is **generated output and is committed**, so the wheel
is self-contained and the lean `prod` environment never needs Node. Rebuild it with
`pixi run web-build` and commit the result whenever you change `frontend/` or
`src/expense_tracker/greeting.json`; `pixi run web-verify` (also run in CI) fails if
the committed bundle has drifted.

The greeting is baked into the bundle at build time from
`src/expense_tracker/greeting.json`, which the backend reads too. That one file is the
single source of truth, and it is why the app exposes no greeting API - the rendered
page is the only public surface.

For frontend-only work, `pnpm dev` gives you vite's dev server with hot reload.

Frontend tests use vitest and live in `frontend/tests/`. `frontend/src/main.tsx` is
excluded from coverage in both `vite.config.ts` and `sonar-project.properties` - it
only wires React to the DOM. Note that `vite.config.ts` pins vitest's root to the
repo root so the lcov report records repo-relative paths; without that SonarCloud
resolves them against the Python package and reports the frontend as uncovered.

### Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml`
alongside Node. Two deliberate choices worth knowing:

- **There is no `packageManager` field in `package.json`, and there must not be.**
  pnpm's `pmOnFail` defaults to `download`, so that field would make pnpm fetch and
  run its own copy of the declared version, bypassing the pixi pin. `pixi.toml` is the
  single source of truth for the pnpm version.
- **Pins must be at least 24 hours old.** pnpm 11 refuses to install versions
  published in the last 24 hours (`minimumReleaseAge`, default 1440 minutes) as a
  supply-chain guard. Because this project pins exact versions, pnpm cannot silently
  fall back to an older release - it will instead ask you to exempt the version in a
  `pnpm-workspace.yaml`. **Prefer picking the newest release that already clears the
  window over adding an exemption**, which would disable the guard for precisely the
  freshest, least-vetted package. There is deliberately no `pnpm-workspace.yaml` in
  this repo.

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

### Verifying the pins

To confirm the declared pins match what is installed:

```sh
pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`. One nested entry is expected and is
not drift: `@vtsls/language-server` bundles its own `typescript@5.9.3`, but Zed sends
`{"typescript": {"tsdk": "node_modules/typescript/lib"}}` as workspace configuration,
which redirects it to the pinned top-level copy.

To confirm Zed is actually using them, run this on the Linux side while Zed is open:

```sh
ps -eo pid,args | grep -E '[v]tsls|[t]ailwindcss-language-server'
```

Paths under this repo's `node_modules/` mean the pins took effect. Paths under
`~/.local/share/zed/` mean they did not - usually because `node_modules` is missing
(run `pixi run web-install`) or `node` is not on PATH for Zed's remote server.

### Known Zed quirk: "Binary: Unknown" over a remote/WSL backend

In `dev: open language server logs` -> **Server Info**, `vtsls` reports
`Binary: Unknown` and `Version: Unknown`. **This is expected and does not mean the
server failed to start.**

On a remote project (a Windows Zed client against a WSL backend, for example) the
client registers each language server with no binary information, and only fills it
in if the server later sends an LSP `client/registerCapability`. The Tailwind server
does that, so its binary path shows up; `vtsls` does not, so its entry stays
`Unknown` no matter how many times you restart Zed. `Version` is likewise never
populated for any server on a remote project.

Two related things that also look like faults but are not:

- The per-server **Logs** tab is usually empty. It only shows `window/logMessage`
  notifications, which most servers never send. Traffic under **RPC Messages** is the
  sign of a healthy server.
- Use the `ps` command above rather than Server Info when you actually need to know
  which binary Zed launched. For the version, find the `initialize` response in
  **RPC Messages** and read its `serverInfo` field.

## Development tasks

| Command | What it does |
| --- | --- |
| `pixi run serve` | Run the uvicorn dev server on port 8000 (with reloader) |
| `pixi run test` | Run the test suite with coverage |
| `pixi run lint` | Lint with ruff |
| `pixi run fix` | Auto-fix lint issues |
| `pixi run format` | Format with ruff |
| `pixi run format-check` | Check formatting without writing changes |
| `pixi run typecheck` | Type-check with basedpyright (strict) |
| `pixi run web-install` | Install frontend dependencies (`pnpm install --frozen-lockfile`) |
| `pixi run web-build` | Build the frontend into `src/expense_tracker/static/` |
| `pixi run web-check` | Type-check the frontend with tsc |
| `pixi run web-test` | Run the frontend tests (vitest) with coverage |
| `pixi run web-format` | Format the frontend with prettier |
| `pixi run web-format-check` | Check frontend formatting without writing changes |
| `pixi run web-verify` | Rebuild and fail if the committed bundle has drifted |

CI runs `lint`, `format-check`, `typecheck`, `test`, `web-format-check`, `web-check`,
`web-test`, and `web-verify` on every pull request, then the SonarCloud scan.

## Configuration

There is none: the app reads no environment variables and no config files. The
greeting is baked into the bundle at build time, so the only inputs are the committed
static files. FastAPI's OpenAPI schema and its `/docs` and `/redoc` UIs are switched
off in `create_app()` - the app exposes no API for them to describe, and the rendered
page is meant to be the only public surface.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit,
and squash-merge rules.
