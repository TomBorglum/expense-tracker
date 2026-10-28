# The API image. Two stages: pixi materialises the `backend` environment, distroless gets
# the finished prefix and nothing that built it.
#
# No `# syntax=` directive: BuildKit's built-in frontend already parses everything below,
# including the cache mounts, so the directive would only add an external image fetched
# over the network at build time - and one that cannot be pinned the way the bases are
# without going stale unnoticed.
#
# The build context is the REPOSITORY ROOT, not this directory - the environment is declared
# across pixi.toml and pixi.lock, which live there. `pixi run backend-image` passes it.
#
# Both bases carry a tag and a digest: the tag says which version a reader is looking at,
# the digest is what is actually pulled. Same rule CLAUDE.md sets for GitHub Actions.

FROM ghcr.io/prefix-dev/pixi:0.81.0-noble@sha256:788ae451641666e2d1f79d3dbe35392dfc7e9b394b16a3acb75c347f3badb2ab AS builder

# /app is load-bearing twice over. pixi writes the environment to <manifest>/.pixi/envs/backend
# and a conda prefix is not relocatable, so the runtime stage has to hold it at this exact
# path; and pixi rewrites every console script's shebang to an absolute interpreter path
# underneath it, so a prefix that moved would leave them pointing at nothing.
WORKDIR /app

# Everything `pixi install` reads and nothing else. backend/ is here rather than copied
# after the install because the environment installs the app itself as a path dependency -
# hatchling builds a wheel out of backend/src - so the source has to be present before the
# environment can be solved against the lock at all.
COPY pixi.toml pixi.lock ./
COPY backend/pyproject.toml ./backend/
COPY backend/src ./backend/src

# --locked refuses to re-resolve, so the lock is the single source of truth here exactly as
# it is in CI. The cache mounts keep a rebuild to a relink and a wheel build rather than a
# fresh download of the whole environment; neither mount reaches the stage below.
RUN --mount=type=cache,target=/root/.cache/rattler \
    --mount=type=cache,target=/root/.cache/uv \
    pixi install --locked -e backend


FROM gcr.io/distroless/base-debian12:nonroot@sha256:7f0c72cd138b442ae0deeb69c08b1acf5525439ba251a49ad93c320a061567e5

# The prefix, at the path the builder wrote it to; the repetition is the point, not a typo.
# No --chown: nothing in this image writes to the prefix, and root-owned is what keeps it
# that way under a non-root user.
COPY --from=builder /app/.pixi/envs/backend /app/.pixi/envs/backend

# What `pixi shell-hook` would export, set by hand because there is no shell here to run an
# activation script in. None of the packages pinned in pixi.toml ships one, which is what
# makes this substitution complete rather than approximate. The two SSL names matter because
# distroless carries no system trust store for the prefix's own openssl to find.
#
# PATH names the prefix and nothing else, because there is nothing else: /bin and /usr/bin
# are empty in this base, so the usual tail would only suggest otherwise.
ENV PATH="/app/.pixi/envs/backend/bin" \
    SSL_CERT_FILE="/app/.pixi/envs/backend/ssl/cacert.pem" \
    SSL_CERT_DIR="/app/.pixi/envs/backend/ssl/certs"

# distroless's `nonroot`, written numerically so the image depends on no entry in the base's
# /etc/passwd.
USER 65532:65532

EXPOSE 8000

# The interpreter named outright rather than the `uvicorn` console script: that script works
# only while its rewritten shebang still matches the COPY above, and naming python keeps the
# image from depending on a detail of how pixi wrote it.
#
# Same factory target as the `dev` task in pyproject.toml. --host 0.0.0.0 because a
# container's loopback reaches nobody; the port is fixed rather than read from UVICORN_PORT
# because `docker run -p` is what maps it; and no --reload.
ENTRYPOINT ["/app/.pixi/envs/backend/bin/python", "-m", "uvicorn", \
            "expense_tracker:create_app", "--factory", \
            "--host", "0.0.0.0", "--port", "8000"]
