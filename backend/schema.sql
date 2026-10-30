-- The whole schema: the expenses this API reports on, and the rates they convert at.
--
-- There is no migration tool and the app issues no DDL, so nothing but
-- `pixi run backend-db-init` ever runs this. The LoadedExpenseFile, Expense, Category
-- and CurrencyRate models under src/expense_tracker/ are these tables declared a second
-- time, in Python, with nothing checking the agreement. Change both halves together.
--
-- Every statement is idempotent, because db-init re-runs against live clusters.

-- One row per expense file the loader has taken in, and the only thing that makes a
-- re-run idempotent. A file has an identity the rows below do not: two identical lines
-- are two real purchases, so the ledger is where a repeat load is recognised, and the
-- expense rows carry no content hash and no ON CONFLICT.
CREATE TABLE IF NOT EXISTS loaded_expense_file (
    -- GENERATED ALWAYS rather than bigserial, which PostgreSQL's own "Don't Do This"
    -- page advises against for new tables. ALWAYS rather than BY DEFAULT because only
    -- the loader writes here; pg_dump still restores via OVERRIDING SYSTEM VALUE.
    id        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The bare name, never a path, so moving the directory does not orphan the ledger.
    filename  text        NOT NULL UNIQUE,
    -- Lowercase hex sha256 of the file's bytes, taken before parsing. Reproducible
    -- with `sha256sum $EXPENSE_DATA_DIR/<filename>`.
    sha256    text        NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    -- What the loader believed it inserted. Not derived from a COUNT, so a
    -- disagreement with COUNT(*) on expense stays visible.
    row_count integer     NOT NULL,
    CONSTRAINT loaded_expense_file_filename_not_blank CHECK (filename <> ''),
    CONSTRAINT loaded_expense_file_sha256_is_hex      CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT loaded_expense_file_row_count_positive CHECK (row_count >= 0)
);

-- One row per imported record of one loaded file. A discarded or deferred record
-- has none.
CREATE TABLE IF NOT EXISTS expense (
    -- Surrogate, because nothing in the data identifies a row: the same amount, day,
    -- currency and category can legitimately repeat.
    id                     bigint         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- No CASCADE: the ledger is append-only, so a DELETE that leaves expenses behind
    -- fails on this reference. The column carries no index for the same reason - a
    -- parent DELETE is the one scan an index here would spare.
    loaded_expense_file_id bigint         NOT NULL
                                          REFERENCES loaded_expense_file (id),
    -- numeric, never float: this is money. (12,2) is ten integer digits and two
    -- decimal places; the loader rejects a third rather than letting PostgreSQL round
    -- it away silently. The sign carries the meaning: a negative amount is a credit.
    amount                 numeric(12, 2) NOT NULL,
    -- ISO 4217 alpha-3. The loader checks the same shape, so this is the backstop.
    currency               text           NOT NULL,
    -- An RFC 3339 date-time in the file, the day of it here, so ordering is a date
    -- comparison.
    expense_date           date           NOT NULL,
    -- A colon-separated path from the outermost category inward: Groceries, or
    -- Settlement:Alice. The loader checks the same two things, so these are the
    -- backstop.
    category               text           NOT NULL,
    -- The text the bank's export carried for this record, e.g. FUEL. The loader strips
    -- it and refuses a blank one, so this is the backstop.
    key                    text           NOT NULL,
    -- An expense of nothing is not an entry, and numeric has no signed zero, so
    -- this refuses -0.00 as well.
    CONSTRAINT expense_amount_not_zero      CHECK (amount <> 0),
    CONSTRAINT expense_currency_is_iso_4217 CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT expense_category_not_blank   CHECK (category <> ''),
    -- One or more levels, none of them empty - so no level can hold the separator, and
    -- splitting a path or joining one back up is lossless and needs no escaping.
    CONSTRAINT expense_category_is_a_path   CHECK (category ~ '^[^:]+(:[^:]+)*$'),
    CONSTRAINT expense_key_not_blank        CHECK (key <> '')
);

-- Exactly the order GET /api/expenses asks for, tiebreak included.
CREATE INDEX IF NOT EXISTS expense_oldest_first_idx
    ON expense (expense_date, id);

-- One row per node of the category tree, holding the slug that names it in a URL.
--
-- Ancestors are rows too, not only the paths expenses are filed under: a node's slug is
-- a component of every slug below it, so it has to be stored rather than truncated out
-- of a descendant. It is also what makes the UNIQUE below reach an ancestor collision -
-- Going Out:Dinner and Going-Out:Lunch slug to two unique paths while their depth-1
-- ancestors are one slug meaning two categories.
--
-- Derived state, unlike the append-only expense rows: the loader recomputes the whole
-- assignment, refuses to proceed if a stored slug would change, and inserts what is new.
CREATE TABLE IF NOT EXISTS category (
    id             bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The real path, as the expense rows spell it and as the user is shown it.
    category       text    NOT NULL UNIQUE,
    -- The URL path: each level lower kebab case over a-z0-9, levels joined by the same
    -- separator, so it needs no percent-encoding anywhere in a URL. UNIQUE is a backstop
    -- on the assignment, which numbers colliding siblings per parent.
    slug           text    NOT NULL UNIQUE,
    -- How many levels deep the path is, so listing one level is a plain WHERE.
    level          integer NOT NULL,
    -- The first file, in name order, that mentions this node. The order the slugs are
    -- handed out in, stored so a load does not re-read the whole directory to find it.
    first_filename text    NOT NULL,
    CONSTRAINT category_is_a_path  CHECK (category ~ '^[^:]+(:[^:]+)*$'),
    CONSTRAINT category_slug_shape
        CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*(:[a-z0-9]+(-[a-z0-9]+)*)*$'),
    CONSTRAINT category_level_positive     CHECK (level >= 1),
    CONSTRAINT category_filename_not_blank CHECK (first_filename <> '')
);

-- Exactly the order GET /api/expenses/categories asks for, with the level it filters on
-- leading.
CREATE INDEX IF NOT EXISTS category_by_level_idx
    ON category (level, category);

-- What the slug filter joins an expense to.
CREATE INDEX IF NOT EXISTS category_by_slug_idx
    ON category (slug);

-- One row per data line of data/currencies/*.tsv: what one currency is worth in another.
--
-- No ledger table beside this one, where the expenses above have one, because a rate for
-- a pair is a current fact rather than an event. `backend-load-currencies` deletes every
-- row and inserts the file's again, so a second load lands the same table and editing a
-- rate then reloading is the supported workflow.
CREATE TABLE IF NOT EXISTS currency_rate (
    -- Surrogate: a pair may legitimately appear twice, so nothing in the data
    -- identifies a row.
    id            bigint         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- ISO 4217 alpha-3, both of them. The loader checks the same shape.
    from_currency text           NOT NULL,
    to_currency   text           NOT NULL,
    -- numeric, never float: multiplying an amount by a float is how a total drifts.
    -- Six decimal places is the resolution published rates carry; the loader rejects a
    -- seventh rather than letting PostgreSQL round it away silently.
    exchange_rate numeric(18, 6) NOT NULL,
    CONSTRAINT currency_rate_from_is_iso_4217 CHECK (from_currency ~ '^[A-Z]{3}$'),
    CONSTRAINT currency_rate_to_is_iso_4217   CHECK (to_currency ~ '^[A-Z]{3}$'),
    -- A zero or negative rate converts nothing.
    CONSTRAINT currency_rate_is_positive      CHECK (exchange_rate > 0)
);

-- Exactly the order GET /api/currencies asks for, tiebreak included.
CREATE INDEX IF NOT EXISTS currency_rate_by_pair_idx
    ON currency_rate (from_currency, to_currency, id);
