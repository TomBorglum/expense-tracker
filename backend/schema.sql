-- The whole schema: the greeting this API serves, and the expenses it reports on.
--
-- There is no migration tool. Three tables do not earn Alembic when two of them are
-- append-only and rebuildable - `db-reset && db-init && load-expenses` reproduces every
-- row in them from data/expenses/ - and the app issues no DDL of its own - no create_all
-- at startup - so nothing but `pixi run backend-db-init` ever runs this. The Greeting,
-- LoadedFile and Expense models in src/expense_tracker/db.py are these tables declared a
-- second time, in Python, with nothing checking the agreement. Change both halves
-- together.
--
-- Every statement is idempotent, because db-init re-runs against live clusters.

CREATE TABLE IF NOT EXISTS greeting (
    -- A singleton by construction. The CHECK is what stops a second row appearing and
    -- making "the" greeting ambiguous; the endpoint still orders and limits, so it
    -- stays correct if this is ever relaxed into a real key.
    id      integer PRIMARY KEY,
    message text    NOT NULL,
    CONSTRAINT greeting_is_singleton CHECK (id = 1),
    CONSTRAINT greeting_message_not_blank CHECK (message <> '')
);

-- DO NOTHING rather than DO UPDATE: re-running db-init must not stamp on a greeting
-- that was edited in place, which is the whole point of moving it out of the wheel.
INSERT INTO greeting (id, message)
VALUES (1, 'Hello, World!')
ON CONFLICT (id) DO NOTHING;

-- One row per CSV file the loader has taken in, and the ONLY thing that makes a re-run
-- idempotent. There is deliberately no content hash on the expense rows below and no
-- ON CONFLICT anywhere: two identical lines - same amount, day, category and details -
-- are two real purchases, so the rows themselves cannot tell you whether they have been
-- loaded before. This table can, because a file can.
CREATE TABLE IF NOT EXISTS loaded_file (
    -- GENERATED ALWAYS rather than bigserial, which PostgreSQL's own "Don't Do This"
    -- page advises against for new tables: serial is a macro for a separate sequence
    -- object with its own ownership and grants, where an identity column is part of the
    -- table. ALWAYS rather than BY DEFAULT because only the loader writes here, so an
    -- explicit id in an INSERT is a bug worth rejecting rather than honouring. pg_dump
    -- still restores it, via OVERRIDING SYSTEM VALUE.
    id        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The bare name, never a path, so moving data/expenses/ does not orphan the ledger.
    -- UNIQUE is what turns "have I seen this file?" into a lookup rather than a scan,
    -- and what makes the loader's skip-or-refuse decision well defined.
    filename  text        NOT NULL UNIQUE,
    -- Lowercase hex sha256 of the file's BYTES, taken before any parsing, so it
    -- describes the file rather than the loader's reading of it. Reproducible from a
    -- shell with `sha256sum data/expenses/<filename>`. A known filename arriving with a
    -- different digest is what the loader refuses: the file was edited after loading,
    -- and neither skipping it nor re-reading it would be honest.
    sha256    text        NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    -- What the loader believed it inserted. Deliberately not derived from a COUNT, so a
    -- disagreement with COUNT(*) on expense stays visible instead of definitionally true.
    row_count integer     NOT NULL,
    CONSTRAINT loaded_file_filename_not_blank CHECK (filename <> ''),
    CONSTRAINT loaded_file_sha256_is_hex      CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT loaded_file_row_count_positive CHECK (row_count >= 0)
);

-- One row per data line of one loaded file.
CREATE TABLE IF NOT EXISTS expense (
    -- Surrogate, because nothing in the data identifies a row: the same amount, day,
    -- currency, category and details can legitimately repeat, and the ledger above is
    -- what stops that becoming a duplicate-load problem. See the identity note above.
    id             bigint         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Plain REFERENCES: no CASCADE, no SET NULL. The ledger is append-only, and a DELETE
    -- that would orphan expenses must fail rather than quietly take them along. That is
    -- also why this column carries no index of its own - PostgreSQL does not index a
    -- foreign key for you, and the only scan one would spare is the one a parent DELETE
    -- causes, which nothing here ever does. Add it the day something deletes.
    loaded_file_id bigint         NOT NULL REFERENCES loaded_file (id),
    -- numeric, never float: this is money, and 775.37 has no exact binary form. (12,2)
    -- is ten integer digits and two decimal places; the loader rejects a third rather
    -- than letting PostgreSQL round it away silently.
    amount         numeric(12, 2) NOT NULL,
    -- ISO 4217 alpha-3, e.g. DKK. The loader checks the same shape before a row gets
    -- here, so this constraint is the backstop rather than the error message.
    currency       text           NOT NULL,
    -- DD/MM/YYYY in the file, a real date here, so ordering is a date comparison and not
    -- a string one that would sort 02/01/2026 before 14/01/2025.
    expense_date   date           NOT NULL,
    category       text           NOT NULL,
    -- The free-text memo, e.g. 'Accident / Car'. NOT NULL but allowed to be empty: a
    -- blank memo is a real thing an export produces, and is not an error.
    details        text           NOT NULL,
    CONSTRAINT expense_currency_is_iso_4217 CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT expense_category_not_blank   CHECK (category <> '')
);

-- Exactly the order GET /api/expenses asks for, tiebreak included. The endpoint has no
-- pagination and no filtering, so this table serves one query and this is it.
CREATE INDEX IF NOT EXISTS expense_newest_first_idx
    ON expense (expense_date DESC, id DESC);
