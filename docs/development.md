# Developing here

## Where commands are defined

**Every task in `pixi.toml` forwards.** Each directory owns its own command bodies, in the
manifest that already owns how its tools behave:

- **Backend:** `[tool.poe.tasks]` in `backend/pyproject.toml`, beside the ruff, pytest and
  basedpyright config they invoke, with [poethepoet](https://poethepoet.natn.io) as the
  task runner.
- **Database:** `[tool.poe.tasks]` in `database/pyproject.toml`, which is a poe manifest
  and nothing else, with no `[project]` table and no Python package.
- **Frontend:** the `scripts` block in `frontend/package.json`.

The two layers buy both properties at once: `pixi run` is a single index across two
ecosystems, and each directory stays runnable natively (`cd backend && poe test`, `cd
frontend && pnpm test`). **Put the command body in the stack, never in the forwarder.**

## Continuous integration

`.github/workflows/ci.yml` runs every gate in **one job**, which lets the SonarCloud scan
at the end reuse the `coverage.xml` and `lcov.info` the test steps already wrote. The job
is named `Checks` because the `main-protection` ruleset requires that check **by name**.

**Each stack's gates run cheapest first**, then its tests, then anything that builds. That
puts lint near the end of both lists: `backend-lint` is ruff plus import-linter over the
graph, and `frontend-lint` is type-aware (`projectService` plus `strictTypeChecked`), so
eslint builds the same full TypeScript program `tsc` does.

`backend-db-init` is the one place that rule yields, sitting after the static gates
because it provisions rather than checks. GitHub sets `CI=true`, which turns a database
that failed to come up into a failure rather than a silent skip.

**The scan brings its own JRE.** `actions/setup-java` installs Temurin 21 and the scan
step passes `-Dsonar.scanner.skipJreProvisioning=true`. The two are a pair, and the flag
keeps the scan off a JRE downloaded from SonarCloud's API at runtime. The version tracks
the scanner CLI's floor, which refuses to start below 21.

## Editor setup (Zed)

`.zed/settings.json` pins each language server to the version this repo pins, and nothing
else; linter and type-checker settings stay in each stack's own config. The file carries
the per-server reasoning. It needs `direnv allow`, for the basedpyright path under
`.pixi/` and for the database settings a test runner launched from the editor reaches, and
`pixi run frontend-install`, for the servers under `frontend/node_modules/`. Where an
editor disagrees with CI, `pixi run backend-typecheck` and `pixi run frontend-lint` are
the authority.
