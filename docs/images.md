# The container images

How the three images are built.

## Keeping the bases current

All three Dockerfiles pin their runtime base as `tag@sha256:...`, the tag naming the
version a reader sees and the digest deciding what is pulled, and the `docker` entry in
`.github/dependabot.yml` moves that pair. One entry covers `/backend`, `/database` and
`/frontend`, weekly, and Dependabot rewrites the tag and the digest together.

Its commits are prefixed **`deps`**, so a base bump lands in `CHANGELOG.md` under
Dependencies and cuts a patch release. A base is part of what a user receives when they run
the image, which is the line [`CONTRIBUTING.md`](../CONTRIBUTING.md) draws between `deps:` and
`ci:`, and that release is what republishes the image: `publish.yml` publishes when a GitHub
Release is published.

Three properties of the entry live outside the configuration:

- **The three-day `cooldown` applies to the SPA's and the database's bases.** Dependabot
  takes publication dates from Docker Hub's `tag_last_pushed`, which covers
  `nginxinc/nginx-unprivileged` and `postgres`; for `gcr.io` and `ghcr.io` it records a
  `cooldown_date_unavailable` warning and allows the update. `default-days` is the whole
  window, an update that moves a digest under an unchanged tag carrying no semver level.
- **The API's base arrives as a digest refresh on the `nonroot` tag**, which stays where it
  is: that is how a rebuilt distroless base reaches the image. The database's `18-alpine`
  behaves the same way, being a major-series tag that a new PostgreSQL minor keeps - so a
  18.6 to 18.7 move arrives here as a digest and nothing else. The SPA's `1.31-alpine`
  moves to another tag carrying the same `-alpine` suffix.
- **The pixi builder image is ignored.** That version is pinned by hand in three places,
  `use pixi` in `.envrc` and both Dockerfiles, and the root [`CLAUDE.md`](../CLAUDE.md) records
  the trio; `update-pixi-dependencies.yml` bumps the pins *inside* `pixi.toml`. The ignore
  suppresses security updates for that image with it.

## The API image

`backend/Dockerfile` builds it out of the `backend` environment above, in two
stages: a `ghcr.io/prefix-dev/pixi` builder materialises the environment, and a
`gcr.io/distroless/base-nossl-debian12:nonroot` runtime stage receives the finished prefix
and nothing that produced it - no pixi, no package cache, no package manager, no shell.

```sh
pixi run backend-image
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user@host:5432/expense_tracker \
  expense-tracker-backend:dev
```

The build context is the **repository root** rather than `backend/`, because the
environment is declared across `pixi.toml` and `pixi.lock` and both of those live there.
`docker-bake.hcl` states it as `context = ".."`, which bake refuses to read until a caller
allows it - hence the `--allow=fs.read=..` in the task above, which CI needs none of
because `docker/bake-action` allows `fs=*` on its own.
The builder runs `pixi install --locked`, so an image resolves the same lock a developer
and CI do, and `.dockerignore` keeps this machine's own `.pixi/` prefixes out of the
context.

Four properties are worth writing down, because nothing checks any of them.

**The prefix keeps the path it was built at.** A conda prefix is not relocatable, and pixi
rewrites each console script's shebang to an absolute interpreter path inside it:

```sh
head -1 .pixi/envs/backend/bin/uvicorn
# #!/home/you/projects/expense-tracker/.pixi/envs/backend/bin/python3.15
```

So the builder works in `/app` and the runtime stage copies `/app/.pixi/envs/backend` to
that same path, source and destination matching for that reason. The entrypoint then names
the interpreter outright rather than the `uvicorn` script, which keeps the image from
depending on how pixi wrote that line at all.

**There is no shell, and nothing else either.** `/bin` and `/usr/bin` are empty in this
base, so `docker run --entrypoint /bin/sh` fails with `no such file or directory`, and
code execution inside the container finds no interpreter to pivot through. `PATH` names
the prefix alone for the same reason. The image declares no `HEALTHCHECK`: a shell-form one
needs that shell, and the API's surface is the four `GET`s.

**`pixi shell-hook`'s exports are written out by `ENV`.** With no shell to run an
activation script in, `PATH` and `SSL_CERT_FILE` are set by hand, and those two are the
whole substitution because every package pinned in `pixi.toml` ships without an activation
script. A package shipping one has its exports added there.

`SSL_CERT_FILE` restates OpenSSL's own default rather than correcting one. conda-forge's
openssl is built with its own `OPENSSLDIR`, so it reads `ssl/cert.pem` out of the prefix
and never `/etc/ssl` - the base's own `ca-certificates.crt` is present and goes unread -
and that default lands correctly only because the `COPY` puts the prefix back where it was
built. Naming the file keeps the trust store greppable in the Dockerfile instead of
compiled invisibly into libcrypto. There is no `SSL_CERT_DIR`: the prefix's `ssl/certs`
holds a `.keep` and nothing else.

**The image has no configuration defaults.** `DATABASE_URL`, or all four `PG*` names, has
to arrive at `docker run` time: `config.py` validates and the process refuses to start
otherwise, exactly as it does locally. `.dockerignore` excludes every `.env` variant, the
two committed ones included, so this checkout's loopback database cannot reach an image.

It runs as UID 65532 - distroless's `nonroot` - owns nothing it can write to, and listens
on 8000. The port is a literal, `docker run -p` being what maps a container port;
`UVICORN_PORT` is the `dev` task's alone.

**What `base-nossl` supplies.** The distroless family stacks up as `static` (no libc),
`base-nossl` (glibc), `base` (plus libssl and libcrypto), `cc` (plus libstdc++). glibc is
what the prefix needs, and it carries its own libssl, libcrypto and libstdc++ - `_ssl`
resolves `libssl.so.3` through the prefix's own RPATH - so `base-nossl` is the rung that
holds everything the image links. It is 24.6 MB where `base` is 33.1 MB, and the fourteen
entries between them (`libssl.so.3`, `libcrypto.so.3`, three OpenSSL engines, one module,
their dpkg records and their changelogs) are what a scanner inventories out of
`/var/lib/dpkg/status.d/` and reports CVEs against. Keeping them out keeps the release
gate reading only on libraries the application loads.

glibc is also what fixes the family: conda-forge publishes glibc builds, so every binary
in the prefix links it, and `gcompat` over musl does not cover what a CPython prefix asks
of libc.

Both bases carry a tag and a digest, the tag naming the version a reader sees and the
digest deciding what is pulled. Dependabot bumps the runtime one, on the terms
[Keeping the bases current](#keeping-the-bases-current) sets out; the pixi builder is pinned
by hand.

The image is about 396 MB, nearly all of it the prefix: a complete CPython plus the shared
libraries behind asyncpg, pydantic-core and SQLAlchemy. Two things in it are build-time
leftovers rather than runtime needs - some 14 MB of C headers under `include/`, and the
one linker binary that arrives because conda-forge's `python` hard-depends on
`ld_impl_linux-64`. Both sit behind the absent interpreter, and shedding either means
deleting it from the prefix, `pixi.toml` holding the dependency that brings it.

## The SPA image

`frontend/Dockerfile` builds it out of the `frontend` environment, in the same two stages:
the pixi builder installs node and pnpm and runs `tsc -b && vite build`, and an
`nginxinc/nginx-unprivileged:1.31-alpine` runtime stage receives `dist/` and nothing that
produced it - no node, no pnpm, no `node_modules`.

```sh
pixi run frontend-image
docker run --rm -p 8080:8080 -e API_BASE_URL=http://127.0.0.1:8000 \
  expense-tracker-frontend:dev
```

Alpine here against distroless there follows from what each image carries. This one
carries static files and a web server Alpine packages, where the backend's conda prefix is
glibc-linked. Alpine's shell is load-bearing as well: the configuration below is applied
by a shell script at startup.

**The configuration arrives at two different times, and that is the whole design.** The
backend reads `DATABASE_URL` from the environment when it starts. vite **inlines**
`import.meta.env.VITE_API_BASE_URL` into the bundle at build time, so the origin is fixed
by the time a container starts. One image serves every deployment, so the build bakes a
placeholder and the container rewrites it:

```sh
# in the builder, before vite build
printf 'VITE_API_BASE_URL=__EXPENSE_TRACKER_API_BASE_URL__\n' > frontend/.env.production.local
```

`.env.production.local` is vite's **highest-precedence** source in production mode, so it
beats the committed `frontend/.env` by a documented rule. `.gitignore`'s `.env*` rule makes
the file uncommittable and `.dockerignore`'s keeps a developer's own copy out of the
context, so it can only ever be the one that line writes.

`frontend/docker/40-api-base-url.sh` does the rewrite, from
`/docker-entrypoint.d/`, which the base image's entrypoint runs before starting nginx. It
is copied with `--chmod=0755`, the exec bit being what has that entrypoint run it: a file
there without one is logged and skipped.

The script refuses to start the container unless `API_BASE_URL` is an absolute `http(s)`
URL with no path - the backend's no-defaults rule, applied to the other stack:

```sh
docker run --rm expense-tracker-frontend:dev
# ERROR: API_BASE_URL is not set.
docker run --rm -e API_BASE_URL=http://host/gateway expense-tracker-frontend:dev
# ERROR: API_BASE_URL must be scheme://host[:port] with no path, query or fragment
```

That last refusal is the one worth having. All four `api/` modules resolve their requests
as `new URL("/api/expenses", API_BASE_URL)`, and an absolute path **discards** whatever
path the base carried, so the check is what reports a path at startup instead of at every
call site. The value is the origin the **browser** calls, so it is whatever a user's
browser can reach.

Three properties here are also unchecked by anything.

**The placeholder's survival is asserted at build time, not at run time.** esbuild does not
constant-fold `new URL(path, "__TOKEN__")`, so the token reaches the chunk as a string
literal - but that is a property of the minifier rather than a promise, so the Dockerfile
ends the builder stage with a `grep -rq` over `dist/` that fails the build while that holds
no longer. The startup script tolerates finding nothing, a container restarted on a
filesystem it already rewrote being the ordinary case, and the build-time check is what
keeps that tolerance from covering a bad build.

**The document root is `/srv/expense-tracker`**, a directory the `COPY` creates, so it
holds `dist/` and nothing the base shipped - the base's `/usr/share/nginx/html` arrives
carrying a stock `50x.html` that names nginx, where `server_tokens off` does not. The
`--chown=101:101` on that `COPY` is load-bearing: the startup script rewrites those files
as that user.

**`Cache-Control` is computed by two `map`s read by a single server-level `add_header`.**
`add_header` in a nested block **replaces** the inherited set rather than adding to it, so
keeping every header on one directive is what keeps the security headers on every
response. The response status is half the key, so the year-long `immutable` lifetime
belongs to a response that carries an asset and a `404` during a deployment stays
retryable.

```sh
curl -sI localhost:8080/                         # Cache-Control: no-store
curl -sI localhost:8080/totals                   # no-store - the SPA fallback, served the shell
curl -sI localhost:8080/assets/index-<hash>.js   # public, max-age=31536000, immutable
curl -sI localhost:8080/assets/missing.js        # 404, and no-store
```

`/totals` is a client-side route with no file behind it, so `try_files $uri $uri/
/index.html` answers anything that is not a real file with the shell. `/assets/` is the one
exception, resolving or `404`ing, so a missing chunk reaches the module loader as the 404
it is.

**The CSP is derived from what the bundle actually loads**, and is reported as
`default-src 'none'` plus four allowances. Three are unremarkable - one same-origin module
script, one same-origin stylesheet, `data:` images because daisyUI inlines its checkbox and
select glyphs into the CSS, and `connect-src` naming the one API origin. The fourth is
`style-src 'unsafe-inline'`, which the bundle asks for: React renders inline `style`
**attributes** for the date picker and the table column widths, and a style attribute is
governed by `style-src-attr`, which falls back to `style-src`. `style-src-elem 'self'`
sits beside it so the stylesheet itself keeps the tighter rule wherever a browser
implements that directive; Firefox ignores it. There is no `font-src`: the type scale is
system fonts and the bundle declares no `@font-face`.

The build context is the repository root here too, and `backend/pyproject.toml` is the one
backend file the build reads: `pixi install --locked` resolves the lock against it. pixi
validates the lock against the **whole** workspace, and the lock records the backend's pypi
path dependency, so that file has to be there even though this environment holds no python
at all. Only its metadata is read - `backend/src` stays out of the build - which is what
keeps a backend source change from invalidating any layer here.

The image is about 92 MB, and roughly 91 MB of that is the base: `dist/` is some 550 kB.
Compression is switched on in the server config because `nginx.conf` ships `#gzip  on;`,
and it earns its line - the one application chunk is 330 kB raw against 105 kB gzipped.
The base carries a tag and a digest on the same terms as the backend's two, and Dependabot
bumps it, with the three-day cooldown applying because this image lives on Docker Hub. See
[Keeping the bases current](#keeping-the-bases-current).

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
locally: every statement idempotent, `IF NOT EXISTS` never altering, and a change to an
existing table cured by throwing the cluster away rather than by a migration. Here the
cluster is a volume, so **dropping the volume is what re-applies the schema** -
`backend-db-reset` by another name.

The image sets `POSTGRES_INITDB_ARGS=--locale=C --encoding=UTF8`, the two flags
`db-create` passes `initdb`. That is not decoration: `GET /api/expenses/categories` orders
`category` in SQL, and C collation is byte order under musl and glibc alike, so the
deployed server sorts exactly as the conda-forge cluster a developer runs. Declaring it in
the image rather than leaving it to the caller is what stops it being lost by whoever runs
the thing. `18-alpine` resolves to 18.6, the version `pixi.toml` pins, so the two agree
today without either naming the other.

**It runs as uid 70 and ships no `gosu`.** The base calls `gosu` in exactly one situation,
dropping from root to the `postgres` user, and all three of its call sites sit behind
`if [ "$(id -u)" = '0' ]` - so starting as 70 reaches none of them and the binary is
unreachable code. It was also 1.7 MB of Go carrying **26 HIGH/CRITICAL** findings into
[the vulnerability gate](releases.md#the-vulnerability-gate), in `net/http`, `crypto/tls`,
`encoding/xml`, `html/template` and `net/url`, none of which a program that resolves a user
and `exec`s could reach either. Deleting it takes this image to **zero** findings.

What that gives up is the other thing root does: `docker_create_db_directories` chowns the
data directory. A fresh **named** volume needs no chown, docker seeding it from the image's
own `/var/lib/postgresql`, which the base ships `70:70` and mode `1777`. A host **bind**
mount needs `chown 70:70` on the directory first, or `initdb` stops at
`mkdir: can't create directory '/var/lib/postgresql/18/': Permission denied`. An explicit
`--user 0` fails at once with `gosu: not found` and exit 127 rather than starting degraded.

`PGDATA` is the base's own `/var/lib/postgresql/18/docker`, underneath the volume it
declares - which is the whole `/var/lib/postgresql` directory rather than the pre-18
`data/` beneath it. That is the path to mount.

The image is about 433 MB and effectively all of it is the base; `schema.sql` is 8 kB. The
debian variant is 650 MB, but the reason for alpine is the gate rather than the size: 62
HIGH/CRITICAL in `postgres:18.6` with a fix available for **none** of them, against the 2
here, both of which `.trivyignore.yaml` already covered for the SPA's alpine base.
