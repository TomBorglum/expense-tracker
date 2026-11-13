# The container images

## Keeping the bases current

All three Dockerfiles pin their runtime base as `tag@sha256:...`, and
`.github/dependabot.yml` moves that pair weekly across all three. Its commits are prefixed
**`deps`**, so a base bump cuts a patch release and that release republishes the image.

- **The three-day `cooldown` applies to the SPA's and the database's bases only.**
  Dependabot takes publication dates from Docker Hub's `tag_last_pushed`; for `gcr.io` and
  `ghcr.io` it records a `cooldown_date_unavailable` warning and allows the update.
- **The API's base arrives as a digest refresh on the `nonroot` tag**, which stays where
  it is. The database's `18-alpine` behaves the same way.
- **The pixi builder image is ignored**, which suppresses security updates for it too.
  That version is pinned by hand in `.envrc` and both Dockerfiles, and the root
  [`CLAUDE.md`](../CLAUDE.md) records the trio.

## The API image

`backend/Dockerfile` builds in two stages: a `ghcr.io/prefix-dev/pixi` builder
materialises the `backend` environment, and a
`gcr.io/distroless/base-nossl-debian12:nonroot` runtime stage receives the finished prefix
and nothing that produced it: no pixi, no package cache, no package manager, no shell.

```sh
pixi run backend-image
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user@host:5432/expense_tracker \
  expense-tracker-backend:dev
```

The build context is the **repository root**, the environment being declared across
`pixi.toml` and `pixi.lock`. `docker-bake.hcl` states it as `context = ".."`, which bake
refuses to read until a caller allows it, hence `--allow=fs.read=..` above. CI needs none
of it, `docker/bake-action` allowing `fs=*` on its own.

Nothing checks any of the four properties below.

**The prefix keeps the path it was built at**, `/app/.pixi/envs/backend`. A conda prefix
is not relocatable and pixi writes absolute shebangs inside it. The entrypoint names the
interpreter outright rather than the `uvicorn` script.

**There is no shell.** `/bin` and `/usr/bin` are empty, so `docker run --entrypoint
/bin/sh` fails. The image declares no `HEALTHCHECK`: a shell-form one needs that shell.

**`pixi shell-hook`'s exports are written out by `ENV`**: `PATH` and `SSL_CERT_FILE`.
`SSL_CERT_FILE` restates OpenSSL's own default, conda-forge's openssl reading
`ssl/cert.pem` out of the prefix and never `/etc/ssl`.

**The image has no configuration defaults.** `DATABASE_URL`, or all four `PG*` names, has
to arrive at `docker run` time; `config.py` validates and the process refuses to start
otherwise. `.dockerignore` excludes every `.env` variant. It runs as UID 65532,
distroless's `nonroot`, owns nothing it can write to, and listens on 8000.

`base-nossl` is the distroless rung carrying glibc, which the prefix needs; the prefix
brings its own libssl, libcrypto and libstdc++. Keeping the fourteen packages between it
and `base` out keeps the release gate reading only on libraries the application loads.

## The SPA image

`frontend/Dockerfile` builds in the same two stages: the pixi builder installs node and
pnpm and runs `tsc -b && vite build`, and an `nginxinc/nginx-unprivileged:1.31-alpine`
runtime stage receives `dist/`. Alpine rather than distroless because the startup script
below needs a shell.

```sh
pixi run frontend-image
docker run --rm -p 8080:8080 -e API_BASE_URL=http://127.0.0.1:8000 \
  expense-tracker-frontend:dev
```

vite **inlines** `import.meta.env.VITE_API_BASE_URL` at build time, so the build bakes a
placeholder into `frontend/.env.production.local`, vite's **highest-precedence** source in
production mode, and the container rewrites it. `frontend/docker/40-api-base-url.sh` does
that from `/docker-entrypoint.d/`, copied with `--chmod=0755`, the exec bit being what has
the base's entrypoint run it at all.

The script refuses to start the container unless `API_BASE_URL` is an absolute `http(s)`
URL **with no path**. All four `api/` modules resolve as `new URL("/api/expenses",
API_BASE_URL)`, and an absolute path **discards** the base's path. The value is the origin
the **browser** calls.

Nothing checks the three properties below either.

**The placeholder's survival is asserted at build time**, by a `grep -rq` over `dist/` at
the end of the builder stage. The startup script tolerates finding nothing, a restart on a
filesystem it already rewrote being the ordinary case.

**The document root is `/srv/expense-tracker`**, a directory the `COPY` creates, so it
holds `dist/` and nothing the base shipped. `--chown=101:101` lets the startup script
rewrite those files.

**`Cache-Control` is computed by two `map`s read by a single server-level `add_header`.**
`add_header` in a nested block **replaces** the inherited set rather than adding to it, so
keeping every header on one directive is what keeps the security headers on every
response. The response status is half the key, so a `404` during a deployment stays
retryable.

```sh
curl -sI localhost:8080/                         # Cache-Control: no-store
curl -sI localhost:8080/assets/index-<hash>.js   # public, max-age=31536000, immutable
curl -sI localhost:8080/assets/missing.js        # 404, and no-store
```

`try_files $uri $uri/ /index.html` answers anything that is not a real file with the
shell, so `/totals` resolves on a cold load. `/assets/` resolves or `404`s instead, so a
missing chunk reaches the module loader as the 404 it is.

The CSP is `default-src 'none'` plus a same-origin script and stylesheet, `data:` images
because daisyUI inlines its glyphs, and `connect-src` naming the one API origin. The
fourth is `style-src 'unsafe-inline'`: React renders inline `style` **attributes** for the
date picker and the column widths, governed by `style-src-attr` falling back to
`style-src`. `style-src-elem 'self'` sits beside it so the stylesheet keeps the tighter
rule.

The build context is the repository root here too, and `backend/pyproject.toml` is the one
backend file the build reads, pixi validating the lock against the **whole** workspace.

## The database image

`database/Dockerfile` has no builder stage and one `COPY`. It is `postgres:18-alpine` with
`backend/schema.sql` dropped into `/docker-entrypoint-initdb.d/`, the base's own hook for
first-boot SQL.

```sh
docker run -d -v expense-tracker-data:/var/lib/postgresql \
  -e POSTGRES_USER=expense_tracker -e POSTGRES_DB=expense_tracker \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  tomborglum/expense-tracker-database:2.1.0
```

**The hook runs only when the data directory is empty.** The cluster is a volume, so
**dropping the volume is what re-applies the schema**.

The image sets `POSTGRES_INITDB_ARGS=--locale=C --encoding=UTF8`, the two flags
`db-create` passes `initdb`. `GET /api/expenses/categories` orders `category` in SQL, and
C collation is byte order under musl and glibc alike, so the deployed server sorts as a
developer's cluster does.

**It runs as uid 70 and ships no `gosu`.** The base calls `gosu` only to drop from root to
the `postgres` user, and all three call sites sit behind `if [ "$(id -u)" = '0' ]`, so
starting as 70 reaches none of them. It was also 1.7 MB of Go carrying **26
HIGH/CRITICAL** findings into [the vulnerability
gate](publish.md#the-vulnerability-gate), none reachable; deleting it takes this image to
**zero**.

What that gives up is chowning the data directory. A fresh **named** volume needs no
chown, docker seeding it from the image's own `/var/lib/postgresql`, shipped `70:70`. A
host **bind** mount needs `chown 70:70` on the directory first, or `initdb` stops at
`Permission denied`. An explicit `--user 0` fails at once with `gosu: not found`.

`PGDATA` is the base's own `/var/lib/postgresql/18/docker`, underneath the volume it
declares, which is the whole `/var/lib/postgresql` rather than the pre-18 `data/` beneath
it. **That is the path to mount.**

Alpine is for the gate rather than the size: 62 HIGH/CRITICAL in `postgres:18.6` with a
fix available for **none** of them, against the 2 here, both covered by
`database/.trivyignore.yaml`.
