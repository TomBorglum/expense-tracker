-- The whole schema: the expenses this API reports on.
--
-- There is no migration tool and the app issues no DDL, so nothing but
-- `pixi run backend-db-init` ever runs this. The LoadedExpenseFile and Expense models
-- under src/expense_tracker/ are these tables declared a second time, in Python, with
-- nothing checking the agreement. Change both halves together.
--
-- Every statement is idempotent, because db-init re-runs against live clusters.

-- One row per expense file the loader has taken in, and the only thing that makes a
-- re-run idempotent. The expense rows below carry no content hash and no ON CONFLICT:
-- two identical lines are two real purchases, so the rows cannot say whether they have
-- been loaded before. A file can.
CREATE TABLE IF NOT EXISTS loaded_expense_file (
    -- GENERATED ALWAYS rather than bigserial, which PostgreSQL's own "Don't Do This"
    -- page advises against for new tables. ALWAYS rather than BY DEFAULT because only
    -- the loader writes here; pg_dump still restores via OVERRIDING SYSTEM VALUE.
    id        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The bare name, never a path, so moving the directory does not orphan the ledger.
    filename  text        NOT NULL UNIQUE,
    -- Lowercase hex sha256 of the file's bytes, taken before parsing. Reproducible
    -- with `sha256sum data/expenses/<filename>`.
    sha256    text        NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    -- What the loader believed it inserted. Not derived from a COUNT, so a
    -- disagreement with COUNT(*) on expense stays visible.
    row_count integer     NOT NULL,
    CONSTRAINT loaded_expense_file_filename_not_blank CHECK (filename <> ''),
    CONSTRAINT loaded_expense_file_sha256_is_hex      CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT loaded_expense_file_row_count_positive CHECK (row_count >= 0)
);

-- One row per data line of one loaded file.
CREATE TABLE IF NOT EXISTS expense (
    -- Surrogate, because nothing in the data identifies a row: the same amount, day,
    -- currency, category and details can legitimately repeat.
    id                     bigint         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- No CASCADE: the ledger is append-only, and a DELETE that would orphan expenses
    -- must fail rather than take them along. That is also why this column carries no
    -- index - the only scan one would spare is the one a parent DELETE causes.
    loaded_expense_file_id bigint         NOT NULL
                                          REFERENCES loaded_expense_file (id),
    -- numeric, never float: this is money. (12,2) is ten integer digits and two
    -- decimal places; the loader rejects a third rather than letting PostgreSQL round
    -- it away silently.
    amount                 numeric(12, 2) NOT NULL,
    -- ISO 4217 alpha-3. The loader checks the same shape, so this is the backstop.
    currency               text           NOT NULL,
    -- DD/MM/YYYY in the file, a real date here, so ordering is a date comparison.
    expense_date           date           NOT NULL,
    category               text           NOT NULL,
    -- The free-text memo. NOT NULL but allowed to be empty.
    details                text           NOT NULL,
    CONSTRAINT expense_currency_is_iso_4217 CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT expense_category_not_blank   CHECK (category <> '')
);

-- Exactly the order GET /api/expenses asks for, tiebreak included.
CREATE INDEX IF NOT EXISTS expense_newest_first_idx
    ON expense (expense_date DESC, id DESC);
