# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Branch and merge rules (soft, must be followed)

This repo is on the GitHub **free plan**, so branch protection and required checks
**cannot be enforced**. The rules below are enforced by discipline only - follow
them as if GitHub blocked non-compliant merges. The full rationale lives in
[`CONTRIBUTING.md`](CONTRIBUTING.md); the hard rules:

- **Never push directly to `main`.** Make every change on a branch and open a PR.
- **Squash-merge only** (rebase is fine; **no merge commits**, except the
  multi-entry-branch exception documented in `CONTRIBUTING.md`).
- **The PR title must be a valid Conventional Commit** - it becomes the squashed
  commit subject that release-please parses (`feat`/`fix`/`deps` cut releases;
  other types ride along hidden).
- **Wait for the `SonarCloud Code Analysis` check to pass before merging.**
- **Resolve all review threads before merging.**
- **Keep `main` linear** (no force-pushes) and **delete the branch after merge**:
  `gh pr merge --squash --delete-branch`.
- **Branch naming:** `<type>/<short-kebab-description>` (e.g. `feat/monthly-report`).

## Releases

Releases are automated by [release-please](https://github.com/googleapis/release-please)
via `.github/workflows/release-please.yml`. **Never hand-edit versions, git tags,
or `CHANGELOG.md`** - merging Conventional-Commit PRs into `main` drives the
`.release-please-manifest.json` version, and merging the release PR tags and
publishes the GitHub Release.

## Source conventions

- **ASCII-only** committed source (no em-dashes, smart quotes, arrows, ellipses).
- **Pin dependency versions exactly** (`==` in `pixi.toml`) and **SHA-pin GitHub
  Actions** with a version comment.
