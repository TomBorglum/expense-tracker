# Pure Python image. Because the Tailwind output CSS is committed, there is no
# Node, no tailwindcss binary, and no network fetch for assets at build time.

# Pinned exactly, matching the pixi version used locally.
FROM ghcr.io/prefix-dev/pixi:0.73.0-bookworm-slim AS build

WORKDIR /app

# Copy only the manifest and lockfile first so the solve layer caches until one
# of them actually changes.
COPY pixi.toml pixi.lock ./

# The prod environment excludes the test feature (pytest, ruff, basedpyright).
RUN pixi install --locked -e prod

# Produce an activation script so the runtime stage does not need pixi itself.
RUN pixi shell-hook -e prod -s bash > /shell-hook.sh \
    && echo 'exec "$@"' >> /shell-hook.sh

FROM debian:bookworm-slim AS runtime

WORKDIR /app

COPY --from=build /app/.pixi/envs/prod /app/.pixi/envs/prod
COPY --from=build /shell-hook.sh /shell-hook.sh
COPY expense_tracker/ ./expense_tracker/

# Instance folder holds the SQLite database. Mount a volume here to persist it
# across container restarts.
RUN mkdir -p /app/instance

EXPOSE 5000

ENV FLASK_APP=expense_tracker

ENTRYPOINT ["/bin/bash", "/shell-hook.sh"]
CMD ["flask", "run", "--host", "0.0.0.0", "--port", "5000"]
