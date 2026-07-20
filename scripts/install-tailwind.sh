#!/usr/bin/env bash
# Fetch the pinned tailwindcss standalone binary into bin/, verifying its checksum.
#
# Tailwind is not packaged on conda-forge, so it cannot be a pixi dependency and
# cannot enter pixi.lock. TAILWIND_VERSION and TAILWIND_SHA256 are supplied by the
# pixi task in pixi.toml, keeping the pin alongside every other pinned dependency.
#
# Lives in a script rather than inline in pixi.toml because pixi runs tasks through
# deno_task_shell, which does not support `if`/`fi`.

set -euo pipefail

: "${TAILWIND_VERSION:?must be set by the pixi task}"
: "${TAILWIND_SHA256:?must be set by the pixi task}"

target="bin/tailwindcss"
url="https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-x64"

mkdir -p bin

# Already present and matching the pin: nothing to do.
if [ -x "$target" ] && printf '%s  %s' "$TAILWIND_SHA256" "$target" | sha256sum -c - >/dev/null 2>&1; then
  echo "tailwindcss ${TAILWIND_VERSION} already installed"
  exit 0
fi

# Download to a temp name and only promote it once the checksum verifies, so an
# interrupted or tampered download never leaves a usable binary behind.
tmp="${target}.tmp"
curl -fsSL --proto '=https' -o "$tmp" "$url"
printf '%s  %s' "$TAILWIND_SHA256" "$tmp" | sha256sum -c -
chmod +x "$tmp"
mv "$tmp" "$target"

echo "installed tailwindcss ${TAILWIND_VERSION}"
