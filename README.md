# expense-tracker

A FastAPI REST API and a React + Tailwind CSS v4 single-page app, as two independent
applications.

`backend/` and `frontend/` are siblings, each owning its own tooling, tests and build.
Neither can see the other: the backend serves JSON and ships no frontend assets, the
frontend builds to its own `dist/` and reaches the API cross-origin over CORS. Each
can be built, tested and linted with the other's directory missing entirely. The root
holds only what spans both: pixi orchestrates the two toolchains, and one SonarCloud
project covers both languages.

Locally that means two processes. Packaging them into a single deployable artifact is
out of scope for now.

```
expense-tracker/
  pixi.toml, pixi.lock          # environments and every `pixi run` task, both stacks
  sonar-project.properties      # one Sonar project spanning both languages
  pyrightconfig.json            # basedpyright; at the root so editors find it
  backend/
    pyproject.toml              # hatchling, ruff, pytest
    src/expense_tracker/        # create_app() factory, greeting.json
    tests/
  frontend/
    package.json, tsconfig*.json, vite.config.ts, eslint.config.ts, .prettierrc.json
    .env                        # VITE_API_BASE_URL - where the API lives
    index.html, src/, tests/
    dist/                       # vite output, gitignored
```

## Prerequisites

- [direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc`
  runs `use pixi python`, so entering the directory provisions the Python toolchain,
  Node, and dependencies from `pixi.toml` - and re-provisions whenever `pixi.toml`
  changes, because the directive watches it. Run `direnv allow` once after cloning;
  there is no separate `pixi install` step.

  The `.envrc` also runs `use sonarqube_mcp`, which exports the configuration for the
  SonarQube MCP server declared in `.mcp.json` (a container that gives an editor or
  agent access to this project's SonarCloud analysis). It reads `SONARQUBE_TOKEN` and
  `SONARQUBE_ORG` from the environment; the server is the only thing that needs them,
  so nothing else here breaks if they are unset.

  Neither directive is built into direnv - both come from the direnv library
  installed by [`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init),
  whose `setup-direnv` action CI uses to activate this same `.envrc`. Without that
  library, `direnv allow` reports the directives as unknown commands.

## Quickstart

```sh
cd expense-tracker    # direnv provisions the environment on entry
pixi run web-install  # install frontend dependencies (pnpm)
```

Then start both, in two terminals:

```sh
pixi run serve        # the REST API on http://localhost:8000
pixi run web-dev      # the SPA on http://localhost:5173
```

Visit http://localhost:5173 and you should see `Hello, World!`. The page fetches it
from `http://localhost:8000/api/greeting` - a genuine cross-origin request, which
works only because the API allows it (see [CORS](#cors)).

The API alone is enough for backend work; the SPA alone runs too, it just renders its
error state until something answers on 8000.

## Routes

The backend is a REST API and serves nothing else:

| Route | What it serves |
| --- | --- |
| `GET /api/greeting` | `{"greeting": "Hello, World!"}`, read from `greeting.json` |

That is the whole surface. There is no page route and no static mount - the frontend
is a separate app - and no OpenAPI schema, `/docs` or `/redoc`; see
[Configuration](#configuration). `backend/tests/test_app.py` asserts that `/` and
`/static/*` return 404, so the coupling cannot come back by accident.

## CORS

`create_app()` adds `CORSMiddleware` with `allow_origins=["*"]`, because the SPA is
served from its own origin and every call it makes is therefore cross-origin.

`allow_credentials` is **`False`** and has to stay that way while the origin is a
wildcard: the CORS spec forbids the combination and browsers reject it. This API sends
no cookies and reads no `Authorization` header, so nothing is lost. When that changes,
replace the wildcard with a real origin list - not the other way round.

The middleware is registered *after* the security-headers middleware, which makes it
the outermost of the two; that is what lets it answer a preflight `OPTIONS` itself,
rather than passing it to a router that has no such route.

## Frontend

The frontend is a React 19 SPA built by vite, styled with Tailwind CSS v4 (configured
in CSS via `frontend/src/styles/app.css` - there is no `tailwind.config.js`).

`pixi run web-build` writes to `frontend/dist/`, vite's default. It is **gitignored**
and nothing in this repo consumes it - the backend ships no frontend assets, and
packaging the two together is out of scope. CI runs the build as a gate (tsc and
vitest never exercise the bundler), but keeps nothing from it.

`backend/src/expense_tracker/greeting.json` is the single source of truth for the
greeting, and only Python reads it: the backend serves it from `GET /api/greeting` and
the page fetches it at runtime with [TanStack Query](https://tanstack.com/query), in
`frontend/src/api/greeting.ts`. Nothing generates a client from a schema -
`create_app()` publishes no OpenAPI document - so the payload is written out by hand on
both sides and the two declarations must be changed together. Nothing checks that
agreement automatically now that the two build separately; a mismatch shows up as a
404 or a failed shape guard at runtime.

### Where the API lives

`frontend/.env` holds `VITE_API_BASE_URL`, and `frontend/src/api/greeting.ts` resolves
every request path against it. That one variable is the frontend's only knowledge of
the backend - there is deliberately no vite proxy, so the dev-time request is a real
cross-origin call and exercises the same CORS path a deployed one would. Override it
in `frontend/.env.local` (gitignored) to point at a backend elsewhere.

Two details worth knowing:

- It lives in bare `.env`, not `.env.development`, because vite loads `.env` in
  *every* mode - including the `test` mode vitest runs in, where MSW needs the same
  value to bind its handlers to.
- `frontend/vite.config.ts` pins `envDir` to `frontend/`. Without it, the `test`
  block's repo-root `root` would drag env-file lookup up there too and leave the
  suite with no base URL.

It is typed in `frontend/src/vite-env.d.ts`, which also sets
`ViteTypeOptions.strictImportMetaEnv` - that drops vite's `any` index signature on
`ImportMetaEnv`, so a mistyped `import.meta.env.VITE_*` is a type error rather than a
silent `undefined`.

The flip side of `.env` loading in every mode is that `pixi run web-build` **bakes
`http://localhost:8000` into the bundle**. That is fine today - the build exists as a
CI gate and nothing deploys it - but a real deployment needs the value supplied for
the production mode, via a `.env.production` or a `VITE_API_BASE_URL` set in the build
environment. vite inlines it at build time; there is no runtime lookup to override.

Tests reach into the app through the `@` alias (`@/api/greeting` rather than
`../../src/api/greeting`). It is declared twice - `resolve.alias` in
`frontend/vite.config.ts` for the bundler and `paths` in `frontend/tsconfig.app.json`
for the type checker, because vite does not read tsconfig `paths` - so both must point
at the same place. Imports *within* `src/` stay relative; the alias is there for
crossing into it from `tests/`.

Frontend tests use vitest and live in `frontend/tests/`. The backend is stubbed with
[MSW](https://mswjs.io); `frontend/tests/setup.ts` starts the server with
`onUnhandledRequest: "error"`, so a request no handler covers fails the test instead of
quietly reaching the network. That setting does real work here: handlers bind to the
absolute `GREETING_URL` exported by `frontend/src/api/greeting.ts`, because a
path-only pattern would resolve against jsdom's origin rather than the API's and never
match. A base-URL mismatch therefore fails a test rather than escaping to the network.
`frontend/src/main.tsx` is
excluded from coverage in both `frontend/vite.config.ts` and
`sonar-project.properties` - it only wires React to the DOM. Note that
`frontend/vite.config.ts` pins vitest's root back up to the repo root (`new
URL("../", import.meta.url)`) even though vite's own root is `frontend/`. That is what
makes the lcov report record repo-relative paths like `frontend/src/App.tsx`; without
it SonarCloud resolves them against the Python package and reports the frontend as
uncovered - silently, with a green build.

### Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml`
alongside Node. Three deliberate choices worth knowing:

- **There is no `packageManager` field in `frontend/package.json`, and there must not
  be.**
  pnpm's `pmOnFail` defaults to `download`, so that field would make pnpm fetch and
  run its own copy of the declared version, bypassing the pixi pin. `pixi.toml` is the
  single source of truth for the pnpm version.
- **Pins must be at least 24 hours old.** pnpm 11 refuses to install versions
  published in the last 24 hours (`minimumReleaseAge`, default 1440 minutes) as a
  supply-chain guard. Because this project pins exact versions, pnpm cannot silently
  fall back to an older release - it will instead ask you to exempt the version in a
  `pnpm-workspace.yaml`. **Prefer picking the newest release that already clears the
  window over adding an exemption**, which would disable the guard for precisely the
  freshest, least-vetted package. `frontend/pnpm-workspace.yaml` exists **only** to
  answer `allowBuilds` (below) and must not gain a `minimumReleaseAge` exemption.
- **Install scripts are answered explicitly.** pnpm 11 exits non-zero while a
  dependency's install script is neither allowed nor denied, which would fail
  `pixi run web-install` in CI. The decision lives in `frontend/pnpm-workspace.yaml`
  under `allowBuilds` - pnpm 11 stopped reading the `pnpm` field in `package.json`, so
  that file is the only place it can go. `msw` is denied there: its script only copies
  the browser service worker, and the tests use `msw/node`.

## Editor setup (Zed)

`.zed/settings.json` exists so Zed **reports** exactly what CI enforces. The two
stacks drift for different reasons, so they are fixed differently: the frontend
servers drift in **version**, basedpyright drifts in **config**.

**basedpyright needs no editor setting.** Its settings live in `pyrightconfig.json`
at the **repo root**, not in `backend/pyproject.toml`, because that is the only place a
language server looks: it searches its worktree root and does not descend into
subdirectories.

That location is what makes the settings *authoritative*. basedpyright ignores a
developer's own `typeCheckingMode` only when it finds a `pyrightconfig.json` or a
`pyproject.toml` with a `[tool.basedpyright]` section; with neither, **the editor's
settings win**. So while the config sat under `backend/`, anyone whose global Zed or VS
Code config set `recommended` got that instead of this repo's `strict` - a *different*
rule set rather than a smaller one, enabling `reportUnusedCallResult`, `reportAny`,
`reportImplicitOverride` and `failOnWarnings`. The editor flagged code CI is happy with,
and no amount of editor configuration could reconcile the two.

Zed's `basedpyright.analysis.configFilePath` looks like the fix and is not: a directory
is rejected outright (`Config file "..." could not be read`) and a file path is ignored.
A root config removes the need for any editor-specific setting, in Zed or anywhere else,
and holds regardless of what each contributor has set globally.

Two consequences worth knowing:

- **`pyrightconfig.json` takes precedence over `pyproject.toml`**, so
  `[tool.basedpyright]` was *removed* from `backend/pyproject.toml`. Putting it back
  would create dead config that still reads as live. ruff and pytest stay there - the
  type checker is the one tool an editor runs continuously against the whole worktree,
  which is what makes it the exception to each stack owning its own tooling.
- **`pixi run typecheck` is the only task with no `cwd`.** It runs from the repo root so
  that CI and the editor read the same file. Running it from `backend/` would find no
  config and silently fall back to `recommended`.

To confirm the editor and CI agree, flip `typeCheckingMode` to `recommended` and run
`pixi run typecheck`: the `reportUnusedCallResult` warning on
`response.headers.setdefault(...)` in `create_app()` reappears. Set it back to `strict`
and it clears.

**The frontend servers are pinned to `frontend/node_modules`.** Those paths
are relative to the worktree root, and the `vtsls` entry also spells out a `tsdk` -
Zed's implicit lookup only checks `<worktree>/node_modules/typescript/lib`, which does
not exist now that the frontend owns its dependencies. Zed would otherwise
install its own always-latest copies. Run `pixi run web-install` before opening the
project, or those paths do not exist yet and the language servers will not start.

**ESLint is pinned differently.** Zed's ESLint support is a built-in adapter that runs
Zed's own bundled `vscode-eslint` server, so there is no binary to repoint. What
matters is the `eslint` **module** that server loads at runtime, because that is what
supplies the rules, their severities and the version. `.zed/settings.json` therefore
sets `nodePath` to `frontend/node_modules` and `workingDirectories` to `["frontend"]`
instead of a `binary.path`. Without those, resolution can land on the worktree root -
which has no `node_modules` now that the frontend owns its dependencies, the same gap
that breaks Zed's implicit `typescript/lib` lookup - and the server silently falls back
to a globally installed eslint or reports nothing. The same `pixi run web-install`
precondition applies.

The file is deliberately minimal and does not enable `format_on_save` - that is left
to your own Zed settings. Formatting is applied by `pixi run web-format` and gated in
CI by `pixi run web-format-check`, the same way `ruff format` works on the Python
side. If you do turn `format_on_save` on, Zed picks up the pinned `prettier` from
`frontend/node_modules` rather than its bundled copy, so the result still matches CI -
but note
that combining it with an `autosave.after_delay` reformats continuously as you type.

### Verifying the pins

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`, `10.8.0`. One nested entry is expected and is
not drift: `@vtsls/language-server` bundles its own `typescript@5.9.3`, but the `tsdk`
setting in `.zed/settings.json` sends
`{"typescript": {"tsdk": "frontend/node_modules/typescript/lib"}}` as workspace
configuration, which redirects it to the pinned top-level copy.

To confirm Zed is actually using them, run this on the Linux side while Zed is open:

```sh
ps -eo pid,args | grep -E '[v]tsls|[t]ailwindcss-language-server|[e]slintServer'
```

Paths under this repo's `frontend/node_modules/` mean the pins took effect. Paths under
`~/.local/share/zed/` mean they did not - usually because `node_modules` is missing
(run `pixi run web-install`) or `node` is not on PATH for Zed's remote server.

`eslintServer.js` is the exception: it always runs from `~/.local/share/zed/`, because
that server is Zed's own and only the module it loads is pinned. To check that one, put
a deliberate error in a `.tsx` file - `const x: any = 1;` should raise
`@typescript-eslint/no-explicit-any`, and a `<li>` inside a `.map()` without a `key`
should raise `@eslint-react/no-missing-key`. A stray global eslint has neither this
config nor these plugins, so it would report nothing at all.

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
| `pixi run serve` | Run the API on uvicorn, port 8000 (with reloader) |
| `pixi run test` | Run the test suite with coverage |
| `pixi run lint` | Lint with ruff |
| `pixi run fix` | Auto-fix lint issues |
| `pixi run format` | Format with ruff |
| `pixi run format-check` | Check formatting without writing changes |
| `pixi run typecheck` | Type-check with basedpyright (strict) |
| `pixi run web-install` | Install frontend dependencies (`pnpm install --frozen-lockfile`) |
| `pixi run web-dev` | Run vite's dev server on port 5173 (hot reload) |
| `pixi run web-build` | Build the frontend into `frontend/dist/` |
| `pixi run web-check` | Type-check the frontend with tsc |
| `pixi run web-lint` | Lint the frontend with eslint (type-aware, `--max-warnings 0`) |
| `pixi run web-lint-fix` | Auto-fix frontend lint issues |
| `pixi run web-test` | Run the frontend tests (vitest) with coverage |
| `pixi run web-format` | Format the frontend with prettier |
| `pixi run web-format-check` | Check frontend formatting without writing changes |

Every task sets its own working directory in `pixi.toml` (`backend/` or `frontend/`),
so `pixi run <task>` behaves the same wherever you invoke it from. No task crosses
between the two directories.

CI runs `lint`, `format-check`, `typecheck`, `test`, `web-install`,
`web-format-check`, `web-check`, `web-lint`, `web-test`, and `web-build` on every pull
request, then the SonarCloud scan.

## Configuration

The backend has none: it reads no environment variables and no config files. Its only
input is `greeting.json`, which ships inside the wheel. (The frontend has exactly one,
`VITE_API_BASE_URL` - see [Where the API lives](#where-the-api-lives).)

FastAPI's OpenAPI schema and its `/docs` and `/redoc` UIs are switched off
in `create_app()` - one hand-written JSON route does not earn a generated document, and
the schema would be public surface advertising it. `backend/tests/test_app.py` asserts
they stay off.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit,
and squash-merge rules.
