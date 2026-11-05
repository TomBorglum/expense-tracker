# What the database image IS, declared beside it rather than in the pipeline.
#
# Paths resolve the way a plain `docker build` resolves them - `context` against the
# working directory, `dockerfile` against the context - so this file is invoked from THIS
# directory, as `poe image` does. A context that leaves this directory needs
# `--allow=fs.read=..`.

variable "DESCRIPTION" {
  default = "The expense-tracker database - PostgreSQL carrying the four tables schema.sql declares, applied on first boot."
}

# The release target. Its name is fixed at `image`; CLAUDE.md pairs it with what calls it.
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
