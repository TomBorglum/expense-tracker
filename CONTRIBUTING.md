# Contributing

Releases are automated with [release-please](https://github.com/googleapis/release-please).
It reads the commit history on `main`, decides the next version, and maintains a
"chore(main): release X.Y.Z" pull request that updates `CHANGELOG.md` and the version.
Merging that PR tags the version and publishes the GitHub Release. release-please
creates `CHANGELOG.md` itself, in the first release PR it opens.

For that to work, commits must follow
[Conventional Commits](https://www.conventionalcommits.org/). This document is the
guard rail for naming commits and branches so the automation does the right thing.

## Soft branch protection

This repo is on the GitHub **free plan**, so branch protection rules and required
status checks **cannot be enforced** on a private repository. The rules below are
therefore **soft rules**: followed by discipline, not by GitHub blocking a
non-compliant merge. Treat them as if they were enforced. The sibling repo
`wsl-cloud-init` enforces the same rules with a repository ruleset; we keep parity
here manually.

- **Never push directly to `main`.** Every change lands through a pull request.
- **Squash-merge** (or rebase); **never a merge commit** (see the exception below).
- **The PR title must be a valid Conventional Commit** (it becomes the commit
  subject on `main`).
- **Keep `main` linear** (no force-pushes, no merge commits).
- **Let the SonarCloud check pass before merging.**
- **Resolve all review threads before merging.**
- **Delete the branch after merge.**

A compliant merge from the CLI:

```bash
gh pr merge --squash --delete-branch
```

## Commit message format

```
<type>(<optional scope>): <description>

<optional body - what changed and why>

<optional footer - BREAKING CHANGE:, Refs #123, Co-Authored-By:>
```

The first line (the *subject*) is what release-please parses. Keep it lowercase, in
the imperative mood ("add", not "added" or "adds"), with no trailing period, and
ideally under ~72 characters.

## Types

These are the types configured in
[`release-please-config.json`](release-please-config.json). A type selects the
changelog section, and - because release-please treats any commit in a **visible**
section as a releasable unit - decides whether the change can cut a release on its
own. Only `feat`, `fix` and `deps` are visible.

| Type | Example | Changelog section | Cuts a release? |
| --- | --- | --- | --- |
| `feat` | `feat: add monthly budget report` | Features | yes - **minor** (1.1.0) |
| `fix` | `fix: correct currency rounding` | Bug Fixes | yes - **patch** (1.0.1) |
| `deps` | `deps: bump python to 3.14.7` | Dependencies | yes - **patch** (1.0.1) |
| `perf` | `perf: cache the category lookup` | *(hidden)* | no - rides along |
| `revert` | `revert: undo the schema change` | *(hidden)* | no - rides along |
| `docs` | `docs: expand the README` | *(hidden)* | no - rides along |
| `chore` | `chore: tidy config comments` | *(hidden)* | no - rides along |
| `ci` | `ci: pin actions by sha` | *(hidden)* | no - rides along |
| `build` `refactor` `style` `test` | `refactor: extract a helper` | *(hidden)* | no - rides along |

A hidden type neither triggers a release nor appears in the notes. A PR containing
only hidden types will not open a release PR until a `feat`/`fix`/`deps` lands.

> **Visibility = releasability.** Un-hiding a section in
> `release-please-config.json` makes commits of that type start cutting releases.
> That is deliberate for `deps`; be intentional before un-hiding anything else.

### `deps:` vs `ci:`

**If the change alters what a user receives when they run the application, it is
`deps:` (or `feat`/`fix`); if it only touches the build or CI, it is `ci:`/`chore:`.**
That is why `update-python.yml`, which bumps the shipped `pixi.toml` python pin, uses
`deps:`, while Dependabot's GitHub Actions bumps use `ci:`.

## Breaking changes

A breaking change forces a **major** bump (2.0.0). Mark it either with a `!` after
the type, or with a `BREAKING CHANGE:` footer:

```
feat!: drop support for the old import format
```

```
feat: drop support for the old import format

BREAKING CHANGE: pre-1.0 CSV imports are no longer accepted.
```

## Squash merges

Pull requests are **squash-merged**: the branch collapses into one commit on `main`
whose subject is the **PR title**, and the branch's own commit messages are
discarded. So the PR title must be a valid Conventional Commit - a PR titled
`Update budget code` is invisible to release-please and will neither appear in the
changelog nor bump the version.

The one thing release-please still reads from a squash commit's body is a
`BREAKING CHANGE:` footer, so put that in the PR description when it applies.

### Multiple changelog entries from one branch

A squash-merged PR yields exactly one changelog entry, so prefer **focused PRs**:
one logical change, one type. If a single branch genuinely has to produce several
entries, merge it with a **merge commit** so each Conventional Commit on the branch
is parsed individually. This is the only case where a merge commit is acceptable.

## Version selection

release-please aggregates **every commit merged since the last release** (across all
PRs, not just one branch) and applies the highest-impact bump:

```
any  feat! / BREAKING CHANGE       ->  MAJOR
else any  feat                     ->  MINOR
else any  fix / deps               ->  PATCH
else only ride-along types         ->  no release
   (perf, revert, docs, chore, ci, ...)
```

## Branch names

release-please ignores branch names entirely - it reads only commit subjects and PR
titles on `main`. Branch names are a human convention: mirror the commit type.

```
<type>/<short-kebab-description>

feat/monthly-budget-report
fix/currency-rounding
deps/bump-python
docs/readme-overview
```

Optionally prefix an issue number: `feat/123-monthly-budget-report`.

## The release flow

1. Open a PR with a Conventional Commit **title** and let the SonarCloud check pass.
2. Merge it (squash). release-please opens or updates the **chore(main): release
   X.Y.Z** PR.
3. Merge that release PR - the version is tagged and the GitHub Release is published
   automatically. No manual tagging, and never hand-edit the version, tags, or
   `CHANGELOG.md`.

## ASCII-only source

Keep committed source files **ASCII-only**. Avoid characters an editor or paste
inserts automatically: em/en dashes, smart quotes, arrows, and ellipses. Use their
ASCII equivalents (`-` or `--`, `->`, straight `"` / `'`, `...`).

Check before committing:

```bash
git grep -nP '[^\x00-\x7F]'   # review anything it prints
```
