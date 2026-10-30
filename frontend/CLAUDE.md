# frontend/CLAUDE.md

Invariants for the frontend stack. Repo-wide rules and [what earns a place
here](../CLAUDE.md#adding-to-these-files) are in the root [`CLAUDE.md`](../CLAUDE.md).
**This file stays under 200 lines.** Each bullet ends with the test or gate that pins it,
or with what nothing checks. jsdom evaluates no CSS, so appearance rules are by eye.

## Rendering

- **Both tables render dates verbatim, and amounts verbatim but for the sign.** The strings
  the API sends reach the DOM as they arrive: `amount` is `str(Decimal)`, so no float
  touches a cent, and a bare `YYYY-MM-DD` is printed as given. A period is headed by its
  bounds. **A negative is a credit, `+` in `CREDIT_CLASS`**, and `src/amounts.ts` is the one
  module that rewrites an amount's text. Pinned by `amounts.test.ts` and "shows an alert
  when an amount arrives as a number".
- **The expenses table is four columns, and Category is the unsized one**, holding two
  values: the path, then the row's `key` in parentheses at `text-base-content/60`, wrapping.
  Amount and Currency carry the widths the totals table gives them, so the two views size
  those columns alike. Pinned by "heads the four columns Date, Category, Amount and
  Currency" and by "renders every expense the API serves"; the widths are by eye, as every
  appearance rule here is.
- **`src/dates.ts` is the one crossing point** between the picker's `Date` objects and the
  API's bare `YYYY-MM-DD`, built from `getFullYear`/`getMonth`/`getDate` so every
  conversion is local. It is also the only date formatter in the tree: `date-fns` arrives
  transitively and stays unimported. Pinned by `dates.test.ts`, which needs the fixed
  **`TZ: "Europe/Copenhagen"`** in `vite.config.ts`'s `test` block, local and UTC agreeing
  on CI's UTC runner.
- **The type scale is three sizes at two weights, and 0.875rem is the body of it.**
  `text-xl` is the app title, `text-2xl` the page heading, and there is no root
  `font-size`. The calendar, the nav tabs and the category `<fieldset>` each carry a
  `text-sm` bringing them onto the scale from daisyUI's 0.75rem, `.label` dims to 60% so the
  category choices carry none, and a table reaches 0.875rem the same way. Nothing checks
  this.
- **A period's subtotal and the range average are both the ungrouped request.**
  `PeriodTotals` and `TotalsSummary` both key on `ungrouped(query)` and split one body with
  `select`, so they cost one request. Pinned by "takes the subtotal from the ungrouped
  request rather than adding the lines up" and "costs one request when it renders beside the
  table".
- **An empty list is a row**, and so is a period with no `amount`. `role="alert"` is
  reserved for a request that failed - this side of the backend's "an empty table is 200".
  **The period's own row heading spans the category column**, the sum carrying a category in
  no payload. Pinned by "adds a line per category when the grouping was asked for".
- **The surface is `bg-base-200 text-base-content` on `<html>` in `index.html`.** daisyUI
  paints `base-100` on `:root`, so that is the one background covering the whole canvas.
  **Every colour is referenced by role.** The one theme, `dim`, and why there is no toggle
  are in [`README.md`](../README.md#frontend).
- **The calendar is themed by daisyUI**, which ships a first-party theme keyed on the
  `react-day-picker` class and written in role tokens. `@daypicker/react/style.css` stays
  out of the bundle, so the theme is the only source of those rules: everything
  `@import "tailwindcss"` emits sits inside `@layer`, where the theme reaches it.
  **Nothing local names a `--rdp-*` property.** Only `frontend-build` proves the theme is in
  the bundle: `grep react-day-picker frontend/dist/assets/*.css`.
- **`src/styles/app.css` holds exactly one local rule, and it is unlayered on purpose.** It
  deepens `--input-color` on hover for `.input` and `.select`, which daisyUI gives no hover
  state; unlayered is what reaches that variable past daisyUI's layer, and assigning to a
  custom property is what passes `css/no-invalid-properties`. **Reach for a utility class
  before a second rule here.**
- **`dayPickerClassNames` carries three corrections over five names**, as utility classes.
  - **No day is marked "today".** `today` is emptied and `getClassNamesForModifiers` keeps
    only truthy entries, so the current day reads as picked exactly when the range picks it:
    daisyUI's four-class selector outranks `.rdp-selected`'s three.
  - **The month and year dropdowns are given a background.** They are real `<select>`s
    daisyUI leaves transparent over the caption, and a browser paints the *native popup*
    from the control's own colours. `[&>option]:bg-base-100` carries that colour to the
    options, which some browsers need.
  - **The panel is brought onto the page's type scale**, `text-sm` on both panels and on
    `month_caption`, `weekday` and `selected`. **`selected` is the one that is not
    obvious**: a day number inherits through `.rdp-day_button`'s `font: inherit`, while
    `.rdp-selected` sets a `font-size` of its own that the utility overrides. The override
    lands without `!important`, Tailwind's utilities being unlayered *within* `utilities`
    and daisyUI's theme a nested sublayer.
- **The filters are one control wearing several faces, and `FilterField` is what keeps
  them that way**: same height, border, fill, radius and focus, and none of them a `btn`.
  Its props are a union, naming each control the way its element allows: a `<select>` and a
  checkbox take a real `<label htmlFor>`, and the two picker triggers get `labelId` and a
  `<span id>`. Each `containerRef` sits on its own positioning `div`, which is what puts a
  click on the caption inside.

## Routing and layering

- **Routes are file-based: a route is declared by where its file sits in `src/routes/`.**
  `@tanstack/router-plugin` is configured inline in `vite.config.ts` and writes
  `src/routeTree.gen.ts`. `src/router.ts` holds `createAppRouter`, a factory so tests can
  pass a `createMemoryHistory`, and the search serializer. Pinned by `routing.test.tsx`.
- **The router spells a list as a key repeated once per value**, `?category=A&category=B`,
  through its own `parseSearch`/`stringifySearch`, whose `With` helpers work per value. One
  value parses to a bare string, so assert on `searchStr` rather than
  `router.state.location.search`. It also **puts back the `:` `URLSearchParams` escapes**,
  legal in a query and the only escape a category slug holds. `routing.test.tsx`.
- **`src/routeTree.gen.ts` is committed and never hand-edited**, and eslint covers it
  through `globalIgnores`, beside the three exclusions prettier, coverage and Sonar each
  declare. Why each holds is in [`README.md`](../README.md#routing) and the root
  [`CLAUDE.md`](../CLAUDE.md) table. The one thing neither says: **regenerate it with `pnpm exec vite build`** after a
  route file is added, typecheck running first under `pnpm run build`.
- **`src/components/` is the router-free layer.** Under file-based routing the route and
  its page are the same module: `routes/index.tsx` holds `validateSearch` and the component
  and reads the URL through **`Route.useSearch()`**. Components take props and know no
  router, so they mount without one.
- **`validateSearch` fills in an absent parameter and validates nothing else**, the shared
  six through `sharedSearch` in `src/search.ts`. `?currency=` is handed to the backend as
  typed, so `/?currency=euro` gets the 422 `conversion.py` raises, and that pattern stays in
  one place. The parameter is always sent, an **empty** `?currency=` being a malformed code,
  and the two dates follow suit. The one thing it adds is the default: an absent bound
  becomes the first or last day of the current *year*, **the same one on both routes**,
  because a switch between them carries the range as it stands and reads a default and a
  pick alike. It reads the clock, so both page tests pin it. `group_by` and the three
  category keys have **no default to fill in**: absent means ungrouped, or every category.
  `categoryFilter` keeps `""` for the backend to refuse and `categoryDefault` drops a flag
  the backend does not name.
- **The currency options are what the rate table can reach, not a list of ISO codes.**
  `targetCurrencies` keeps only the `to_currency` of a pair whose `from_currency` is
  `BASE_CURRENCY`, a rate being used in one direction only; `BASE_CURRENCY` itself is
  always offered and needs no rate. A rate list that is pending, 503s, empty or malformed
  leaves the select disabled while the table below it renders, the two being separate
  requests, and the category list is on the same terms: a slug it never named is shown
  flipped all the same.
- **The picker builds its tree from `parent_slug`**, which is what makes it independent of
  the order the list arrived in. **Every box is ticked by default, and unticking one unticks
  its subtree**: a selection is the root's sign plus the slugs that flip it
  (`src/categorySelection.ts`, the mirror of `category_filter.py`), and setting one clears
  the flips below it. **Only the render filters a collapsed row away**: the walk covers the
  whole tree and reports the selection in its order, so a flip out of sight stays in the
  URL. **Expansion is a map of twisty clicks**, which keeps every twisty live however the
  selection moves. `CategoryPicker.test.tsx`.
- **The date range is always bounded, and every `navigate` carries the whole search.**
  `DateRangePicker` holds a half-picked range in local state and reports nothing until both
  ends are set, an empty bound being malformed to the backend. Because `validateSearch`
  re-defaults an **absent** parameter, every handler spreads the whole search and overrides
  one part - and the three category keys go as **`undefined` rather than left out**, which
  is what `retainSearchParams` needs to carry the default selection, so all three are
  **required and `| undefined`** in `ExpensesQuery`. Pinned by tsc and "picking a currency
  keeps the range and asks again".
- **A switch between the views keeps the currency, the range and the categories**, through
  `retainSearchParams` in each route's `search.middlewares`; the nav links carry no search
  of their own and `group_by` stays out of the list. **A bare landing URL is rewritten, with
  `replace`, to what `validateSearch` filled in**, which is what makes it self-contained.
  Both pinned by `routing.test.tsx`.
- **Two `DayPicker` instances.** Each holds its own `month` and `onMonthChange` while
  sharing `selected` and `onSelect`, so the panels move independently - the left on 2025
  while the right shows 2026 - and a range can start in either. The dropdowns replace the
  arrows.
- **Both pickers are a `<button aria-expanded>` and a conditional render**, which is what
  makes `queryByRole` genuinely `null` when closed: jsdom implements no Popover API and
  `@testing-library/dom` gives `<summary>` no role. `useDismiss` closes either on an outside
  click and on Escape, from `document` listeners - a `keydown` on a non-interactive `<div>`
  is sonar S6847 - and the range one **discards a half-picked range**. Each trigger is named
  by `aria-labelledby` over the caption **and its own id**, `<label htmlFor>` naming a form
  control.

## Environment and tooling

- **The API origin lives in bare `.env`**, for the reason
  [`README.md`](../README.md#where-the-api-lives) gives. `envDir` is pinned to `frontend/`
  because the `test` block moves vite's `root` to the repo root.
- **Every linted file needs a tsconfig that owns it.** eslint runs type-aware via
  `parserOptions.projectService`, so a `.ts`/`.tsx` file outside every tsconfig's `include`
  fails to lint. `src/` and `tests/` come from `tsconfig.app.json`, the two root config
  files from `tsconfig.node.json` - a new file at the `frontend/` root goes there too.
- **`package.json` carries no `packageManager` field**, the pnpm version being pinned in
  `pixi.toml`, and `pnpm-lock.yaml` stays at `lockfileVersion: 9.0`, which is what
  Dependabot reads its pnpm major from. See
  [`README.md`](../README.md#package-manager).
- **`pnpm-workspace.yaml` states `minimumReleaseAge`**, and that guard covers every
  package. The value it mirrors and why is in
  [`README.md`](../README.md#package-manager).

## Quality gates

- **`eslint-config-prettier` is applied last, so the linter owns correctness and prettier
  owns formatting.** Never add a formatting rule to the eslint config.
- **A warning fails the build like an error.** The `lint` script passes `--max-warnings 0`,
  which is what makes gates of the XSS, `target="_blank"`, leaked-timer, `exhaustive-deps`
  and `reportUnusedDisableDirectives` rules. Demote a rule in its config if you disagree
  with it; keep the flag.
- **CSS is linted by eslint too.** `@eslint/css` adds a `**/*.css` block to the same config
  and rides `frontend-lint`, so one tool and one task cover both. Tailwind's syntax comes
  from `tailwind-csstree`'s `tailwind4` rather than being hand-written, so a new at-rule
  needs no config change, and nothing is exempted.
  - **`tolerant: true` stays.** `tailwind4` reads `source(none)` by trying `<string>` and
    falling back to `<ident>`, and css-tree reports that recovered attempt through
    `onParseError` regardless; `@eslint/css` promotes every such call to a fatal parse
    error unless tolerating them. The cost: unbalanced braces go unreported, that check
    being skipped under `tolerant` too.
