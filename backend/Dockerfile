# The API image. Two stages: pixi materialises the `backend` environment, distroless gets
# the finished prefix and nothing that built it.
#
# BuildKit's built-in frontend parses everything below, the cache mounts included, so this
# file needs no `# syntax=` directive and fetches no frontend image at build time.
#
# The build context is the REPOSITORY ROOT, not this directory - the environment is declared
# across pixi.toml and pixi.lock, which live there. `pixi run backend-image` passes it.
#
# Both bases carry a tag and a digest: the tag says which version a reader is looking at,
# the digest is what is actually pulled. Same rule CLAUDE.md sets for GitHub Actions.

FROM ghcr.io/prefix-dev/pixi:0.81.0-noble@sha256:788ae451641666e2d1f79d3dbe35392dfc7e9b394b16a3acb75c347f3badb2ab AS builder

# /app is load-bearing twice over. pixi writes the environment to <manifest>/.pixi/envs/backend
# and a conda prefix resolves against that absolute path, so the runtime stage holds it at
# this exact one; and pixi rewrites every console script's shebang to an interpreter path
# underneath it, which the same path keeps valid.
WORKDIR /app

# Everything `pixi install` reads and nothing else. backend/ comes first because the
# environment installs the app itself as a path dependency - hatchling builds a wheel out of
# backend/src - so the install reads that source while solving against the lock.
COPY pixi.toml pixi.lock ./
COPY backend/pyproject.toml ./backend/
COPY backend/src ./backend/src

# --locked refuses to re-resolve, so the lock is the single source of truth here exactly as
# it is in CI. The cache mounts keep a rebuild to a relink and a wheel build rather than a
# fresh download of the whole environment; neither mount reaches the stage below.
#
# They are warm only where a builder persists, which is this command run locally and not
# release.yml: setup-buildx-action creates a new builder for each job, and no cache
# exporter carries a mount's contents - `cache-to` exports build steps, not mounts - so
# every CI build fills them from scratch.
RUN --mount=type=cache,target=/root/.cache/rattler \
    --mount=type=cache,target=/root/.cache/uv \
    pixi install --locked -e backend


# base-nossl supplies glibc, which the prefix links, and leaves openssl to the prefix's own
# copy. It is base minus libssl.so.3, libcrypto.so.3, the OpenSSL engines and their dpkg
# entry - 24.6 MB against 33.1 MB - which keeps those four out of what a scanner inventories
# and reports CVEs against. /etc/ssl/certs/ca-certificates.crt ships in both variants and
# goes unread in both; see the ENV block below.
FROM gcr.io/distroless/base-nossl-debian12:nonroot@sha256:be40c00dfabd86576d92666e87e406714d5618342de1a0c213ad232de255172e

# The prefix, at the path the builder wrote it to, source and destination matching for that
# reason. It stays root-owned, which is read-only to the non-root user below.
COPY --from=builder /app/.pixi/envs/backend /app/.pixi/envs/backend

# What `pixi shell-hook` exports, set by hand, this base holding no shell to run an
# activation script in. These two are the whole substitution: every package pinned in
# pixi.toml ships without an activation script.
#
# SSL_CERT_FILE restates a default rather than correcting one. conda-forge's openssl is
# built with its own OPENSSLDIR, so it reads ssl/cert.pem out of the prefix - which is why
# the base's own ca-certificates.crt goes unread - and the COPY above is what puts that
# prefix back where it was built. Naming the file keeps the trust store greppable in this
# file rather than compiled invisibly into libcrypto. SSL_CERT_DIR is unset: the prefix's
# ssl/certs holds a .keep.
#
# PATH names the prefix alone, which is where every binary in this image lives: /bin and
# /usr/bin are empty in this base.
ENV PATH="/app/.pixi/envs/backend/bin" \
    SSL_CERT_FILE="/app/.pixi/envs/backend/ssl/cacert.pem"

# distroless's `nonroot`, written numerically so the image depends on no entry in the base's
# /etc/passwd.
USER 65532:65532

EXPOSE 8000

# The interpreter named outright rather than the `uvicorn` console script, so the image reads
# the prefix at a path of its own rather than through the shebang pixi rewrote.
#
# Same factory target as the `dev` task in pyproject.toml. --host 0.0.0.0 to answer from
# outside the container, and a literal port, `docker run -p` being what maps it;
# UVICORN_PORT is the `dev` task's alone.
ENTRYPOINT ["/app/.pixi/envs/backend/bin/python", "-m", "uvicorn", \
            "expense_tracker:create_app", "--factory", \
            "--host", "0.0.0.0", "--port", "8000"]
