# The frontend

How the SPA is put together: the three pickers, routing, and where it finds the API.

## Choosing a currency

A select beside the heading picks the currency the expenses are presented in, and the
choice is the `?currency=` the table asks the API for. **The conversion stays the
backend's** - the frontend sends a code and renders the strings that come back, so the
`Decimal` arithmetic in `conversion.py` is the only place an amount is ever computed.

The choice lives in the **URL**, so `/?currency=EUR` is a link worth sending and a reload
returns to it. `validateSearch` in `frontend/src/router.ts` supplies `DKK` when the
parameter is absent and checks nothing else: a code the backend refuses is passed through
and answered with a 422, which reaches the page as its ordinary "Could not load the
expenses." The parameter is always sent, an **empty** `?currency=` being a malformed code
to the backend, and the ledger's own currency is `DKK`, the one code that needs no rate.

The options are read from `GET /api/currencies` by `frontend/src/api/currencies.ts` and
are **the targets the rate table can reach**: the `to_currency` of a pair whose
`from_currency` is the base - `EUR`, `GBP`, `NOK`, `SEK`, `USD` today - each rate being
used in the one direction `rates.tsv` states. The file's `EUR -> DKK` and `USD -> DKK`
rows convert *into* the base, where the expenses already are. A rate list that has not
arrived, fails, or comes back empty leaves the select disabled on `DKK` while the table
below renders - two independent requests - and an empty rate table is a working server on
the terms an empty ledger is.

## Choosing a date range

A calendar beside the currency select picks the days the expenses are drawn from, and the
choice is the `?from_date=` and `?to_date=` the table asks the API for. **The filtering
stays the backend's** - it is a `WHERE` clause on `expense_date`, described under
[Asking for a range of dates](api.md#asking-for-a-range-of-dates); the frontend sends two dates
and drops no row of its own.

Both bounds live in the **URL** alongside the currency, so
`/?currency=EUR&from_date=2026-01-01&to_date=2026-01-31` is a link worth sending - and
every URL is one, the router rewriting a bare path to the search it filled in.
`validateSearch`, in the two route files under `frontend/src/routes/`, fills an absent
bound with the first or last day of the current year, from one reading of the clock, the
same default on both views so that switching between them changes nothing. It checks
nothing else - a date
the backend refuses is passed through and answered with a 422, which reaches the page as
its ordinary "Could not load the expenses." Both parameters are always sent, an **empty**
`?from_date=` being a malformed date to the backend, so the way to see more is to pick
earlier or later days. A range holding no expenses is a 200 with an empty `items` array,
which the table shows as a row.

The currency, the range and the categories follow you between the two views: each route
retains them through `retainSearchParams`, so a switch keeps what you were looking at. The
**By category** toggle does not, being declared on `/totals` alone.

The control is [DayPicker](https://daypicker.dev) in `mode="range"`, pinned as
`@daypicker/react`, which renders an ordinary `<table role="grid">` of buttons - every
query in `frontend/tests/` goes by role and accessible name. It brings `date-fns` along
transitively, and `frontend/src/dates.ts` is the one place a `Date` becomes a
`YYYY-MM-DD`, built from the local field getters so the day it names is the local one.

It shows two calendars side by side, each captioned by a month and a year dropdown. They
navigate **independently** - the left can sit on January 2025 while the right shows
December 2026 - and follow one another far enough to stay in order, so any span is two
clicks away. A range can start in either panel and end in the other. Opening puts one
panel on each end of the range currently selected.

Those dropdowns need a finite list, so the calendar is bounded: 1 January of `FIRST_YEAR`
in `frontend/src/dates.ts` through 31 December of the current year. Both bounds are the
frontend's own, and that list is the whole of what the dropdowns reach, so a day before
`FIRST_YEAR` is reached by typing the URL, the dates being passed through as typed.

The panel closes on a click outside it or on Escape, like the select beside it, and either
way a half-picked range is discarded, so the control and the URL agree.

DayPicker orders the pair itself, so a click before the start becomes the new start. The
backend refuses an inverted range, for the URL typed by hand.

## Choosing categories

A **Categories** control beside the currency select narrows both views to a selection of
categories, and that selection is the `?category=`, `?not_category=` and
`?category_default=` the table and the totals ask the API for - **each list repeats its
key once per value**, as described under
[Asking for one or more categories](api.md#asking-for-one-or-more-categories). The filtering
stays the backend's: the frontend sends slugs and drops no row of its own, and the totals
view hands the same selection to its subtotal and its breakdown, so a period is summed
over the expenses it is split by.

The nodes on offer come from `GET /api/expenses/categories`, read by
`frontend/src/api/categories.ts` in the order the backend sends them - once each, by path.
The control asks for `?to_level=3`, so **the whole bounded tree arrives in one request**;
`from_level` is the backend's own parameter.

**The panel is a tree, indented, and each box reads as its own level** - `Alice` under
`Settlement`, not `Settlement:Alice` - which is what the payload's `name` and
`parent_slug` are for: the separator stays the backend's, and **the slug the payload
carries is the one that goes out**. The tree is built from `parent_slug`, which is what
makes it independent of the order the list arrived in - path order is only nearly
pre-order, a level name beginning with a character below `:` sorting between a node and
its own children.

**Every box starts ticked**, because the default is every category and the panel says so.
**Unticking a box unticks its
whole subtree**, and a node whose subtree disagrees with it carries a dash rather than a
tick - `Car` is dashed while `Car:Fuel` alone is out. Ticking a box back puts its subtree
in again, which is how one branch of something otherwise deselected is kept: untick
`Settlement`, tick `Alice` under it, and the request is everything except the settlements,
hers included.

**A box reports the whole slug**, so `Alice` is `settlement:alice` on the wire. What the
URL carries is **where the selection departs from the root's sign**: dropping one category
out of forty is one `not_category` value rather than thirty-nine `category` ones. `frontend/src/categorySelection.ts` is where that is
worked out, the mirror of `category_filter.py` reading the same three parameters back on
the other side.

**A category is picked, never typed**: each click applies at once, the list stays open for
the next, and **Select all** and **Select none** reach the two extremes in one click -
both present and each disabled at the end it leads to, so the panel is the same size
whatever is selected. Select none is what makes a selection additive: empty it and tick
the few categories you want. The trigger reads
**All categories** or **No categories** at the extremes, names the single slug that is
missing or the single one that is picked, and counts past that - a fixed width either way,
so the filter row never moves as the selection changes.

The selection lives in the **URL** alongside the rest, and is spelled the way the API
reads it: `/?not_category=car` is a link worth sending and one you can type by hand. A
slug keeps its separator there - `?not_category=settlement:alice` - because a colon is
legal in a query string as it stands: `URLSearchParams` escapes it to `%3A` and the
router puts it back, so the URL reads the way the categories do and **is free of percent
signs**, which is the whole point of a slug. Typed either way it arrives as the single
value it is. The empty selection is `?category_default=none` on its own, and the default
selection is no category parameter at all - which is why all three are navigated together,
`undefined` where empty: `retainSearchParams` keeps a key the next navigation leaves out,
so `undefined` is what returns to the default.

That is the router's own doing - `frontend/src/router.ts` replaces TanStack Router's
default search serializer with one that repeats a key per value and reads every
parameter as the string it was typed, leaving the separator in a slug alone (a value
that itself reads `%3A` is escaped to `%253A`, which the put-back leaves as it stands).
`validateSearch` folds one value or several into a list and checks nothing else: a slug
the ledger does not hold is passed through and answered with an empty `items` array, an
empty `?category=` with the 422 `category_filter.py` raises, and either is shown as it
stands - a slug the list does not offer still appears, flipped and labelled with itself,
at the top.

A list that has not arrived, fails, or comes back empty leaves the control disabled while
the table below renders - two requests, like the rate table and the expenses. The panel
closes on a click outside it, on Escape and on a second click of the
trigger, sharing `useDismiss` with the calendar; focus stays on the trigger when it opens,
and Tab reaches the boxes.

## Routing

One route, declared by where its file sits, with
[TanStack Router](https://tanstack.com/router)'s file-based routing:
`frontend/src/routes/index.tsx` is `/`, the expenses table, and
`frontend/src/routes/__root.tsx` is the layout it renders inside.
`@tanstack/router-plugin`, configured inline in `frontend/vite.config.ts`, reads that
directory and writes `frontend/src/routeTree.gen.ts`.

**That generated file is committed and never hand-edited.** It is part of the runtime
rather than a build artifact - `tsc`, eslint and the editor all need it on a fresh
checkout, and every frontend gate except the build reads it without being able to
produce it. Two independent checks keep it honest, and they catch different things:
adding a route file fails `frontend-typecheck`, because `createFileRoute("/new")` is
not assignable against a stale tree; a rename, a deletion or a changed path typechecks
fine and is caught instead by the `git diff --exit-code` step `.github/workflows/ci.yml`
runs after `frontend-build`, the one gate that runs vite and so the one that
regenerates. The file is excluded from prettier, coverage and Sonar - three declarations
that nothing checks agree - while eslint is covered by the file's own
`/* eslint-disable */` header, which keeps an editor quiet about it too. Prettier's
exclusion is load-bearing: the generator formats with prettier's own defaults rather than
`.prettierrc.json`, so the file lands at `printWidth` 80 against a check at 88.

`createAppRouter` in `frontend/src/router.ts` takes an optional history so the tests can
pass `createMemoryHistory()`; `frontend/src/main.tsx` calls it with none and gets the
browser's. The `declare module` block at its foot is what makes a `Link`'s `to` typed
against the real route tree. `__root.tsx` is the only file that renders the router's own
components.

The route owns its search schema, so its component is the one that reads it - and under
file-based routing they are the same module, so `index.tsx` holds `validateSearch` and
the page together and reads the URL through `Route.useSearch()`. **The router-free layer
is `frontend/src/components/`**: `ExpensesTable` and `ExpenseFilters` take props, know
nothing of the URL, and mount in a bare `QueryClientProvider`. `autoCodeSplitting` is on,
so the route's component is emitted as its own chunk. A deployed SPA needs its server to
fall back to `index.html` so a non-root path resolves on a cold load; vite's dev server
does that already, and the SPA image's nginx config does it in production.

Tests use vitest, live in `frontend/tests/`, and reach into the app through the `@`
alias (`@/api/expenses`). The alias is declared twice - `resolve.alias` in
`frontend/vite.config.ts` for the bundler and `paths` in `frontend/tsconfig.app.json`
for the type checker, each tool reading its own - so both must point at the same place.
Imports *within* `src/` stay relative.

The backend is stubbed with [MSW](https://mswjs.io). `frontend/tests/setup.ts` starts
the server with `onUnhandledRequest: "error"`, so an unstubbed request fails the test.
Handlers bind to the absolute `EXPENSES_URL` exported by the module under
`frontend/src/api/`, which is what matches the API's origin rather than jsdom's.

`frontend/src/main.tsx` is excluded from coverage in both `frontend/vite.config.ts` and
`sonar-project.properties` - it only wires React to the DOM. `frontend/vite.config.ts`
also pins vitest's root back up to the repo root (`new URL("../", import.meta.url)`),
even though vite's own root is `frontend/`. That is what makes the lcov report record
repo-relative paths like `frontend/src/App.tsx`, which is what SonarCloud resolves the
coverage against.

## Where the API lives

`frontend/.env` holds `VITE_API_BASE_URL`, and the modules under `frontend/src/api/`
resolve every request path against it. That one variable is the frontend's only
knowledge of the backend, and the request it makes is a real cross-origin call over the
same CORS path a deployed one takes. Override it in `frontend/.env.local` (gitignored) to
point at a backend elsewhere.

Two details worth knowing:

- It lives in bare `.env`, which vite loads in *every* mode - including the `test` mode
  vitest runs in, where MSW needs the same value.
- `frontend/vite.config.ts` pins `envDir` to `frontend/`, which keeps env-file lookup
  there while the `test` block's `root` sits at the repo root.

It is typed in `frontend/src/vite-env.d.ts`, which also sets
`ViteTypeOptions.strictImportMetaEnv` - that drops vite's `any` index signature on
`ImportMetaEnv`, so a mistyped `import.meta.env.VITE_*` is a type error.

Because `.env` loads in every mode, `pixi run frontend-build` **bakes
`http://localhost:8000` into the bundle**, which is what the CI gate builds. A deployment
supplies the value for the production mode instead, through a `.env.production` or a
`VITE_API_BASE_URL` in the build environment - vite inlines it at build time, and the SPA
image does exactly that with a placeholder it rewrites at container start. `.gitignore`
covers every `.env` variant but the two committed defaults, so a `.env.production` is
named back in there before it can be committed.

## Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml`
alongside Node. Three deliberate choices:

- **`frontend/package.json` carries no `packageManager` field, and the pixi pin is what
  decides the version.** pnpm's `pmOnFail` defaults to `download`, so that field is what
  would send pnpm to fetch a copy of its own.
- **Pins must be at least three days old.** `frontend/pnpm-workspace.yaml` sets
  `minimumReleaseAge: 4320`, so pnpm refuses to install versions published in the last
  three days as a supply-chain guard. With exact pins there is no older release to fall
  back to, so pnpm asks for an exemption instead. **Pick a newer release that already
  clears the window**, which keeps the guard over every package.

  The value is 4320 because it has to equal `cooldown.default-days` in
  `.github/dependabot.yml`, which is three days. Dependabot does not use that window
  only to choose versions: it passes `min(semver tier, default-days)` to pnpm as
  `--config.minimumReleaseAge`, enforced across its entire resolution, so anything
  already in the repo that is younger than the gate fails the weekly update job with
  `ERR_PNPM_NO_MATURE_MATCHING_VERSION`. Equal values leave the two in step. Tiers above
  the floor - `semver-minor-days`, `semver-major-days` - delay selection, Dependabot
  capping the gate itself at `default-days`.

  Writing the value down at all is for **Dependabot**, which runs pnpm 10: it picks its
  pnpm major from the lockfile, and the `lockfileVersion: 9.0` pin lands it there, where
  the setting defaults to 0. Stating it is what makes the guard hold where the lockfile is
  *resolved* (Dependabot) as well as where it is *verified* (CI); implicit, it let a
  transitive package five hours old reach `pnpm-lock.yaml` and fail CI in PR #48. One case
  stays outside it: Dependabot disables the guard for **security** updates, so such a PR
  can carry a too-young entry. Re-run the job once that version clears the window
  (`gh run rerun <run-id> --failed`) - the check recomputes the cutoff at install time.
- **Install scripts are answered explicitly.** pnpm 11 exits non-zero while a
  dependency's install script is neither allowed nor denied, so
  `pixi run frontend-install` depends on the answer being there. It lives in
  `frontend/pnpm-workspace.yaml` under `allowBuilds`, the only place pnpm 11 still reads
  it. `msw` is denied there: its script copies the browser service worker, and the tests
  use `msw/node`.
