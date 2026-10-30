# The database image: the official PostgreSQL image carrying this repository's schema.
# One stage, because there is nothing to build - the base is the server and the only thing
# added is one file.
#
# The build context is the REPOSITORY ROOT, not this directory, which is what lets the COPY
# below read backend/schema.sql where it already lives rather than keeping a second copy
# here. `pixi run database-image` passes it, exactly as the other two images do.
#
# The base carries a tag as well as a digest: the tag says which version a reader is looking
# at, the digest is what is actually pulled. Same rule CLAUDE.md sets for GitHub Actions.
# 18-alpine resolves to 18.6, the version pixi.toml pins for the local cluster, so a
# developer and a deployment run the same minor.
#
# alpine rather than the debian variant, for the reason .trivyignore.yaml records for the
# SPA's base: the smaller package inventory is what keeps findings out of the HIGH/CRITICAL
# gate in release.yml, which fails a release outright.

FROM postgres:18-alpine@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5

# The base's entrypoint runs *.sql here in name order, and ONLY when the data directory is
# empty. That is what schema.sql is already written for: every statement idempotent,
# IF NOT EXISTS never altering, and a change to an existing table needing the data
# directory thrown away rather than a migration. So throwing the volume away is what
# re-applies this file, which is the same bargain `backend-db-reset` strikes locally.
#
# The numeric prefix leaves room on either side of it for a second file.
COPY backend/schema.sql /docker-entrypoint-initdb.d/10-schema.sql

# The same two flags `db-create` passes initdb, so this server sorts text the way the local
# cluster does: `category` is ordered in SQL by two endpoints, and C collation is byte order
# under musl and glibc alike, which is what makes the alpine base safe to sort on. Declared
# here rather than left to whatever runs the image, so the ordering schema.sql's indexes
# rest on cannot be lost by a caller who does not know to ask for it. The entrypoint reads
# this name from the environment, so `docker run -e` still overrides it.
ENV POSTGRES_INITDB_ARGS="--locale=C --encoding=UTF8"

# Deleting gosu and running unprivileged are ONE change, not two. The base calls gosu in
# exactly one situation - dropping from root to the postgres user - and all three call sites
# sit behind `if [ "$(id -u)" = '0' ]`, so starting as 70 reaches none of them and the
# binary becomes unreachable code. It is also 1.7 MB of Go whose stdlib carried 26
# HIGH/CRITICAL findings into the gate release.yml fails a release on, every one of them in
# net/http, crypto/tls, encoding/xml, html/template or net/url - none of which a program
# that resolves a user and execs could reach either. Removing it takes this image to zero.
#
# What it gives up is the other thing root does: docker_create_db_directories chowns the
# data directory. A fresh NAMED volume needs no chown, docker seeding it from this image's
# own /var/lib/postgresql, which the base ships 70:70 and mode 1777. A host BIND mount now
# needs `chown 70:70` on the directory first, and an explicit `--user 0` fails at once with
# `gosu: not found` and exit 127 rather than starting degraded.
RUN rm /usr/local/bin/gosu

# The base's own postgres user, written numerically so the image depends on no entry in its
# /etc/passwd - the same reason the other two images spell out 65532 and 101.
#
# No ENTRYPOINT, CMD or EXPOSE: the base declares all three and this image changes none of
# them. PGDATA is the base's too, /var/lib/postgresql/18/docker under the volume it
# declares, which is the whole directory rather than the pre-18 data/ beneath it.
USER 70:70
