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
- **The calendar is themed by daisyUI, and `@daypicker/react/style.css` is deliberately
  not imported.** daisyUI ships a first-party theme for this library - the
  `react-day-picker` class, which both `DayPicker` instances in `DateRangePicker.tsx`
  carry - and it writes every part in role tokens, so the calendar follows nord and dim
  like everything else. **Importing the package's own stylesheet would silently beat it**:
  that file is unlayered, everything `@import "tailwindcss"` emits sits inside `@layer`,
  and unlayered rules win regardless of source order. It is also what made the calendar
  look nothing like the rest of the page, because it hardcodes `font-size: large` on the
  month caption and on selected days - so a day grew when it was picked - and neither is
  reachable through a `--rdp-*` variable. **Nothing local names a `--rdp-*` property any
  more; the class name is the whole contract.** Only `frontend-build` proves the theme is
  in the bundle: daisyUI registers it through `addComponents`, so it is emitted solely
  because a source file `@source "../"` scans names the class. A `grep` for
  `react-day-picker` in `frontend/dist/assets/*.css` is that check, and jsdom evaluates no
  CSS, so no test is.
- **`src/styles/app.css` holds exactly one local rule, and it is unlayered on purpose.**
  daisyUI gives `.input` and `.select` no hover state - only `.btn` has one - which is half
  of why the two filters above the table used to read as different kinds of control. The
  rule deepens `--input-color` on hover for both; unlayered is what lets it reach that
  variable past daisyUI's own layer, `:not(:focus-within)` is what keeps a hovered
  *focused* field on its focus treatment instead of weakening it, and the
  `@media (hover: hover)` around it is what stops a touch device holding the state after a
  tap. **Reach for a utility class before a second rule here**: a daisyUI role token used
  in an ordinary CSS property fails `css/no-invalid-properties`, because eslint cannot see
  what the Tailwind build injects, and the rule must not be relaxed to let one through.
  This rule passes only because it assigns to a custom property, which is not validated.
- **`dayPickerClassNames` carries two fixes for daisyUI's calendar theme, and both are
  handed to the panels rather than written as CSS.** That is deliberate: a daisyUI role
  token used in an ordinary CSS property fails `css/no-invalid-properties`, so a utility
  class is the way to reach one from here.
  - **No day is marked "today".** `today` is emptied, and `getClassNamesForModifiers`
    keeps only truthy entries, so the day never carries `rdp-today`. Without that daisyUI
    fills it with the primary colour through a selector of four classes against
    `.rdp-selected`'s three - it beats the range it sits inside, and the current day reads
    as picked whatever the range is. **The control reports a from date and a to date; a
    third marked day is a third thing to explain.**
  - **The month and year dropdowns are given a background.** They are real `<select>`s
    that daisyUI leaves transparent, because they sit invisible over the caption and only
    the caption is meant to show. A browser paints the *native popup* from the control's
    own colours, so a transparent one comes up on white while still taking the inherited
    text colour - pale on pale, and unreadable under dim. `bg-base-100 text-base-content`
    fixes it, and `[&>option]:bg-base-100` is not redundant: the select's colour does not
    reach its options in every browser. Note this is not a `color-scheme` fault - that
    resolves correctly to `dark` on the element, and the scrollbars prove it.
- **Both filters are one control wearing two faces, and `FilterField` is what keeps them
  that way.** The date range trigger is a daisyUI `input` and the currency picker a
  `select`; they are the same height, border, fill, radius and focus treatment because they
  are the same kind of daisyUI component, and neither is a `btn`.
  `src/components/FilterField.tsx` owns the shell and the caption for both, which is what
  stops the pair drifting apart again. Its props are a union rather than two optionals
  **because the two cannot be named the same way**: a `<select>` takes a real
  `<label htmlFor>` and a `<button>` cannot, so the trigger gets `labelId` and a
  `<span id>` instead. That also means `DateRangePicker`'s `containerRef` sits on its own
  positioning `div` and not on the shell - a click on the caption is outside the control
  and dismisses the panel.
- **Every colour is referenced by role** - `bg-base-100`, `bg-base-200`,
  `text-base-content`, `alert-error` - because a hard-coded shade like `slate-700` is not
  merely awkward with two themes, it is wrong in one of them. jsdom evaluates no CSS, so no
  test covers either half; both are checked by eye, and Chromium's `prefers-color-scheme`
  emulation under *Rendering* is how you reach the one your OS is not set to.

## Routing and layering

- **Routes are file-based: a route is declared by where its file sits in `src/routes/`.**
  `index.tsx` is `/`, `__root.tsx` is the layout. `@tanstack/router-plugin`, configured
  inline in `vite.config.ts` and nowhere else - **there is no `tsr.config.json`** - reads
  that directory and writes `src/routeTree.gen.ts`. `src/router.ts` keeps only
  `createAppRouter` over the generated tree: a factory rather than a module-level
  singleton so the tests can hand it a `createMemoryHistory`, which is also what keeps
  `router.ts` covered without a new exclusion. The `declare module` block registering
  `Register` is what gives `Link` a typed `to`; without it a path matching no route
  compiles.
- **`src/routeTree.gen.ts` is committed and never hand-edited.** It is runtime source,
  not a build artifact - every frontend gate except `frontend-build` reads it and none of
  them can produce it, so a fresh checkout without it fails `tsc` outright. **Two
  independent checks keep it in step, and they catch different things.** Adding a route
  file is caught by `frontend-typecheck`: `createFileRoute("/new")` is not assignable
  until the tree names `/new`, which also means `pnpm run build` (`tsc -b && vite build`)
  cannot regenerate after adding one - run `pnpm exec vite build` to bootstrap. A rename,
  a deletion or a changed path typechecks fine against a stale tree, and is caught
  instead by the `git diff --exit-code` step in `.github/workflows/ci.yml`, placed after
  `frontend-build` because that is the only gate that runs vite. Neither check is a pixi
  task; adding one would have meant a command body in two manifests for no gain.
- **The generated tree is excluded from prettier, coverage and Sonar** -
  `.prettierignore`, `coverage.exclude` in `vite.config.ts` and `sonar.exclusions` in
  `sonar-project.properties`, listed under "Declared twice" in the root
  [`CLAUDE.md`](../CLAUDE.md) because nothing checks the three agree. **eslint is
  deliberately not a fourth, and `globalIgnores` must not gain it.** The file opens with
  its own blanket `/* eslint-disable */`, which is what the generator's header intends
  and is enough; an ignore *pattern* additionally makes eslint answer "File ignored
  because of a matching ignore pattern" whenever it is handed the file directly, which is
  exactly what an editor does when you open it. `--no-warn-ignored` on the `lint` script
  cannot reach that - the editor's language server runs its own eslint - so the config is
  the only place it can be fixed. The directive is never reported as unused either,
  because the `as any` casts under it would genuinely fire rules. **The prettier exclusion is not a preference.** `router-generator` formats by
  calling `prettier.format(source, {...})` with explicit options only; it never resolves
  `.prettierrc.json`, so the file lands at prettier's default `printWidth` 80 against this
  repo's 88 and could not pass `--check` however it were configured. `quoteStyle` and
  `semicolons` are set on the plugin for the same reason - they are the only thing that
  can bring the file in line with the rest of the repo. The upside of that same fact:
  output depends on nothing but the generator version, so the CI diff is stable across
  machines rather than a formatting race.
- **`react-refresh/only-export-components` is off for `src/routes/**`, and that is not a
  demotion.** A route file exports `Route = createFileRoute(...)({...})` beside a
  component it does not export, which is exactly the shape the rule rejects - but
  `autoCodeSplitting` moves the component into a separate `?tsr-split` module, so the file
  eslint reads is not the module the browser gets and the router plugin owns the refresh
  boundary. Narrowing the rule does not work and was tried: `allowExportNames: ["Route"]`
  makes the export *skipped* rather than counted, so the file is then reported for holding
  a local component and no exported one. This is the only rule switched off anywhere in
  the config.
- **Only `src/routes/__root.tsx` imports `Outlet`, and nothing imports `Link`** - it is the
  layout shell and no more, because a nav over a single route would be dead UI.
- **`src/components/` is the router-free layer, not `src/routes/`.** The route owns its
  search schema and its component reads it, and under file-based routing **they are the
  same module**: `routes/index.tsx` holds `validateSearch` and the page together and reads
  the URL through **`Route.useSearch()`**. There is no `getRouteApi` and no `src/pages/` -
  both existed to break a cycle (`router.ts` imported the page) that a route file owning
  its own component does not have. Its test builds a `createMemoryHistory` router the way
  `routing.test.tsx` does. Everything under `src/components/` takes props and knows no
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

- **`autoCodeSplitting` is on**, so the one route's component is emitted as its own chunk
  and arrives through a `?tsr-split` module rather than from the route file directly.
  That is what makes the eslint rule above inapplicable rather than merely inconvenient.
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
- **`pnpm-workspace.yaml` states `minimumReleaseAge: 4320` and must never gain a
  `minimumReleaseAgeExclude`.** The value mirrors `cooldown.default-days` in
  [`.github/dependabot.yml`](../.github/dependabot.yml) and has to keep mirroring it:
  Dependabot enforces the higher of the two across its whole resolution, so a gap in
  either direction fails the weekly update job outright rather than skipping an update.
  Stating the value also matters because Dependabot resolves this lockfile with pnpm 10
  (per the `lockfileVersion: 9.0` pin above), where the default is 0 - so without it the
  guard covers CI's *verification* but not Dependabot's *resolution*. An exclusion, by
  contrast, disables the guard for the least-vetted release there is; pick a version that
  already clears the window. Naming the value also turns on `minimumReleaseAgeStrict`,
  which is intended. The file's two settings are the whole of it - the other is
  `allowBuilds`.

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
