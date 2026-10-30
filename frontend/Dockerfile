# The SPA image. Two stages: pixi materialises the `frontend` environment and vite builds
# the bundle, nginx gets dist/ and nothing that produced it.
#
# Both bases carry a tag as well as a digest, on the terms backend/Dockerfile sets out at
# length - which also covers the `# syntax=` directive this file needs none of, and why the
# two cache mounts below are warm locally and empty in CI.
#
# The build context is the REPOSITORY ROOT, not this directory - the toolchain is declared
# across pixi.toml and pixi.lock, which live there. `pixi run frontend-image` passes it.

FROM ghcr.io/prefix-dev/pixi:0.81.0-noble@sha256:788ae451641666e2d1f79d3dbe35392dfc7e9b394b16a3acb75c347f3badb2ab AS builder

WORKDIR /app

# The toolchain layer. nodejs and pnpm are all the `frontend` environment holds, and they
# come from the manifest pair, so this layer survives every change to the application
# below it.
#
# backend/pyproject.toml is here for `--locked` alone. pixi validates the lock against the
# WHOLE workspace, and the lock records the backend's pypi path dependency, so the install
# resolves that entry against this file even though this environment holds no python at all
# - "lock file not up-to-date with the workspace" is what its absence reads as. Only its
# metadata is read: backend/src stays out of this build, which is what keeps a backend
# source change from invalidating anything here.
COPY pixi.toml pixi.lock ./
COPY backend/pyproject.toml ./backend/

RUN --mount=type=cache,target=/root/.cache/rattler \
    pixi install --locked -e frontend

# The dependency layer, keyed on the three files pnpm reads and no more, so editing a
# component does not reinstall node_modules. pnpm-workspace.yaml is one of the three: it
# carries minimumReleaseAge and the msw allowBuilds answer, and pnpm exits non-zero while
# a build script is unanswered.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./frontend/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pixi run --locked -e frontend frontend-install

# Then the application, last, so that editing a component re-runs the build and nothing
# above it. node_modules is in .dockerignore, so what the layer above installed is what
# the build reads.
COPY frontend/ ./frontend/

# vite inlines import.meta.env.VITE_API_BASE_URL at build time, where the backend reads
# DATABASE_URL from the environment at startup. So a placeholder is baked in and rewritten
# when the container starts, by docker/40-api-base-url.sh.
#
# .env.production.local is vite's HIGHEST-precedence source in production mode, so it beats
# the committed frontend/.env by a documented rule. .gitignore's `.env*` rule makes it
# uncommittable and .dockerignore's keeps a developer's own copy out of this context, so
# the file is the one this line writes.
RUN printf 'VITE_API_BASE_URL=__EXPENSE_TRACKER_API_BASE_URL__\n' > frontend/.env.production.local

RUN pixi run --locked -e frontend frontend-build

# The assertion build time makes and the entrypoint script leaves alone. esbuild does not
# constant-fold `new URL(path, "__TOKEN__")`, so the token survives minification as a
# string literal in all four api/ modules - a property of the minifier, so this grep is
# what reports a build that stops holding it. The entrypoint tolerates finding no
# placeholder, a restarted container having already rewritten its own filesystem.
RUN grep -rq '__EXPENSE_TRACKER_API_BASE_URL__' frontend/dist/


FROM nginxinc/nginx-unprivileged:1.31-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e

# --chown is load-bearing: the entrypoint script rewrites these files as 101, and a COPY
# leaves them root-owned by default. The destination is a directory this COPY creates
# rather than the base's /usr/share/nginx/html, so the document root holds the build output
# and nothing the base shipped; default.conf.template says why.
COPY --from=builder --chown=101:101 /app/frontend/dist/ /srv/expense-tracker/

COPY frontend/docker/default.conf.template /etc/nginx/templates/default.conf.template

# --chmod rather than a separate chmod layer. The exec bit is what has the base's
# entrypoint run this file: it logs one line and carries on past a file in
# /docker-entrypoint.d without one.
COPY --chmod=0755 frontend/docker/40-api-base-url.sh /docker-entrypoint.d/40-api-base-url.sh

# Restricts envsubst to this one name, so every other $name in the template reaches nginx
# as the nginx variable it is. It is an allowlist of one, and what it buys is silent: a
# substituted $uri leaves `try_files  / /index.html;`, valid config that starts clean and
# serves the wrong thing for every request.
#
# Anchored, because the base passes this to awk as `name ~ /<filter>/`, which is a SUBSTRING
# match - the anchors are what hold the list to this exact name. The backslash escapes the $
# for Docker's own parser; awk receives it as a plain anchor.
ENV NGINX_ENVSUBST_FILTER="^API_BASE_URL\$"

# What the base already runs as, restated numerically so the image depends on no entry in
# its /etc/passwd - the same reason backend/Dockerfile spells out 65532.
USER 101:101

# 8080, the port this base's nginx listens on, a privileged one being out of reach of an
# unprivileged process.
EXPOSE 8080

# The base's own entrypoint runs /docker-entrypoint.d/ and therefore the substitution
# above, so this image keeps it and declares no ENTRYPOINT or CMD of its own.
