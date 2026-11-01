# Developing here

How commands are defined, how CI runs them, and editor setup.

## Where commands are defined

The middle column is the whole mechanism - **every task in `pixi.toml` forwards.** Each
directory owns its own command bodies, in the manifest that already owns how its tools
behave:

- **Backend:** `[tool.poe.tasks]` in `backend/pyproject.toml`, beside the ruff, pytest
  and basedpyright config they invoke, with
  [poethepoet](https://poethepoet.natn.io) as the task runner.
- **Database:** `[tool.poe.tasks]` in `database/pyproject.toml`, which is a poe manifest
  and nothing else - no `[project]` table, no Python package. The one command that
  directory runs has to be defined in that directory for the rule above to hold, and a
  directory with no manifest has nowhere to put it.
- **Frontend:** the `scripts` block in `frontend/package.json`, where a Node developer
  expects it.

The two layers buy both properties at once: `pixi run` is a single discoverable index
across two ecosystems, and each directory stays a standalone project you can run
natively.

```sh
cd backend  && poe test    # poe with no task lists the backend's
cd frontend && pnpm test   # pnpm run lists the frontend's
```

The cost is that adding a command means two edits - define it in the stack's manifest,
then forward it from `pixi.toml`. Put the command body in the stack, never in the
forwarder.

## Continuous integration

`.github/workflows/ci.yml` runs every gate in **one job**, which is what lets the
SonarCloud scan at the end reuse the `coverage.xml` and `lcov.info` the test steps already
wrote - two workflows would mean building the pixi environment twice and running the suite
twice to produce the same two files. The job is named `Checks` because the
`main-protection` ruleset requires that check by name, so the name is a gate and not a
label.

**Each stack's gates run cheapest first**, then its tests, then anything that builds, so a
broken change fails on the fastest gate that can catch it and nothing after it - including
the JDK setup and the scan - runs at all. That rule puts lint near the end of *both* lists
for different reasons, and the last position in each is the one carrying the weight:

```
backend    format-check ~0.2s   lint ~0.3s   typecheck ~1.1s
frontend   format-check ~0.8s   typecheck ~1.8s   lint ~3.2s
```

- **`backend-lint` is two tools in one task** - ruff over each file, then import-linter
  over the graph they form - so it costs more than the formatter it follows, but still
  less than pyright.
- **`frontend-lint` is type-aware** (`projectService` plus `strictTypeChecked`), so eslint
  builds the same full TypeScript program `tsc` does and then runs every rule over it,
  making it the priciest frontend gate at roughly twice the type checker.

Those figures are **cold**, as CI always runs them. Cold matters for `tsc` alone: it caches
to `node_modules/.tmp`, and `frontend-install` rebuilds that directory every run, so the
cache is never there to reuse. Warm, it is about a third of the figure above.

`backend-db-init` is the one place the cheapest-first rule yields, and it sits after the
static gates deliberately: it *provisions* rather than checks, so a lint or type error
should surface before a cluster is built. GitHub sets `CI=true`, which is what turns a
database that failed to come up into a failure rather than a silent skip.

**The scan brings its own JRE.** `actions/setup-java` installs Temurin 21 and the scan
step passes `-Dsonar.scanner.skipJreProvisioning=true`; the two are a pair, and the flag is
what makes that JDK the one the scan runs on instead of one the scanner downloads from
SonarCloud's API at runtime - a transient point of failure on an otherwise green build. The
version therefore tracks the scanner CLI's floor, and the CLI refuses to start on anything
below 21.

## Editor setup (Zed)

`.zed/settings.json` exists to make Zed **report** what CI enforces. Every entry does
one job: pin a language server to the version this repo pins. The linter and type-checker
settings stay in each stack's own config file, which is the single source for both. Read
the file itself for the per-server reasoning.

Preconditions: run `direnv allow` (for the basedpyright path under `.pixi/`) and
`pixi run frontend-install` (for the frontend servers under `frontend/node_modules/`), so
those paths exist for the servers to start from. `direnv allow` is also what puts the
database settings into the environment, so a test runner launched from inside the editor
reaches the local cluster when the editor inherits that environment - one started from a
shell direnv has blessed does.

`format_on_save` is left to your own Zed settings. Formatting is applied by
`pixi run frontend-format` and gated in CI by `pixi run frontend-format-check`, the same
way `ruff format` works on the Python side.

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`, `10.8.1`. One nested entry belongs
there: `@vtsls/language-server` bundles its own `typescript@5.9.3`, which the `tsdk`
setting in `.zed/settings.json` redirects to the pinned top-level copy.

To confirm Zed is using them, open a `.tsx` file **and** `frontend/src/styles/app.css`
first - Zed starts a language server when a buffer of a language it serves is open, so the
list below holds the servers with something to do - then run:

```sh
ps -eo pid,args | grep -E '[v]tsls|[c]ss-language-server|[e]slintServer'
```

Expect four processes. `@tailwindcss/language-server` ships **two** binaries and this
repo runs both, so that middle pattern is loose enough to match each:
`tailwindcss-language-server` completes class names in TSX, and `css-language-server`
is the Tailwind-aware CSS server named in the `CSS` block. The second one needs Zed
**1.16.1 or newer**, which is where the `tailwindcss-intellisense-css` adapter was added.

Paths under `frontend/node_modules/` mean the pins took effect; paths under
`~/.local/share/zed/` mean they did not - usually a missing `node_modules` or no `node`
on PATH for Zed's remote server. `eslintServer.js` is the exception and always runs from
`~/.local/share/zed/`, that server being Zed's own with only the module it loads pinned;
check it by putting `const x: any = 1;` in a `.tsx` file and confirming
`@typescript-eslint/no-explicit-any` fires.

Three things read as faults and are ordinary. Over a remote/WSL backend, Server Info
reports `Binary: Unknown` and `Version: Unknown` for `vtsls` however healthy it is, and
the per-server Logs tab is usually empty, most servers sending no `window/logMessage`.
Use the `ps` command above instead. Zed also underlines `tailwindcss-intellisense-css` in
`.zed/settings.json` as **"Property tailwindcss-intellisense-css is not allowed"** while
applying the setting; the same key in your own `settings.json` draws no warning. It is an
upstream schema bug: Zed builds the *project* settings schema from its language-attached
servers, where the *user* schema also includes opt-in ones (zed#46766), and this server is
opt-in. `ps` is the check that settles it. Where your editor disagrees with CI,
`pixi run backend-typecheck` and `pixi run frontend-lint` are the authority.
