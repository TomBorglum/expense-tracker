# The SPA image. Two stages: pixi materialises the `frontend` environment and vite builds
# the bundle, nginx gets dist/ and nothing that produced it.
#
# No `# syntax=` directive, and both bases carry a tag as well as a digest, for the
# reasons backend/Dockerfile sets out at length.
#
# The build context is the REPOSITORY ROOT, not this directory - the toolchain is declared
# across pixi.toml and pixi.lock, which live there. `pixi run frontend-image` passes it.

FROM ghcr.io/prefix-dev/pixi:0.81.0-noble@sha256:788ae451641666e2d1f79d3dbe35392dfc7e9b394b16a3acb75c347f3badb2ab AS builder

WORKDIR /app

# The toolchain layer. nodejs and pnpm are all the `frontend` environment holds, and they
# come from the manifest pair, so this layer survives every change to the application
# below it.
#
# backend/pyproject.toml is here for `--locked` and for nothing else. pixi validates the
# lock against the WHOLE workspace, and the lock records the backend's pypi path
# dependency, so without that file the install fails with "lock file not up-to-date with
# the workspace" even though this environment holds no python at all. Only its metadata is
# read: backend/src never enters this build, which is what keeps a backend source change
# from invalidating anything here.
COPY pixi.toml pixi.lock ./
COPY backend/pyproject.toml ./backend/

RUN --mount=type=cache,target=/root/.cache/rattler \
    pixi install --locked -e frontend

# The dependency layer, keyed on the three files pnpm reads and no more, so editing a
# component does not reinstall node_modules. pnpm-workspace.yaml is not optional: it
# carries minimumReleaseAge and the msw allowBuilds answer, and pnpm exits non-zero while
# a build script is unanswered.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./frontend/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pixi run --locked -e frontend frontend-install

# Then the application, last, so that editing a component re-runs the build and nothing
# above it. node_modules is in .dockerignore, so this cannot overwrite what the layer
# above installed.
COPY frontend/ ./frontend/

# vite inlines import.meta.env.VITE_API_BASE_URL at build time, so the API origin cannot
# be a runtime variable the way the backend's DATABASE_URL is. A placeholder is baked in
# instead and rewritten when the container starts, by docker/40-api-base-url.sh.
#
# .env.production.local rather than a build argument or a plain .env: it is vite's
# HIGHEST-precedence source in production mode, so it beats the committed frontend/.env
# deterministically instead of depending on how an environment variable ranks against a
# dotenv file. .gitignore's `.env*` rule already makes it uncommittable and
# .dockerignore's keeps a developer's own copy out of this context, so the file can only
# ever be the one this line writes.
RUN printf 'VITE_API_BASE_URL=__EXPENSE_TRACKER_API_BASE_URL__\n' > frontend/.env.production.local

RUN pixi run --locked -e frontend frontend-build

# The assertion the entrypoint script cannot make. esbuild does not constant-fold
# `new URL(path, "__TOKEN__")`, so the token survives minification as a string literal in
# all four api/ modules - but that is a property of the minifier rather than a promise,
# and the entrypoint deliberately tolerates finding no placeholder so a restarted
# container still comes up. Something has to fail loudly if a build ever inlines the token
# away, and build time is where that belongs.
RUN grep -rq '__EXPENSE_TRACKER_API_BASE_URL__' frontend/dist/


FROM nginxinc/nginx-unprivileged:1.31-alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e

# --chown is load-bearing: the entrypoint script rewrites these files as 101, and a COPY
# leaves them root-owned by default. The destination is not the base's
# /usr/share/nginx/html but a directory this COPY creates, so that the document root holds
# the build output and nothing the base shipped; default.conf.template says why.
COPY --from=builder --chown=101:101 /app/frontend/dist/ /srv/expense-tracker/

COPY frontend/docker/default.conf.template /etc/nginx/templates/default.conf.template

# --chmod rather than a separate chmod layer: the base's entrypoint SKIPS a file in
# /docker-entrypoint.d that is not executable, logging one line and carrying on, so a
# missing exec bit would serve the bundle with its placeholder unsubstituted instead of
# failing.
COPY --chmod=0755 frontend/docker/40-api-base-url.sh /docker-entrypoint.d/40-api-base-url.sh

# Restricts envsubst to this one name, so every other $name in the template reaches nginx
# as the nginx variable it is. None of this base's own environment variables collides with
# one today, which makes this a guard against a future collision rather than a fix for a
# present bug.
ENV NGINX_ENVSUBST_FILTER="API_BASE_URL"

# What the base already runs as, restated numerically so the image depends on no entry in
# its /etc/passwd - the same reason backend/Dockerfile spells out 65532.
USER 101:101

# 8080, not 80: an unprivileged process cannot bind a privileged port.
EXPOSE 8080

# No ENTRYPOINT and no CMD: the base's own entrypoint is what runs /docker-entrypoint.d/
# and therefore the substitution above, and overriding either would skip it.
