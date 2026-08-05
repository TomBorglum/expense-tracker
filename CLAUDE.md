# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Branch and merge rules

The rationale is in [`CONTRIBUTING.md`](CONTRIBUTING.md). This repo is on the GitHub
free plan, so none of this is enforced by GitHub - follow it as if it were.

- **Never push directly to `main`.** Every change goes on a branch, through a PR.
- **The PR title must be a valid Conventional Commit.** It becomes the squashed commit
  subject that release-please parses.
- **Squash-merge only**, keeping `main` linear. The one merge-commit exception is
  documented in `CONTRIBUTING.md`.
- **Before merging:** the `SonarCloud Code Analysis` check passes and every review
  thread is resolved.
- **Merge with `gh pr merge --squash --delete-branch`.**
- **Branch naming:** `<type>/<short-kebab-description>`, e.g. `feat/monthly-report`.

## Releases

Automated by release-please (`.github/workflows/release-please.yml`). **Never
hand-edit versions, git tags, or `CHANGELOG.md`.**

## Source conventions

- **ASCII-only** committed source: no em-dashes, smart quotes, arrows, ellipses.
- **Pin versions exactly** - `==` in `pixi.toml`, bare versions in
  `frontend/package.json`, GitHub Actions by SHA with a version comment.
- **Every suppression carries a reason** beside the pragma: a comment next to
  `# pyright: ignore[...]` (see `backend/src/expense_tracker/__init__.py`), or on/above
  an `// eslint-disable-next-line <rule>`. A bare disable is not acceptable.

## Commands

**Each stack owns its commands, in the manifest that already owns how its tools
behave.** The backend's are poe tasks in `backend/pyproject.toml`; the frontend's are
the `scripts` block in `frontend/package.json`. `pixi.toml` declares **no** tasks - it
provides the environment, and a forwarding task there would only add a name to look up.
Add a new command to the stack that runs it, never to `pixi.toml`.

Both runners take `-C`, so everything runs from the repo root with no `cd`, and `-C`
also sets the working directory:

```sh
poe -C backend <task>          # poe -C backend with no task lists them
pnpm -C frontend run <script>  # pnpm -C frontend run lists them
```

Full table in [`README.md`](README.md#development-tasks).

Before opening a PR, run the gate sequence from `.github/workflows/ci.yml`, in order
(cheapest first, so it fails fast):

```sh
poe -C backend lint && poe -C backend format-check && poe -C backend typecheck &&
poe -C backend test && pnpm -C frontend install --frozen-lockfile &&
pnpm -C frontend run format-check && pnpm -C frontend run check &&
pnpm -C frontend run lint && pnpm -C frontend run test && pnpm -C frontend run build
```

The two halves are independent, so a change to one stack can only fail that stack's
gates.

## Build invariants

Break one of these and CI goes red on an otherwise correct change.

- **The backend serves no frontend.** It is a REST API whose whole surface is
  `GET /api/greeting`: no `/` route, no `StaticFiles` mount, no build artifact under
  `backend/`. Pinned by `test_root_is_not_served`,
  `test_static_files_are_not_served` and `test_unknown_api_routes_404`.
- **No OpenAPI.** `docs_url`, `redoc_url` and `openapi_url` stay `None` in
  `create_app()`. Pinned by `test_openapi_docs_are_disabled`.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so
  the day the API grows cookies or an `Authorization` header the wildcard is what has
  to become a real origin list. Pinned by `test_cors_does_not_allow_credentials`. It
  is registered after the security-headers middleware, which makes it outermost and
  lets it answer preflights itself.
- **Four things are declared twice. Change both halves together:**
  - the greeting payload - `backend/src/expense_tracker/__init__.py` and
    `frontend/src/api/greeting.ts`, with nothing checking the agreement;
  - the `@` alias (`frontend/src`) - `frontend/vite.config.ts` and
    `frontend/tsconfig.app.json`, because vite does not read tsconfig `paths`;
  - the `frontend/src/main.tsx` coverage exclusion - `frontend/vite.config.ts` and
    `sonar-project.properties`;
  - `VITE_API_BASE_URL` - set in `frontend/.env`, typed in
    `frontend/src/vite-env.d.ts`.
- **The API origin lives in bare `frontend/.env`, not `.env.development`.** vite loads
  `.env` in every mode, including the `test` mode vitest runs in, where MSW binds its
  handlers to the URL built from it. `frontend/vite.config.ts` also pins `envDir` to
  `frontend/`, because the `test` block moves vite's `root` to the repo root and
  `envDir` would otherwise follow it.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` from
  `tsconfig.node.json`, where a new file at the `frontend/` root has to be added too.
  Same reason `frontend/eslint.config.ts` opens with `globalIgnores(["dist"])`.
- **`frontend/package.json` must not gain a `packageManager` field**, and
  `frontend/pnpm-lock.yaml` must stay at `lockfileVersion: 9.0`. The first bypasses the
  pnpm pin in `pixi.toml`; both break Dependabot's lockfile parsing. See
  [`README.md`](README.md#package-manager).
- **`frontend/pnpm-workspace.yaml` must not gain a `minimumReleaseAge` exemption.** It
  exists only to answer `allowBuilds`. Exempting a version disables the 24-hour
  supply-chain guard for the least-vetted release there is; pick a version that already
  clears the window.

## Quality gates

- **Python:** basedpyright in `recommended` mode and ruff with
  `select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]`, both in
  `backend/pyproject.toml`. There is no config file at the repo root and no Python
  setting duplicated in the editor config.
- **Frontend:** `tsc -b` against a `strict` tsconfig, prettier, and eslint 10 in
  `frontend/eslint.config.ts`. `eslint-config-prettier` is applied last, so **the
  linter owns correctness and prettier owns formatting** - never add a formatting rule
  to the eslint config.
- **Neither stack has a warn tier.** `recommended` sets `failOnWarnings`, and the
  frontend `lint` script passes `--max-warnings 0`; a warning fails the build like an
  error. Without them roughly 45 frontend rules would be advisory, including the XSS,
  `target="_blank"` and leaked-timer rules, `exhaustive-deps`, and
  `reportUnusedDisableDirectives`. Demote a rule deliberately in its config if you
  disagree with it; do not let either flag go.
