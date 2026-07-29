#!/bin/bash
set -euo pipefail

# Fetch the standalone Tailwind CSS CLI into bin/tailwindcss.
#
# Tailwind ships no conda-forge package, and this repo deliberately has no Node
# toolchain, so the standalone binary is the only Node-free option. It is pinned
# by version *and* sha256 - bump both together from the release page:
# https://github.com/tailwindlabs/tailwindcss/releases
TAILWIND_VERSION="4.3.3"
TAILWIND_SHA256="dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$REPO_ROOT/bin/tailwindcss"

# pixi.toml pins platforms = ["linux-64"], so only the linux-x64 asset is fetched.
OS="$(uname -s)"
ARCH="$(uname -m)"
if [[ "$OS" != "Linux" || "$ARCH" != "x86_64" ]]; then
  echo "install-tailwind: unsupported platform $OS/$ARCH (this repo targets linux-64 only)" >&2
  exit 1
fi

# Idempotency guard: a re-run is a clean no-op, which is what makes this safe as a
# depends-on for every css task. Matching on the hash (not just the path) also
# re-downloads automatically when the pin above is bumped.
if [[ -x "$TARGET" ]] && echo "$TAILWIND_SHA256  $TARGET" | sha256sum --check --status; then
  echo "tailwindcss $TAILWIND_VERSION already installed, skipping"
  exit 0
fi

URL="https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-x64"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "install-tailwind: downloading tailwindcss $TAILWIND_VERSION"
curl -fsSL --proto '=https' --tlsv1.2 "$URL" -o "$TMP"

if ! echo "$TAILWIND_SHA256  $TMP" | sha256sum --check --status; then
  echo "install-tailwind: sha256 mismatch for $URL" >&2
  echo "install-tailwind: expected $TAILWIND_SHA256" >&2
  echo "install-tailwind: got      $(sha256sum "$TMP" | cut -d' ' -f1)" >&2
  exit 1
fi

mkdir -p "$REPO_ROOT/bin"
# Move into place only after the hash check, so an interrupted or corrupt download
# never leaves a half-written binary that the guard would later accept.
mv "$TMP" "$TARGET"
trap - EXIT
chmod +x "$TARGET"

echo "install-tailwind: installed tailwindcss $TAILWIND_VERSION at $TARGET"
