# expense-tracker

A FastAPI REST API and a React + Tailwind CSS v4 single-page app, as two independent
applications.

`backend/` and `frontend/` are siblings, each owning its own tooling, tests and build.
Neither can see the other: the backend serves JSON and ships no frontend assets, the
frontend builds to its own `dist/` and reaches the API cross-origin over CORS. Either
can be built, tested and linted with the other's directory missing entirely. The root
holds only what spans both - pixi orchestrates the two toolchains, and one SonarCloud
project covers both languages.

Locally that means two processes.

```
expense-tracker/
  pixi.toml, pixi.lock          # environments, dependencies, and one `pixi run` task
                                #   per command, each forwarding to the stack below
  sonar-project.properties      # one Sonar project spanning both languages
  compose.yaml                  # the deployment: three services, two profiled
                                #   loaders, one volume
  .github/                      # CI, release-please, dependabot
  backend/
    pyproject.toml              # hatchling, ruff, pytest, basedpyright, poe tasks
    schema.sql                  # the whole schema: four tables and their indexes
    data/currencies/            # the committed exchange rates, loaded into the database
    src/expense_tracker/        # __init__ (the API), deps, config, db,
                                #   expense_repository, expense_loader
    tests/
      data/expenses/            # sample-*.yaml, the suite's fixtures
    .pgdata/                    # the local PostgreSQL cluster, gitignored
  frontend/
    package.json, pnpm-lock.yaml, pnpm-workspace.yaml
    tsconfig*.json, vite.config.ts, eslint.config.ts
    .prettierrc.json, .prettierignore
    .env                        # VITE_API_BASE_URL - where the API lives
    index.html, src/, tests/
    dist/                       # vite output, gitignored
```

## Prerequisites

[direnv](https://direnv.net) and [pixi](https://pixi.sh). The committed `.envrc` runs
`use pixi python`, so entering the directory provisions Python, Node and every
dependency from `pixi.toml`, and re-provisions whenever `pixi.toml` changes. Run
`direnv allow` once after cloning, which covers installation.

That includes PostgreSQL: the server is a conda-forge package like everything else, so it
arrives with the rest of the environment. See [Database](#database).

Docker is the one tool pixi does not supply. The three `*-image` tasks call for it, and so
does `compose.yaml`, which is the whole deployment; the development loop runs without
either. A machine without it gets `docker: command not found` from those tasks. See
[Container images](#container-images) and [Deployment](#deployment).

`use pixi` comes from a direnv library. On a workstation it is the one
[`wsl-cloud-init`](https://github.com/TomBorglum/wsl-cloud-init) provisions; in CI, the
`setup-direnv` action from [`TomBorglum/actions`](https://github.com/TomBorglum/actions)
installs its own copy and activates this same `.envrc`. Where that library is absent,
`direnv allow` reports the directive as an unknown command.

Its last line is `dotenv_if_exists`, which puts the database connection settings and the
port the API serves on into the environment. That is stock direnv, and the **only** thing
that puts them there, so `direnv allow` is what makes the database reachable.
See [Configuration](#configuration).

## Quickstart

```sh
cd expense-tracker          # direnv provisions the environment on entry
pixi run frontend-install   # install frontend dependencies (pnpm)
```

Then start both, in two terminals:

```sh
pixi run backend-dev   # the local database, then the REST API on http://localhost:8000
pixi run frontend-dev  # the SPA on http://localhost:5173
```

`backend-dev` creates the local database, starts it and applies the schema before it
launches the API, and every part of that is idempotent, so it is the same one command on
the first day and on any later one. The `backend-db-*` tasks drive the cluster on its
own when you want that; see [Database](#database). Sample expenses are a separate,
explicit step - `pixi run backend-load-expenses` and
`pixi run backend-load-currencies`, described under
[Loading expenses](#loading-expenses) and
[Loading exchange rates](#loading-exchange-rates) - because an empty table is a
legitimate state the API answers `200` with an empty `items` array.

Visit http://localhost:5173 and you should see the **Expenses** table, fetched from
`http://localhost:8000/api/expenses` - a genuine cross-origin request, which works only
because the API allows it (see [CORS](#cors)) - and read in turn out of the `expense`
table (see [Database](#database)). Until you run the loader it says
`No expenses match the selected criteria.`, which is the empty state.

The API alone is enough for backend work. The SPA alone runs too; it just renders its
error state until something answers on 8000.

## Routes

| Route | What it serves |
| --- | --- |
| `GET /api/expenses` | `[{"amount", "currency", "date", "category", "key"}, ...]` - the `ExpensePayload` model |
| `GET /api/expenses?currency=EUR` | The same, restated in one currency |
| `GET /api/expenses?from_date=2026-01-01&to_date=2026-01-31` | Only the expenses dated within that range |
| `GET /api/expenses?category=food&category=housing` | Only the expenses in either category, or under it - each value a category **slug** |
| `GET /api/expenses?not_category=food` | Every expense except the ones in `food`, or under it; `category_default` names the root's own sign |
| `GET /api/expenses/categories` | `[{"category", "name", "slug", "parent", "parent_slug"}, ...]` - the `CategoryPayload` model, every category at the levels asked for, once each, in path order; takes `from_level` and `to_level` |
| `GET /api/expenses/totals?period=month` | `[{"period", "from_date", "to_date", "amount", "currency", "category"}, ...]` - the `PeriodTotalPayload` model, taking `group_by`, `currency`, `from_date`, `to_date` and the three category parameters too; its body carries a `summary` beside `items` |
| `GET /api/currencies` | `[{"from_currency", "to_currency", "exchange_rate"}, ...]` - the `CurrencyPayload` model |

**Every body is an object holding `items`**, so each shape above is what fills that
array - `GET /api/currencies` answers
`{"items": [{"from_currency", "to_currency", "exchange_rate"}, ...]}`. An object is what
lets a response gain a field later without breaking a client. Totals is the one endpoint
that has taken that room, with [the range average](#the-range-average) beside its rows;
the other three send `items` alone.
**The key is `items`**: Zalando, whose rule puts the object there, names it that on every
collection, and one key across all four keeps `fetchList` free of per-endpoint knowledge.
A ledger narrowed to a date range is served whole, and `/api/expenses/totals` reads its
whole answer at once. A refusal body is the plain `{"detail": "..."}` object.

All four send `Cache-Control: no-store`.

Expenses come back **oldest first**, and `amount` is a **string**, not a number: the
column is `numeric(12, 2)`, JSON has no decimal type, and a decimal has no exact binary
form, so a float round trip is how a total drifts by a cent. That shape is declared once,
as the `ExpensePayload` pydantic model in `backend/src/expense_tracker/__init__.py`;
the tests parse responses back into it. An unreachable database answers
`503 {"detail": "expenses unavailable"}`, and an **empty table answers
`200 {"items": []}`** - a database nobody has run the loader against yet is a legitimate
state.

Exchange rates come back **by pair**, `from_currency` then `to_currency`, and
`exchange_rate` is a **string** for the same reason `amount` is: the column is
`numeric(18, 6)`, and an amount multiplied by a rate that made a float round trip is an
amount that has drifted. The empty table and the unreachable database behave as above,
with `{"detail": "currencies unavailable"}` as the 503 body.

### Asking for one currency

`?currency=` restates every expense in the code given, **replacing** `amount` and
`currency`, so the payload is the same shape either way. `1250.00 DKK` at `0.134048`
comes back as `"167.56" EUR`: `Decimal` arithmetic throughout, quantized to two places
with `ROUND_HALF_UP`, and still a string on the wire.

Only what `data/currencies/rates.tsv` states in that direction is used, each rate as the
file writes it. An expense already in the requested currency passes through untouched, so
the file holds no `DKK DKK 1.000000` row.

Anything else is a `422` carrying a plain-string `detail`, the same shape as the 503s
above:

| Request | Body |
| --- | --- |
| `?currency=CHF` | `{"detail": "no exchange rate from DKK to CHF"}` |
| `?currency=euro` | `{"detail": "currency must be an ISO 4217 code"}` |

A lowercase code is refused, matching the loaders, which refuse one in a file. One
unconvertible expense refuses the **whole** request, so every amount in a list stands in
one currency. A pair loaded twice is refused the same way, and only when that pair is
actually needed.

The arithmetic lives in `backend/src/expense_tracker/conversion.py`, which knows no HTTP
and holds no session - it takes records and rates and gives records back, so it is
tested in `backend/tests/test_conversion.py` without a client or a database.

### Asking for a range of dates

`?from_date=` and `?to_date=` narrow the list to the expenses dated between them.
**Both bounds are inclusive**, so `?from_date=2026-01-01&to_date=2026-01-31` is January
including both the 1st and the 31st, and **each is optional on its own**: give only
`from_date` and the range runs to the newest expense there is, give only `to_date` and it
runs from the oldest. Give neither and the request is the one that was there before the
parameters existed.

The filtering is a `WHERE` clause on `expense_date`, served by the
`expense_oldest_first_idx` index that was already there. **A range holding no expenses is
`200 {"items": []}`**, on the terms an empty table is. The two parameters compose with
`?currency=`, and the range is applied first, so an expense outside it needs no exchange
rate.

Dates are read as `YYYY-MM-DD`, the form the payload's own `date` field uses. Anything
else is a `422` carrying the same plain-string `detail`:

| Request | Body |
| --- | --- |
| `?from_date=01/01/2026` | `{"detail": "from_date must be a date in YYYY-MM-DD form"}` |
| `?to_date=2026-02-30` | `{"detail": "to_date must be a date in YYYY-MM-DD form"}` |
| `?from_date=2026-03-01&to_date=2026-01-01` | `{"detail": "from_date must not be after to_date"}` |

A range that ends before it begins is refused. That refusal belongs to the `DateRange`
type rather than to the parsing, so it holds however the range is built, and the
repository takes that type with its ordering already checked. Both live in
`backend/src/expense_tracker/date_range.py`, which knows no HTTP and no database at all,
and are tested in `backend/tests/test_date_range.py`.

### Asking for one or more categories

**Every value is a slug, never a category path.** A slug is the URL spelling of a
category - `going-out:jalsa-pool` for `Going Out:Jalsa+pool` - assigned once as the
expenses are loaded and sent on every payload that names a category; see
[Category slugs](#category-slugs).

`?category=` narrows the list to the expenses in the category whose slug it names. **The
key repeats once per value**, so `?category=food&category=housing` is every expense in
either, and a value given twice counts once. Give none and every category is included.

`?not_category=` is the same key read the other way: every expense **except** the ones in
the category named. The two compose, because a request states **where the selection
changes**: the root has a sign, each value flips a subtree, and **the longest slug over a
row decides**. So `?category=settlement` is the settlements alone,
`?not_category=settlement` is everything else, and
`?category=settlement&not_category=settlement:alice` is the settlements except hers. A
slug in both lists is refused: two flips of the same length over one node.

`?category_default=` is the root's own sign, `all` or `none`. Absent, it is `all` unless
`?category=` names a slug, in which case it is `none`: that is what keeps a request naming
categories meaning those and no others. The flag carries weight in two places -
`?category_default=none` alone, which selects **nothing** and is `200 {"items": []}`, and
`?category_default=all` beside both lists, which is everything but one subtree with a
branch of that subtree kept. A client that sends none of the three asks for every
category.

A value is matched the way the loader stored the slug: **stripped level by level, then
verbatim**, so `?category=%20food` is `food`, and every slug is lower case. That is the
loader's own strip, so the filter meets a stored value on the terms it was stored under,
and the case is the client's to send, as a currency code is.

**A value matches the node it names together with every node below it.** So
`?category=settlement` is every settlement and `?category=settlement:alice` is only
hers. Over categories that carry no path the two are the same thing.

The filtering is one `WHERE` clause beside the two date clauses - a join from
`expense.category` to the `category` table, then a `CASE` whose arms are the flips in
longest-slug order, each `= slug OR LIKE slug || ':%'`, falling through to the root's
sign. It composes with `?currency=`, `?from_date=` and `?to_date=` the way those compose
with each other: all three narrow the query, and the conversion runs over whatever they
left. The index behind it is `expense_oldest_first_idx`, which orders the scan over a
small table, while `category` carries one for the slug it is joined on and one for the
level the list is read by. **A category nobody has spent in is `200 {"items": []}`**, on
the terms an empty table is. A category is whatever a file said, and the filter is read
against the stored slugs alone.

`GET /api/expenses/categories` is that list: every category at the levels asked for,
**once each and in path order**, as `{"items": [{"category": "Settlement:Alice", "name":
"Alice", "slug": "settlement:alice", "parent": "Settlement", "parent_slug":
"settlement"}]}`. `name` is the path's last level and `parent` the path above it, so **no
client has to know what joins one level to the next**; a depth-1 category carries both
parent keys absent. `slug` is what the three filter parameters take and `parent_slug` is
the slug above it, so a client keys its own tree on the pair it sends and shows `name`,
the slugs arriving ready to use. The ordering is the repository's, `list_categories` in
`backend/src/expense_tracker/expense_repository.py`: the route reproduces the order it is
handed, as the other three do.

`?from_level=` and `?to_level=` choose the depths, both inclusive. **Absent, they are the
top level alone**, and an absent `to_level` is whatever `from_level` is, so
`?from_level=2` is exactly depth 2 while
`?to_level=3` is depths 1 through 3. The `category` table holds one row per node with its
own depth, so the range is a plain `WHERE level IN (...)`, and **an ancestor nobody filed
anything directly under is still listed**: `Settlement` appears even when every settlement
is `Settlement:<someone>`, the loader having written that row, which is what makes the
node selectable. `MAX_LEVEL` in
`backend/src/expense_tracker/level_range.py` bounds how many levels a client can name.
The cluster is `initdb --locale=C`, so name order is byte order - `Zoo` before `apple` -
which is the order Python's `sorted()` gives too. **An empty table is
`200 {"items": []}`** and an unreachable database
`503 {"detail": "expenses unavailable"}`, the same table answering the same way.

A blank value is a `422` carrying the same plain-string `detail`:

| Request | Body |
| --- | --- |
| `?category=` | `{"detail": "category must not be blank"}` |
| `?category=%20` | `{"detail": "category must not be blank"}` |
| `?not_category=` | `{"detail": "category must not be blank"}` |
| `?category=food&not_category=food` | `{"detail": "category both selected and deselected: food"}` |
| `?category_default=every` | `{"detail": "unknown category_default: every"}` |
| `?from_level=two` | `{"detail": "from_level must be a whole number"}` |
| `?from_level=0` | `{"detail": "from_level must be 1 or more"}` |
| `?to_level=11` | `{"detail": "to_level must not be more than 10"}` |
| `?from_level=3&to_level=2` | `{"detail": "from_level must not be after to_level"}` |

An empty value is malformed, as an empty `?from_date=` is, and blank means blank after
the strip, as it does to the loader. The refusal belongs to the `CategoryFilter` type
rather than to the parsing, so it holds however the filter is built, and the repository
takes that type. Both live
in `backend/src/expense_tracker/category_filter.py`, which knows no HTTP and no database
at all, and are tested in `backend/tests/test_category_filter.py`.

#### Category paths

A category is one `text` column holding a `:`-separated path - `Groceries`, or
`Settlement:Alice`. **Depth is unbounded and a third level needs no API change**, the
path being one column however deep it goes.

The separator is declared twice and only twice: `SEPARATOR` in `category_filter.py`, and
the `expense_category_is_a_path` CHECK in `schema.sql` that refuses an empty level. That
CHECK is what keeps **the separator out of every level**, so splitting a path or joining
one back up is lossless and **the levels need no escaping** in the SQL, the URL or the
payload. Matching is by level rather than by characters, which is why the clause has two
legs: `food` covers `food:dining` and leaves `foodstuffs` alone.

The storage is plain `text`, where the CHECK above makes a prefix match exact.
PostgreSQL's own `ltree` models the same shape, with labels that hold no space, and stays
the upgrade path if the table ever outgrows the scan.

#### Category slugs

A category path is what a file said, and a URL carries a spelling of its own.
`Going Out:Jalsa+pool` holds a space and a plus; percent-encoded, the address bar reads
`Going%20Out%3AJalsa%2Bpool`, and `+` is what `application/x-www-form-urlencoded` already
spells a space as. So the value a user reads and the value a URL carries part company:
every category also has a **slug**, and the slug is what the API takes and what the
frontend puts in the URL.

A slug holds `a-z`, `0-9`, `-` within a level and `:` between levels. The one character
in it a query escapes is the colon, which `frontend/src/router.ts` puts back, so a
category URL is free of percent signs. One level becomes one slug level
by lower-casing it, transliterating the three Danish letters (`ae`, `oe`, `aa`) and
stripping any other diacritic, then collapsing each run of anything left to a single `-`
and trimming the ends: `Jalsa & pool` is `jalsa-pool`, `100%` is `100`. A level that comes
out empty - punctuation alone, or letters no transliteration reaches - is refused while
loading, so every slug names one category.

Two siblings can want one slug, and the **second is numbered rather than refused**:
`Going Out` is `going-out` and `Going-Out` is `going-out-1`, with the next free number
taken, so a real `Going Out 1` beside them keeps `going-out-1` for itself and pushes the
collision to `going-out-2`. The numbering is **per sibling group**, a parent's own slug
already separating the branches, so upstream data stands as it is.

Which sibling gets the bare slug is decided by **order of first appearance in file-name
order, then by path within a file**, which makes the assignment a function of the loaded
files and nothing else. Two invariants follow, and both are checked rather than assumed:

- **The same files give the same slugs**, however they were loaded, so a link survives a
  `backend-db-reset` and a reload.
- **Loading a new file never changes a slug already assigned.** A later month sorts last
  and can only append.

**Backfilling** is the case the second invariant is enforced against - loading
`2024-01.yaml` after `2026-*.yaml`, where the earlier name sorts ahead of the slugs
already assigned. The loader recomputes every slug on every file, compares them with the
stored ones, and **refuses the file** if any would move, naming the category and both
slugs, on the same terms as any other file problem. The fix is a rebuild, the ordinary
path here anyway.

The slugs live in the `category` table, one row per node with its path, its slug, its
depth and the file it first appeared in - the ancestors included, since an ancestor's slug
is a component of every slug below it, and since a node nothing is filed directly under is
still selectable. `UNIQUE (slug)` sits behind the assignment as a backstop, which the
numbering keeps quiet; a violation is a bug in this project. `slug_level` is in
`category_filter.py` and `assign_slugs` in
`expense_loader.py`, both of which know no database; the tests are in
`backend/tests/test_category_filter.py` and `backend/tests/test_expense_loader.py`.

### Asking for totals

`GET /api/expenses/totals` sums the rows `/api/expenses` lists, over the period
`?period=` names. It takes the same `?currency=`, `?from_date=`, `?to_date=` and
`?category=` as the list does and means the same thing by each.

**`?period=` is required**, a grain being the caller's to choose; `month` is the only one,
so the payload field is the grain-neutral `period`. Rows are keyed by
`(period, currency)`, and `?group_by=category` adds a third part to that key.
**`currency` stays in the key whatever was asked for**, so every sum is in one currency.

**`?group_by=` is only a toggle: a row sums under the path its expenses carry.** The
difference between this endpoint and the list is the aggregation: a totals row names
exactly what an expenses row names. `?category=` narrows which rows arrive and chooses no
grain. Say Alice's settlement is 150 and Bob's is 25:

| Selection | Rows |
| --- | --- |
| nothing | `Settlement:Alice` 150, `Settlement:Bob` 25, and every other path |
| `Settlement` | `Settlement:Alice` 150, `Settlement:Bob` 25 |
| `Settlement` and `Settlement:Alice` | the same two rows |

The third one is worth reading twice: ticking an ancestor as well changes nothing, the
longest flip over a row deciding. The rows under a period still add to what the same
request returns ungrouped. **Depth belongs to the category list**, so a sum is always at
the grain its own rows carry.

The response is a **dense calendar**: one row per period from the oldest matching expense
to the newest, whether or not anything was spent in it. `period`, `from_date` and
`to_date` are on every row; `amount`, `currency` and `category` are present with a value
or **absent altogether**.

That absence carries meaning, and credits are why. A credit - a refund, a reimbursement,
a share paid back - is a negative expense, so a period can hold rows that cancel each
other out:

| Period | Rows in it | What comes back |
| --- | --- | --- |
| Nothing recorded | none | no `amount` key at all |
| `430.00` spent, `430.00` refunded | two | `"amount": "0.00"` |
| `150.00` refunded, nothing bought | one | `"amount": "-150.00"` |

An absent `amount` says "none recorded"; `"0.00"` says "these cancelled out", which is
what keeps a month of credits legible as one.

The conversion runs **before** the summing, and the order is the point: `?currency=`
quantizes each amount to cents, and converting then adding is what makes a total equal
what a reader adds up from `/api/expenses?currency=EUR`. That is why the summing lives in
`backend/src/expense_tracker/aggregation.py` in Python, over the rows `list_expenses`
returns. A bad `period` or `group_by` is a `422` carrying the same plain-string `detail`
as the refusals above.

### The range average

**The body carries a `summary` beside `items`**: one entry per currency, each naming that
currency and `average`, the mean of its period totals over the whole calendar the rows
span. It is what the totals view shows above the table, and answers "what does a month
cost" across the range.

```json
{
  "items": [{"period": "2026-01", "amount": "3498.56", "currency": "DKK", "...": "..."}],
  "summary": [{"currency": "DKK", "average": "3443.07"}]
}
```

**Both keys are always present.** An entry exists only for a currency that has expenses,
so `exclude_none` has nothing to drop here. A currency's entry is where a figure about the
whole range lives.

**The divisor is the same calendar the rows walk** - first matching expense to last, with
interior gaps counted - so a month nobody spent in pulls the figure down. A range filtered
wider than the data divides by the data, which is why the number can differ from what the
requested bounds suggest.

**It is the same whether or not `?group_by=` was sent.** Grouping re-keys the rows without
changing which expenses they sum, so both bodies carry an identical summary and a client
can read it from either. `test_the_range_summary_is_the_same_grouped_or_not` pins it on
both sides of the route. The quantization is a conversion's: `ROUND_HALF_UP` to cents, and
a cumulative credit too small to show at that scale is normalised from `-0.00` to `0.00`.

**No expenses means an empty summary**, the same `200` an empty `items` is: an empty
extent is an empty calendar, so there is nothing to average.

All four endpoints are read-only over HTTP. Rows arrive through
`pixi run backend-load-expenses` and `pixi run backend-load-currencies`, which is the
whole write path.

Those four routes are the whole surface: the frontend is a separate app, and the API
publishes no OpenAPI schema, `/docs` or `/redoc`. `backend/tests/test_app.py` asserts that
`/`, `/static/*`, any other `/api` path and the three docs routes all return 404, which is
what holds the surface at four.

## CORS

`create_app()` adds `CORSMiddleware` with `allow_origins=["*"]`, because the SPA is
served from its own origin and every call it makes is cross-origin.

`allow_credentials` is **`False`**, which is the pairing the CORS spec allows beside a
wildcard origin and the one browsers accept. This API sends no cookies and reads no
`Authorization` header. A real origin list is what the wildcard becomes the day it does.

The middleware is registered *after* the security-headers middleware, making it the
outermost of the two. That is what lets it answer a preflight `OPTIONS` itself.

## Database

PostgreSQL, holding four tables: `loaded_expense_file`, `expense` and `category`, which
together are a view of the files in `$EXPENSE_DATA_DIR`, and `currency_rate`, which is a
view of `backend/data/currencies/`. See [Loading expenses](#loading-expenses) and
[Loading exchange rates](#loading-exchange-rates).

The server is a **pixi dependency**. `postgresql` is pinned in `pixi.toml` beside python
and node, so `direnv allow` provisions it and the `db-*` tasks drive it. CI runs
`pixi run backend-db-init`, exactly what a developer runs.

### The cluster

`pixi run backend-db-create` runs `initdb` into `backend/.pgdata/` (gitignored), beside
the only code that talks to it. Three settings are baked into the generated
`postgresql.conf` rather than passed at launch, which is why `db-start` needs no flags:

| Setting | Value | Why |
| --- | --- | --- |
| `port` | `$PGPORT`, `5433` by default | Clear of a system PostgreSQL on 5432 |
| `listen_addresses` | `127.0.0.1` | Loopback only |
| `unix_socket_directories` | `/tmp` | The DSN is TCP |

The port comes from `backend/.env` (see [Configuration](#configuration)); the other two
are literals in the `db-create` task. Because all three are baked into the cluster rather
than passed at launch, changing `PGPORT` takes a `pixi run backend-db-reset` and a fresh
`backend-db-init` to take effect - `db-create` is a no-op against a `.pgdata/` that
already exists.

The superuser and the database are both named `expense_tracker`, so the DSN is
identical on every machine and on CI. Authentication is `trust`, which rests on
`listen_addresses`: this is a throwaway cluster holding public text, rebuildable at any
moment from `backend/schema.sql`. These `initdb` flags belong to this cluster alone.

All five tasks are idempotent, and the chain is `dev` depends on `db-init` depends on
`db-start` depends on `db-create` - so `pixi run backend-dev` brings the cluster up on
its way to the API and none of the five is one you normally run by hand.
`pixi run backend-db-init` is the one to reach for when you want the database up without
a server: the `postgres`-marked tests need it, and the two loaders do too.
`db-reset` throws the cluster away, which is how a change to an existing table lands,
`schema.sql` holding `IF NOT EXISTS` statements alone.

### Schema and access

`backend/schema.sql` is the entire schema and the only DDL, run by `db-init` and by
nothing else - the app issues none of its own, and a rebuild from the expense files takes
the place of a migration tool. Every statement in it is idempotent, because `db-init`
re-runs against live clusters. Generated keys use `GENERATED ALWAYS AS IDENTITY`, which
PostgreSQL's own [Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) page
recommends for new applications. The `LoadedExpenseFile`, `Expense` and `Category` models
declare the same tables a second time, in Python, with nothing checking the agreement;
change both together.

Access is SQLAlchemy 2 async over asyncpg, split across five modules:

| Module | Holds |
| --- | --- |
| `__init__.py` | `create_app()`, the route, the exception handler, `ExpensePayload` |
| `deps.py` | the lifespan, the per-request session, and the `provide_expense_repository` seam |
| `expense_loader.py` | the month-file parser and the `python -m` entry point - the only thing that writes |
| `expense_repository.py` | `LoadedExpenseFile`, `Expense`, `Category`, and the expense repository |
| `db.py` | the declarative `Base` every repository module builds on |
| `config.py` | the database connection settings, and nothing else |

A repository module holds its models, an **abstract base class**, its `Postgres*`
implementation and the `...UnavailableError` it raises, and imports nothing from
FastAPI - so it knows no status code. Callers depend on the base class; implementations
subclass it and carry `@override`, so the coupling is visible at the class declaration and
drift fails `backend-typecheck`. `expense_loader.py` is a *sibling* of `deps.py`, which is
what keeps FastAPI out of `python -m`.

The dependency arrows run one way, and are checked rather than merely intended: `pixi
run backend-lint` runs import-linter after ruff, against the contracts in
`backend/pyproject.toml`, which fail the build on an import pointing back up the stack,
on anything but `deps.py` learning about FastAPI, and on a cycle anywhere in the
package. `create_app()` holds the only handler that maps an exception to a 503.

The engine is owned by the app's **lifespan** and handed to requests as lifespan state,
from which a session is opened per request. That is what makes `create_app()` open no
socket, and what lets most of the test suite construct a real app with no database
anywhere.

`backend/tests/test_app.py` overrides the repository dependency with a fake and never
connects. Only `backend/tests/test_expense_postgres.py` talks to the real server, behind
the `postgres` marker registered in `backend/pyproject.toml`; it skips when nothing
answers, so a developer who has not run `db-init` gets a green suite, and **fails** under
`CI=true`, where a database is expected to be up.

### Loading expenses

**The expense files live in a separate private repository.** Real spending is
confidential and this repository is public, so `EXPENSE_DATA_DIR` in `backend/.env` is the
absolute path to the `data/` directory in your clone of that one, which keeps one month
file per bank there and its category vocabulary and decision maps in `meta/`. Keeping that
clone current is your job.

```sh
pixi run backend-load-expenses      # reads $EXPENSE_DATA_DIR/*.yaml into the database
```

**A missing directory loads nothing and succeeds.** A machine without the data repository
is an ordinary state, so the task says so and stops. An *unset* `EXPENSE_DATA_DIR` is the
other case - a shell that never ran `direnv allow` - and aborts on the same `${VAR:?}`
guard the `db-*` tasks use. A directory handed to the loader directly is still checked,
which is what surfaces a typed path:

```sh
cd backend && python -m expense_tracker.expense_loader ~/expnses   # error: not a directory
```

The twelve `sample-*.yaml` files under `backend/tests/data/expenses/` are the test suite's
fixtures and no task points at them. To fill a database from them anyway:

```sh
cd backend && EXPENSE_DATA_DIR=tests/data/expenses poe load-expenses
```

They carry the `sample-` prefix for a reason. `loaded_expense_file.filename` is unique on
the bare name, and the prefix is what keeps a fixture's name clear of a real
`nykredit-2026-01.yaml` in that ledger.

Files are `*.yaml`: one month file per bank and calendar month, named
`<bank>-YYYY-MM.yaml`, holding the bank's own export header, then every record that bank
exported for the month - the raw line as evidence, and beside it what the other repository
decided about it.

```yaml
---
header: '"Dato";"Beloeb";"Tekst";'
records:
  - record: '01-09-2026;-17000,00;"54790005551959";'
    extracted:
      datetime: '2026-09-01T00:00:00+02:00'
      action: discard
  - record: '01-09-2026;-2438,47;"BS E/F SOLBAKKEN";'
    extracted:
      datetime: '2026-09-01T00:00:00+02:00'
      key: BS E/F SOLBAKKEN
      action: import
      amount: '2438.47'
      currency: DKK
      category: Building
  - record: '03-09-2026;-340,00;"TRAIN TICKET";'
    extracted:
      datetime: '2026-09-03T00:00:00+02:00'
      key: TRAIN TICKET
      action: import
      amount: '340.00'
      currency: DKK
      category: Transport:Train
  - record: '04-09-2026;-240,00;"CAFE NEXT DOOR";'
    extracted:
      datetime: '2026-09-04T00:00:00+02:00'
      action: defer
```

**`extracted` is the whole of what this repository reads**, and only where its `action` is
`import`. A `discard` is a record the other repository decided against and a `defer` one
whose bank state is not terminal yet - a card payment the merchant has not claimed - and
either states just the two fields that place it in its file; `record` is read by nothing
here. An `import` states the rest.

| Field | Format | Notes |
| --- | --- | --- |
| `datetime` | RFC 3339, with an offset | The day it names is `expense_date`; the offset stands unapplied |
| `amount` | decimal | At most two decimal places; may be negative; non-zero |
| `currency` | ISO 4217 alpha-3 | Uppercase |
| `category` | a `:`-separated path | Each level stripped, non-empty, and slugging to something |
| `key` | the bank's own text for the record | Stripped and non-blank |

A third decimal place is refused by the loader, ahead of `numeric(12, 2)`. A negative
amount is accepted, a credit being a negative expense; a zero one is refused, with
`expense_amount_not_zero` as the database's backstop. A `category` outside the path shape
- `Food:`, `:Food`, `Food::Drink` - is refused by the loader, which names the file,
with `expense_category_is_a_path` behind it; a blank `key` is refused on the same terms,
`expense_key_not_blank` being its backstop. **Every field is read as text**, so `2438.47`
and the date-time both arrive quoted, clear of YAML 1.1's float resolution. The
`datetime`'s offset is required and stands unapplied: the date wanted is the one the file
states, which is the date the bank's own statement shows and the one the month file is
named for. `header` is read to confirm the YAML is a month file. A byte-order mark is
tolerated.

**Re-running the loader is a no-op**, and that is the ledger's doing, not the rows'.
`loaded_expense_file` records each file's name and the SHA-256 of its bytes; a file
already recorded with a matching digest is skipped whole. The expense rows carry neither a
content hash nor an `ON CONFLICT`: two identical records are two real purchases, such as a
pair of same-day fill-ups, and both belong in the month.

Each file is its own transaction: its ledger row, its expenses and the category rows it
introduces commit together or not at all, so a run that dies half way can simply be
re-run.

**The `category` table is derived**, which is a third shape beside the two loaders' own:
`expense` is append-only and `currency_rate` is replaced whole, while `category` is
extended and verified. Each file's load recomputes every slug from the stored rows plus
that file's own categories, refuses the file if a stored slug would move, and inserts the
nodes that are new, ancestors included. What it refuses and why is
[Category slugs](#category-slugs).

**Editing a loaded file is refused.** A known filename arriving with a different digest
stops the run, naming the file and when it was taken in, so the database stays the
read-only view of the files it was loaded from. Append a new file, or rebuild.

**With month files, that rebuild is the ordinary path rather than the exception.** The
other repository adds a later export's records to the month file they fall in, rewriting
it, so any import touching a month already loaded here arrives as an edit. A settling
`defer` is that same case - the record is replaced where it stands, so its month file
changes and the rebuild is what brings the completed expense in. A new month is a new
filename and loads on its own:

```sh
pixi run backend-db-reset && pixi run backend-db-init && pixi run backend-load-expenses
```

That rebuild is also the cure after `pixi run backend-test`, which TRUNCATEs the expense
tables before and after every test in `test_expense_postgres.py`, and `currency_rate`
around every test in `test_currency_postgres.py` - running the suite empties whatever you
had loaded.

It is the path for a **schema change**, too. Every statement in `schema.sql` is
`CREATE ... IF NOT EXISTS`, so `db-init` adds what is missing and leaves what is there as
it stands. Pulling a branch that changes a column or a table name means resetting the
cluster. A branch that only *adds* a table - as `currency_rate` did - takes `db-init`
alone. A table the loader fills - as `category` is - takes the reset all the same once
anything is loaded, the ledger skipping every file it has already seen.

### Loading exchange rates

```sh
pixi run backend-load-currencies    # replaces the rates with backend/data/currencies/*.tsv
```

Same file conventions - tab-separated, UTF-8, strict header, BOM tolerated, blank lines
skipped - over three columns.

| Column | Format | Notes |
| --- | --- | --- |
| `FROM_CURRENCY` | ISO 4217 alpha-3 | Uppercase |
| `TO_CURRENCY` | ISO 4217 alpha-3 | Uppercase |
| `EXCHANGE_RATE` | decimal | At most six decimal places; must be positive |

A seventh decimal place is refused rather than rounded away by `numeric(18, 6)`, and a
zero or negative rate converts nothing, so it is refused too.

**This loader replaces rather than appends**, where the expense loader above appends. A
rate for a pair is a current fact rather than an event: there is no ledger table, every
run deletes the rates it finds and inserts the file's, and **editing a rate and re-running
is the supported workflow**. Deleting and inserting share one transaction, so nothing ever observes the
table empty, and every file is parsed *before* anything is deleted, so a typo leaves the
loaded rates exactly as they were.

## Frontend

A React 19 SPA built by vite and styled with Tailwind CSS v4, configured in CSS via
`frontend/src/styles/app.css`.

The palette and the component classes come from [daisyUI](https://daisyui.com), enabled
as a `@plugin` in that same stylesheet. One theme is named: `dim --default`, which daisyUI
binds at `:where(:root)` so it applies whatever the operating system asks for. Colours are
written by role (`bg-base-100`, `text-base-content`, `alert-error`) and the theme points
them at its own palette.

The app is dark-only by choice, and `dim` is the soft end of what daisyUI ships - the
lightest of its dark themes, a desaturated blue-grey rather than black. The theme
declares `color-scheme: dark` itself, which is what keeps browser-painted UI - scrollbars,
native `<select>` popups, form controls - in step. Because that only reaches the browser
with the stylesheet, `index.html` repeats it as `<meta name="color-scheme" content="dark">`
so the first paint carries it. Swapping the theme means checking all of that still holds.

`pixi run frontend-build` writes to `frontend/dist/`, vite's default. It is
**gitignored**. CI runs the build as a gate over the bundler, which tsc and vitest leave
untouched, and keeps nothing from it.

`GET /api/expenses` is the app's main read, fetched at runtime with
[TanStack Query](https://tanstack.com/query) in `frontend/src/api/expenses.ts` and
rendered by `frontend/src/components/ExpensesTable.tsx` as one table of date, category,
amount and currency - the category cell holding the path and then the row's `key`, the
bank's own text for it, dimmed in parentheses. The payload *shape* is written out by hand
on both sides and the two must be changed together; a mismatch shows up as a 404 or a
failed shape guard at runtime. Every field is a string on the wire - `amount` included,
because JSON has no decimal type - so the guard rejects a numeric amount. Both values are
rendered as they arrive, except that a negative amount - a credit, money coming in - is
shown as `+` in green, the sign rewritten on the string alone, so the amount and the date
reach the page as the API spelled them. The rows keep the order the API sends them in
(oldest first), and an empty ledger arrives as a 200 with an empty `items` array, which
the table shows as a row.

### Choosing a currency

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

### Choosing a date range

A calendar beside the currency select picks the days the expenses are drawn from, and the
choice is the `?from_date=` and `?to_date=` the table asks the API for. **The filtering
stays the backend's** - it is a `WHERE` clause on `expense_date`, described under
[Asking for a range of dates](#asking-for-a-range-of-dates); the frontend sends two dates
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

### Choosing categories

A **Categories** control beside the currency select narrows both views to a selection of
categories, and that selection is the `?category=`, `?not_category=` and
`?category_default=` the table and the totals ask the API for - **each list repeats its
key once per value**, as described under
[Asking for one or more categories](#asking-for-one-or-more-categories). The filtering
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

### Routing

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

### Where the API lives

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

### Package manager

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

## Editor setup (Zed)

`.zed/settings.json` exists to make Zed **report** what CI enforces. Every entry does
one job: pin a language server to the version this repo pins. The linter and type-checker
settings stay in each stack's own config file, which is the single source for both. Read
the file itself for the per-server reasoning.

Preconditions: run `direnv allow` (for the basedpyright path under `.pixi/`) and
`pixi run frontend-install` (for the frontend servers under `frontend/node_modules/`), so
those paths exist for the servers to start from. `direnv allow` is also what puts the
database settings into the environment, so a test runner launched from inside the editor
reaches the local cluster when the editor inherits that environment - one started from a
shell direnv has blessed does.

`format_on_save` is left to your own Zed settings. Formatting is applied by
`pixi run frontend-format` and gated in CI by `pixi run frontend-format-check`, the same
way `ruff format` works on the Python side.

To confirm the declared pins match what is installed:

```sh
cd frontend && pnpm ls @tailwindcss/language-server @vtsls/language-server typescript tailwindcss prettier eslint
```

Expect `0.16.0`, `0.3.0`, `6.0.3`, `4.3.3`, `3.9.6`, `10.8.1`. One nested entry belongs
there: `@vtsls/language-server` bundles its own `typescript@5.9.3`, which the `tsdk`
setting in `.zed/settings.json` redirects to the pinned top-level copy.

To confirm Zed is using them, open a `.tsx` file **and** `frontend/src/styles/app.css`
first - Zed starts a language server when a buffer of a language it serves is open, so the
list below holds the servers with something to do - then run:

```sh
ps -eo pid,args | grep -E '[v]tsls|[c]ss-language-server|[e]slintServer'
```

Expect four processes. `@tailwindcss/language-server` ships **two** binaries and this
repo runs both, so that middle pattern is loose enough to match each:
`tailwindcss-language-server` completes class names in TSX, and `css-language-server`
is the Tailwind-aware CSS server named in the `CSS` block. The second one needs Zed
**1.16.1 or newer**, which is where the `tailwindcss-intellisense-css` adapter was added.

Paths under `frontend/node_modules/` mean the pins took effect; paths under
`~/.local/share/zed/` mean they did not - usually a missing `node_modules` or no `node`
on PATH for Zed's remote server. `eslintServer.js` is the exception and always runs from
`~/.local/share/zed/`, that server being Zed's own with only the module it loads pinned;
check it by putting `const x: any = 1;` in a `.tsx` file and confirming
`@typescript-eslint/no-explicit-any` fires.

Three things read as faults and are ordinary. Over a remote/WSL backend, Server Info
reports `Binary: Unknown` and `Version: Unknown` for `vtsls` however healthy it is, and
the per-server Logs tab is usually empty, most servers sending no `window/logMessage`.
Use the `ps` command above instead. Zed also underlines `tailwindcss-intellisense-css` in
`.zed/settings.json` as **"Property tailwindcss-intellisense-css is not allowed"** while
applying the setting; the same key in your own `settings.json` draws no warning. It is an
upstream schema bug: Zed builds the *project* settings schema from its language-attached
servers, where the *user* schema also includes opt-in ones (zed#46766), and this server is
opt-in. `ps` is the check that settles it. Where your editor disagrees with CI,
`pixi run backend-typecheck` and `pixi run frontend-lint` are the authority.

## Development tasks

`pixi run <task>` is the entry point, and the same command CI runs.

| Command | Delegates to | What it does |
| --- | --- | --- |
| `pixi run backend-db-init` | `poe db-init` | Create, start and apply the schema to the local database, without a server in front of it |
| `pixi run backend-db-create` | `poe db-create` | `initdb` a cluster into `backend/.pgdata/`, if there is not one |
| `pixi run backend-db-start` | `poe db-start` | Start the cluster on `$PGHOST:$PGPORT`, if it is not running |
| `pixi run backend-db-stop` | `poe db-stop` | Stop the cluster; succeeds if it is already stopped |
| `pixi run backend-db-reset` | `poe db-reset` | Stop the cluster and delete `backend/.pgdata/` entirely |
| `pixi run backend-dev` | `poe dev` | Start the database if it is not up, then run the API on uvicorn, port `$UVICORN_PORT` (with reloader) |
| `pixi run backend-test` | `poe test` | Run the test suite with coverage |
| `pixi run backend-lint` | `poe lint` | Lint with ruff, then check the import graph with import-linter |
| `pixi run backend-lint-fix` | `poe lint-fix` | Auto-fix lint issues (ruff only) |
| `pixi run backend-load-expenses` | `poe load-expenses` | Read `$EXPENSE_DATA_DIR/*.yaml` into the database, or nothing if that directory is absent |
| `pixi run backend-load-currencies` | `poe load-currencies` | Replace the exchange rates with `backend/data/currencies/*.tsv` |
| `pixi run backend-format` | `poe format` | Format with ruff |
| `pixi run backend-format-check` | `poe format-check` | Check formatting without writing changes |
| `pixi run backend-typecheck` | `poe typecheck` | Type-check with basedpyright (recommended) |
| `pixi run backend-image` | `poe image` | Build the API container image from the `backend` environment |
| `pixi run database-image` | `poe image` | Build the database container image: the PostgreSQL base plus `backend/schema.sql` |
| `pixi run frontend-install` | `pnpm install` | Install frontend dependencies (`--frozen-lockfile`) |
| `pixi run frontend-dev` | `pnpm run dev` | Run vite's dev server on port 5173 (hot reload) |
| `pixi run frontend-build` | `pnpm run build` | Build the frontend into `frontend/dist/` |
| `pixi run frontend-typecheck` | `pnpm run typecheck` | Type-check the frontend with tsc |
| `pixi run frontend-lint` | `pnpm run lint` | Lint the frontend with eslint (type-aware, plus CSS, `--max-warnings 0`) |
| `pixi run frontend-lint-fix` | `pnpm run lint-fix` | Auto-fix frontend lint issues |
| `pixi run frontend-test` | `pnpm run test` | Run the frontend tests (vitest) with coverage |
| `pixi run frontend-format` | `pnpm run format` | Format the frontend with prettier |
| `pixi run frontend-format-check` | `pnpm run format-check` | Check frontend formatting without writing changes |
| `pixi run frontend-image` | `pnpm run image` | Build the SPA container image from the `frontend` environment |

Every task sets its own working directory in `pixi.toml` (`backend/`, `database/` or
`frontend/`), so `pixi run <task>` behaves the same wherever you invoke it from. Each task
stays inside its own directory, and every one of them - the five `backend-db-*` included -
addresses its files by a plain relative path.

That holds when you skip the forwarder too: poe runs a task from the directory of the
`pyproject.toml` it loaded, so `poe -C backend db-start` resolves `backend/.pgdata/`
exactly as `cd backend && poe db-start` does. The *path* travels; the environment does
not. Run it from inside the worktree, where direnv has loaded, so the `${PGPORT:?}` guard
in a `db-*` task finds the port `.env` names. `pixi task list` prints this table's first
column.

CI runs every gate above on each pull request, then the SonarCloud scan. It leaves out the
two `dev` tasks, the two `-fix` variants, `backend-format`, the three `*-image` tasks, the
two loaders and the four `backend-db-*` tasks other than `backend-db-init`. The three
`*-image` tasks build rather than check, and are the only tasks reaching for a tool
outside the runner's pixi environment; `publish.yml` is what builds all three images on a
pull request. The loaders mutate data, and
`test_expense_postgres.py` and `test_currency_postgres.py` already put the committed
sample files through the real database path inside `backend-test`.

### Where commands are defined

The middle column is the whole mechanism - **every task in `pixi.toml` forwards.** Each
directory owns its own command bodies, in the manifest that already owns how its tools
behave:

- **Backend:** `[tool.poe.tasks]` in `backend/pyproject.toml`, beside the ruff, pytest
  and basedpyright config they invoke, with
  [poethepoet](https://poethepoet.natn.io) as the task runner.
- **Database:** `[tool.poe.tasks]` in `database/pyproject.toml`, which is a poe manifest
  and nothing else - no `[project]` table, no Python package. The one command that
  directory runs has to be defined in that directory for the rule above to hold, and a
  directory with no manifest has nowhere to put it.
- **Frontend:** the `scripts` block in `frontend/package.json`, where a Node developer
  expects it.

The two layers buy both properties at once: `pixi run` is a single discoverable index
across two ecosystems, and each directory stays a standalone project you can run
natively.

```sh
cd backend  && poe test    # poe with no task lists the backend's
cd frontend && pnpm test   # pnpm run lists the frontend's
```

The cost is that adding a command means two edits - define it in the stack's manifest,
then forward it from `pixi.toml`. Put the command body in the stack, never in the
forwarder.

## Environments

`pixi.toml` declares three, on one solve-group so every shared pin is identical across
them - python and the runtime libraries between `default` and `backend`, node and pnpm
between `default` and `frontend`:

| Environment | Contains | Used by |
| --- | --- | --- |
| `default` | runtime libraries, test tooling, node, PostgreSQL, and the app **editable** | the editor, local dev, CI, every task |
| `backend` | runtime libraries and the app as a **wheel** | what the API image is built from |
| `frontend` | node and pnpm, and nothing else | what the SPA image is built from |

The install mode is the difference that matters. An editable install is a redirect to
`backend/src`: nothing is copied, so the source tree stays where it was at install time,
which is what gives a developer edit, re-run, no reinstall. A deployment gets the wheel
instead, so an image carries an artifact rather than the source tree, `backend/data/` and
`backend/tests/` and a directory layout.

So the app is declared per feature rather than in the default feature, which is why
`[dependencies]` holds runtime *libraries* only:

```toml
[feature.dev.pypi-dependencies]
expense-tracker = { path = "backend", editable = true }

[feature.backend.pypi-dependencies]
expense-tracker = { path = "backend", editable = false }
```

`backend` gets a real wheel, built by hatchling, containing `src/expense_tracker` and
nothing else. **The split is about what ships, and the settings behave the same either
way.** The app reads its settings from the environment and opens no file, so a
misconfigured process refuses to start in either environment - which you can check
directly, clearing what direnv exported first:

```sh
pixi install -e backend
env -u DATABASE_URL -u PGHOST -u PGPORT -u PGUSER -u PGDATABASE \
  pixi run -e backend python -c "from expense_tracker.config import database_url; database_url()"
# ValidationError: set DATABASE_URL, or all of PGUSER, PGHOST, PGPORT, PGDATABASE
```

Swap `-e backend` for `-e default` and it fails identically: the app reads the
environment, whichever way it was installed.

`frontend` is a *toolchain* rather than a payload. It holds node and pnpm, it runs
`tsc -b && vite build`, and the SPA image ships `dist/` behind nginx instead. It is also
the only environment that declares `no-default-feature = true`: `[dependencies]` **is**
the default feature and is folded into every environment that does not opt out, so the
flag is what holds this one to node and pnpm. That leanness is what lets the SPA image
build from a context with no backend source in it, which in turn keeps a backend commit
from invalidating its layer cache.

`pixi run frontend-build` from a blessed shell still resolves through `default`, which is
what the editor and CI use; `pixi run -e frontend frontend-build` is the same build in the
lean environment, and the two produce byte-identical output.

Both are built by `release.yml` on a published release, and both can be built by hand the
same way CI builds them - `pixi run backend-image` and `pixi run frontend-image`, below.
The database image is published beside them but belongs to neither environment; it is
built from no pixi environment at all.

## Container images

Three images, each taking the repository root as its build context and each declaring
itself in a `docker-bake.hcl` beside its Dockerfile - the context, the Dockerfile and the
two OCI values only that image knows - so both the local task below and `release.yml`
build a target out of that file rather than passing those settings on a command line. All
three are published to Docker Hub by `release.yml`; see [Releases](#releases).

Two of them are one per stack, built from the lean pixi environment of the same name. The
database image is the odd one out and installs no environment at all: it is the official
PostgreSQL image plus `backend/schema.sql`, so it has no builder stage and carries nothing
of the lock.

### Keeping the bases current

All three Dockerfiles pin their runtime base as `tag@sha256:...`, the tag naming the
version a reader sees and the digest deciding what is pulled, and the `docker` entry in
`.github/dependabot.yml` moves that pair. One entry covers `/backend`, `/database` and
`/frontend`, weekly, and Dependabot rewrites the tag and the digest together.

Its commits are prefixed **`deps`**, so a base bump lands in `CHANGELOG.md` under
Dependencies and cuts a patch release. A base is part of what a user receives when they run
the image, which is the line [`CONTRIBUTING.md`](CONTRIBUTING.md) draws between `deps:` and
`ci:`, and that release is what republishes the image: `publish.yml` publishes when a GitHub
Release is published.

Three properties of the entry live outside the configuration:

- **The three-day `cooldown` applies to the SPA's and the database's bases.** Dependabot
  takes publication dates from Docker Hub's `tag_last_pushed`, which covers
  `nginxinc/nginx-unprivileged` and `postgres`; for `gcr.io` and `ghcr.io` it records a
  `cooldown_date_unavailable` warning and allows the update. `default-days` is the whole
  window, an update that moves a digest under an unchanged tag carrying no semver level.
- **The API's base arrives as a digest refresh on the `nonroot` tag**, which stays where it
  is: that is how a rebuilt distroless base reaches the image. The database's `18-alpine`
  behaves the same way, being a major-series tag that a new PostgreSQL minor keeps - so a
  18.6 to 18.7 move arrives here as a digest and nothing else. The SPA's `1.31-alpine`
  moves to another tag carrying the same `-alpine` suffix.
- **The pixi builder image is ignored.** That version is pinned by hand in three places,
  `use pixi` in `.envrc` and both Dockerfiles, and the root [`CLAUDE.md`](CLAUDE.md) records
  the trio; `update-pixi-dependencies.yml` bumps the pins *inside* `pixi.toml`. The ignore
  suppresses security updates for that image with it.

### The API image

`backend/Dockerfile` builds it out of the `backend` environment above, in two
stages: a `ghcr.io/prefix-dev/pixi` builder materialises the environment, and a
`gcr.io/distroless/base-nossl-debian12:nonroot` runtime stage receives the finished prefix
and nothing that produced it - no pixi, no package cache, no package manager, no shell.

```sh
pixi run backend-image
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user@host:5432/expense_tracker \
  expense-tracker-backend:dev
```

The build context is the **repository root** rather than `backend/`, because the
environment is declared across `pixi.toml` and `pixi.lock` and both of those live there.
`docker-bake.hcl` states it as `context = ".."`, which bake refuses to read until a caller
allows it - hence the `--allow=fs.read=..` in the task above, which CI needs none of
because `docker/bake-action` allows `fs=*` on its own.
The builder runs `pixi install --locked`, so an image resolves the same lock a developer
and CI do, and `.dockerignore` keeps this machine's own `.pixi/` prefixes out of the
context.

Four properties are worth writing down, because nothing checks any of them.

**The prefix keeps the path it was built at.** A conda prefix is not relocatable, and pixi
rewrites each console script's shebang to an absolute interpreter path inside it:

```sh
head -1 .pixi/envs/backend/bin/uvicorn
# #!/home/you/projects/expense-tracker/.pixi/envs/backend/bin/python3.15
```

So the builder works in `/app` and the runtime stage copies `/app/.pixi/envs/backend` to
that same path, source and destination matching for that reason. The entrypoint then names
the interpreter outright rather than the `uvicorn` script, which keeps the image from
depending on how pixi wrote that line at all.

**There is no shell, and nothing else either.** `/bin` and `/usr/bin` are empty in this
base, so `docker run --entrypoint /bin/sh` fails with `no such file or directory`, and
code execution inside the container finds no interpreter to pivot through. `PATH` names
the prefix alone for the same reason. The image declares no `HEALTHCHECK`: a shell-form one
needs that shell, and the API's surface is the four `GET`s.

**`pixi shell-hook`'s exports are written out by `ENV`.** With no shell to run an
activation script in, `PATH` and `SSL_CERT_FILE` are set by hand, and those two are the
whole substitution because every package pinned in `pixi.toml` ships without an activation
script. A package shipping one has its exports added there.

`SSL_CERT_FILE` restates OpenSSL's own default rather than correcting one. conda-forge's
openssl is built with its own `OPENSSLDIR`, so it reads `ssl/cert.pem` out of the prefix
and never `/etc/ssl` - the base's own `ca-certificates.crt` is present and goes unread -
and that default lands correctly only because the `COPY` puts the prefix back where it was
built. Naming the file keeps the trust store greppable in the Dockerfile instead of
compiled invisibly into libcrypto. There is no `SSL_CERT_DIR`: the prefix's `ssl/certs`
holds a `.keep` and nothing else.

**The image has no configuration defaults.** `DATABASE_URL`, or all four `PG*` names, has
to arrive at `docker run` time: `config.py` validates and the process refuses to start
otherwise, exactly as it does locally. `.dockerignore` excludes every `.env` variant, the
two committed ones included, so this checkout's loopback database cannot reach an image.

It runs as UID 65532 - distroless's `nonroot` - owns nothing it can write to, and listens
on 8000. The port is a literal, `docker run -p` being what maps a container port;
`UVICORN_PORT` is the `dev` task's alone.

**What `base-nossl` supplies.** The distroless family stacks up as `static` (no libc),
`base-nossl` (glibc), `base` (plus libssl and libcrypto), `cc` (plus libstdc++). glibc is
what the prefix needs, and it carries its own libssl, libcrypto and libstdc++ - `_ssl`
resolves `libssl.so.3` through the prefix's own RPATH - so `base-nossl` is the rung that
holds everything the image links. It is 24.6 MB where `base` is 33.1 MB, and the fourteen
entries between them (`libssl.so.3`, `libcrypto.so.3`, three OpenSSL engines, one module,
their dpkg records and their changelogs) are what a scanner inventories out of
`/var/lib/dpkg/status.d/` and reports CVEs against. Keeping them out keeps the release
gate reading only on libraries the application loads.

glibc is also what fixes the family: conda-forge publishes glibc builds, so every binary
in the prefix links it, and `gcompat` over musl does not cover what a CPython prefix asks
of libc.

Both bases carry a tag and a digest, the tag naming the version a reader sees and the
digest deciding what is pulled. Dependabot bumps the runtime one, on the terms
[Keeping the bases current](#keeping-the-bases-current) sets out; the pixi builder is pinned
by hand.

The image is about 396 MB, nearly all of it the prefix: a complete CPython plus the shared
libraries behind asyncpg, pydantic-core and SQLAlchemy. Two things in it are build-time
leftovers rather than runtime needs - some 14 MB of C headers under `include/`, and the
one linker binary that arrives because conda-forge's `python` hard-depends on
`ld_impl_linux-64`. Both sit behind the absent interpreter, and shedding either means
deleting it from the prefix, `pixi.toml` holding the dependency that brings it.

### The SPA image

`frontend/Dockerfile` builds it out of the `frontend` environment, in the same two stages:
the pixi builder installs node and pnpm and runs `tsc -b && vite build`, and an
`nginxinc/nginx-unprivileged:1.31-alpine` runtime stage receives `dist/` and nothing that
produced it - no node, no pnpm, no `node_modules`.

```sh
pixi run frontend-image
docker run --rm -p 8080:8080 -e API_BASE_URL=http://127.0.0.1:8000 \
  expense-tracker-frontend:dev
```

Alpine here against distroless there follows from what each image carries. This one
carries static files and a web server Alpine packages, where the backend's conda prefix is
glibc-linked. Alpine's shell is load-bearing as well: the configuration below is applied
by a shell script at startup.

**The configuration arrives at two different times, and that is the whole design.** The
backend reads `DATABASE_URL` from the environment when it starts. vite **inlines**
`import.meta.env.VITE_API_BASE_URL` into the bundle at build time, so the origin is fixed
by the time a container starts. One image serves every deployment, so the build bakes a
placeholder and the container rewrites it:

```sh
# in the builder, before vite build
printf 'VITE_API_BASE_URL=__EXPENSE_TRACKER_API_BASE_URL__\n' > frontend/.env.production.local
```

`.env.production.local` is vite's **highest-precedence** source in production mode, so it
beats the committed `frontend/.env` by a documented rule. `.gitignore`'s `.env*` rule makes
the file uncommittable and `.dockerignore`'s keeps a developer's own copy out of the
context, so it can only ever be the one that line writes.

`frontend/docker/40-api-base-url.sh` does the rewrite, from
`/docker-entrypoint.d/`, which the base image's entrypoint runs before starting nginx. It
is copied with `--chmod=0755`, the exec bit being what has that entrypoint run it: a file
there without one is logged and skipped.

The script refuses to start the container unless `API_BASE_URL` is an absolute `http(s)`
URL with no path - the backend's no-defaults rule, applied to the other stack:

```sh
docker run --rm expense-tracker-frontend:dev
# ERROR: API_BASE_URL is not set.
docker run --rm -e API_BASE_URL=http://host/gateway expense-tracker-frontend:dev
# ERROR: API_BASE_URL must be scheme://host[:port] with no path, query or fragment
```

That last refusal is the one worth having. All four `api/` modules resolve their requests
as `new URL("/api/expenses", API_BASE_URL)`, and an absolute path **discards** whatever
path the base carried, so the check is what reports a path at startup instead of at every
call site. The value is the origin the **browser** calls, so it is whatever a user's
browser can reach.

Three properties here are also unchecked by anything.

**The placeholder's survival is asserted at build time, not at run time.** esbuild does not
constant-fold `new URL(path, "__TOKEN__")`, so the token reaches the chunk as a string
literal - but that is a property of the minifier rather than a promise, so the Dockerfile
ends the builder stage with a `grep -rq` over `dist/` that fails the build while that holds
no longer. The startup script tolerates finding nothing, a container restarted on a
filesystem it already rewrote being the ordinary case, and the build-time check is what
keeps that tolerance from covering a bad build.

**The document root is `/srv/expense-tracker`**, a directory the `COPY` creates, so it
holds `dist/` and nothing the base shipped - the base's `/usr/share/nginx/html` arrives
carrying a stock `50x.html` that names nginx, where `server_tokens off` does not. The
`--chown=101:101` on that `COPY` is load-bearing: the startup script rewrites those files
as that user.

**`Cache-Control` is computed by two `map`s read by a single server-level `add_header`.**
`add_header` in a nested block **replaces** the inherited set rather than adding to it, so
keeping every header on one directive is what keeps the security headers on every
response. The response status is half the key, so the year-long `immutable` lifetime
belongs to a response that carries an asset and a `404` during a deployment stays
retryable.

```sh
curl -sI localhost:8080/                         # Cache-Control: no-store
curl -sI localhost:8080/totals                   # no-store - the SPA fallback, served the shell
curl -sI localhost:8080/assets/index-<hash>.js   # public, max-age=31536000, immutable
curl -sI localhost:8080/assets/missing.js        # 404, and no-store
```

`/totals` is a client-side route with no file behind it, so `try_files $uri $uri/
/index.html` answers anything that is not a real file with the shell. `/assets/` is the one
exception, resolving or `404`ing, so a missing chunk reaches the module loader as the 404
it is.

**The CSP is derived from what the bundle actually loads**, and is reported as
`default-src 'none'` plus four allowances. Three are unremarkable - one same-origin module
script, one same-origin stylesheet, `data:` images because daisyUI inlines its checkbox and
select glyphs into the CSS, and `connect-src` naming the one API origin. The fourth is
`style-src 'unsafe-inline'`, which the bundle asks for: React renders inline `style`
**attributes** for the date picker and the table column widths, and a style attribute is
governed by `style-src-attr`, which falls back to `style-src`. `style-src-elem 'self'`
sits beside it so the stylesheet itself keeps the tighter rule wherever a browser
implements that directive; Firefox ignores it. There is no `font-src`: the type scale is
system fonts and the bundle declares no `@font-face`.

The build context is the repository root here too, and `backend/pyproject.toml` is the one
backend file the build reads: `pixi install --locked` resolves the lock against it. pixi
validates the lock against the **whole** workspace, and the lock records the backend's pypi
path dependency, so that file has to be there even though this environment holds no python
at all. Only its metadata is read - `backend/src` stays out of the build - which is what
keeps a backend source change from invalidating any layer here.

The image is about 92 MB, and roughly 91 MB of that is the base: `dist/` is some 550 kB.
Compression is switched on in the server config because `nginx.conf` ships `#gzip  on;`,
and it earns its line - the one application chunk is 330 kB raw against 105 kB gzipped.
The base carries a tag and a digest on the same terms as the backend's two, and Dependabot
bumps it, with the three-day cooldown applying because this image lives on Docker Hub. See
[Keeping the bases current](#keeping-the-bases-current).

### The database image

`database/Dockerfile` is the odd one of the three: no builder stage, no pixi environment,
one `COPY`. It is `postgres:18-alpine` with `backend/schema.sql` dropped into
`/docker-entrypoint-initdb.d/`, the base's own hook for first-boot SQL.

```sh
docker run -d -v expense-tracker-data:/var/lib/postgresql \
  -e POSTGRES_USER=expense_tracker -e POSTGRES_DB=expense_tracker \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  tomborglum/expense-tracker-database:2.1.0
```

**The hook runs only when the data directory is empty**, and that is what makes this work
rather than a limitation to work around. It is the bargain `schema.sql` already strikes
locally: every statement idempotent, `IF NOT EXISTS` never altering, and a change to an
existing table cured by throwing the cluster away rather than by a migration. Here the
cluster is a volume, so **dropping the volume is what re-applies the schema** -
`backend-db-reset` by another name.

The image sets `POSTGRES_INITDB_ARGS=--locale=C --encoding=UTF8`, the two flags
`db-create` passes `initdb`. That is not decoration: `GET /api/expenses/categories` orders
`category` in SQL, and C collation is byte order under musl and glibc alike, so the
deployed server sorts exactly as the conda-forge cluster a developer runs. Declaring it in
the image rather than leaving it to the caller is what stops it being lost by whoever runs
the thing. `18-alpine` resolves to 18.6, the version `pixi.toml` pins, so the two agree
today without either naming the other.

**It runs as uid 70 and ships no `gosu`.** The base calls `gosu` in exactly one situation,
dropping from root to the `postgres` user, and all three of its call sites sit behind
`if [ "$(id -u)" = '0' ]` - so starting as 70 reaches none of them and the binary is
unreachable code. It was also 1.7 MB of Go carrying **26 HIGH/CRITICAL** findings into
[the vulnerability gate](#the-vulnerability-gate), in `net/http`, `crypto/tls`,
`encoding/xml`, `html/template` and `net/url`, none of which a program that resolves a user
and `exec`s could reach either. Deleting it takes this image to **zero** findings.

What that gives up is the other thing root does: `docker_create_db_directories` chowns the
data directory. A fresh **named** volume needs no chown, docker seeding it from the image's
own `/var/lib/postgresql`, which the base ships `70:70` and mode `1777`. A host **bind**
mount needs `chown 70:70` on the directory first, or `initdb` stops at
`mkdir: can't create directory '/var/lib/postgresql/18/': Permission denied`. An explicit
`--user 0` fails at once with `gosu: not found` and exit 127 rather than starting degraded.

`PGDATA` is the base's own `/var/lib/postgresql/18/docker`, underneath the volume it
declares - which is the whole `/var/lib/postgresql` directory rather than the pre-18
`data/` beneath it. That is the path to mount.

The image is about 433 MB and effectively all of it is the base; `schema.sql` is 8 kB. The
debian variant is 650 MB, but the reason for alpine is the gate rather than the size: 62
HIGH/CRITICAL in `postgres:18.6` with a fix available for **none** of them, against the 2
here, both of which `.trivyignore.yaml` already covered for the SPA's alpine base.

## Releases

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published, calling `.github/workflows/release.yml` to do
it. Four tags per image, derived once by `docker/metadata-action` so they cannot disagree:
`1.1.0`, `1.1`, `sha-<full commit>` and `latest`.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
```

**No one of those names is written down.** `publish.yml` names the directories, `backend`,
`database` and `frontend`, and `release.yml`'s `meta` job composes
`<namespace>/<repository>-<directory>` from them - the namespace an input that
`publish.yml` fills from the `DOCKERHUB_NAMESPACE` repository variable, the repository
read from `github.event.repository.name`. **So renaming this GitHub repository renames
what a release publishes to**, which `CLAUDE.md` carries as a pair that nothing checks.
The composition is logged on every pull request run.

The same job derives the OCI metadata: eight `org.opencontainers.image.*` values, carried
twice over, as labels in the image config and as annotations on its manifest, so a
registry client can read `source` and `revision` without pulling the image. Two of the
eight do not come from there, because metadata-action reads them from the **repository**
and so hands every image the same answer - which had the SPA image advertising the REST
API and titled both of them `expense-tracker`:

- **`title` and `description` are the image's own**, declared in its `docker-bake.hcl`
  beside the context and the Dockerfile and nowhere in the workflow. The image is what
  knows what it is; the pipeline knows how to combine the pieces.

Merging those two with the shared set is what the `build` job uses `docker buildx bake`
for rather than a plain build. metadata-action writes its labels and annotations out as
bake files of their own, and bake merges a list of files onto one target: `labels` is a map
and merges per key, so a key the stack names wins and every shared one survives, and
`annotations` is a list and is appended, a repeated key resolving last-wins in the built
image. **The stack's own file is therefore loaded last**, which is what puts its `title`
and `description` on the published image.

The target is spelled `image` in four places: both bake files, metadata-action's
`bake-target`, and the build step's `targets` and `set:` keys. Those four agreeing is what
lands the overrides on the target the stack declares, and nothing reports a mismatch, which
is why `CLAUDE.md` carries that pair.

Both values are set as a label *and* as an annotation, so each lands in its own place - the
image config and the manifest - and the pair reads the same from either. Both come from the
build command: a Dockerfile `LABEL` writes the config alone, and a `--label` on the command
takes precedence over it.

It is a release workflow rather than a deployment workflow. Its whole output is a tag on
Docker Hub, and when such a tag becomes live somewhere is a separate concern, so the
workflow involves no GitHub Environment and files no deployment records.

### Why it is three jobs

```
publish.yml  ->  meta  ->  build (matrix: backend, frontend)  ->  push
                 \____________ release.yml ____________________________/
```

`publish.yml` is the caller and holds the triggers, the concurrency group and both
inputs: the **directories** to build and the **namespace** to publish under.
`release.yml` is called, and holds everything about how an image is built, scanned and
pushed. The filenames look inverted on purpose - the AWS trust policy below pins
`job_workflow_ref`, which names the **called** workflow, so `release.yml` keeping its
path is what leaves that policy alone.

**The split exists for one reason, and it is the only interesting thing about the file.**
`build` runs repository code: a Dockerfile, `pixi install`, `pnpm install`. A malicious
dependency in any of those is one layer away from push access to published images, so
`build` is the only job that checks the repository out, and it is granted `contents: read`
and **no `id-token: write`**, so the token AWS accepts is out of its reach. `push` is the
mirror image: it holds the credentials and **checks nothing out**, so everything that
executes in it is either a SHA-pinned action or a `run` block written in the workflow file
itself. `CLAUDE.md` carries the split as an invariant.

`build` hands `push` an OCI archive through an artifact, along with the digest it built.
Untrusted bytes are safe to hand over precisely because `push` never executes them - it
copies them to a registry. `push` re-derives the digest after staging and fails if it
moved, so "what was scanned" and "what was published" are provably the same bytes rather
than two numbers compared by eye.

Each artifact also carries **the repository its image publishes to**, which is why no step
in `push` names a directory or a repository: it iterates the artifacts it was handed. That
name is composed in one place - `meta`'s `images` step - and both consumers read it back
out of there, so the tags and the artifacts cannot spell a repository differently. Before
anything is copied, `push` still compares the two sets, which is what catches a count that
does not match: a build that uploaded nothing, or an artifact that arrived twice, would
otherwise publish a partial release quietly.

### How the credential is reached

Docker Hub supports no OIDC for personal accounts, so AWS stands in as the intermediary:
the job mints a GitHub OIDC token, exchanges it for temporary credentials on an AWS role
whose trust policy only accepts this repository's release workflow at a version tag, and
reads a Docker Hub PAT out of SSM Parameter Store. `oidc-smoke-test.yml` proved that path
and remains the cheapest way to diagnose a claim mismatch.

Three details carry the weight:

- `aws-actions/configure-aws-credentials` runs with `output-credentials: true` and
  **`output-env-credentials: false`**, so the temporary credentials become step outputs
  rather than job environment variables. Steps that need them name them; the rest never
  see them.
- The PAT is piped **straight** from `aws ssm get-parameter` into
  `docker login --password-stdin`, so it never occupies a shell variable, a step output or
  a file. Every step after it needs no secret: `regctl` and `cosign` both read what
  `docker login` wrote.
- `cosign-installer` runs **before** `regctl-installer`, which is load-bearing rather than
  tidy. The regctl installer verifies the binary it downloads against regclient's cosign
  signature `if [ -x "$(command -v cosign)" ]`, so cosign being on `PATH` already is what
  gets that verification run.

**`regctl` does the push itself.** It copies the local OCI layout's index byte for byte,
which is what keeps one digest across the scan, the push, the attestations and the
signature, and carries the multi-platform index and its attestations as they are.

**The published images are x86-64, and for two of the three the platform comes from the
lock.** `pixi.toml`'s `platforms = ["linux-64"]` is the declaration: the API and SPA images
install from `pixi.lock`, which carries that solve and no other, so `pixi install --locked`
is where their architecture is decided, and the bake file and the workflow name no
platform. **The database image is the exception** - it installs no environment at all, and
`postgres:18-alpine` publishes eight platforms, so what holds that one to x86-64 is the
architecture of the runner it is built on and nothing in this repository. Adding
`linux/arm64` starts with the lock gaining that solve, and with this image needing to name
a platform it can leave implicit today.

Each image carries an SBOM and a SLSA provenance attestation, the provenance at
`mode=max`. That is a deliberate choice with one consequence worth knowing, because it is
published rather than merely logged: `mode=max` records the **whole GitHub event payload**
under `buildDefinition.internalParameters.github_event_payload`, which on a pull request
is around 6 kB of a 52 kB predicate and includes the pull request body. It holds here
because this repository is public, so the payload carries nothing that is not already
public, and `mode=max` is what keeps the build detail in the provenance.

### The vulnerability gate

Each image is scanned by Trivy before anything is published, and a HIGH or CRITICAL
finding fails the release. The scan runs over the **unpacked** OCI layout, which is the
form Trivy walks: it rejects an OCI archive outright, and a layout written by
`regctl image import` leads with a referrers index, which Trivy reads first, resolves
nothing from, and then reports zero vulnerabilities and success.

So the gate makes **two** assertions, and the first is about identity: the `ImageID` Trivy
reports - the digest of the image config it read - has to name a config that is present in
the layout just scanned **and** declares a platform. That is what tells a clean scan from
a scan that examined nothing.

The direction matters. Pointed at a layout it cannot walk, Trivy resolves the empty config
`{}` - `sha256:44136fa3...` - reports no findings and exits 0, and that blob **is** in the
layout, beside the image, as the attestation manifest's own config. So the check reads
Trivy's claim against the layout, where `{}` declares no platform, rather than walking the
layout to derive what Trivy should have reported, which can land on that same empty value
from both sides and agree with itself. It is a check on the platform rather than on
Trivy having resolved an operating system, so a legitimately clean image passes whatever
package database either base carries. It extends the chain the push job ends: bake's
digest, the archive, the scanned config, the imported digest, the signature.

Suppressions live in **`.trivyignore.yaml`**, and every entry carries an `expired_at`
date. On that date Trivy stops honouring the entry and the finding fails the release
again, so a suppression cannot outlive its reason by being forgotten. The entries there
today are two CVEs in the frontend's nginx base that are fixed in alpine 3.24.3 while the
image is still built on 3.24.2 - the pinned digest is already the newest that tag
resolves to, so only an upstream rebuild clears them, and neither is reachable in an image
that loads no brotli module and never invokes curl.

### Residual risk

Trust is pinned to `release.yml` at a version tag, but that file is still repository
content, so anyone able to create a matching tag carrying an altered `release.yml` could
reach the role. What bounds it is the `main-protection` ruleset - changes to that file land
only through a reviewed PR - and tags being created by release-please from `main`.

### The AWS objects

Created once, by hand, in region `eu-north-1`. `<account-id>` below is the 12-digit AWS
account id, which is why the role ARN is a repository **variable** and never a literal in
the workflow: it keeps the account id out of a world-readable file and out of the diff,
while `mask-aws-account-id` is what keeps it out of the log.

Everything here sits inside AWS's **always-free** tier, which is a standing constraint on
what gets created. IAM, STS, the OIDC provider, a standard-tier SSM parameter and the
AWS-managed `aws/ssm` key carry no monthly charge, and one `kms:Decrypt` per release sits
far inside the free 20,000 requests a month. The shared `aws/ssm` key is also what makes
the parameter ARN below the whole isolation boundary; this account holds two principals -
an administrator with access to every parameter under any key, and a release role scoped to
one parameter - so that scoping is where the separation lives.

1. **Docker Hub.** Both repositories created explicitly, so their visibility is set before
   the first push, and both **public**, which Docker Personal allows without limit. Then
   a personal access token with **Read & Write** and no Delete; a personal-account token's
   scope is the account.

2. **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
   tier**, encrypted with the default `alias/aws/ssm`. Standard tier is load-bearing
   twice: it is the free one, and it encrypts with the `kms:Decrypt` the policy below
   grants, where an advanced parameter uses `kms:GenerateDataKey`.

3. **IAM role** `gha-expense-tracker-release`, created as a Web identity role against the
   existing `token.actions.githubusercontent.com` provider with audience
   `sts.amazonaws.com` and nothing attached. The trust policy the wizard generates is
   roughly `repo:TomBorglum/expense-tracker:*` - any ref, any workflow - and is replaced
   wholesale:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "GitHubActionsReleaseTagsOnly",
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:TomBorglum/expense-tracker:ref:refs/tags/v*",
             "token.actions.githubusercontent.com:job_workflow_ref": "TomBorglum/expense-tracker/.github/workflows/release.yml@refs/tags/v*"
           }
         }
       }
     ]
   }
   ```

   `Principal.Federated` is the OIDC provider, which represents **GitHub Actions as a
   whole** - every repository on github.com - so the `Condition` block is the entire
   security boundary. The two `StringLike` conditions each pin one half: `sub` holds the
   ref to a version tag in this repository, and `job_workflow_ref` holds the workflow to
   this file.

   **The key is `job_workflow_ref`.** AWS maps the claims its condition-key reference
   lists: `actor`, `actor_id`, `job_workflow_ref`, `repository`, `repository_id`,
   `repository_owner_id`, `workflow`, `ref`, `environment` and `enterprise_id`, beside
   `sub` and `aud`, so those are the keys a condition here can read. A `StringLike` on a
   name outside that list leaves the one `Allow` statement unmatched, and STS answers
   `Not authorized to perform sts:AssumeRoleWithWebIdentity`, naming no condition, with
   every other part of the exchange correct - which is what `workflow_ref` as a key name
   looks like. AWS describes `job_workflow_ref` as the *reusable* workflow's path; GitHub
   populates it on every job, equal to the `workflow_ref` claim wherever no reusable
   workflow is involved, and the claim dump carries both. **`release.yml` is now a called
   workflow**, invoked by `publish.yml`, so `job_workflow_ref` is its path rather than the
   caller's - which is exactly the value pinned here, and why the split needed no change
   to this policy. The `sub` claim is the caller's and is also unchanged. Moving or
   renaming `release.yml` is what would move this condition.

   **IAM Access Analyzer warns** that the `*` in `sub` "can allow requests from more
   sources than you intended" and recommends naming a branch. The check fires on a
   wildcard's presence; this one sits after the owner, the repository, the `ref:` claim
   type, `refs/tags/` and the `v`, so all it admits is which version number, and a release
   has a tag where the advice reads a branch. `StringLike` offers `*` and `?`, and `?`
   matches any character, so `v*.*.*` is the narrowest shape it can express. Save through
   it.

   Then one inline policy: `ssm:GetParameter` on the one ARN and `kms:Decrypt` via SSM, so
   the role reads that parameter and lists nothing under `/expense-tracker/`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadDockerHubPat",
         "Effect": "Allow",
         "Action": "ssm:GetParameter",
         "Resource": "arn:aws:ssm:eu-north-1:<account-id>:parameter/expense-tracker/release/dockerhub-pat"
       },
       {
         "Sid": "DecryptViaSsmOnly",
         "Effect": "Allow",
         "Action": "kms:Decrypt",
         "Resource": "arn:aws:kms:eu-north-1:<account-id>:key/<aws/ssm key id>",
         "Condition": {
           "StringEquals": { "kms:ViaService": "ssm.eu-north-1.amazonaws.com" }
         }
       }
     ]
   }
   ```

   **With a shared key the isolation boundary is that parameter ARN alone.** `aws/ssm`
   carries a fixed policy granting `kms:Decrypt` to `"Principal": {"AWS": "*"}` for any
   caller in the account authorised for SSM, so the exact parameter path above - a literal
   rather than a prefix - is what holds this role to its own parameter and away from the
   smoke test's under the same key.

4. **GitHub repository variables.** `AWS_RELEASE_ROLE_ARN`, set to
   `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, and
   `DOCKERHUB_NAMESPACE`, set to `tomborglum` - the namespace `publish.yml` passes to
   `release.yml`, which has to be the account the PAT above belongs to. `AWS_REGION`
   already exists for the smoke test.

### Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*expense-tracker.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

`cosign verify` is the only view of the signature from outside. `cosign-installer`'s
default is cosign 3 - v3.0.6 at `v2.0.0` - which attaches the signature as an **OCI 1.1
referrer** instead of writing a `sha256-<digest>.sig` tag, so a tag listing shows the four
published tags and nothing more. The sign step's log is terse for the same reason: the v3
bundle carries the Rekor entry, so no tlog index is printed. That version is the
installer's, not this repository's - the step pins the action by SHA and takes whatever
cosign it ships, unlike `regctl-installer` beside it.

The `push` job's log is the other half: the claim dump shows the `sub` and
`job_workflow_ref` the trust policy was written against, and it is the only place the
tag-shaped claims can be observed, the smoke test running on `workflow_dispatch` from a
branch and so seeing branch-shaped ones.

**If the exchange is refused**, read the claim dump, correct the trust policy in the
console and re-run the failed job: the AWS side lives outside the tag, so that loop is
free. **If the workflow file itself is wrong**, a `release` event runs the file as it
exists on the tag, so the fix is a `fix:` PR and the patch release it cuts. The
`pull_request` trigger is what exercises the file ahead of that: every pull request builds,
scans and gates all three images, with the `push` job held back by
`if: github.event_name == 'release'`, so the change that touches the file runs it. The
trigger covers every path, keeping what it watches in one place with what the Dockerfiles
read, and a superseded pull request run is cancelled where a release run runs to the end.

## Deployment

**`compose.yaml` is the deployment.** There is no chart, no manifest and no deploy script
beside it: one file describing the three images as three services, plus the two loaders
behind a `load` profile, on one network with one volume. The target is a single host - a
laptop - and `docker compose up` is the whole operation.

Every service names an `image:` and none a `build:`. That is a hard rule rather than a
preference: `docker compose publish` refuses a service carrying `build` without `image`,
and the file is meant to be published as an OCI artifact and loaded on a machine holding no
checkout, where there is nothing to build from anyway.

### The services

| Service | Port | What it is |
|---|---|---|
| `database` | none | The database image, which carries `schema.sql` and applies it on an empty data directory. Trust auth, reachable on the compose network alone. |
| `backend` | `8000` | The API. Published because the **browser** calls it. |
| `frontend` | `8080` | The SPA, nginx serving the bundle, with the API origin substituted at container start. |
| `load-currencies` | - | `profiles: ["load"]`. One shot, over the API image, reading `/currencies`. |
| `load-expenses` | - | `profiles: ["load"]`. One shot, over the API image, reading `/expenses`. |

The database publishes **no port**, which is what makes trust auth safe - the same bargain
`db-create` strikes with `--set=listen_addresses=127.0.0.1` for the local cluster, and the
reason `docker compose up` needs no arguments and nothing published holds a credential.
Adding a `ports:` entry to that service would publish an unauthenticated superuser to the
host.

`backend` waits on `database` being **healthy**, not merely started. The API answers `200`
with an empty `items` array against an empty table, so a database still applying its schema
would not fail loudly - it would serve plausible, wrong, empty answers. The healthcheck is
`pg_isready -h 127.0.0.1`, and the `-h` is load-bearing: without it `pg_isready` uses the
unix socket, which the entrypoint's init-phase temporary server answers while the schema is
still being applied. That temporary server is socket-only, so over TCP readiness and init
completing are the same moment.

Neither `backend` nor `frontend` declares a healthcheck. The API image is distroless and
holds no shell, no curl and no wget, so there is nothing in it to probe itself with, and
adding one would mean adding a binary to a published image to serve compose.

### Running it from this checkout

The three image references default to the local `:dev` tags, which are exactly what the
`*-image` tasks build, so a checkout needs no variables at all:

```sh
pixi run backend-image && pixi run database-image && pixi run frontend-image
docker compose up -d
```

The SPA is then on <http://localhost:8080> and the API on <http://localhost:8000>. **8000
is also the port `pixi run backend-dev` binds**, so the two cannot run at once; stop one
before starting the other, or move the stack with the variables below.

Which images it runs is two variables:

```sh
EXPENSE_TRACKER_IMAGE_PREFIX   # default `expense-tracker`
EXPENSE_TRACKER_VERSION        # default `dev`
```

They compose as `<prefix>-<service>:<version>`, which is the shape
[Releases](#releases) composes published names in, so pointing the stack at a release is
one setting and **no published name is written down in this file either**:

```sh
EXPENSE_TRACKER_IMAGE_PREFIX=<namespace>/expense-tracker \
EXPENSE_TRACKER_VERSION=2.1.0 docker compose up -d
```

Where the browser should reach the API is a third, `EXPENSE_TRACKER_API_BASE_URL`,
defaulting to `http://localhost:8000`. It cannot be `http://backend:8000`: the bundle runs
in the host's browser, where that name does not resolve. The SPA image's entrypoint refuses
an absent value and one carrying a path, so a mistake here stops that container rather than
serving an app that reaches nothing. Moving the API off host port 8000 means editing the
`ports:` entry and setting this variable to match.

### Loading data

The two loaders are one-shot, so `run --rm` is the precise form and reaches a profiled
service without naming the profile:

```sh
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`docker compose --profile load up -d` is the other form, and brings the whole stack up with
both loaders alongside it.

The loaders keep the differing reload shapes [Loading
expenses](#loading-expenses) and [Loading exchange rates](#loading-exchange-rates)
describe: currencies replace the whole rate table every run, and expenses are append-only
with a ledger that **refuses** a file whose contents changed.
So a reclassified month is not cured by re-running `load-expenses`. It is cured by throwing
the database away:

```sh
docker compose down -v                     # drop the volume: this IS the wipe
docker compose up -d                       # a fresh volume re-runs schema.sql
docker compose run --rm load-currencies
docker compose run --rm load-expenses
```

`down -v` drops the one named volume, the image's `initdb.d` re-applies `schema.sql` on the
empty data directory it leaves behind, and both loaders start from nothing. **No backend
code exists for that sequence and none is needed** - which is the whole reason the schema
travels in the image rather than being applied by a step of its own.

### The two directories it mounts

```sh
EXPENSE_TRACKER_CURRENCIES_DIR   # default ./backend/data/currencies
EXPENSE_DATA_DIR                 # default ./backend/tests/data/expenses
```

Both are mounted read-only, and both must be readable by **uid 65532**, which is what the
API image runs as.

`EXPENSE_DATA_DIR` is the name `backend/.env` already carries, so **a blessed shell points
`load-expenses` at the private expense repository with no further setting** - the committed
fixture default applies only where that variable is unset. To load the synthetic fixtures
in a shell that has it, override it for the one command.

Both mounts are declared in long syntax carrying **`create_host_path: false`**, and that is
the one setting here with data loss behind it. Compose creates a missing bind source by
default, and the currency loader replaces the whole rate table from whatever it finds, so an
empty directory **deletes every rate** and reports `0 files read` with exit 0. Refusing to
create the path turns a mistyped directory into a container that does not start:

```
Error response from daemon: invalid mount config for type "bind":
bind source path does not exist: /...
```

### What publishing it will change

Nothing publishes this file yet. The `oci://` path was rehearsed end to end against a
throwaway local registry before any workflow is written to depend on it, and three things
it found are worth writing down here, because none of them is guessable from the compose
documentation:

- **A relative bind source resolves against compose's download cache**, not the current
  directory, when the file is loaded from `oci://`. The two defaults above are relative and
  correct for a checkout; a deployment holding no checkout names both directories
  **absolutely**, in a `.env` beside wherever the deploy command runs. That `.env` is then
  the only state the host keeps.
- **Loading an `oci://` file prompts** for the interpolation variables and the sources they
  resolved from, every time. `docker compose up` takes `-y` for it. `docker compose run`
  has **no such flag**, so it wants a `y` typed - or `printf 'y\n' |` ahead of it with
  `-T`, which is what a script needs.
- **`COMPOSE_FILE` cannot carry an `oci://` reference.** Compose splits that variable on
  `:`, so the value becomes three nonexistent paths. Pass `-f oci://...` instead, or set
  `COMPOSE_PATH_SEPARATOR=,` first.

The project name is pinned to `expense-tracker` in the file rather than taken from the
directory, so the volume is `expense-tracker_database-data` wherever the file is loaded
from and `down -v` reaches the same one every time.

## Configuration

Where this checkout's backend listens is written down once, in **`backend/.env`**: the
four facts `psql` and `createdb` already read, the port `uvicorn` already reads, and where
the expense files are.

```
PGHOST=127.0.0.1
PGPORT=5433
PGUSER=expense_tracker
PGDATABASE=expense_tracker
UVICORN_PORT=8000
EXPENSE_DATA_DIR=$HOME/projects/expense-data/data
```

`EXPENSE_DATA_DIR` is the odd one out, and knowingly so: it is the only value here that is
a fact about a *machine* rather than about the project, because it points outside the
checkout at the `data/` directory inside a clone of the private data repository. direnv
expands `$HOME` as it loads the file, so the committed default is a real path wherever the
clone sits beside this one; anywhere else, set it in **`backend/.env.local`**, which
`.envrc` loads after `backend/.env` and which is gitignored, so no tracked file carries one
machine's layout. Unset and set-but-absent differ: unset aborts on the guard, and
set-but-absent loads nothing and succeeds, which is what tells a machine without the data
repository from one whose shell was never blessed. See
[Loading expenses](#loading-expenses).

Every one of them is a name the tool itself looks for, which is why no task passes
`--host`, `--port` or `--username`. `UVICORN_PORT` is the API's half of that: uvicorn's
CLI is a click command carrying `auto_envvar_prefix="UVICORN"`, so it resolves `--port`
from the environment on its own, and `poe dev` stays the same command it was. That is
what lets a second checkout run its API beside the first the same way it runs its cluster
beside the first - by editing this one file.

**The application never opens that file.** `config.py` reads the environment and nothing
else, resolving no path in the package. Loading a dotenv file is the job of whatever
*launches* the process, and `.envrc` is the one launcher that does it here:

```sh
# .envrc
dotenv_if_exists backend/.env
dotenv_if_exists backend/.env.local
```

**So `direnv allow` is a prerequisite.** `.envrc` is the single source of these names:
`pixi run` reads no `.envrc` and `pixi.toml` declares no `[activation.env]`; poe declares
no `envfile`. In a shell direnv has not blessed, the app raises a `ValidationError` naming
the missing settings and every task that reaches a server aborts on a `${PGPORT:?}` guard
first - `backend-db-init` on its own, and `backend-dev` on the one in the `db-create`
behind it, before uvicorn ever binds.

CI gets the same names the same way: `setup-direnv` activates this `.envrc` and forwards
the resulting environment to `$GITHUB_ENV` for the steps after it.
`.github/workflows/ci.yml` calls it directly;
`.github/workflows/update-pixi-dependencies.yml` reaches it through the reusable workflow
it delegates to, which activates this same `.envrc` for the pixi version its `use pixi`
line pins. It is the first thing to check if CI ever fails to find `PGPORT`.

One loader covers everything, including what no task wraps:

```sh
psql                                              # the local cluster, no flags
pytest tests/test_expense_postgres.py -k truncate --pdb
python -m expense_tracker.expense_loader ~/exports # a directory other than the configured one
```

`PGHOST`, `PGPORT`, `PGUSER` and `PGDATABASE` are the variables libpq itself reads, so
`psql`, `pg_dump` and friends need no arguments, and a test run started from your editor
reaches the same cluster as `pixi run backend-test`. `backend/.env` is the one place these
names are written, and `pixi.toml` declares none of them.

That split is what makes the deployed path and the local path one code path: the app reads
the environment, as 12-factor has it and as a container supplies it, and a launcher is what
turns a dotenv file into that environment. A wheel-installed package then needs no project
directory to find, deriving no path from `__file__`.

Precedence is short: `backend/.env` *overwrites* what is already in the environment, so
`export PGPORT=...` in your shell leaves the port as the file states it, and
`backend/.env.local` overwrites that in turn. Above both sits `DATABASE_URL`, which the app
prefers over the four parts.

The DSN itself is built per call. `config.py` assembles it with `sqlalchemy.URL`, which
takes the port as a number of its own and escapes any part containing `@`, `:` or `/`.
`database_url()` returns a `URL` rather than a `str`, so `str()` and `repr()` render any
password as `***`, keeping a DSN that reaches a log or a traceback free of one.
**`DATABASE_URL` overrides the four parts wholesale**, and that is the deployment path.
**A deployment supplies its own.**

Every one of them is **required**. With no `DATABASE_URL` and none of the four names in the
environment, the process refuses to start and names every missing one. The environment is
the whole input, in every environment.

To move either port off something else has taken, edit **`backend/.env`** itself, a dotenv
overwriting the ambient environment. `PGPORT` is baked into the cluster at `initdb` time,
so follow that edit with `pixi run backend-db-reset && pixi run backend-db-init`;
`UVICORN_PORT` takes effect on the next `pixi run backend-dev`.

That leaves the file as a committed default you edit in place, which shows up as a dirty
working tree. A port is one of the facts this file exists to state once, so moving it
changes a shared default; `backend/.env.local` is where a value that names a machine goes.

Worth knowing: `.gitignore` ignores **every** `.env` variant and names back only the two
committed defaults, so a `backend/.env.production` you create is untracked as a rule.

The frontend has exactly one variable of its own, `VITE_API_BASE_URL` - see
[Where the API lives](#where-the-api-lives).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, Conventional Commit, and
squash-merge rules. To report a security issue, see
[`SECURITY.md`](SECURITY.md) - please do not open a public issue for one.

## License

MIT. See [`LICENSE`](LICENSE).
