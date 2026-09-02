# Security Policy

## Supported Versions

This project is a REST API and a single-page app, maintained on a rolling basis.
Fixes land only on `main`; please reproduce against the latest commit on `main`
before reporting an issue. Tagged releases are not patched - a fix ships in the
next release.

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/TomBorglum/expense-tracker/security/advisories/new)
(the **Security -> Report a vulnerability** button on the repository). This keeps
the report confidential until a fix is available.

When reporting, please include:

- A description of the vulnerability and its impact.
- Steps to reproduce, or a proof of concept.
- The affected component(s) and the commit you observed it on.

You can expect an acknowledgement within a few days. Once confirmed, a fix will
be prepared and a GitHub Security Advisory published crediting the reporter
(unless you prefer to remain anonymous).

## Scope & Notes

In scope: the FastAPI application and its CORS configuration, the SQL in
`backend/schema.sql` and the repositories that read it, the expense loader's
handling of untrusted TSV input, and the pinned dependency chain in `pixi.toml`,
`backend/pyproject.toml` and `frontend/package.json`.

Out of scope: the local PostgreSQL cluster the `db-*` tasks create. It listens on
`127.0.0.1` only and runs with `--auth=trust` by design - it is a development
fixture, never a deployment. A deployed API is handed a `DATABASE_URL` by whoever
operates its database.

No real financial data is in this repository. The files under
`backend/tests/data/expenses/` are synthetic fixtures; real spending lives in a
separate private repository that `EXPENSE_DATA_DIR` points at.
