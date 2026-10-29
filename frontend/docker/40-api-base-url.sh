#!/bin/sh
# Rewrites the build-time placeholder in the served bundle to the API origin this
# container was given. It sits in /docker-entrypoint.d/, so the base image's entrypoint
# runs it before nginx starts and a non-zero exit here stops the container coming up.
#
# This script exists because the two stacks take their configuration at different times.
# The backend reads DATABASE_URL from the environment when it starts; vite inlines
# VITE_API_BASE_URL into the bundle at build time, so there is nothing left to read. A
# placeholder substituted at start is what keeps one published image servable against any
# API origin instead of one image per deployment.

set -eu

ME=$(basename "$0")
PLACEHOLDER='__EXPENSE_TRACKER_API_BASE_URL__'
# Matches `root` in default.conf.template, and the destination of the Dockerfile's COPY.
HTML_ROOT=/srv/expense-tracker

# No default, deliberately, and the same rule config.py applies to the database: a guessed
# origin is a container that comes up looking healthy and serves an app that cannot reach
# anything. Refusing to start is the louder half of that pair.
if [ -z "${API_BASE_URL:-}" ]; then
    echo "$ME: ERROR: API_BASE_URL is not set." >&2
    echo "$ME:        Give the container the origin the BROWSER should call, for example" >&2
    echo "$ME:        -e API_BASE_URL=http://127.0.0.1:8000" >&2
    exit 1
fi

case "$API_BASE_URL" in
    http://* | https://*) ;;
    *)
        echo "$ME: ERROR: API_BASE_URL must be an absolute http:// or https:// URL," >&2
        echo "$ME:        got '$API_BASE_URL'" >&2
        exit 1
        ;;
esac

# scheme://host[:port] and nothing after it. The path is the part worth refusing: the
# bundle resolves every request as new URL("/api/expenses", API_BASE_URL), and an absolute
# path discards whatever path the base carried - so a value like http://host/gateway would
# be accepted here and then silently ignored at all four call sites. The character check
# is what also keeps the value safe as a sed replacement below.
authority=${API_BASE_URL#*://}
authority=${authority%/}
if [ -z "$authority" ] || [ -n "$(printf '%s' "$authority" | tr -d 'A-Za-z0-9.:_[]-')" ]; then
    echo "$ME: ERROR: API_BASE_URL must be scheme://host[:port] with no path, query or" >&2
    echo "$ME:        fragment, got '$API_BASE_URL'" >&2
    exit 1
fi

# Found rather than named: which chunk the four api/ modules land in is rollup's decision,
# and its filename carries a content hash that changes with them.
#
# Finding nothing is not an error. The image is asserted at build time to carry the
# placeholder, so the only way to reach this with none left is a container started a
# second time on a filesystem this script already rewrote - `docker start` after a stop -
# where the origin is already in place and already correct.
files=$(grep -rl "$PLACEHOLDER" "$HTML_ROOT" || true)

if [ -z "$files" ]; then
    echo "$ME: no placeholder left to substitute; the bundle already names an API origin"
    exit 0
fi

echo "$files" | while read -r file; do
    sed -i "s|$PLACEHOLDER|$API_BASE_URL|g" "$file"
done

echo "$ME: substituted the API origin $API_BASE_URL into $(echo "$files" | wc -l) file(s)"
