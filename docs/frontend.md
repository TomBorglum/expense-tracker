# The frontend

**Every choice lives in the URL.** Each route retains the currency, the range and the
categories through `retainSearchParams`; the **By category** toggle does not, being
declared on `/totals` alone. In all three cases `validateSearch` supplies a default and
**checks nothing else**: a value the backend refuses is passed through and answered with a
422, which reaches the page as its ordinary "Could not load the expenses."

## Choosing a currency

A select beside the heading picks the currency, as the `?currency=` the table asks for.
**The conversion stays the backend's.** The default is `DKK`, and the parameter is always
sent, an **empty** `?currency=` being a malformed code.

The options come from `GET /api/currencies` and are **the targets the rate table can
reach**: the `to_currency` of a pair whose `from_currency` is the base. A rate list that
has not arrived, fails, or comes back empty leaves the select disabled on `DKK` while the
table below renders, the two being independent requests.

## Choosing a date range

A calendar picks the days, as `?from_date=` and `?to_date=`. **The filtering stays the
backend's.** See [Asking for a range of dates](api.md#asking-for-a-range-of-dates). An
absent bound is filled with the first or last day of the current year, from one reading of
the clock. Both are always sent, an **empty** `?from_date=` being malformed.

The control is [DayPicker](https://daypicker.dev) in `mode="range"`, which renders an
ordinary `<table role="grid">` of buttons, so every query in `frontend/tests/` goes by
role and accessible name. `frontend/src/dates.ts` is the one place a `Date` becomes a
`YYYY-MM-DD`, built from the local field getters.

**The calendar is bounded**, its month and year dropdowns needing a finite list: 1 January
of `FIRST_YEAR` in `frontend/src/dates.ts` through 31 December of the current year. Both
bounds are the frontend's own, so an earlier day is reached by typing the URL. The panel
closes on a click outside it or on Escape, discarding a half-picked range either way.

## Choosing categories

A **Categories** control narrows both views, as the `?category=`, `?not_category=` and
`?category_default=` described under [Asking for one or more
categories](api.md#asking-for-one-or-more-categories). The totals view hands the same
selection to its subtotal and its breakdown.

The nodes come from `GET /api/expenses/categories` at `?to_level=3`, so **the whole
bounded tree arrives in one request**. **The panel is a tree, indented, and each box reads
as its own level**, `Alice` under `Settlement` rather than `Settlement:Alice`, which is
what the payload's `name` and `parent_slug` are for. The tree is built from `parent_slug`,
which makes it independent of the order the list arrived in.

**Every box starts ticked**, the default being every category. **Unticking a box unticks
its whole subtree**, and a node whose subtree disagrees with it carries a dash rather than
a tick. Ticking a box back puts its subtree in again: untick `Settlement`, tick `Alice`
under it, and the request is everything except the settlements, hers included. **Select
all** and **Select none** reach the two extremes in one click, each disabled at the end it
leads to.

**A box reports the whole slug**, so `Alice` is `settlement:alice` on the wire, and what
the URL carries is **where the selection departs from the root's sign**: dropping one
category out of forty is one `not_category` value rather than thirty-nine `category` ones.
`frontend/src/categorySelection.ts` works that out.

A slug keeps its separator in the URL, as in `?not_category=settlement:alice`:
`URLSearchParams` escapes the colon to `%3A` and `frontend/src/router.ts` puts it back, so
the URL **is free of percent signs**. That router also replaces TanStack Router's default
search serializer with one that repeats a key per value. The empty selection is
`?category_default=none` alone and the default selection is no category parameter at all,
so all three are navigated together, `undefined` where empty. A slug the ledger does not
hold still appears, flipped and labelled with itself, at the top.

## Routing

File-based routing with [TanStack Router](https://tanstack.com/router):
`frontend/src/routes/index.tsx` is `/` and `__root.tsx` is the layout it renders inside.
`@tanstack/router-plugin`, configured in `frontend/vite.config.ts`, writes
`frontend/src/routeTree.gen.ts`.

**That generated file is committed and never hand-edited.** It is part of the runtime
rather than a build artifact: `tsc`, eslint and the editor all need it on a fresh
checkout, and every frontend gate except the build reads it without being able to produce
it. Two checks cover it. Adding a route file fails `frontend-typecheck`, because
`createFileRoute("/new")` is not assignable against a stale tree. A rename, a deletion or
a changed path typechecks fine and is caught instead by the `git diff --exit-code` step
`ci.yml` runs after `frontend-build`, the one gate that regenerates. The file is excluded
from prettier, coverage and Sonar, with eslint covered by its own `/* eslint-disable */`
header. **Prettier's exclusion is what keeps the gate green**: the generator formats with
prettier's own defaults, so the file lands at `printWidth` 80 against a check at 88.

The route owns its search schema, so `index.tsx` holds `validateSearch` and the page
together. **The router-free layer is `frontend/src/components/`**: `ExpensesTable` and
`ExpenseFilters` take props, know nothing of the URL, and mount in a bare
`QueryClientProvider`. `createAppRouter` takes an optional history so the tests can pass
`createMemoryHistory()`. A deployed SPA needs its server to fall back to `index.html` so a
non-root path resolves on a cold load; vite's dev server does that, and the SPA image's
nginx config does it in production.

Tests use vitest, live in `frontend/tests/`, and reach into the app through the `@` alias,
which is **declared twice**: `resolve.alias` in `frontend/vite.config.ts` and `paths` in
`frontend/tsconfig.app.json`. Imports *within* `src/` stay relative. The backend is
stubbed with [MSW](https://mswjs.io); `frontend/tests/setup.ts` sets
`onUnhandledRequest: "error"`, so an unstubbed request fails the test.

`frontend/vite.config.ts` pins vitest's root back up to the repo root, even though vite's
own root is `frontend/`, which is what makes the lcov report record repo-relative paths
for SonarCloud to resolve coverage against.

## Where the API lives

`frontend/.env` holds `VITE_API_BASE_URL`, and the modules under `frontend/src/api/`
resolve every request path against it. That one variable is the frontend's only knowledge
of the backend. Override it in `frontend/.env.local` (gitignored) to point elsewhere.

- It lives in bare `.env`, which vite loads in *every* mode, including the `test` mode
  vitest runs in, where MSW needs the same value.
- `frontend/vite.config.ts` pins `envDir` to `frontend/`, which keeps env-file lookup
  there while the `test` block's `root` sits at the repo root.
- It is typed in `frontend/src/vite-env.d.ts`, which also sets
  `ViteTypeOptions.strictImportMetaEnv`, so a mistyped `import.meta.env.VITE_*` is a type
  error.

Because `.env` loads in every mode, `pixi run frontend-build` **bakes
`http://localhost:8000` into the bundle**, which is what the CI gate builds. A deployment
supplies the production value instead, through a `.env.production` or a
`VITE_API_BASE_URL` in the build environment.

## Package manager

Dependencies are installed with **pnpm**, whose version is pinned in `pixi.toml` alongside
Node.

- **`frontend/package.json` carries no `packageManager` field**, and the pixi pin is what
  decides the version. pnpm's `pmOnFail` defaults to `download`, so that field is what
  would send pnpm to fetch a copy of its own.
- **Pins must be at least three days old.** `frontend/pnpm-workspace.yaml` sets
  `minimumReleaseAge: 4320` as a supply-chain guard. With exact pins there is no older
  release to fall back to, so **pick a newer release that already clears the window**
  rather than taking pnpm's offered exemption.

  The value has to equal `cooldown.default-days` in `.github/dependabot.yml`, because
  Dependabot passes `min(semver tier, default-days)` to pnpm as
  `--config.minimumReleaseAge` across its entire resolution: anything in the repo younger
  than the gate fails the weekly update job with `ERR_PNPM_NO_MATURE_MATCHING_VERSION`.
  Writing it down at all is for Dependabot, which runs pnpm 10, where the setting defaults
  to 0. Dependabot disables the guard for **security** updates, so such a PR can carry a
  too-young entry. Re-run the job once that version clears the window (`gh run rerun
  <run-id> --failed`), as the check recomputes the cutoff at install time.
- **Install scripts are answered explicitly.** pnpm 11 exits non-zero while a dependency's
  install script is neither allowed nor denied, so `pixi run frontend-install` depends on
  the answer being there. It lives in `frontend/pnpm-workspace.yaml` under `allowBuilds`,
  the only place pnpm 11 still reads it. `msw` is denied there: its script copies the
  browser service worker, and the tests use `msw/node`.
