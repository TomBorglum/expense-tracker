# backend/CLAUDE.md

Invariants for the backend stack. Repo-wide rules and [what earns a place
here](../CLAUDE.md#adding-to-these-files) are in the root [`CLAUDE.md`](../CLAUDE.md).
**This file stays under 200 lines.** Break one of these and either CI goes red on an
otherwise correct change, or nothing does; each bullet says which.

## The HTTP surface

- **The backend serves no frontend and publishes no OpenAPI.** The whole surface is the
  four `GET`s the route table in [`README.md`](../README.md) lists: no `/` route, no
  `StaticFiles` mount, no build artifact, and `docs_url`, `redoc_url` and `openapi_url`
  stay `None`. All four are **read-only**, rows arriving through the two loaders alone.
  Pinned by `test_root_is_not_served` and its three surface neighbours.
- **CORS is wildcard with `allow_credentials=False`.** The spec forbids the pair, so the
  day the API grows cookies or an `Authorization` header the wildcard has to become a real
  origin list. It is registered outermost, after the security-headers middleware, so it
  answers preflights itself. Pinned by `test_cors_does_not_allow_credentials`.
- **`create_app()` opens no socket.** The engine is built by the lifespan in `deps.py`,
  which keeps `TestClient(app)` (without `with`) database-free and `uvicorn --factory`
  working. Moving engine creation into the factory breaks the entire HTTP suite.
- **An empty table is 200 with an empty `items` array, not 503.** A database nobody has
  loaded yet is a legitimate state, so both repositories raise only from their `except`
  arm. `test_expenses_endpoint_returns_an_empty_list_when_nothing_is_loaded` + twins.
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

- **The three loader shapes differ on reloading, and that difference is the design.**
  `expense_loader` is append-only: its ledger skips a file whose sha256 matches and
  *refuses* one that changed - and a month file is rewritten in place upstream, so that
  refusal is the ordinary path and the rebuild is the cure, not a loader that replaces a
  changed file's rows. `currency_loader` has no ledger and replaces the whole
  `currency_rate` table every run, a rate being a current fact rather than an event, so
  editing `rates.tsv` and reloading is supported; it parses every file before deleting
  anything, in one transaction. The `category` table is the third: derived state the
  expense loader extends and verifies inside each file's own transaction. Pinned by
  `test_an_edited_rate_replaces_the_old_one` and
  `test_an_edited_file_is_refused_by_name_and_load_date`.
- **The loader assigns the slugs, and the two invariants are checked, not assumed.**
  `assign_slugs` orders nodes by `(first filename, path)`, so a reset and a reload
  reproduce the mapping and a later-named file can only append; one that would **move** a
  stored slug is refused, as is a level that slugs to nothing, and colliding siblings are
  numbered per parent instead. So the write is a plain `insert()`: the idiomatic
  `on_conflict_do_nothing()` would absorb exactly those two refusals.
  `test_a_rebuild_reproduces_the_slugs_an_incremental_load_arrived_at` + five twins.

## Conversion

- **`?currency=` converts in `conversion.py`, and four refusals are the design, not gaps to
  fill in later.** A rate is used **only** in the direction `rates.tsv` states it, never
  inverted, never composed through a third currency; a pair loaded twice is refused rather
  than picked between, and only when needed; one unconvertible expense refuses the
  **whole** request; a code that is not `\A[A-Z]{3}\Z` is refused rather than uppercased.
  Pinned by the refusal tests in `test_conversion.py`.
- **The identity is the one thing it does not refuse:** `record.currency == target` returns
  the record before any lookup, which is why no `DKK DKK 1.000000` row exists. Pinned by
  `test_an_expense_already_in_the_target_currency_is_untouched`.
- **`ROUND_HALF_UP` is spelled out because `Decimal` rounds half to even by default**, in
  `aggregation.py` as well as here - they are `|`-joined siblings, so neither may import
  the other. `test_a_half_cent_rounds_up_rather_than_to_even` and its average twin.

## Aggregation

- **`GET /api/expenses/totals` sums the rows `/api/expenses` lists**, grouped by
  `(period, currency, category)` and taking the same four query parameters. It adds **no
  repository method**: `list_expenses` is what it reads. Pinned by
  `test_two_currencies_in_one_month_stay_two_totals`.
- **A row sums under its own path, so a total names what an expense names.** `?category=`
  filters and chooses no grain, so `aggregate` never sees it. **No level parameter
  either** - rolling a sum up to an ancestor is what this prevents.
  `test_totals_name_the_same_paths_the_list_endpoint_shows`.
- **The conversion runs before the summing, and the order is the point** - it is what
  puts the summing in Python rather than a SQL `GROUP BY`, on the terms
  [`README.md`](../README.md#asking-for-totals) states. Pinned by
  `test_a_total_is_the_sum_of_the_rows_the_list_endpoint_shows`.
- **A row's optional keys are absent when they have no value, never `null`.**
  `exclude_none=True` on the route dump is the whole rule, not `exclude_unset` -
  `_total_payload` sets all six fields, and `?group_by=category` is what puts `category`
  in the key. Pinned by `test_totals_drop_the_category_key_when_it_was_not_grouped_by`,
  read as plain dicts: parsing proves nothing about a key's presence.
- **The dense calendar's extent is `min`/`max` over the records returned**, so it relies
  on no ordering of the repository's, and never the requested range - which would trail a
  bounded one off into periods nobody has reached yet. A period nobody spent in is one
  bare row carrying the span. **Dense in periods only**: a date range has a defined
  universe of periods and categories do not.
  `test_a_month_nobody_spent_in_is_still_a_row` and its bare-row twin.
- **A requested bound narrows a period only when it falls inside it**, which keeps
  `?from_date=2026-01-01` honoured as the 1st even when nothing was spent until the 7th.
  Load-bearing, not an optimisation: the fake filters nothing, so it *can* hand a March
  period a January range, and a plain `max`/`min` would end the span before it began. A
  period's `to_date` is inclusive, from `calendar.monthrange`. Pinned by
  `test_a_range_that_cannot_touch_a_period_leaves_it_whole` and its leap-February twin.
- **The `summary` beside `items` is the same grouped or not**: one entry per currency
  holding the mean of its period totals over the same calendar, which grouping re-keys the
  rows of without changing. Unlike a row's, **neither key is ever absent**. Pinned by
  `test_the_range_summary_is_the_same_grouped_or_not` and
  `test_a_range_summary_entry_carries_both_keys`.
- **`?period=` is required and refuses rather than defaulting**, because a grain nobody
  chose is an assumption inside a sum. `test_a_total_without_a_period_is_refused` + twin.

## The date range and the category filter

- **The dates and the categories filter in SQL, not in the route.** The `DateRange` and the
  `CategorySelection` go to `list_expenses`, which adds one `>=`, one `<=` and one `CASE` -
  `= slug OR LIKE slug || ':%'` per arm over a join to `category`, `autoescape` because a
  **query** value is unvalidated. Both bounds are **inclusive** and open on their own;
  `everything()` adds no clause and so no join, and nothing selected is a bare `false()`,
  so the empty selection is a request rather than the unfiltered one. Postgres suite.
- **A selection states where it changes, never what it covers.** The root carries a sign -
  `?category_default=`, `all` unless `?category=` names a slug, which keeps every request
  written before anything could be deselected meaning what it meant, and why `all` has to
  be sendable - and each value flips a subtree, **the longest slug over a row deciding**.
  `flips()` owns that order, longest first and by **levels** rather than characters.
  `test_flips_are_ordered_longest_path_first` and the flag's own twin.
- **All three types validate in `__post_init__`, so the repository does not.** `DateRange`
  refuses `start > end`, `LevelRange` a level outside `1..MAX_LEVEL`, and
  `CategorySelection` a blank value and a slug flipped both ways, at **every** construction,
  so `list_expenses` stops trusting its caller; a second check gives one rule two homes. An
  **empty** pair of lists is legal, being the default.
  `test_the_type_refuses_an_inverted_range_however_it_is_built`.
- **`date_range._DATE` is the accepted date form, and the only one.** `date.fromisoformat`
  also takes `20260102` and `2026-W01-1`, which this API never sends, so the pattern
  refuses them first, as `validate_currency_code` refuses rather than uppercases. Both
  bounds are read before either is compared, so an unreadable value is refused as itself:
  `test_a_malformed_bound_is_refused_before_the_two_are_compared`.
- **A category is a `:`-separated path, the filter matches the slug beside it, and either
  names a node and every node below it.** `category_filter.SEPARATOR` spells both and is
  its only declaration in Python; `schema.sql`'s CHECKs stop a level holding it, so nothing
  escapes. Matching is by **level, never character** - `foodstuffs` is not under `food`,
  hence `_under`'s two legs. Each **level** is stripped, not each field, or
  `Settlement : Alice` becomes a node that renders identically and never merges.
  `test_a_category_matches_its_descendants_as_well` and the strip twin.
- **`GET /api/expenses/categories` is `list_categories` over the `category` table, ordered
  in SQL, never `list_expenses` deduplicated in the route** - pulling every row for one
  column is what that prevents - and `?from_level=`/`?to_level=` is one
  `WHERE level IN (...)` over the stored depth, not a `UNION` of truncations. An ancestor
  nothing is filed under **is** listed because the loader wrote that row, `MAX_LEVEL`
  bounds the list, and the filter is **not** checked against it.
  `test_categories_endpoint_preserves_the_repository_order` + the node's own twin.

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
