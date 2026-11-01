# The database

The schema, and how the two loaders read their files.

## Schema and access

`backend/schema.sql` is the entire schema and the only DDL, run by `db-init` and by
nothing else - the app issues none of its own, and **a rebuild from the expense files
takes the place of a migration tool**. Every statement is `CREATE ... IF NOT EXISTS`,
because `db-init` re-runs against live clusters. Generated keys use
`GENERATED ALWAYS AS IDENTITY`, per PostgreSQL's own
[Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) page. The
`LoadedExpenseFile`, `Expense` and `Category` models declare the same tables a second
time in Python, with nothing checking the agreement; change both together.

Access is SQLAlchemy 2 async over asyncpg. A repository module holds its models, an
**abstract base class**, its `Postgres*` implementation and the `...UnavailableError` it
raises, and imports nothing from FastAPI - so it knows no status code. Callers depend on
the base class; implementations carry `@override`, so drift fails `backend-typecheck`.
`expense_loader.py` is a *sibling* of `deps.py`, which is what keeps FastAPI out of
`python -m`. The dependency arrows are checked rather than intended: `backend-lint` runs
import-linter against the contracts in `backend/pyproject.toml`, failing the build on an
import pointing back up the stack, on anything but `deps.py` learning about FastAPI, and
on a cycle anywhere in the package.

The engine is owned by the app's **lifespan** and handed to requests as lifespan state,
which is what makes `create_app()` open no socket and lets most of the suite construct a
real app with no database anywhere. Only `backend/tests/test_expense_postgres.py` talks to
the real server, behind the `postgres` marker; it **skips when nothing answers**, so a
developer who has not run `db-init` gets a green suite, and **fails under `CI=true`**,
where a database is expected to be up.

## Loading expenses

**The expense files live in a separate private repository.** Real spending is
confidential and this repository is public, so `EXPENSE_DATA_DIR` in `backend/.env` is the
absolute path to the `data/` directory in your clone of that one. Keeping that clone
current is your job.

```sh
pixi run backend-load-expenses      # reads $EXPENSE_DATA_DIR/*.yaml into the database
```

**A missing directory loads nothing and succeeds**, a machine without the data repository
being an ordinary state. An *unset* `EXPENSE_DATA_DIR` - a shell that never ran
`direnv allow` - aborts on the same `${VAR:?}` guard the `db-*` tasks use. A directory
handed to the loader directly is still checked, which is what surfaces a typed path.

The twelve `sample-*.yaml` files under `backend/tests/data/expenses/` are the suite's
fixtures and no task points at them. To fill a database from them anyway:

```sh
cd backend && EXPENSE_DATA_DIR=tests/data/expenses poe load-expenses
```

They carry the `sample-` prefix for a reason: `loaded_expense_file.filename` is unique on
the bare name, and the prefix keeps a fixture clear of a real `nykredit-2026-01.yaml`.

Files are named `<bank>-YYYY-MM.yaml`, one per bank and calendar month, holding the bank's
own export header and then every record it exported - the raw line as evidence, and beside
it what the other repository decided about it.

```yaml
---
header: '"Dato";"Beloeb";"Tekst";'
records:
  - record: '01-09-2026;-2438,47;"BS E/F SOLBAKKEN";'
    extracted:
      datetime: '2026-09-01T00:00:00+02:00'
      key: BS E/F SOLBAKKEN
      action: import
      amount: '2438.47'
      currency: DKK
      category: Building
  - record: '04-09-2026;-240,00;"CAFE NEXT DOOR";'
    extracted:
      datetime: '2026-09-04T00:00:00+02:00'
      action: defer
```

**`extracted` is the whole of what this repository reads**, and only where its `action` is
`import`. A `discard` was decided against and a `defer` has a bank state that is not
terminal yet - a card payment the merchant has not claimed - and either states just the
two fields that place it in its file; `record` is read by nothing here.

| Field | Format | Notes |
| --- | --- | --- |
| `datetime` | RFC 3339, with an offset | The day it names is `expense_date`; the offset stands unapplied |
| `amount` | decimal | At most two decimal places; may be negative; non-zero |
| `currency` | ISO 4217 alpha-3 | Uppercase |
| `category` | a `:`-separated path | Each level stripped, non-empty, and slugging to something |
| `key` | the bank's own text for the record | Stripped and non-blank |

A third decimal place is refused by the loader, ahead of `numeric(12, 2)`. A negative
amount is accepted, a credit being a negative expense; a zero one is refused, with
`expense_amount_not_zero` as the database's backstop. A `category` outside the path shape -
`Food:`, `:Food`, `Food::Drink` - is refused by the loader, which names the file, with
`expense_category_is_a_path` behind it; a blank `key` is refused on the same terms.
**Every field is read as text**, so `2438.47` and the date-time both arrive quoted, clear
of YAML 1.1's float resolution. A byte-order mark is tolerated.

**Re-running the loader is a no-op**, and that is the ledger's doing, not the rows'.
`loaded_expense_file` records each file's name and the SHA-256 of its bytes; a file
already recorded with a matching digest is skipped whole. The expense rows carry neither a
content hash nor an `ON CONFLICT`: two identical records are two real purchases, such as a
pair of same-day fill-ups, and both belong in the month. Each file is its own transaction,
so a run that dies half way can simply be re-run.

**The `category` table is derived**, a third shape beside the two loaders' own: `expense`
is append-only and `currency_rate` is replaced whole, while `category` is extended and
verified. Each file's load recomputes every slug from the stored rows plus that file's own
categories, refuses the file if a stored slug would move, and inserts the nodes that are
new, ancestors included. What it refuses and why is
[Category slugs](api.md#category-slugs).

**Editing a loaded file is refused.** A known filename arriving with a different digest
stops the run, so the database stays the read-only view of the files it was loaded from.
Append a new file, or rebuild.

**With month files, that rebuild is the ordinary path rather than the exception.** The
other repository adds a later export's records to the month file they fall in, rewriting
it, so any import touching a month already loaded here arrives as an edit. A settling
`defer` is that same case. A new month is a new filename and loads on its own:

```sh
pixi run backend-db-reset && pixi run backend-db-init && pixi run backend-load-expenses
```

That rebuild is also the cure after `pixi run backend-test`, which TRUNCATEs the expense
tables around every test in `test_expense_postgres.py` and `currency_rate` around every
test in `test_currency_postgres.py` - **running the suite empties whatever you had
loaded**.

It is the path for a **schema change**, too. `db-init` adds what is missing and leaves
what is there, so pulling a branch that changes a column or a table name means resetting
the cluster. A branch that only *adds* a table - as `currency_rate` did - takes `db-init`
alone. A table the loader fills - as `category` is - takes the reset all the same once
anything is loaded, the ledger skipping every file it has already seen.

## Loading exchange rates

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

**This loader replaces rather than appends.** A rate for a pair is a current fact rather
than an event: there is no ledger table, every run deletes the rates it finds and inserts
the file's, and **editing a rate and re-running is the supported workflow**. Deleting and
inserting share one transaction, so nothing ever observes the table empty, and every file
is parsed *before* anything is deleted, so a typo leaves the loaded rates as they were.
