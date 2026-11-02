# Releases

How a release is cut, signed, scanned and published.

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published, calling `.github/workflows/release.yml` to do
it. Four tags per image, derived once by `docker/metadata-action`: `1.1.0`, `1.1`,
`sha-<full commit>` and `latest`.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker            <- the stack, not an image
```

**No one of those names is written down.** `publish.yml` names the directories and
`release.yml`'s `meta` job composes `<namespace>/<repository>-<directory>`, the repository
read from `github.event.repository.name`. **So renaming this GitHub repository renames what
a release publishes to**, which `CLAUDE.md` carries as a pair that nothing checks. The
fourth repository is the same pair **without** a directory suffix, holding `compose.yaml`
as an OCI artifact - see [The published stack](#the-published-stack).

The same job derives eight `org.opencontainers.image.*` values, carried twice over as
labels in the image config and annotations on the manifest, so a registry client reads
`source` and `revision` without pulling the image. Two are not metadata-action's, which
reads from the **repository** and so hands every image the same answer - which had the SPA
image advertising the REST API: **`title` and `description` are the image's own**, declared
in its `docker-bake.hcl`.

Merging those with the shared set is why `build` uses `docker buildx bake`. metadata-action
writes its labels and annotations out as bake files, and bake merges a list of files onto
one target, `labels` merging per key, so **the stack's own file is loaded last** and its two
values win. The target is spelled `image` in five places - all three bake files,
metadata-action's `bake-target`, and the build step's `targets` and `set:` keys - and
nothing reports a mismatch, which is why `CLAUDE.md` carries that pair.

Its whole output is a tag on Docker Hub, so it involves no GitHub Environment and files no
deployment records.

## The automation App

Two workflows open pull requests: `release-please.yml`, and `update-pixi-dependencies.yml`,
which bumps the versions pinned in `pixi.toml` weekly because Dependabot carries no pixi
ecosystem. **Both authenticate as a GitHub App** rather than with the built-in
`GITHUB_TOKEN`, for the same reason each: a push or pull request made with `GITHUB_TOKEN`
**triggers no workflow**, by design, so the release PR would open with no `Checks` run and
the dependency PR would never learn whether the new pins build. An App installation token
is a first-class actor, so its PRs run the full gate.

The App is installed on this repository alone, with every permission the two workflows need
between them:

| Permission | Why |
| --- | --- |
| Contents: read and write | push the release branch and `deps/pixi`, and create the tag |
| Pull requests: read and write | open, update and label both PRs |
| Issues: read and write | the `autorelease:*` labels release-please tracks state with, which live on the issues API |

Its credentials reach both workflows as the repository secrets
`AUTOMATION_APP_CLIENT_ID` and `AUTOMATION_APP_PRIVATE_KEY`. Nothing checks that the
installation still holds those three: a release PR that opens but is never labelled, or a
tag that is never created, is that pair out of agreement.

## Why it is four jobs

```
publish.yml  ->  meta  ->  build (matrix: backend, database, frontend)  -\
                                                                          >-  push
                 compose  -----------------------------------------------/
                 \_____________________ release.yml _____________________/
```

`publish.yml` is the caller and holds the triggers, the concurrency group and every value
belonging to this repository: the **directories** to build, plus `aws-region`,
`aws-ssm-parameter`, `dockerhub-namespace` and the `aws-role-arn` secret. `release.yml` is
called, reads no `vars` and names no AWS object. The filenames look inverted on purpose -
the trust policy below pins `job_workflow_ref`, which names the **called** workflow, so
`release.yml` keeping its path is what leaves that policy alone.

**The split exists for one reason.** `build` runs repository code: a Dockerfile,
`pixi install`, `pnpm install`. A malicious dependency in any of those is one layer away
from push access to published images, so `build` is granted `contents: read` and **no
`id-token: write`**, putting the token AWS accepts out of its reach. `compose` checks out
too and gets the same pair. `push` is the mirror image of both: it holds the credentials
and **checks nothing out**, so everything that executes in it is either a SHA-pinned
action or a `run` block written in the workflow file itself. `CLAUDE.md` carries the split
as an invariant.

`build` hands `push` an OCI archive through an artifact, along with the digest it built.
Untrusted bytes are safe to hand over precisely because `push` never executes them - it
copies them to a registry. **`push` re-derives the digest after staging and fails if it
moved**, so "what was scanned" and "what was published" are provably the same bytes.

Each artifact also carries **the repository its image publishes to**, which is why no step
in `push` names a directory: it iterates the artifacts it was handed, both consumers
reading that name out of `meta`'s `images` step. Before copying, `push` compares the two
sets, catching a build that uploaded nothing or an artifact that arrived twice - either
would otherwise publish a partial release quietly.

`compose` is the fourth job because of that same split, not because the work is heavy: it
checks out `compose.yaml`, loads it with every variable unset, and uploads it. **That load
is the only gate on the file anywhere** - `ci.yml` never reads it - so a `${...}` left
without a default is caught by the pull request rather than by a release. The job also
asserts `docker compose publish` exists on the runner, `push` being the one job no pull
request can exercise.

## How the credential is reached

Docker Hub supports no OIDC for personal accounts, so AWS stands in as the intermediary:
the job mints a GitHub OIDC token, exchanges it for temporary credentials on an AWS role
whose trust policy only accepts this repository's release workflow at a version tag, and
reads a Docker Hub PAT out of SSM Parameter Store. `oidc-smoke-test.yml` proved that path
and remains the cheapest way to diagnose a claim mismatch.

Four details carry the weight:

- The **role ARN is a secret at both ends** - stored as one, and passed to `release.yml` as
  one - so GitHub masks it everywhere. A plain input would not do, for a reason that has
  nothing to do with the exchange failing: **the runner echoes a step's `with:` block into
  the log before the action runs**, so the credential step would print the full ARN on every
  release. `mask-aws-account-id: true` cannot reach that line, and is not redundant either -
  it masks the account id and `authenticated-arn` that STS *returns*, which the input never
  carried. The cost is that a wrong ARN logs as `***`, which the configuration check at the
  top of `push` is what makes diagnosable instead.
- `aws-actions/configure-aws-credentials` runs with `output-credentials: true` and
  **`output-env-credentials: false`**, so the temporary credentials become step outputs
  rather than job environment variables. Steps that need them name them; the rest never
  see them.
- The PAT is piped **straight** from `aws ssm get-parameter` into
  `docker login --password-stdin`, so it never occupies a shell variable, a step output or
  a file. Every step after it needs no secret: `regctl` and `cosign` both read what
  `docker login` wrote.
- `cosign-installer` runs **before** `regctl-installer`, which is load-bearing rather than
  tidy. The regctl installer verifies the binary it downloads against regclient's cosign
  signature `if [ -x "$(command -v cosign)" ]`, so cosign being on `PATH` already is what
  gets that verification run.

**`regctl` does the push itself.** It copies the local OCI layout's index byte for byte,
which keeps one digest across the scan, the push, the attestations and the signature.

**The published images are x86-64, and for two of the three the platform comes from the
lock.** `pixi.toml`'s `platforms = ["linux-64"]` is the declaration, so `pixi install
--locked` is where their architecture is decided and the bake file names no platform.
**The database image is the exception** - it installs no environment at all, and
`postgres:18-alpine` publishes eight platforms, so what holds it to x86-64 is the runner's
architecture and nothing in this repository. Adding `linux/arm64` starts with the lock
gaining that solve, and with this image needing to name a platform it can leave implicit
today.

Each image carries an SBOM and a SLSA provenance attestation at `mode=max`, which has one
consequence worth knowing because it is published rather than merely logged: `mode=max`
records the **whole GitHub event payload**, which on a pull request includes the pull
request body. It holds here because this repository is public.

## The vulnerability gate

Each image is scanned by Trivy before anything is published, and a HIGH or CRITICAL
finding fails the release. The scan runs over the **unpacked** OCI layout, which is the
form Trivy walks: it rejects an OCI archive outright, and a layout written by
`regctl image import` leads with a referrers index, which Trivy reads first, resolves
nothing from, and then reports zero vulnerabilities and success.

So the gate makes **two** assertions, the first about identity: the `ImageID` Trivy reports
has to name a config present in the layout just scanned **and** declaring a platform, which
is what tells a clean scan from a scan that examined nothing. The direction matters -
pointed at a layout it cannot walk, Trivy resolves the empty config `{}`, reports no
findings and exits 0, and that blob **is** in the layout as the attestation manifest's own
config. So the check reads Trivy's claim against the layout, where `{}` declares no
platform, rather than deriving what Trivy should have reported, which can land on that same
empty value from both sides and agree with itself.

Suppressions live in **`.trivyignore.yaml`**, and every entry carries an `expired_at`
date, so a suppression cannot outlive its reason by being forgotten. The two entries today
are CVEs in the frontend's nginx base fixed in an alpine the pinned digest does not yet
resolve to, neither reachable in an image that loads no brotli module and never invokes
curl.

## Residual risk

Trust is pinned to `release.yml` at a version tag, but that file is still repository
content, so anyone able to create a matching tag carrying an altered `release.yml` could
reach the role. What bounds it is the `main-protection` ruleset - changes to that file land
only through a reviewed PR - and tags being created by release-please from `main`.

## The AWS objects

Created once, by hand, in region `eu-north-1`. `<account-id>` below is the 12-digit AWS
account id, which never appears in this repository - the ARN carrying it is a repository
**secret**, for the reason above.

Everything here sits inside AWS's **always-free** tier, a standing constraint on what gets
created: IAM, STS, the OIDC provider, a standard-tier SSM parameter and the AWS-managed
`aws/ssm` key carry no monthly charge.

1. **Docker Hub.** Both repositories created explicitly, so their visibility is set before
   the first push, and both **public**. Then a personal access token with **Read & Write**
   and no Delete; a personal-account token's scope is the account.

2. **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
   tier**, encrypted with the default `alias/aws/ssm`. Standard tier is load-bearing twice:
   it is the free one, and it encrypts with the `kms:Decrypt` the policy below grants,
   where an advanced parameter uses `kms:GenerateDataKey`.

3. **IAM role** `gha-expense-tracker-release`, created as a Web identity role against the
   existing `token.actions.githubusercontent.com` provider with audience
   `sts.amazonaws.com` and nothing attached. The trust policy the wizard generates is
   roughly `repo:TomBorglum/expense-tracker:*` - any ref, any workflow - and is replaced
   wholesale:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "GitHubActionsReleaseTagsOnly",
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:TomBorglum/expense-tracker:ref:refs/tags/v*",
             "token.actions.githubusercontent.com:job_workflow_ref": "TomBorglum/expense-tracker/.github/workflows/release.yml@refs/tags/v*"
           }
         }
       }
     ]
   }
   ```

   `Principal.Federated` represents **GitHub Actions as a whole** - every repository on
   github.com - so the `Condition` block is the entire security boundary. `sub` holds the
   ref to a version tag in this repository; `job_workflow_ref` holds the workflow to this
   file.

   **The key is `job_workflow_ref`.** AWS maps only the claims its condition-key reference
   lists, so a `StringLike` on a name outside that list leaves the one `Allow` statement
   unmatched and STS answers `Not authorized to perform sts:AssumeRoleWithWebIdentity`,
   naming no condition, with every other part of the exchange correct - which is what
   `workflow_ref` as a key name looks like. AWS describes `job_workflow_ref` as the
   *reusable* workflow's path; GitHub populates it on every job. **`release.yml` is a called
   workflow**, so it is its path rather than the caller's, which is why the split needed no
   change here. **Moving or renaming `release.yml` is what would move this condition.**

   **IAM Access Analyzer warns** that the `*` in `sub` "can allow requests from more sources
   than you intended" and recommends naming a branch. The check fires on a wildcard's
   presence; this one sits after the owner, the repository, the `ref:` claim type,
   `refs/tags/` and the `v`, so all it admits is which version number. Save through it.

   Then one inline policy, so the role reads that parameter and lists nothing under
   `/expense-tracker/`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadDockerHubPat",
         "Effect": "Allow",
         "Action": "ssm:GetParameter",
         "Resource": "arn:aws:ssm:eu-north-1:<account-id>:parameter/expense-tracker/release/dockerhub-pat"
       },
       {
         "Sid": "DecryptViaSsmOnly",
         "Effect": "Allow",
         "Action": "kms:Decrypt",
         "Resource": "arn:aws:kms:eu-north-1:<account-id>:key/<aws/ssm key id>",
         "Condition": {
           "StringEquals": { "kms:ViaService": "ssm.eu-north-1.amazonaws.com" }
         }
       }
     ]
   }
   ```

   **With a shared key the isolation boundary is that parameter ARN alone.** `aws/ssm`
   carries a fixed policy granting `kms:Decrypt` to any caller in the account authorised
   for SSM, so the exact parameter path above - a literal rather than a prefix - is what
   holds this role to its own parameter and away from the smoke test's under the same key.

4. **GitHub repository variables and one secret.** `release.yml` reads none of these: it
   declares an input or a secret for each, and **`publish.yml` is the only file that names
   them**.

   - **Secret** `AWS_RELEASE_ROLE_ARN`, set to
     `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, passed as the
     `aws-role-arn` secret. A fork's pull request gets no secrets, so it arrives empty
     there and nothing reads it - `push` runs on the release event alone. Note the name is
     one word away from the smoke test's own `AWS_ROLE_ARN`, a **variable** naming the
     **CI** role instead.
   - `DOCKERHUB_NAMESPACE`, set to `tomborglum`, passed as `dockerhub-namespace`. Has to be
     the account the PAT above belongs to, which nothing checks.
   - `AWS_REGION`, passed as `aws-region`, with two consumers: `publish.yml` fills the input
     from it, and `oidc-smoke-test.yml` - dispatched rather than called, so it has no caller
     to take inputs from - still reads it directly.

   The SSM path is neither: `publish.yml` passes it as the `aws-ssm-parameter` input, a
   literal beside the directory list, because a path is an address and this file publishes
   it verbatim above.

## The published stack

`compose.yaml` is published to the fourth repository as an OCI artifact of type
`application/vnd.docker.compose.project`, by `docker compose publish` in the `push` job and
**after** the images are copied - `--resolve-image-digests` reads each digest back out of
the registry, so they have to be there first.

It holds **two layers**, measured against a throwaway registry rather than taken from the
documentation:

| Layer | What it is |
|---|---|
| `compose.yaml` | The committed file, **byte for byte**, comments and all. |
| `image-digests.yaml` | A generated overlay restating all five `image:` keys as `<tag>@sha256:...`. |

The overlay is merged last, so `EXPENSE_TRACKER_IMAGE_PREFIX` and `EXPENSE_TRACKER_VERSION`
**have no effect on a deployment that loads the artifact**. They exist for a checkout, and
for telling the publish step which images to resolve - which is why the artifact is
published **once per tag**, each resolving against that tag's own images. Every tag resolves
to the same digests; only the text beside them differs. The published digest is then signed
by `cosign`, keyless, on the terms the images are. Only the bind mount *declarations*
travel: **no directory contents are published.**

## Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*expense-tracker.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

The stack takes the same two against the suffixless repository, and `docker compose config`
is the third - it renders what a deployment would actually run:

```sh
docker compose -f oci://docker.io/tomborglum/expense-tracker:2.0.0 config
```

`cosign verify` is the only view of the signature from outside. `cosign-installer`'s
default is cosign 3, which attaches the signature as an **OCI 1.1 referrer** instead of
writing a `sha256-<digest>.sig` tag, so a tag listing shows the four published tags and
nothing more. That version is the installer's, not this repository's.

The `push` job's log is the other half: the claim dump shows the `sub` and
`job_workflow_ref` the trust policy was written against, and is the only place the
tag-shaped claims can be observed, the smoke test running from a branch.

**If the exchange is refused**, read the claim dump, correct the trust policy in the
console and re-run the failed job: the AWS side lives outside the tag, so that loop is
free. **If the workflow file itself is wrong**, a `release` event runs the file as it
exists on the tag, so the fix is a `fix:` PR and the patch release it cuts. The
`pull_request` trigger is what exercises the file ahead of that: every pull request builds,
scans and gates all three images, with `push` held back by
`if: github.event_name == 'release'`.

**A release run is never cancelled**, where a superseded pull request run is. The
concurrency group lives in `publish.yml` rather than `release.yml`, because GitHub cancels
the *caller* when caller and called share a group, and `cancel-in-progress` is conditioned
on the event: a run stopped partway through `push` can leave one image published and
another not, where a pull request has nothing to leave half-done.
