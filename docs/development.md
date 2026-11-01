# Developing here

How commands are defined, how CI runs them, and editor setup.

## Where commands are defined

**Every task in `pixi.toml` forwards.** Each directory owns its own command bodies, in the
manifest that already owns how its tools behave:

- **Backend:** `[tool.poe.tasks]` in `backend/pyproject.toml`, beside the ruff, pytest and
  basedpyright config they invoke, with [poethepoet](https://poethepoet.natn.io) as the
  task runner.
- **Database:** `[tool.poe.tasks]` in `database/pyproject.toml`, which is a poe manifest
  and nothing else - no `[project]` table, no Python package. The one command that
  directory runs has to be defined there for the rule above to hold.
- **Frontend:** the `scripts` block in `frontend/package.json`.

The two layers buy both properties at once: `pixi run` is a single discoverable index
across two ecosystems, and each directory stays a standalone project you can run natively
(`cd backend && poe test`, `cd frontend && pnpm test`; either with no task lists that
stack's own). The cost is that adding a command means two edits. **Put the command body in
the stack, never in the forwarder.**

## Continuous integration

`.github/workflows/ci.yml` runs every gate in **one job**, which is what lets the
SonarCloud scan at the end reuse the `coverage.xml` and `lcov.info` the test steps already
wrote - two workflows would mean building the pixi environment twice and running the suite
twice for the same two files. The job is named `Checks` because the `main-protection`
ruleset requires that check **by name**, so the name is a gate and not a label.

**Each stack's gates run cheapest first**, then its tests, then anything that builds, so a
broken change fails on the fastest gate that can catch it and nothing after it runs at
all. That rule puts lint near the end of *both* lists for different reasons:

```
backend    format-check ~0.2s   lint ~0.3s   typecheck ~1.1s
frontend   format-check ~0.8s   typecheck ~1.8s   lint ~3.2s
```

- **`backend-lint` is two tools in one task** - ruff over each file, then import-linter
  over the graph they form - so it costs more than the formatter, still less than pyright.
- **`frontend-lint` is type-aware** (`projectService` plus `strictTypeChecked`), so eslint
  builds the same full TypeScript program `tsc` does and then runs every rule over it,
  making it the priciest frontend gate at roughly twice the type checker.

Those figures are **cold**, as CI always runs them. Cold matters for `tsc` alone: it
caches to `node_modules/.tmp`, which `frontend-install` rebuilds every run, so the cache is
never there to reuse. Warm, it is about a third of the figure.

`backend-db-init` is the one place the cheapest-first rule yields, sitting after the static
gates deliberately: it *provisions* rather than checks. GitHub sets `CI=true`, which turns
a database that failed to come up into a failure rather than a silent skip.

**The scan brings its own JRE.** `actions/setup-java` installs Temurin 21 and the scan step
passes `-Dsonar.scanner.skipJreProvisioning=true`; the two are a pair, and the flag is what
keeps the scan off a JRE downloaded from SonarCloud's API at runtime - a transient point of
failure on an otherwise green build. The version tracks the scanner CLI's floor, which
refuses to start below 21.

## Editor setup (Zed)

`.zed/settings.json` exists to make Zed **report** what CI enforces. Every entry does one
job: pin a language server to the version this repo pins. The linter and type-checker
settings stay in each stack's own config file, the single source for both. Read the file
itself for the per-server reasoning.

Preconditions: `direnv allow` (for the basedpyright path under `.pixi/`) and
`pixi run frontend-install` (for the servers under `frontend/node_modules/`), so those
paths exist for the servers to start from. `direnv allow` is also what puts the database
settings into the environment, so a test runner launched from inside the editor reaches the
local cluster. `format_on_save` is left to your own Zed settings.

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

One nested entry belongs there: `@vtsls/language-server` bundles its own typescript, which
the `tsdk` setting redirects to the pinned top-level copy. To confirm Zed is using them,
open a `.tsx` file **and** `frontend/src/styles/app.css` first, then
`ps -eo pid,args | grep -E '[v]tsls|[c]ss-language-server|[e]slintServer'`. Expect four
processes - `@tailwindcss/language-server` ships **two** binaries and this repo runs both,
the CSS one needing Zed **1.16.1 or newer**. Paths under `frontend/node_modules/` mean the
pins took effect; paths under `~/.local/share/zed/` mean they did not. `eslintServer.js`
always runs from there, that server being Zed's own with only the module it loads pinned.

Two things read as faults and are ordinary: over a remote/WSL backend, Server Info reports
`Binary: Unknown` for `vtsls` however healthy it is, and Zed underlines
`tailwindcss-intellisense-css` as not allowed while applying it - an upstream schema bug
(zed#46766) for opt-in servers. `ps` is the check that settles both. Where your editor
disagrees with CI, `pixi run backend-typecheck` and `pixi run frontend-lint` are the
authority.
