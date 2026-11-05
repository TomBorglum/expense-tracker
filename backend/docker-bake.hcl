# What the API image IS, declared beside it rather than in the pipeline.
#
# Paths resolve the way a plain `docker build` resolves them - `context` against the
# working directory, `dockerfile` against the context - so this file is invoked from THIS
# directory, as `poe image` does. A context that leaves this directory needs
# `--allow=fs.read=..`.

variable "DESCRIPTION" {
  default = "The expense-tracker REST API - four read-only JSON endpoints over PostgreSQL, served by uvicorn."
}

# The release target. Its name is fixed at `image`; CLAUDE.md pairs it with what calls it.
target "image" {
  context    = ".."
  dockerfile = "backend/Dockerfile"

  labels = {
    "org.opencontainers.image.title"       = "expense-tracker-backend"
    "org.opencontainers.image.description" = DESCRIPTION
  }

  # The same two values again, because a label lands in the image config and an annotation
  # on the manifest, and a registry client reads the manifest without pulling the config.
  annotations = [
    "manifest:org.opencontainers.image.title=expense-tracker-backend",
    "manifest:org.opencontainers.image.description=${DESCRIPTION}",
  ]
}

# What a developer builds. The tag is here rather than on `image` so that nothing in the
# published archive carries a local name.
target "dev" {
  inherits = ["image"]
  tags     = ["expense-tracker-backend:dev"]
}
