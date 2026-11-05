# Releases

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published. It holds the triggers, the concurrency group
and every value belonging to this repository; the work is done by the reusable
`docker-hub-publish.yml` in [TomBorglum/workflows][workflows], pinned at an exact version.
Four tags per image, derived once by `docker/metadata-action`: `1.1.0`, `1.1`,
`sha-<full commit>` and `latest`.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker-stack      <- the stack, not an image
```

**No one of those names is written down.** `publish.yml` names the image directories and
the called workflow composes `<namespace>/<repository>-<directory>`, the repository read
from `github.event.repository.name`. **So renaming this GitHub repository renames what a
release publishes to.** The fourth repository is composed by the same formula from the
compose directories `publish.yml` names, so `stack/` publishes to
`<namespace>/<repository>-stack`. See [The published stack](#the-published-stack).

Eight `org.opencontainers.image.*` values are derived alongside, carried as both labels
and manifest annotations. **`title` and `description` are each image's own**, declared in
its `docker-bake.hcl` and merged last, which is why the build uses `docker buildx bake`.
The bake target is spelled `image` in five places: all three bake files, metadata-action's
`bake-target`, and the build step's `targets` and `set:` keys.

[`docs/docker-hub-publish.md`][reference] is the reference for everything the called
workflow does: its four jobs, the credential path, how the vulnerability gate is made
trustworthy, the trust policy in general form and who may create a tag. This page carries
what is this repository's to decide.

## The version pin

`publish.yml` pins the called workflow at an exact `vX.Y.Z` tag, which is a security
boundary rather than a style. The release role's trust policy conditions
`job_workflow_ref` on
`TomBorglum/workflows/.github/workflows/docker-hub-publish.yml@refs/tags/v*.*.*`. An AWS
`StringLike` `*` matches dots, so two literal dots admit the immutable `vX.Y.Z` tags
alone; the moving `v1` and `v1.1` tags carry at most one dot and match nothing.

**Pinning `@v1` therefore fails every release** at `Configure AWS credentials`, with
`Not authorized to perform sts:AssumeRoleWithWebIdentity` naming no condition. Denying the
moving tags is the point of the pattern: a caller pinned at one could be handed new
workflow content by whoever moves it. Dependabot's `github-actions` ecosystem bumps the
pin to the next exact version, and every `vX.Y.Z` matches, so a bump needs no AWS change.

## What publish.yml supplies

| Input | Value |
| --- | --- |
| `image-directories` | `["backend", "database", "frontend"]` |
| `compose-directories` | `["stack"]` |
| `aws-region` | `vars.AWS_REGION` |
| `aws-ssm-parameter` | `/expense-tracker/release/dockerhub-pat` |
| `dockerhub-namespace` | `vars.DOCKERHUB_NAMESPACE` |
| `trivyignores` | `.trivyignore.yaml` |
| `aws-role-arn` (secret) | `secrets.AWS_RELEASE_ROLE_ARN` |

What each value must contain is its declaration's `description` in the called workflow,
which reads no `vars` and names no AWS object. `trivyignores` is the one that fails
quietly when dropped; see [The vulnerability gate](#the-vulnerability-gate).

`publish.yml` grants `contents: read` and `id-token: write` as a **ceiling**, which the
called workflow lowers: its `build` and `compose` jobs check out repository code and take
`contents: read` alone, and only `push` holds the credential and checks nothing out.
`CLAUDE.md` carries that split as an invariant.

The concurrency group is declared here rather than in the called workflow, because GitHub
cancels the *caller* when caller and called share a group. `cancel-in-progress` is
conditioned on the event: **a release run is never cancelled**, where a superseded pull
request run is. A run stopped partway through `push` can leave one image published and
another not.

## The automation App

`release-please.yml` and `update-pixi-dependencies.yml` both authenticate as a GitHub App
rather than with `GITHUB_TOKEN`, because a push or pull request made with `GITHUB_TOKEN`
**triggers no workflow**, so neither PR would run `Checks`. The App is installed on this
repository alone.

| Permission | Why |
| --- | --- |
| Contents: read and write | push the release branch and `deps/pixi`, and create the tag |
| Pull requests: read and write | open, update and label both PRs |
| Issues: read and write | the `autorelease:*` state labels, served by the issues API |

Its credentials are the repository secrets `AUTOMATION_APP_CLIENT_ID` and
`AUTOMATION_APP_PRIVATE_KEY`. Nothing checks the installation still holds those three
permissions: a release PR that opens but is never labelled, or a tag that is never
created, is that pair out of agreement.

The App is also the **only bypass actor** on this repository's tag ruleset, which it needs
in order to create the release tag at all.

## The vulnerability gate

Each image is scanned by Trivy before anything is published, and a HIGH or CRITICAL
finding fails the release. [The reference][reference] records how the scan is made
trustworthy; the suppressions belong here.

Suppressions live in **`.trivyignore.yaml`**, and every entry carries an `expired_at`
date. The five today are CVEs in the alpine bases, each fixed in a package version the
pinned digest does not yet resolve to, and none reachable: nothing loads a brotli module,
invokes curl, or parses XML with the expat sitting behind an nginx module never loaded.

**The file is found only because `publish.yml` names it.** The `trivyignores` input
defaults to empty, and an empty value configures no ignore file at all, so dropping that
one line applies no suppression and fails the release on all five findings. That direction
is deliberate - a suppression never applies unseen - but it fails on findings already read
and dated, so the input is as load-bearing as the file.

## The AWS objects

Created once, by hand, in region `eu-north-1`. [The reference][reference] carries the
runbook in general form, including why AWS stands in at all; the concrete values are here.
`<account-id>` is the 12-digit AWS account id, which never appears in this repository, the
ARN carrying it being a repository **secret**.

- **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
  tier**, encrypted with the default `alias/aws/ssm`.
- **IAM role** `gha-expense-tracker-release`, trusting the pair below, and granting
  `ssm:GetParameter` on that one parameter's ARN as a literal plus `kms:Decrypt` on the
  `aws/ssm` key under a `kms:ViaService` condition. **With a shared key the literal
  parameter ARN is the whole isolation boundary.**
- **Secret** `AWS_RELEASE_ROLE_ARN` =
  `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, passed as the
  `aws-role-arn` secret. A fork's pull request gets no secrets, and `push` runs on the
  release event alone.
- `DOCKERHUB_NAMESPACE` = `tomborglum`, passed as `dockerhub-namespace`. Has to be the
  account the PAT belongs to, which nothing checks.
- `AWS_REGION`, passed as `aws-region`.

The SSM path is neither a variable nor a secret: `publish.yml` passes it as the
`aws-ssm-parameter` input.

The role's `Allow` statement names the account's `token.actions.githubusercontent.com`
provider as `Principal.Federated` and `sts:AssumeRoleWithWebIdentity` as its `Action`. Its
`Condition` block, as applied:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  },
  "StringLike": {
    "token.actions.githubusercontent.com:sub":
      "repo:TomBorglum@9831360/expense-tracker@1296807188:ref:refs/tags/v*",
    "token.actions.githubusercontent.com:job_workflow_ref":
      "TomBorglum/workflows/.github/workflows/docker-hub-publish.yml@refs/tags/v*.*.*"
  }
}
```

**`sub` describes this repository and `job_workflow_ref` the called workflow, and the pair
is the entire boundary**, `Principal.Federated` representing every repository on
github.com. Either claim alone is insufficient: `sub` alone would let any workflow in this
repository reach the role, and `job_workflow_ref` alone would let **any repository at
all** reach it, the called workflow being public.

The `sub` form carries the **owner and repository IDs** because immutable subject claims
are enabled, under Settings → Actions → OIDC. IDs survive a rename, where a name-based
`sub` would follow a renamed repository and could then be claimed by a new repository
taking the old name. `job_workflow_ref` carries no IDs under that setting, which was read
out of a claim dump rather than assumed.

**IAM Access Analyzer raises two security warnings** on this policy, both advisory, and
Save stays enabled: the `*` in `sub`, and a wildcard in `job_workflow_ref` not preceded by
six literal characters. The second counts characters and does not model the claim - the
two dots are the control, and loosening to `v1.*` would pass the check while admitting
the force-moved `v1.1`.

Tag creation is restricted in **both** repositories, each by a tag ruleset on
`refs/tags/v*` carrying Restrict creations, Restrict deletions and Block force pushes,
with that repository's own automation App as the only bypass actor. Branch protection does
not close this: a tag in this repository satisfies `sub`, and a tag in `workflows`
carrying an altered workflow satisfies `job_workflow_ref`.

## The published stack

`stack/compose.yaml` is published to the fourth repository as an OCI artifact of type
`application/vnd.docker.compose.project`, by `docker compose publish` in `push` and
**after** the images are copied, `--resolve-image-digests` reading each digest back out of
the registry. It holds **two layers**:

| Layer | What it is |
|---|---|
| `compose.yaml` | The committed file, **byte for byte**, comments and all. |
| `image-digests.yaml` | Overlay restating the five `image:` keys as `<tag>@sha256:...` |

The overlay is merged last, so `IMAGE_PREFIX` and `IMAGE_TAG` **have no effect on a
deployment that loads the artifact**. That is why those two alone carry no `:?`: guarding
them would demand a value the overlay then discards. Interpolation runs per document and
**before** the merge, so a guard there would fire on a host that has no use for the name,
and a bare `${...}` would warn ten times instead. Both carry a `:-` placeholder for that
reason, which is substituted into document 1 and then discarded with it.
The remaining three travel unresolved and guarded, so the deployment supplies them or is
refused. The artifact is published **once per tag**, each resolving against that tag's own
images, and every tag resolves to the same digests. The published digest is signed by
`cosign`, keyless, as the images are. Only the bind mount *declarations* travel: **no
directory contents are published.**

### What the compose job gates

`stack/compose.yaml` declares `name: expense-tracker-stack`, and the `compose` job fails a
release whose `name:` is not `<repository>-<directory>` or whose directory is nested. The
formula is the images' own, so an operator reads the project, its network
(`expense-tracker-stack_default`) and its volume (`expense-tracker-stack_database-data`)
off the artifact's reference, and two repositories cannot collide on one host. The job
reads the **declared** key rather than `config`'s resolved `.name`, which
`COMPOSE_PROJECT_NAME` would override - a deployer and `stack/.env` both set that to run a
second copy beside the first, and neither changes what is published.

It also fails any name carrying neither a `:?` guard nor a `:-` default. The file is
published uninterpolated, so a bare `${VAR}` renders blank on the deploy host and `up`
then reports `invalid reference format` without naming it. **No `.env` beside the compose
file is required**, and `stack/.env` reaches neither end: the workflow exports
`IMAGE_PREFIX` and `IMAGE_TAG` itself, and `image-digests.yaml` wins at deploy.

## Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*/workflows/.*/docker-hub-publish\.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker compose -f oci://docker.io/tomborglum/expense-tracker-stack:2.0.0 config
```

The stack takes the same two verifications against its own repository.
`cosign-installer`'s default is cosign 3, which attaches the signature as an **OCI 1.1
referrer** rather than a `sha256-<digest>.sig` tag, so a tag listing shows the four
published tags and nothing more.

**The signing identity is the called workflow, not this repository.** Fulcio puts
`job_workflow_ref` in the certificate's SAN, so the identity to match is
`TomBorglum/workflows/.github/workflows/docker-hub-publish.yml@refs/tags/vX.Y.Z`. A regexp
written against `expense-tracker` matched the workflow while it lived here and matches
nothing now.

**If the credential exchange is refused**, read the `push` job's claim dump, correct the
trust policy in the console and re-run the failed job: the AWS side lives outside the tag,
so that loop is free.

**If the called workflow itself is wrong**, the fix is a release in `workflows` and a pin
bump here - a `release` event runs `publish.yml` as it exists on the tag, and that file
names an exact version. Every pull request builds, scans and gates all three images, with
`push` held back by `if: github.event_name == 'release'`.

[workflows]: https://github.com/TomBorglum/workflows
[reference]: https://github.com/TomBorglum/workflows/blob/main/docs/docker-hub-publish.md
