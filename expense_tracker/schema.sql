-- Initial schema. Deliberately minimal: enough for init-db to run and for the
-- connection to be exercised end to end. Columns will grow with the CSV import.

DROP TABLE IF EXISTS expense;

CREATE TABLE expense (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- ISO-8601 date (YYYY-MM-DD). SQLite has no native date type.
    incurred_on TEXT    NOT NULL,
    -- Amount in minor units (cents) to avoid binary floating point rounding.
    amount      INTEGER NOT NULL,
    description TEXT    NOT NULL,
    category    TEXT
);

CREATE INDEX idx_expense_incurred_on ON expense (incurred_on);
