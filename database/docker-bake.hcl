# What the database image IS, declared beside it rather than in the pipeline. release.yml
# loads the release metadata docker/metadata-action derives UNDER this file, so bake merges
# the two: `labels` is a map and merges per key, so a key named here wins and every shared
# one survives, and `annotations` is a list and is appended to.
#
# Paths resolve the way a plain `docker build` resolves them - `context` against the
# working directory, `dockerfile` against the context - so this file is invoked from THIS
# directory, by `poe image` locally and by release.yml's `source` input in CI. A context
# that leaves this directory needs `--allow=fs.read=..`, which both callers pass.

variable "DESCRIPTION" {
  default = "The expense-tracker database - PostgreSQL carrying the four tables schema.sql declares, applied on first boot."
}

# The release target: no tags, because release.yml exports an OCI archive and the push job
# is what names the images.
target "image" {
  context    = ".."
  dockerfile = "database/Dockerfile"

  labels = {
    "org.opencontainers.image.title"       = "expense-tracker-database"
    "org.opencontainers.image.description" = DESCRIPTION
  }

  # The same two values again, because a label lands in the image config and an annotation
  # on the manifest, and a registry client reads the manifest without pulling the config.
  annotations = [
    "manifest:org.opencontainers.image.title=expense-tracker-database",
    "manifest:org.opencontainers.image.description=${DESCRIPTION}",
  ]
}

# What a developer builds. The tag is here rather than on `image` so that nothing in the
# published archive carries a local name.
target "dev" {
  inherits = ["image"]
  tags     = ["expense-tracker-database:dev"]
}
