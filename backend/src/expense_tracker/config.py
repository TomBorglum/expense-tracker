"""Where settings come from. One function, read from the environment.

Its own module rather than a corner of deps.py because there are two entry points into
this package, not one: create_app() and the CSV loader. deps.py imports fastapi, so a
loader that reached through it for the DSN would drag the whole web framework into
`python -m expense_tracker.loader` and would have to sit above the HTTP wiring in the
layer order - claiming the loader is part of it. It is not. Both entry points import
this instead, and the import-linter contracts keep them from importing each other.
"""

import os


def database_url() -> str:
    """The DSN to connect with. Required, with deliberately no fallback.

    The development value is declared once, in pixi.toml's
    [feature.test.activation.env], so `pixi run` hands it to serve, load, test and the
    editor alike. A default here would be that value written a second time, and in a
    deployment it would turn a forgotten setting into a silent connection attempt
    against the deployment's own loopback.
    """
    url = os.environ.get("DATABASE_URL")
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set; `pixi run` supplies the development value"
        )
    return url
