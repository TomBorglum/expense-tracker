# frontend/CLAUDE.md

Invariants for the frontend stack. Repo-wide rules - branching, ASCII-only, version
pinning, the command layers and the gate sequence - are in the root
[`CLAUDE.md`](../CLAUDE.md).

Break one of these and CI goes red on an otherwise correct change.

## Rendering

- **The expenses table renders `amount` and `date` verbatim.** No `Intl.NumberFormat`, no
  `new Date()`. The backend sends `amount` as `str(Decimal)` precisely so no float round
  trip can drift a total by a cent, and formatting it client-side would put that round trip
  back; `date` is a bare `YYYY-MM-DD`, which `new Date()` reads as UTC and prints a day
  early west of Greenwich. The shape guard in `src/api/expenses.ts` rejects a numeric
  amount rather than coercing it, pinned by `ExpensesTable.test.tsx`'s "shows an alert when
  an amount arrives as a number"; the backend half is pinned by
  `test_expense_amounts_are_strings_not_numbers`.
- **An empty list is a row, not an alert.** `ExpensesTable` renders `[]` as a row reading
  `No expenses loaded.` and reserves its `role="alert"` for a request that actually failed.
  That is this side of the backend's "an empty table is 200, not 503"; see
  [`backend/CLAUDE.md`](../backend/CLAUDE.md).
- **The theme follows the OS, and nothing can override it.** daisyUI is enabled by the
  single `@plugin "daisyui"` block in `src/styles/app.css`, naming two themes:
  `nord --default`, bound at `:where(:root)`, and `dim --prefersdark`, bound at
  `:root:not([data-theme])` inside `@media (prefers-color-scheme: dark)`. There is no
  `data-theme` attribute, no theme provider, no `@custom-variant dark`, and no `dark:`
  variant anywhere in `src/` - the pair is the whole mechanism, and a user-facing toggle
  would be a feature on top of it, not a config change. A theme paints nothing on its own,
  so the surface is `bg-base-200 text-base-content` on `<body>` in `index.html`: a body
  background is what propagates to the canvas beyond the app shell, and moving it onto a
  `<div>` is what leaves an unpainted band below short content.
- **Every colour is referenced by role** - `bg-base-100`, `bg-base-200`,
  `text-base-content`, `alert-error` - because a hard-coded shade like `slate-700` is not
  merely awkward with two themes, it is wrong in one of them. jsdom evaluates no CSS, so no
  test covers either half; both are checked by eye, and Chromium's `prefers-color-scheme`
  emulation under *Rendering* is how you reach the one your OS is not set to.

## Routing and layering

- **The one route is code-based, in `src/router.ts`.** No `routeTree.gen.ts` and no
  `@tanstack/router-plugin`: a generated route tree is a committed file that has to satisfy
  prettier, eslint's type-aware pass, a tsconfig that owns it and the coverage exclusions,
  and the plugin drags in `@babel/core`, `chokidar`, `zod` and `unplugin` to produce it.
  `createAppRouter` is a factory rather than a module-level singleton so the tests can hand
  it a `createMemoryHistory`, which is also what keeps `router.ts` covered without a new
  exclusion. The `declare module` block registering `Register` is what gives `Link` a typed
  `to`; without it a path matching no route compiles.
- **Only `App.tsx` imports `Outlet`, and nothing imports `Link`** - it is the layout shell
  and no more, because a nav over a single route would be dead UI.
- **`src/components/` is the router-free layer, not `src/pages/`.** The route owns its
  search schema and its component reads it, so `ExpensesPage` calls `useSearch` and
  `useNavigate` and its test builds a `createMemoryHistory` router the way
  `routing.test.tsx` does. It reaches the route through **`getRouteApi("/")`, never by
  importing `expensesRoute`** - `router.ts` imports the page, so the reverse import is a
  cycle; `getRouteApi` takes a path string, adds no import edge, and stays typed through the
  `declare module` block. Everything under `src/components/` takes props and knows no
  router, which is what keeps `ExpensesTable` and `CurrencySelect` mountable in a bare
  `QueryClientProvider`. Reading the URL from a component instead is what this splits to
  prevent: it would couple a leaf to a route path and put a `RouterProvider` in every test
  that renders it.
- **`validateSearch` fills in an absent parameter and validates nothing else.**
  `?currency=` is handed to the backend as typed, so `/?currency=euro` gets the 422 that
  `conversion.py` raises rather than being corrected or rejected here - re-checking
  `\A[A-Z]{3}\Z` in the frontend would put that pattern in a second place to drift from,
  and the frontend reads no `detail` out of an error body, so the failure surfaces as the
  table's ordinary alert. `CurrencySelect` still shows such a code as its value: a
  `<select>` whose value matches no option displays the first one instead, which would
  disagree with both the URL and the request in flight. There is no "as recorded" mode -
  the parameter is always sent, because an **empty** `?currency=` is a malformed code to
  the backend and not a request for no conversion.
- **The currency options are what the rate table can reach, not a list of ISO codes.**
  `targetCurrencies` in `src/api/currencies.ts` keeps only the `to_currency` of a pair whose
  `from_currency` is `BASE_CURRENCY`, because a rate is never inverted and never composed -
  a `SEK -> DKK` row makes `DKK` no more reachable from `SEK` than no row at all.
  `BASE_CURRENCY` itself is always offered and needs no rate, since the backend returns a
  record whose currency already equals the target before any lookup. A rate list that is
  pending, 503s, empty or malformed leaves the select disabled at `BASE_CURRENCY` and **does
  not disturb the expenses table**: they are two requests, and an empty rate table is a
  legitimate `200` for the reason an empty ledger is.

## Environment and tooling

- **The API origin lives in bare `.env`, not `.env.development`.** vite loads `.env` in
  every mode, including the `test` mode vitest runs in, where MSW binds its handlers to the
  URL built from it. `vite.config.ts` also pins `envDir` to `frontend/`, because the `test`
  block moves vite's `root` to the repo root and `envDir` would otherwise follow it.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's `include`
  fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`; `vite.config.ts` and `eslint.config.ts` from `tsconfig.node.json`,
  where a new file at the `frontend/` root has to be added too. Same reason
  `eslint.config.ts` opens with `globalIgnores(["dist"])`.
- **`package.json` must not gain a `packageManager` field**, and `pnpm-lock.yaml` must stay
  at `lockfileVersion: 9.0`. The first bypasses the pnpm pin in `pixi.toml`; both break
  Dependabot's lockfile parsing. That lockfile version is also what Dependabot reads its
  pnpm major from, which is why the next rule exists. See
  [`README.md`](../README.md#package-manager).
- **`pnpm-workspace.yaml` states `minimumReleaseAge: 1440` and must never gain a
  `minimumReleaseAgeExclude`.** Stating the value and excusing a package from it are
  opposites: 1440 is already pnpm 11's default, written down because Dependabot resolves
  this lockfile with pnpm 10 (per the `lockfileVersion: 9.0` pin above), where the default
  is 0 - so without it the 24-hour guard covers CI's *verification* but not Dependabot's
  *resolution*. An exclusion, by contrast, disables the guard for the least-vetted release
  there is; pick a version that already clears the window. Naming the value also turns on
  `minimumReleaseAgeStrict`, which is intended. The file's two settings are the whole of it
  - the other is `allowBuilds`.

## Quality gates

- **`tsc -b` against a `strict` tsconfig, prettier, and eslint 10** in `eslint.config.ts`.
  `eslint-config-prettier` is applied last, so **the linter owns correctness and prettier
  owns formatting** - never add a formatting rule to the eslint config.
- **CSS is linted by eslint too, not by a second tool.** `@eslint/css` adds a `**/*.css`
  block to the same config and rides the same `frontend-lint` task, so there is no
  stylelint, no third manifest layer and no new pixi task. The block carries no rule
  suppressions, and Tailwind's syntax is **not** hand-written here: it comes from
  `tailwind-csstree`'s `tailwind4`, the extension `@eslint/css` points at for this, so a
  Tailwind at-rule this repo starts using needs no config change. Nothing is exempted -
  `@sourse` and a misspelled `@plugin` descriptor both still fail. Two things in that block
  are load-bearing and neither is a preference:
  - **The `@plugin` `descriptors` override is the one local addition.** daisyUI's `@plugin`
    takes a block; core Tailwind's does not, so `tailwind4` gives it no descriptors and
    css-tree then rejects *every* declaration inside one. It is one of the pairs listed
    under "Declared twice" in the root [`CLAUDE.md`](../CLAUDE.md). Drop it once
    [tailwind-csstree#63](https://github.com/humanwhocodes/tailwind-csstree/issues/63)
    lands.
  - **`tolerant: true` stays**, for a subtler reason than an unparseable file. `tailwind4`
    reads `source(none)` by trying `<string>` and falling back to `<ident>`, and css-tree
    reports that recovered first attempt through `onParseError` regardless; `@eslint/css`
    promotes every such call to a fatal parse error unless it is tolerating them. The
    prelude itself parses correctly, which is what lets `css/no-duplicate-imports` read it -
    under the old hand-written map it threw on a `Raw` prelude and had to be switched off.
    The cost is that unbalanced braces go unreported, because that check is skipped under
    `tolerant` too.
- **There is no warn tier.** The `lint` script passes `--max-warnings 0`; a warning fails
  the build like an error. Without it roughly 45 rules would be advisory, including the XSS,
  `target="_blank"` and leaked-timer rules, `exhaustive-deps`, and
  `reportUnusedDisableDirectives`. Demote a rule deliberately in its config if you disagree
  with it; do not let the flag go.
