# What the database image IS, declared beside it rather than in the pipeline. A release
# merges its own metadata under this file, so what is declared here wins.
#
# Paths resolve the way a plain `docker build` resolves them - `context` against the
# working directory, `dockerfile` against the context - so this file is invoked from THIS
# directory, by `poe image` locally and by the release in CI. A context that leaves this
# directory needs `--allow=fs.read=..`, which both callers pass.

variable "DESCRIPTION" {
  default = "The expense-tracker database - PostgreSQL carrying the four tables schema.sql declares, applied on first boot."
}

# The release target: no tags - a release names what it publishes.
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
