-- The greeting this API serves, as data rather than as a constant compiled into the
-- wheel. Changing the wording is an UPDATE now, not a deploy.
--
-- This file is the entire schema. There is no migration tool: one table with one row
-- does not earn Alembic, and the app issues no DDL of its own - no create_all at
-- startup - so nothing but `pixi run backend-db-init` ever runs this. The Greeting
-- model in src/expense_tracker/db.py is the same table declared a second time, in
-- Python, with nothing checking the agreement. Change both halves together.
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
