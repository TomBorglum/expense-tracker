# The container images

How the three images are built.

## Keeping the bases current

All three Dockerfiles pin their runtime base as `tag@sha256:...`, the tag naming the
version a reader sees and the digest deciding what is pulled, and `.github/dependabot.yml`
moves that pair weekly across all three. Its commits are prefixed **`deps`**, so a base
bump cuts a patch release - and that release is what republishes the image.

Three properties of the entry live outside the configuration:

- **The three-day `cooldown` applies to the SPA's and the database's bases only.**
  Dependabot takes publication dates from Docker Hub's `tag_last_pushed`; for `gcr.io` and
  `ghcr.io` it records a `cooldown_date_unavailable` warning and allows the update.
- **The API's base arrives as a digest refresh on the `nonroot` tag**, which stays where
  it is. The database's `18-alpine` behaves the same way, a major-series tag a new
  PostgreSQL minor keeps, so an 18.6 to 18.7 move arrives here as a digest and nothing
  else.
- **The pixi builder image is ignored.** That version is pinned by hand in three places -
  `use pixi` in `.envrc` and both Dockerfiles - and the root [`CLAUDE.md`](../CLAUDE.md)
  records the trio. The ignore suppresses security updates for that image with it.

## The API image

`backend/Dockerfile` builds it in two stages: a `ghcr.io/prefix-dev/pixi` builder
materialises the `backend` environment, and a
`gcr.io/distroless/base-nossl-debian12:nonroot` runtime stage receives the finished prefix
and nothing that produced it - no pixi, no package cache, no package manager, no shell.

```sh
pixi run backend-image
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user@host:5432/expense_tracker \
  expense-tracker-backend:dev
```

The build context is the **repository root**, because the environment is declared across
`pixi.toml` and `pixi.lock`. `docker-bake.hcl` states it as `context = ".."`, which bake
refuses to read until a caller allows it - hence `--allow=fs.read=..` in the task above,
which CI needs none of because `docker/bake-action` allows `fs=*` on its own.

Four properties are worth writing down, because nothing checks any of them.

**The prefix keeps the path it was built at.** A conda prefix is not relocatable, and pixi
rewrites each console script's shebang to an absolute interpreter path inside it. So the
builder works in `/app` and the runtime stage copies `/app/.pixi/envs/backend` to that
same path. The entrypoint then names the interpreter outright rather than the `uvicorn`
script, which keeps the image from depending on how pixi wrote that line at all.

**There is no shell, and nothing else either.** `/bin` and `/usr/bin` are empty in this
base, so `docker run --entrypoint /bin/sh` fails, and code execution inside the container
finds no interpreter to pivot through. The image declares no `HEALTHCHECK`: a shell-form
one needs that shell.

**`pixi shell-hook`'s exports are written out by `ENV`.** With no shell to run an
activation script in, `PATH` and `SSL_CERT_FILE` are set by hand, and those two are the
whole substitution because every package pinned in `pixi.toml` ships without an activation
script. `SSL_CERT_FILE` restates OpenSSL's own default rather than correcting one:
conda-forge's openssl reads `ssl/cert.pem` out of the prefix and never `/etc/ssl`, and
that default lands correctly only because the `COPY` puts the prefix back where it was
built.

**The image has no configuration defaults.** `DATABASE_URL`, or all four `PG*` names, has
to arrive at `docker run` time: `config.py` validates and the process refuses to start
otherwise. `.dockerignore` excludes every `.env` variant, the two committed ones included,
so this checkout's loopback database cannot reach an image. It runs as UID 65532 -
distroless's `nonroot` - owns nothing it can write to, and listens on 8000.

**What `base-nossl` supplies.** The distroless family stacks up as `static` (no libc),
`base-nossl` (glibc), `base` (plus libssl and libcrypto), `cc` (plus libstdc++). glibc is
what the prefix needs, and it carries its own libssl, libcrypto and libstdc++, so
`base-nossl` is the rung that holds everything the image links. The fourteen entries
between it and `base` are what a scanner inventories out of `/var/lib/dpkg/status.d/` and
reports CVEs against, so keeping them out keeps the release gate reading only on libraries
the application loads. glibc is also what fixes the family: conda-forge publishes glibc
builds, and `gcompat` over musl does not cover what a CPython prefix asks of libc.


## The SPA image

`frontend/Dockerfile` builds it in the same two stages: the pixi builder installs node and
pnpm and runs `tsc -b && vite build`, and an `nginxinc/nginx-unprivileged:1.31-alpine`
runtime stage receives `dist/` and nothing that produced it.

```sh
pixi run frontend-image
docker run --rm -p 8080:8080 -e API_BASE_URL=http://127.0.0.1:8000 \
  expense-tracker-frontend:dev
```

Alpine here against distroless there follows from what each image carries: static files
and a web server Alpine packages, where the backend's conda prefix is glibc-linked.
Alpine's shell is load-bearing too - the configuration below is applied by a shell script
at startup.

**The configuration arrives at two different times, and that is the whole design.** The
backend reads `DATABASE_URL` from the environment when it starts. vite **inlines**
`import.meta.env.VITE_API_BASE_URL` into the bundle at build time, so the origin is fixed
by the time a container starts. One image serves every deployment, so the build bakes a
placeholder into `frontend/.env.production.local` - vite's **highest-precedence** source
in production mode - and the container rewrites it. `frontend/docker/40-api-base-url.sh`
does that from `/docker-entrypoint.d/`, copied with `--chmod=0755`, the exec bit being
what has the base's entrypoint run it at all.

The script refuses to start the container unless `API_BASE_URL` is an absolute `http(s)`
URL **with no path** - the backend's no-defaults rule applied to the other stack. The last
refusal earns its place: all four `api/` modules resolve as `new URL("/api/expenses",
API_BASE_URL)`, and an absolute path **discards** the base's path, so the check reports it
at startup rather than at every call site. The value is the origin the **browser** calls.

Three properties here are also unchecked by anything.

**The placeholder's survival is asserted at build time, not at run time.** esbuild does
not constant-fold `new URL(path, "__TOKEN__")`, but that is the minifier's property rather
than a promise, so the builder stage ends with a `grep -rq` over `dist/`. The startup
script tolerates finding nothing - a restart on a filesystem it already rewrote is the
ordinary case - and the build-time check keeps that tolerance off a bad build.

**The document root is `/srv/expense-tracker`**, a directory the `COPY` creates, so it
holds `dist/` and nothing the base shipped, whose `/usr/share/nginx/html` carries a stock
`50x.html` naming nginx. `--chown=101:101` lets the startup script rewrite those files.

**`Cache-Control` is computed by two `map`s read by a single server-level `add_header`.**
`add_header` in a nested block **replaces** the inherited set rather than adding to it, so
keeping every header on one directive is what keeps the security headers on every
response. The response status is half the key, so the year-long `immutable` lifetime
belongs to a response that carries an asset and a `404` during a deployment stays
retryable.

```sh
curl -sI localhost:8080/                         # Cache-Control: no-store
curl -sI localhost:8080/assets/index-<hash>.js   # public, max-age=31536000, immutable
curl -sI localhost:8080/assets/missing.js        # 404, and no-store
```

`try_files $uri $uri/ /index.html` answers anything that is not a real file with the
shell, so `/totals` resolves on a cold load. `/assets/` is the one exception, resolving or
`404`ing, so a missing chunk reaches the module loader as the 404 it is.

**The CSP is derived from what the bundle actually loads**: `default-src 'none'` plus a
same-origin script and stylesheet, `data:` images because daisyUI inlines its glyphs, and
`connect-src` naming the one API origin. The fourth is `style-src 'unsafe-inline'`, which
the bundle asks for - React renders inline `style` **attributes** for the date picker and
the column widths, governed by `style-src-attr` falling back to `style-src`.
`style-src-elem 'self'` sits beside it so the stylesheet keeps the tighter rule.

The build context is the repository root here too, and `backend/pyproject.toml` is the one
backend file the build reads: pixi validates the lock against the **whole** workspace.
Only its metadata is read - `backend/src` stays out of the build - so a backend source
change invalidates no layer here.

## The database image

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
locally. Here the cluster is a volume, so **dropping the volume is what re-applies the
schema** - `backend-db-reset` by another name.

The image sets `POSTGRES_INITDB_ARGS=--locale=C --encoding=UTF8`, the two flags
`db-create` passes `initdb`. That is not decoration: `GET /api/expenses/categories` orders
`category` in SQL, and C collation is byte order under musl and glibc alike, so the
deployed server sorts exactly as the cluster a developer runs. Declaring it in the image
rather than leaving it to the caller is what stops it being lost by whoever runs the
thing.

**It runs as uid 70 and ships no `gosu`.** The base calls `gosu` in exactly one situation,
dropping from root to the `postgres` user, and all three call sites sit behind `if [ "$(id
-u)" = '0' ]` - so starting as 70 reaches none of them. It was also 1.7 MB of Go carrying
**26 HIGH/CRITICAL** findings into [the vulnerability
gate](releases.md#the-vulnerability-gate), none of them reachable; deleting it takes this
image to **zero**.

What that gives up is the other thing root does: chowning the data directory. A fresh
**named** volume needs no chown, docker seeding it from the image's own
`/var/lib/postgresql`, shipped `70:70`. A host **bind** mount needs `chown 70:70` on the
directory first, or `initdb` stops at `Permission denied`. An explicit `--user 0` fails at
once with `gosu: not found`, rather than starting degraded.

`PGDATA` is the base's own `/var/lib/postgresql/18/docker`, underneath the volume it
declares - which is the whole `/var/lib/postgresql` directory rather than the pre-18
`data/` beneath it. **That is the path to mount.**

The reason for alpine is the gate rather than the size: 62 HIGH/CRITICAL in
`postgres:18.6` with a fix available for **none** of them, against the 2 here, both
already covered by `.trivyignore.yaml`.
