---
paths:
  - "frontend/**"
---

# Frontend rules

Break one of these and CI goes red on an otherwise correct change.

- **The expenses table renders `amount` and `date` verbatim.** No `Intl.NumberFormat`,
  no `new Date()`. `amount` arrives as a string precisely so no float round trip can
  drift a total by a cent, and formatting it client-side would put that round trip back;
  `date` is a bare `YYYY-MM-DD`, which `new Date()` reads as UTC and prints a day early
  west of Greenwich. The wire contract both stacks declare is in `CLAUDE.md`, under the
  six things declared twice. `ExpensesTable.test.tsx`'s "shows an alert when an amount
  arrives as a number" pins this half - the shape guard in `src/api/expenses.ts` rejects
  a numeric amount rather than coercing it.
- **An empty list is a row, not an alert.** `ExpensesTable` renders `[]` as a row
  reading `No expenses loaded.` and reserves its `role="alert"` for a request that
  actually failed. That is the frontend half of an asymmetry the backend owns: a
  database nobody has run the loader against yet answers `200` with `[]`, which is a
  working server rather than a fault.
- **The API origin lives in bare `frontend/.env`, not `.env.development`.** vite loads
  `.env` in every mode, including the `test` mode vitest runs in, where MSW binds its
  handlers to the URL built from it. `vite.config.ts` also pins `envDir` to `frontend/`,
  because the `test` block moves vite's `root` to the repo root and `envDir` would
  otherwise follow it.
- **Routes are code-based, in `src/router.ts`.** No `routeTree.gen.ts` and no
  `@tanstack/router-plugin`: a generated route tree is a committed file that has to
  satisfy prettier, eslint's type-aware pass, a tsconfig that owns it and the coverage
  exclusions, and the plugin drags in `@babel/core`, `chokidar`, `zod` and `unplugin`
  to produce it. `createAppRouter` is a factory rather than a module-level singleton so
  the tests can hand it a `createMemoryHistory`, which is also what keeps `router.ts`
  covered without a new exclusion. The `declare module` block registering `Register` is
  what gives `Link` its typed `to`; without it a path matching no route compiles.
  **Only `App.tsx` imports `Link` or `Outlet`** - the pages under `src/pages/` are
  router-free, so each one's test mounts it in a bare `QueryClientProvider` and only
  `routing.test.tsx` builds a router.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's
  `include` fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` from
  `tsconfig.node.json`, where a new file at the `frontend/` root has to be added too.
  Same reason `eslint.config.ts` opens with `globalIgnores(["dist"])`.
- **`package.json` must not gain a `packageManager` field**, and `pnpm-lock.yaml` must
  stay at `lockfileVersion: 9.0`. The first bypasses the pnpm pin in `pixi.toml`; both
  break Dependabot's lockfile parsing. That lockfile version is also what Dependabot
  reads its pnpm major from, which is why the next rule exists. See
  [`README.md`](../../README.md#package-manager).
- **`pnpm-workspace.yaml` states `minimumReleaseAge: 1440` and must never gain a
  `minimumReleaseAgeExclude`.** Stating the value and excusing a package from it are
  opposites: 1440 is already pnpm 11's default, written down because Dependabot resolves
  this lockfile with pnpm 10 (per the `lockfileVersion: 9.0` pin above), where the
  default is 0 - so without it the 24-hour guard covers CI's *verification* but not
  Dependabot's *resolution*. An exclusion, by contrast, disables the guard for the
  least-vetted release there is; pick a version that already clears the window. Naming
  the value also turns on `minimumReleaseAgeStrict`, which is intended. The file's two
  settings are the whole of it - the other is `allowBuilds`.

## Quality gates

- `tsc -b` against a `strict` tsconfig, prettier, and eslint 10 in `eslint.config.ts`.
  `eslint-config-prettier` is applied last, so **the linter owns correctness and
  prettier owns formatting** - never add a formatting rule to the eslint config.
- **There is no warn tier.** The `lint` script passes `--max-warnings 0`, so a warning
  fails the build like an error. Without it a large share of the rule set would be
  advisory, including the XSS, `target="_blank"` and leaked-timer rules,
  `exhaustive-deps`, and `reportUnusedDisableDirectives`. Demote a rule deliberately in
  its config if you disagree with it; do not let the flag go.
