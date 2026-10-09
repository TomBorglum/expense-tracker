# backend/CLAUDE.md

Invariants for the backend stack. Repo-wide rules and [what earns a place
here](../CLAUDE.md#adding-to-these-files) are in the root [`CLAUDE.md`](../CLAUDE.md).
**This file stays under 200 lines.** Break one of these and either CI goes red on an
otherwise correct change, or nothing does; each bullet says which.

## The HTTP surface

- **The backend serves no frontend and publishes no OpenAPI.** The whole surface is
  `GET /api/expenses`, `/api/expenses/totals`, `/api/expenses/categories` and
  `/api/currencies`: no `/` route, no `StaticFiles` mount, no build artifact, and
  `docs_url`, `redoc_url` and `openapi_url` stay `None`. All four are **read-only** -
  rows arrive through the two loaders and nowhere else, so there is no POST, PUT or
  DELETE. Pinned by `test_root_is_not_served` and its three surface neighbours.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so the
  day the API grows cookies or an `Authorization` header the wildcard has to become a real
  origin list. It is registered outermost, after the security-headers middleware, so it
  answers preflights itself. Pinned by `test_cors_does_not_allow_credentials`.
- **`create_app()` opens no socket.** The engine is built by the lifespan in `deps.py`,
  which keeps `TestClient(app)` (without `with`) database-free and `uvicorn --factory`
  working. Moving engine creation into the factory breaks the entire HTTP suite.
- **Every collection body is an object holding `items`**, never a bare array, so a body
  can gain a field without breaking a client; a new endpoint goes through `_collection`.
  Pinned by `test_every_collection_is_an_object_holding_items`.
- **An empty table is 200 with an empty `items` array, not 503.** A database nobody has
  loaded yet is a legitimate state, and a 503 would train a client to retry forever
  against a working server, so both repositories raise only from their `except` arm.
  `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` and its twins.
- **`amount` goes out as `str(Decimal)`** so no float round trip can drift a total by a
  cent, and `date` as a bare `YYYY-MM-DD`. The frontend renders both verbatim. Pinned by
  `test_expense_amounts_are_strings_not_numbers` and its totals and rates twins.

## Module layering

- **Only the HTTP layer knows about HTTP.** `__init__.py` and `deps.py` are that layer;
  every other module imports no fastapi and no starlette. A failed read leaves a repository
  raising `ExpensesUnavailableError` or `CurrenciesUnavailableError`, which the
  `create_app()` handlers alone turn into a 503 - putting an `HTTPException` back in a
  repository is what this prevents. Pinned by the import-linter contracts, not by a test.
- **A new module goes in three lists, not one:** the `layers` contract, where
  `exhaustive = true` fails the gate by itself, and the `source_modules` of *both*
  `forbidden` contracts, which have no `exhaustive` option and so leave an unnamed module
  silently uncovered. The layer order lives in `[tool.importlinter]`; read it there.
- **Every refusal is a plain-string `detail`, and the module raising it knows no status
  code.** `ConversionError`, `DateRangeError` and `AggregationError` each become a 422 in a
  `create_app()` handler, as the repository errors become 503s, which is why the query
  parameters are typed `str` rather than `date` or `Literal`: a parameter FastAPI itself
  refuses answers with a list of errors. Only the 422 handlers read their exception.
- **`db.py` holds `Base` and nothing else.** A shared `DeclarativeBase` in its own module
  lets a second repository arrive without importing the first, which the `|` between
  siblings forbids. A new model goes in the repository reading it. Layers contract.
- **Every repository subclasses its ABC and carries `@override`**, the two fakes in
  `tests/conftest.py` included, because `dependency_overrides` is an untyped dict that
  would accept a look-alike matching the shape without inheriting. Keep `@abstractmethod`
  and its same-line `...`: without it an empty subclass passes. Pinned by the `ABC` and
  ruff's `B027` and `B024`.

## The loaders

- **The two loaders differ on reloading, and that difference is the design.**
  `expense_loader` is append-only: its ledger skips a file whose sha256 matches and
  *refuses* one that changed. `currency_loader` has no ledger and replaces the whole
  `currency_rate` table every run, a rate being a current fact rather than an event, so
  editing `rates.tsv` and reloading is supported. It parses every file before deleting
  anything, in one transaction. Pinned by `test_an_edited_rate_replaces_the_old_one`.
- **A month file is rewritten in place upstream, so the rebuild is the normal path.** A
  later export adds records to the month they fall in, which the refusal above catches as
  an edit; a loader replacing a changed file's rows is what it exists instead of.
  `test_an_edited_file_is_refused_by_name_and_load_date`.

## Conversion

- **`?currency=` converts in `conversion.py`, and four refusals are the design, not gaps to
  fill in later.** A rate is used **only** in the direction `rates.tsv` states it, never
  inverted, never composed through a third currency. A pair loaded twice is refused rather
  than picked between, and only when needed. One unconvertible expense refuses the
  **whole** request: a list mixing converted and unconverted amounts is a column nobody can
  add up. A code that is not `\A[A-Z]{3}\Z` is refused rather than uppercased. Pinned by
  the refusal tests in `test_conversion.py`.
- **The identity is the one thing it does not refuse:** `record.currency == target` returns
  the record before any lookup, which is why no `DKK DKK 1.000000` row exists. Pinned by
  `test_an_expense_already_in_the_target_currency_is_untouched`.
- **`ROUND_HALF_UP` is spelled out because `Decimal` rounds half to even by default.**
  Pinned by `test_a_half_cent_rounds_up_rather_than_to_even`.

## Aggregation

- **`GET /api/expenses/totals` sums the rows `/api/expenses` lists**, grouped by
  `(period, currency, category)` - `currency` stays in the key whatever was asked for,
  because DKK added to EUR means nothing - and takes the same four query parameters. It
  adds **no repository method**: `list_expenses` is what it reads. Pinned by
  `test_two_currencies_in_one_month_stay_two_totals`.
- **That third part's grain comes from `?category=`; `?group_by=` is only a toggle.** A
  row sums under the **deepest** selected path it sits under, so the groups partition the
  rows rather than counting one under an ancestor and a descendant both; nothing selected
  sums under its top level, which for a depth-1 category is the category. **No level
  parameter here** - depth belongs to the category list. The top-level fall-back keeps
  `_group` total against the fake that filters nothing, like `_clamp` below.
  `test_a_selected_child_is_split_out_of_its_selected_parent`.
- **The conversion runs before the summing, and the order is the point.**
  `convert_expenses` quantizes to cents, so converting then adding differs by cents from
  adding then converting, and only the first makes a total equal what a reader adds up from
  `/api/expenses?currency=EUR`. That is what puts the summing in Python rather than a SQL
  `GROUP BY`. Pinned by `test_a_total_is_the_sum_of_the_rows_the_list_endpoint_shows`.
- **`period`, `from_date` and `to_date` are on every row; `amount`, `currency` and
  `category` only when they have a value** - never `null`, never `""`. `exclude_none=True`
  on the route dump is the whole rule, not `exclude_unset` - `_total_payload` sets all six
  fields. `?group_by=category` is what puts `category` in the key, and takes one value.
  Pinned by `test_totals_drop_the_category_key_when_it_was_not_grouped_by` and its
  neighbours, read as plain dicts: parsing proves nothing about a key's presence.
- **The response is a dense calendar: one row per period from the oldest matching expense
  to the newest**, spent in or not, and **absent is not `0.00`** - a month of credits can
  net to zero. The extent is `min`/`max` over the records returned, so it relies on no
  ordering of the repository's. **Dense in periods only**: a date range has a defined
  universe of periods and categories do not. `test_a_month_nobody_spent_in_is_still_a_row`.
- **A requested bound narrows a period only when it falls inside it**, which keeps
  `?from_date=2026-01-01` honoured as the 1st even when nothing was spent until the 7th.
  Load-bearing, not an optimisation: the fake filters nothing, so it *can* hand a March
  period a January range, and a plain `max`/`min` would end the span before it began. A
  period's `to_date` is inclusive, from `calendar.monthrange`. Pinned by
  `test_a_range_that_cannot_touch_a_period_leaves_it_whole` and its leap-February twin.
- **`?period=` is required and refuses rather than defaulting**, because a grain nobody
  chose is an assumption inside a sum. `month` is the only grain, which is why the payload
  field is the grain-neutral `period`. `test_a_total_without_a_period_is_refused` + twin.

## The date range and the category filter

- **`?from_date=`, `?to_date=` and `?category=` filter in SQL, not in the route.** The
  `DateRange` and `CategoryFilter` go to `list_expenses`, which adds one `>=`, one `<=`
  and one OR'd prefix clause per name - `= path OR LIKE path || ':%'`, with `autoescape`
  because a level may hold `%` or `_` - each only when its parameter is set. Both bounds
  are **inclusive** and open on their own; `None` adds no clause, so an absent parameter
  and an empty one are not the same request. Pinned by the postgres suite's range and
  category tests.
- **All three types validate in `__post_init__`, so the repository does not.** `DateRange`
  refuses `start > end`, `LevelRange` a level outside `1..MAX_LEVEL` as well, and
  `CategoryFilter` a blank name, at **every** construction, so `list_expenses` takes the
  types and stops trusting its caller; a second check there gives one rule two homes.
  `test_the_type_refuses_an_inverted_range_however_it_is_built`.
- **`date_range._DATE` is the accepted date form, and the only one.**
  `date.fromisoformat` also takes `20260102` and `2026-W01-1`, which this API never sends,
  so the pattern refuses them first, as `validate_currency_code` refuses rather than
  uppercases. Both bounds are read before either is compared, so an unreadable value is
  refused as itself: `test_a_malformed_bound_is_refused_before_the_two_are_compared`.
- **A category is a `:`-separated path, and a value matches a node and every path below
  it.** `category_filter.SEPARATOR` is its only declaration in Python; the CHECK in
  `schema.sql` is what stops a level holding it, so nothing needs escaping. Matching is by
  **level, never character** - `Foodstuffs` is not under `Food`, hence the clause's two
  legs - and over depth-1 data it is plain equality, so every request written before paths
  still means what it meant. Each **level** is stripped, not each field, or
  `Settlement : Alice` becomes a node that renders identically and never merges; a
  malformed path is not refused but matches nothing, as an unknown category does. Pinned
  by `test_a_category_matches_its_descendants_as_well` and the strip and case twins.
- **`GET /api/expenses/categories` is `list_categories`, deduplicated and ordered in
  SQL, never `list_expenses` deduplicated in the route.** Totals skipped a repository
  method because conversion had to precede the sum; nothing here converts, and pulling
  every row for one column is what this prevents. The filter is **not** checked against
  it. `test_categories_endpoint_preserves_the_repository_order`.
- **`?from_level=`/`?to_level=` are one `SELECT` per level, `UNION`ed**, each truncating
  `category` and guarded by `array_length >= depth` - what makes a level exact, a slice
  past the end returning the array. Every leg needs its own `DISTINCT`, because `union()`
  over one select emits no `UNION` and one level is the default. An ancestor nothing is
  filed under **is** listed, which is what makes it selectable, and `MAX_LEVEL` bounds the
  statement. `test_a_node_with_no_expense_of_its_own_is_still_listed`.

## Database and configuration

- **The HTTP suite never touches PostgreSQL.** `conftest.py` fakes both repositories, so
  a new test hitting an endpoint takes the `client` fixture; only the two `*_postgres.py`
  modules connect, on the terms
  [`README.md`](../README.md#schema-and-access) states, and they TRUNCATE what they read.
- **`schema.sql` is the only DDL, and `IF NOT EXISTS` never alters.** Changing a table -
  a constraint included - means `backend-db-reset` and a reload, because a live cluster
  skips the whole statement. The rest of the rule is in
  [`README.md`](../README.md#schema-and-access). Nothing checks this.
- **The app reads the environment; loading `.env` is a launcher's job.** `config.py` opens
  no file and resolves no path: no `__file__`, no `env_file=`, no `parents[N]`, and
  `[tool.poe]` declares no `envfile`. A wheel-installed package has no project directory
  to derive one from, which is the regression this prevents. No literal DSN and no
  f-string either; what `.env` and `DATABASE_URL` each own is in
  [`README.md`](../README.md#configuration). Pinned by
  `test_missing_database_settings_are_refused_at_startup`.
- **Any new task reaching a server without an explicit `--port` takes the
  `: "${PGPORT:?...}"` guard.** initdb, psql and createdb each default to 5432 and the OS
  username, so a task that lost those names would reach whatever answers there and report
  success. `dev` is the exception and needs none: a lost `UVICORN_PORT` makes uvicorn
  *bind* 8000 rather than silently *reach* the wrong server.
  `test_a_non_numeric_port_is_refused`.

## Quality gates

- **basedpyright's `recommended` mode sets `failOnWarnings`**, which is what makes a
  warning fail the build like an error. It and ruff are configured in `pyproject.toml` only.
- **In a layer list, `|` joins siblings that may *not* import each other and `:` joins
  siblings that *may*** - easy to transpose, and only one enforces anything. `lint-fix`
  is ruff alone: where a new module belongs in the order is a design decision rather than
  a mechanical edit, and ruff builds no cross-module graph.
