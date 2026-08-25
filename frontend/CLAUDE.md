# frontend/CLAUDE.md

Invariants for the frontend stack. Repo-wide rules and [what earns a place
here](../CLAUDE.md#adding-to-these-files) are in the root [`CLAUDE.md`](../CLAUDE.md).
**This file stays under 200 lines.** Break one of these and either CI goes red, or nothing
does; each bullet says which. jsdom evaluates no CSS, so appearance rules are by-eye by
construction.

## Rendering

- **The expenses table renders `amount` and `date` verbatim.** No `Intl.NumberFormat`, no
  `new Date()`. The backend sends `amount` as `str(Decimal)` so no float round trip can
  drift a total by a cent, and `date` as a bare `YYYY-MM-DD`, which `new Date()` reads as
  UTC and prints a day early west of Greenwich. The guard in `src/api/expenses.ts` rejects
  a numeric amount. Pinned by "shows an alert when an amount arrives as a number".
- **A `Date` is never built from a string and never named through UTC.** The picker deals
  in `Date` objects and the API in bare `YYYY-MM-DD`, so `src/dates.ts` is the one crossing
  point, built from `getFullYear`/`getMonth`/`getDate`. **No code in `src/` calls
  `toISOString()` or parses a date string** - each is off by one for half the world.
  `date-fns` arrives transitively and is deliberately not imported: a second formatter is a
  second place to drift. Pinned by `dates.test.ts`, which needs the fixed
  **`TZ: "Europe/Copenhagen"`** in `vite.config.ts`'s `test` block: on a UTC runner, which
  is what CI is, local and UTC agree and the assertion passes on a broken implementation.
- **The type scale is three sizes at two weights, and 0.875rem is the body of it.**
  `text-xl` is the app title, `text-2xl` the page heading, nothing else has a size, and
  there is no root `font-size`. Only `FilterField.tsx`, `ExpensesTable.tsx` and
  `DateRangePicker.tsx` set it locally; the table and alert reach 0.875rem through
  daisyUI's default. **A daisyUI default is not a decision** - the calendar arrived at
  0.75rem that way. Nothing checks this.
- **An empty list is a row, not an alert.** `ExpensesTable` renders `[]` as a row and
  reserves `role="alert"` for a request that actually failed - this side of the backend's
  "an empty table is 200, not 503".
- **The theme follows the OS, and nothing can override it.** The single `@plugin "daisyui"`
  block in `src/styles/app.css` names `nord --default` and `dim --prefersdark`. There is no
  `data-theme`, no theme provider and no `dark:` variant in `src/`; a toggle would be a
  feature on top of the pair, not a config change. A theme paints nothing itself, so the
  surface is `bg-base-200 text-base-content` on `<body>` in `index.html` - a body
  background is what propagates beyond the app shell. **Every colour is referenced by
  role**, never a hard-coded shade, which is wrong in one of the two themes rather than
  merely awkward. Chromium's `prefers-color-scheme` emulation reaches the theme your OS is
  not set to.
- **The calendar is themed by daisyUI, and `@daypicker/react/style.css` is deliberately not
  imported.** daisyUI ships a first-party theme keyed on the `react-day-picker` class,
  written in role tokens. **Importing the package's own stylesheet would silently beat
  it**: it is unlayered, everything `@import "tailwindcss"` emits sits inside `@layer`, and
  unlayered rules win regardless of source order. It also hardcodes `font-size: large` on
  the caption and on selected days, reachable through no `--rdp-*` variable. **Nothing
  local names a `--rdp-*` property.** Only `frontend-build` proves the theme is in the
  bundle - `grep react-day-picker frontend/dist/assets/*.css` is that check.
- **`src/styles/app.css` holds exactly one local rule, and it is unlayered on purpose.** It
  deepens `--input-color` on hover for `.input` and `.select`, which daisyUI gives no hover
  state; unlayered is what reaches that variable past daisyUI's layer. **Reach for a
  utility class before a second rule here**: a daisyUI role token in an ordinary CSS
  property fails `css/no-invalid-properties`, and that rule must not be relaxed. This one
  passes only by assigning to a custom property.
- **`dayPickerClassNames` carries three corrections over five names, handed to the panels
  as utility classes** - a role token in an ordinary property fails
  `css/no-invalid-properties`.
  - **No day is marked "today".** `today` is emptied and `getClassNamesForModifiers` keeps
    only truthy entries. Without it daisyUI fills the day with the primary colour through a
    four-class selector against `.rdp-selected`'s three, so the current day reads as picked
    whatever the range is - a third marked day being a third thing to explain.
  - **The month and year dropdowns are given a background.** They are real `<select>`s
    daisyUI leaves transparent over the caption, and a browser paints the *native popup*
    from the control's own colours, so a transparent one comes up pale on pale.
    `[&>option]:bg-base-100` is not redundant: the select's colour does not reach its
    options in every browser.
  - **The panel is brought onto the page's type scale**, `text-sm` on both panels and on
    `month_caption`, `weekday` and `selected`. **Only `selected` is not obvious**: a day
    number inherits through `.rdp-day_button`'s `font: inherit`, but `.rdp-selected` sets
    `font-size: .75rem` of its own, so a picked day would shrink as it was picked. No
    `!important` is needed: Tailwind's utilities are unlayered *within* `utilities`,
    daisyUI's theme is a nested sublayer.
- **Both filters are one control wearing two faces, and `FilterField` is what keeps them
  that way.** The trigger is a daisyUI `input` and the currency picker a `select`: same
  height, border, fill, radius and focus treatment, and neither is a `btn`. Its props are a
  union rather than two optionals **because the two cannot be named the same way** - a
  `<select>` takes a real `<label htmlFor>` and a `<button>` cannot, so the trigger gets
  `labelId` and a `<span id>`. That is also why `containerRef` sits on its own positioning
  `div`: a click on the caption is outside the control.

## Routing and layering

- **Routes are file-based: a route is declared by where its file sits in `src/routes/`.**
  `@tanstack/router-plugin` is configured inline in `vite.config.ts` - **there is no
  `tsr.config.json`** - and writes `src/routeTree.gen.ts`. `src/router.ts` keeps only
  `createAppRouter`, a factory rather than a singleton so tests can pass a
  `createMemoryHistory`. The `declare module` block registering `Register` gives `Link` a
  typed `to`. Pinned by `routing.test.tsx`.
- **`src/routeTree.gen.ts` is committed and never hand-edited.** It is runtime source, not
  a build artifact: every gate except `frontend-build` reads it and none can produce it.
  **Two independent checks keep it in step.** Adding a route file is caught by
  `frontend-typecheck`, since `createFileRoute("/new")` is not assignable until the tree
  names `/new` - which also means `pnpm run build` cannot regenerate after adding one, so
  use `pnpm exec vite build`. A rename or deletion typechecks fine against a stale tree and
  is caught instead by the `git diff --exit-code` step in `ci.yml`, after `frontend-build`
  because that is the only gate that runs vite.
- **The generated tree is excluded from prettier, coverage and Sonar, and `globalIgnores`
  must not make eslint a fourth.** The three exclusions are in the root
  [`CLAUDE.md`](../CLAUDE.md) table. The file's own blanket `/* eslint-disable */` is
  enough, and an ignore *pattern* additionally makes eslint answer "File ignored because of
  a matching ignore pattern" whenever an editor hands it the file; `--no-warn-ignored`
  cannot reach that. **The prettier exclusion is not a preference**: `router-generator`
  calls `prettier.format` with explicit options and never resolves `.prettierrc.json`, so
  the file lands at `printWidth` 80 against this repo's 88.
- **`react-refresh/only-export-components` is off for `src/routes/**`, and that is not a
  demotion.** A route file exports `Route` beside a component it does not export, which is
  the shape the rule rejects - but `autoCodeSplitting` moves the component into a
  `?tsr-split` module, so the file eslint reads is not the module the browser gets.
  Narrowing was tried: `allowExportNames: ["Route"]` makes the export *skipped*, so the
  file is then reported for holding no exported component.
- **`src/components/` is the router-free layer, not `src/routes/`.** Under file-based
  routing the route and its page are the same module: `routes/index.tsx` holds
  `validateSearch` and the component and reads the URL through **`Route.useSearch()`**.
  There is no `getRouteApi` and no `src/pages/` - both existed to break a cycle this shape
  does not have. Everything under `src/components/` takes props and knows no router, which
  keeps them mountable without a `RouterProvider`.
- **`validateSearch` fills in an absent parameter and validates nothing else.**
  `?currency=` is handed to the backend as typed, so `/?currency=euro` gets the 422
  `conversion.py` raises; re-checking `\A[A-Z]{3}\Z` here would put that pattern in a
  second place to drift from. There is no "as recorded" mode - the parameter is always
  sent, an **empty** `?currency=` being a malformed code rather than a request for no
  conversion, and the two dates follow suit. The one thing it adds is the default: an
  absent bound becomes the first or last day of the current month, which is why
  `ExpensesPage.test.tsx` pins the clock.
- **The currency options are what the rate table can reach, not a list of ISO codes.**
  `targetCurrencies` keeps only the `to_currency` of a pair whose `from_currency` is
  `BASE_CURRENCY`, a rate being never inverted and never composed; `BASE_CURRENCY` itself
  is always offered and needs no rate. A rate list that is pending, 503s, empty or
  malformed leaves the select disabled there and **does not disturb the expenses table**:
  they are two requests.
- **The date range is always bounded, and every `navigate` carries the whole search.**
  There is no clear button and no unbounded mode. `DateRangePicker` holds a half-picked
  range in local state and reports nothing until both ends are set, an empty bound being
  malformed to the backend. Because `validateSearch` re-defaults an **absent** parameter, a
  `navigate` omitting `from_date` would silently reset the range, so both handlers spread
  the whole search and override one part. Pinned by "picking a currency keeps the range and
  asks again" and its twin.
- **Two `DayPicker` instances, not one with `numberOfMonths={2}`.** That prop keeps the
  pair consecutive and moves them as a unit, so the left could not sit on 2025 while the
  right showed 2026. Each holds its own `month` and `onMonthChange` while sharing
  `selected` and `onSelect`, which lets a range start in either panel and end in the other.
  The arrows are hidden because the dropdowns do the whole job.
- **The range control is a `<button aria-expanded>` and a conditional render**, not
  daisyUI's `popover` or `<details>` dropdown. jsdom implements no Popover API and
  `@testing-library/dom` gives `<summary>` no role, so both recipes are unreachable by
  `getByRole`, and a conditional render makes `queryByRole("grid")` genuinely `null` when
  closed. It closes on an outside click and on Escape, both from `document` listeners, a
  `keydown` on a non-interactive `<div>` being sonar S6847; either dismissal **discards a
  half-picked range**. The trigger is named by `aria-labelledby` over the caption **and its
  own id**, `<label htmlFor>` not naming a `<button>`.

## Environment and tooling

- **The API origin lives in bare `.env`, not `.env.development`.** vite loads `.env` in
  every mode, including the `test` mode vitest runs in, where MSW binds its handlers to the
  URL built from it. `envDir` is pinned to `frontend/` because the `test` block moves
  vite's `root` to the repo root and `envDir` would otherwise follow.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's `include`
  fails to lint rather than being skipped. `src/` and `tests/` come from
  `tsconfig.app.json`, the two root config files from `tsconfig.node.json` - where a new
  file at the `frontend/` root has to be added too.
- **`package.json` must not gain a `packageManager` field**, and `pnpm-lock.yaml` must stay
  at `lockfileVersion: 9.0`. The first bypasses the pnpm pin in `pixi.toml`; both break
  Dependabot's lockfile parsing, and that version is what it reads its pnpm major from. See
  [`README.md`](../README.md#package-manager).
- **`pnpm-workspace.yaml` states `minimumReleaseAge` and must never gain a
  `minimumReleaseAgeExclude`.** The value mirrors `cooldown.default-days` in
  [`.github/dependabot.yml`](../.github/dependabot.yml) and has to keep mirroring it:
  Dependabot enforces the higher of the two across its whole resolution, so a gap either
  way fails the weekly update job rather than skipping an update. Stating it matters
  because Dependabot resolves this lockfile with pnpm 10, where the default is 0. An
  exclusion disables the guard for the least-vetted release there is.

## Quality gates

- **`eslint-config-prettier` is applied last, so the linter owns correctness and prettier
  owns formatting.** Never add a formatting rule to the eslint config.
- **There is no warn tier.** The `lint` script passes `--max-warnings 0`; a warning fails
  the build like an error. Without it dozens of rules would be advisory - the XSS,
  `target="_blank"` and leaked-timer rules, `exhaustive-deps`,
  `reportUnusedDisableDirectives`. Demote a rule deliberately in its config if you disagree
  with it; do not let the flag go.
- **CSS is linted by eslint too, not by a second tool.** `@eslint/css` adds a `**/*.css`
  block to the same config and rides `frontend-lint`, so there is no stylelint and no new
  pixi task. Tailwind's syntax comes from `tailwind-csstree`'s `tailwind4` rather than
  being hand-written, so a new at-rule needs no config change, and nothing is exempted. Two
  things there are load-bearing:
  - **The `@plugin` `descriptors` override is the one local addition.** daisyUI's `@plugin`
    takes a block and core Tailwind's does not, so `tailwind4` gives it no descriptors and
    css-tree rejects *every* declaration inside one. Drop it once
    [tailwind-csstree#63](https://github.com/humanwhocodes/tailwind-csstree/issues/63)
    lands.
  - **`tolerant: true` stays**, for a subtler reason than an unparseable file. `tailwind4`
    reads `source(none)` by trying `<string>` and falling back to `<ident>`, and css-tree
    reports that recovered attempt through `onParseError` regardless; `@eslint/css`
    promotes every such call to a fatal parse error unless tolerating them. The cost is
    that unbalanced braces go unreported, that check being skipped under `tolerant` too.
