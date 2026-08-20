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
- **A `Date` is never built from a string and never named through UTC.** The picker deals
  in `Date` objects and the API deals in bare `YYYY-MM-DD`, so `src/dates.ts` is the one
  place either crosses over, and it is built from `getFullYear`/`getMonth`/`getDate` and
  `new Date(y, m - 1, d)`. **`toISOString()` and `new Date("2026-08-01")` appear nowhere
  in `src/`** - the first converts to UTC before naming the day, the second is parsed as
  UTC, and each is off by one for half the world. It is the same fault the rule above
  names, in the write direction. `date-fns` arrives as a transitive dependency of
  react-day-picker and is deliberately not imported: a second formatter is a second place
  for this rule to drift. Pinned by `dates.test.ts`, which is why
  `frontend/vite.config.ts` sets `env: { TZ: "Europe/Copenhagen" }` on the suite - under a
  UTC runner, which is what CI is, local and UTC agree and the test proves nothing.
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
- **The calendar is themed through its own variables, not through utility classes.**
  `@daypicker/react/style.css` is imported from `src/main.tsx` and is **unlayered**, while
  everything `@import "tailwindcss"` emits sits inside `@layer`; unlayered rules win
  regardless of source order, so a Tailwind or daisyUI class aimed at the calendar through
  `classNames` loses silently. Its five colours are reachable only as custom properties,
  and the `.rdp-root` block at the foot of `src/styles/app.css` repoints them at daisyUI's
  role tokens. That block is unlayered for the same reason and has to stay after the
  package stylesheet in the bundle, which is what the import order in `main.tsx` is for.
  Those names are the package's own and nothing checks them, so the pair is listed under
  "Declared twice" in the root [`CLAUDE.md`](../CLAUDE.md).
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
  the backend and not a request for no conversion. `?from_date=` and `?to_date=` follow
  every word of that: `yesterday`, an empty string, and a `from_date` after its `to_date`
  are each handed on and answered with the 422 `date_range.py` raises. `validateSearch`
  does not sort the two bounds, clamp them or compare them. The one thing it adds is the
  default - an absent bound becomes the first or last day of the current month - and that
  is the only default here that is not a constant, which is why `dates.test.ts` and
  `ExpensesPage.test.tsx` pin the clock.
- **The currency options are what the rate table can reach, not a list of ISO codes.**
  `targetCurrencies` in `src/api/currencies.ts` keeps only the `to_currency` of a pair whose
  `from_currency` is `BASE_CURRENCY`, because a rate is never inverted and never composed -
  a `SEK -> DKK` row makes `DKK` no more reachable from `SEK` than no row at all.
  `BASE_CURRENCY` itself is always offered and needs no rate, since the backend returns a
  record whose currency already equals the target before any lookup. A rate list that is
  pending, 503s, empty or malformed leaves the select disabled at `BASE_CURRENCY` and **does
  not disturb the expenses table**: they are two requests, and an empty rate table is a
  legitimate `200` for the reason an empty ledger is.
- **The date range is always bounded, and every `navigate` carries the whole search.**
  There is no clear button and no unbounded mode; the range is widened by picking earlier
  or later days. `DateRangePicker` holds a half-picked range in local state and reports
  nothing until both ends are set, because an empty bound is a malformed date to the
  backend rather than a request for everything - the same rule as the absent "as recorded"
  currency mode above. Because `validateSearch` re-defaults an **absent** parameter, a
  `navigate` that omitted `from_date` would silently reset the range to the current month
  instead of leaving it alone, so both handlers in `ExpensesPage` spread the whole search
  and override one part of it. Pinned by "picking a currency keeps the range and asks
  again" and its twin.
- **An inverted range is unreachable through the UI, and nothing guards against one.**
  react-day-picker's `addToRange` orders the pair itself - a click before the start
  becomes the new start - so `from > to` cannot be produced by any sequence of clicks, and
  a comparison here would be a second copy of a rule `date_range.py` already owns. Pinned
  by "cannot be made to report a range that runs backwards".
- **Two `DayPicker` instances, not one with `numberOfMonths={2}`.** That prop keeps the
  pair consecutive and moves them as a unit, so the left could not sit on 2025 while the
  right showed 2026. Each instance instead holds its own `month` and `onMonthChange`, and
  the two share `selected` and `onSelect` - which is what lets a range start in either
  panel and end in the other. The panel a dropdown moves wins, and the other follows only
  far enough to stay in order, so they can land on the same month but never cross. Opening
  recomputes both from the props, putting one panel on each end of the range; a range
  inside a single month puts the right panel on the month after. The arrows are hidden
  (`hideNavigation`) because the dropdowns do the whole job.
- **The calendar's own bounds are invented, and deliberately so.** `startMonth` is
  1 January of `FIRST_YEAR` in `src/dates.ts` and `endMonth` is 31 December of the current
  year. No endpoint publishes the ledger's span, so neither bound is derived from
  anything - they exist because `captionLayout="dropdown"` has to list a finite set of
  years, and with the arrows hidden that list is the whole of what bounds navigation.
  That is a real cost: an
  expense dated before `FIRST_YEAR` is unreachable from the calendar, though a URL naming
  it is still honoured, because `validateSearch` passes dates through untouched and the
  trigger shows whatever it was given. Raising the floor is a one-constant edit; deriving
  it honestly would mean a new backend read and a new payload.
- **The range control is a `<button aria-expanded>` and a conditional render**, not
  daisyUI's `popover` or `<details>` dropdown, and the panel is positioned with plain
  utilities rather than `dropdown`/`dropdown-content`. jsdom 30 implements no Popover API,
  and `@testing-library/dom` gives `<summary>` no role, so both daisyUI recipes are
  unreachable by `getByRole` - the same constraint that chose react-day-picker over
  cally's shadow root in the first place. With a conditional render `queryByRole("grid")`
  is genuinely `null` when the calendar is closed. It closes on an outside click and on
  Escape, both from listeners on `document` rather than a handler on the panel, because
  a `keydown` on a non-interactive `<div>` is sonar S6847; Escape also hands focus back
  to the trigger. Either dismissal **discards a half-picked range**: the URL still holds
  the range that was there, and a calendar disagreeing with the trigger is worse than
  losing one click. `dropdown-content` is ruled out for a
  second reason worth knowing: it keeps itself hidden until `:focus-within` or
  `:popover-open`, so a panel whose open state is React's disappears the moment focus
  leaves it while still mounted. **jsdom evaluates no CSS, so the suite passes either
  way** - that one was found by opening the page, and it is what the by-eye check in the
  gate sequence is for. The trigger is named by
  `aria-labelledby` over the visible `Dates` caption **and its own id**, because
  `<label htmlFor>` does not name a `<button>` and a bare `aria-label` would replace the
  range the button displays instead of prefixing it.

## Environment and tooling

- **The API origin lives in bare `.env`, not `.env.development`.** vite loads `.env` in
  every mode, including the `test` mode vitest runs in, where MSW binds its handlers to the
  URL built from it. `vite.config.ts` also pins `envDir` to `frontend/`, because the `test`
  block moves vite's `root` to the repo root and `envDir` would otherwise follow it.
- **The suite runs at a fixed, non-zero offset from UTC.** `frontend/vite.config.ts` sets
  `env: { TZ: "Europe/Copenhagen" }` in its `test` block. `dates.test.ts` proves a day is
  named from the local getters rather than through `toISOString()`, and on a UTC runner -
  which is what CI is - the two agree and the assertion passes on a broken implementation.
  Pinning the zone is what gives that test teeth; it is not a preference about where the
  developers sit.
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
