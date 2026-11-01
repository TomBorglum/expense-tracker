# Releases

How a release is cut, signed, scanned and published.

## Releases

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published, calling `.github/workflows/release.yml` to do
it. Four tags per image, derived once by `docker/metadata-action` so they cannot disagree:
`1.1.0`, `1.1`, `sha-<full commit>` and `latest`.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker            <- the stack, not an image
```

**No one of those names is written down.** `publish.yml` names the directories, `backend`,
`database` and `frontend`, and `release.yml`'s `meta` job composes
`<namespace>/<repository>-<directory>` from them - the namespace the `dockerhub-namespace`
input, which `publish.yml` fills from the `DOCKERHUB_NAMESPACE` repository variable, the
repository read from `github.event.repository.name`. **So renaming this GitHub repository renames
what a release publishes to**, which `CLAUDE.md` carries as a pair that nothing checks.
The composition is logged on every pull request run.

The fourth repository is the same pair **without** a directory suffix, and it holds
`compose.yaml` as an OCI artifact rather than an image, under the same four tags derived
from the same patterns. [Deployment](../README.md#deployment) is what loads it; what it holds is
[The published stack](#the-published-stack) below.

The same job derives the OCI metadata: eight `org.opencontainers.image.*` values, carried
twice over, as labels in the image config and as annotations on its manifest, so a
registry client can read `source` and `revision` without pulling the image. Two of the
eight do not come from there, because metadata-action reads them from the **repository**
and so hands every image the same answer - which had the SPA image advertising the REST
API and titled both of them `expense-tracker`:

- **`title` and `description` are the image's own**, declared in its `docker-bake.hcl`
  beside the context and the Dockerfile and nowhere in the workflow. The image is what
  knows what it is; the pipeline knows how to combine the pieces.

Merging those two with the shared set is what the `build` job uses `docker buildx bake`
for rather than a plain build. metadata-action writes its labels and annotations out as
bake files of their own, and bake merges a list of files onto one target: `labels` is a map
and merges per key, so a key the stack names wins and every shared one survives, and
`annotations` is a list and is appended, a repeated key resolving last-wins in the built
image. **The stack's own file is therefore loaded last**, which is what puts its `title`
and `description` on the published image.

The target is spelled `image` in five places: all three bake files, metadata-action's
`bake-target`, and the build step's `targets` and `set:` keys. Those five agreeing is what
lands the overrides on the target the stack declares, and nothing reports a mismatch, which
is why `CLAUDE.md` carries that pair.

Both values are set as a label *and* as an annotation, so each lands in its own place - the
image config and the manifest - and the pair reads the same from either. Both come from the
build command: a Dockerfile `LABEL` writes the config alone, and a `--label` on the command
takes precedence over it.

It is a release workflow rather than a deployment workflow. Its whole output is a tag on
Docker Hub, and when such a tag becomes live somewhere is a separate concern, so the
workflow involves no GitHub Environment and files no deployment records.

## The automation App

Two workflows open pull requests: `release-please.yml`, which maintains the release PR and
tags `main` on merge, and `update-pixi-dependencies.yml`, which bumps the versions pinned
in `pixi.toml` weekly because Dependabot carries no pixi ecosystem. **Both authenticate as
a GitHub App** rather than with the built-in `GITHUB_TOKEN`, and the reason is the same
for each: a push or a pull request made with `GITHUB_TOKEN` **triggers no workflow**, by
design, so the release PR would open with no `Checks` run against it and the dependency PR
would never learn whether the new pins build. An App installation token is a first-class
actor, so the PRs it opens run the full gate.

The App is installed on this repository alone and granted three permissions, which is
every one the two workflows between them need:

| Permission | Why |
| --- | --- |
| Contents: read and write | push the release branch and `deps/pixi`, and create the tag |
| Pull requests: read and write | open, update and label both PRs |
| Issues: read and write | the `autorelease:*` labels release-please tracks state with, which live on the issues API |

Its credentials reach both workflows as the repository secrets
`AUTOMATION_APP_CLIENT_ID` and `AUTOMATION_APP_PRIVATE_KEY`. Nothing checks that the
installation still holds those three permissions: a release PR that opens but is never
labelled, or a tag that is never created, is that pair out of agreement.

## Why it is four jobs

```
publish.yml  ->  meta  ->  build (matrix: backend, database, frontend)  -\
                                                                          >-  push
                 compose  -----------------------------------------------/
                 \_____________________ release.yml _____________________/
```

`publish.yml` is the caller and holds the triggers, the concurrency group and every value
belonging to this repository: the **directories** to build, plus the four under
[The AWS objects](#the-aws-objects) - `aws-region`, `aws-ssm-parameter`,
`dockerhub-namespace` and the `aws-role-arn` secret. `release.yml` is called, reads no
`vars` and names no AWS object, and holds everything about how an image is built, scanned
and pushed. The filenames look inverted on purpose - the AWS trust policy below pins
`job_workflow_ref`, which names the **called** workflow, so `release.yml` keeping its
path is what leaves that policy alone.

**The split exists for one reason, and it is the only interesting thing about the file.**
`build` runs repository code: a Dockerfile, `pixi install`, `pnpm install`. A malicious
dependency in any of those is one layer away from push access to published images, so
`build` is granted `contents: read` and **no `id-token: write`**, and the token AWS
accepts is out of its reach. `compose` checks out too, for the one file it uploads, and is
granted exactly the same pair. `push` is the mirror image of both: it holds the
credentials and **checks nothing out**, so everything that executes in it is either a
SHA-pinned action or a `run` block written in the workflow file itself. `CLAUDE.md`
carries the split as an invariant.

`build` hands `push` an OCI archive through an artifact, along with the digest it built.
Untrusted bytes are safe to hand over precisely because `push` never executes them - it
copies them to a registry. `push` re-derives the digest after staging and fails if it
moved, so "what was scanned" and "what was published" are provably the same bytes rather
than two numbers compared by eye.

Each artifact also carries **the repository its image publishes to**, which is why no step
in `push` names a directory or a repository: it iterates the artifacts it was handed. That
name is composed in one place - `meta`'s `images` step - and both consumers read it back
out of there, so the tags and the artifacts cannot spell a repository differently. Before
anything is copied, `push` still compares the two sets, which is what catches a count that
does not match: a build that uploaded nothing, or an artifact that arrived twice, would
otherwise publish a partial release quietly.

`compose` is the fourth job because of that same split, not because the work is heavy: it
checks out `compose.yaml`, loads it with every variable unset, and uploads it. **That load
is the only gate on the file anywhere** - `ci.yml` never reads it - so a `${...}` left
without a default is caught by the pull request rather than by a release. The job also
asserts `docker compose publish` exists on the runner, since the command was experimental
when it was added and `push` is the one job no pull request can exercise.

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
  carried. The cost of masking is that a wrong ARN logs as `***`, which the configuration
  check at the top of `push` is what makes diagnosable instead.
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
which is what keeps one digest across the scan, the push, the attestations and the
signature, and carries the multi-platform index and its attestations as they are.

**The published images are x86-64, and for two of the three the platform comes from the
lock.** `pixi.toml`'s `platforms = ["linux-64"]` is the declaration: the API and SPA images
install from `pixi.lock`, which carries that solve and no other, so `pixi install --locked`
is where their architecture is decided, and the bake file and the workflow name no
platform. **The database image is the exception** - it installs no environment at all, and
`postgres:18-alpine` publishes eight platforms, so what holds that one to x86-64 is the
architecture of the runner it is built on and nothing in this repository. Adding
`linux/arm64` starts with the lock gaining that solve, and with this image needing to name
a platform it can leave implicit today.

Each image carries an SBOM and a SLSA provenance attestation, the provenance at
`mode=max`. That is a deliberate choice with one consequence worth knowing, because it is
published rather than merely logged: `mode=max` records the **whole GitHub event payload**
under `buildDefinition.internalParameters.github_event_payload`, which on a pull request
is around 6 kB of a 52 kB predicate and includes the pull request body. It holds here
because this repository is public, so the payload carries nothing that is not already
public, and `mode=max` is what keeps the build detail in the provenance.

## The vulnerability gate

Each image is scanned by Trivy before anything is published, and a HIGH or CRITICAL
finding fails the release. The scan runs over the **unpacked** OCI layout, which is the
form Trivy walks: it rejects an OCI archive outright, and a layout written by
`regctl image import` leads with a referrers index, which Trivy reads first, resolves
nothing from, and then reports zero vulnerabilities and success.

So the gate makes **two** assertions, and the first is about identity: the `ImageID` Trivy
reports - the digest of the image config it read - has to name a config that is present in
the layout just scanned **and** declares a platform. That is what tells a clean scan from
a scan that examined nothing.

The direction matters. Pointed at a layout it cannot walk, Trivy resolves the empty config
`{}` - `sha256:44136fa3...` - reports no findings and exits 0, and that blob **is** in the
layout, beside the image, as the attestation manifest's own config. So the check reads
Trivy's claim against the layout, where `{}` declares no platform, rather than walking the
layout to derive what Trivy should have reported, which can land on that same empty value
from both sides and agree with itself. It is a check on the platform rather than on
Trivy having resolved an operating system, so a legitimately clean image passes whatever
package database either base carries. It extends the chain the push job ends: bake's
digest, the archive, the scanned config, the imported digest, the signature.

Suppressions live in **`.trivyignore.yaml`**, and every entry carries an `expired_at`
date. On that date Trivy stops honouring the entry and the finding fails the release
again, so a suppression cannot outlive its reason by being forgotten. The entries there
today are two CVEs in the frontend's nginx base that are fixed in alpine 3.24.3 while the
image is still built on 3.24.2 - the pinned digest is already the newest that tag
resolves to, so only an upstream rebuild clears them, and neither is reachable in an image
that loads no brotli module and never invokes curl.

## Residual risk

Trust is pinned to `release.yml` at a version tag, but that file is still repository
content, so anyone able to create a matching tag carrying an altered `release.yml` could
reach the role. What bounds it is the `main-protection` ruleset - changes to that file land
only through a reviewed PR - and tags being created by release-please from `main`.

## The AWS objects

Created once, by hand, in region `eu-north-1`. `<account-id>` below is the 12-digit AWS
account id, which is why the role ARN is a repository **variable** and never a literal in
the workflow: it keeps the account id out of a world-readable file and out of the diff,
while `mask-aws-account-id` is what keeps it out of the log.

Everything here sits inside AWS's **always-free** tier, which is a standing constraint on
what gets created. IAM, STS, the OIDC provider, a standard-tier SSM parameter and the
AWS-managed `aws/ssm` key carry no monthly charge, and one `kms:Decrypt` per release sits
far inside the free 20,000 requests a month. The shared `aws/ssm` key is also what makes
the parameter ARN below the whole isolation boundary; this account holds two principals -
an administrator with access to every parameter under any key, and a release role scoped to
one parameter - so that scoping is where the separation lives.

1. **Docker Hub.** Both repositories created explicitly, so their visibility is set before
   the first push, and both **public**, which Docker Personal allows without limit. Then
   a personal access token with **Read & Write** and no Delete; a personal-account token's
   scope is the account.

2. **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
   tier**, encrypted with the default `alias/aws/ssm`. Standard tier is load-bearing
   twice: it is the free one, and it encrypts with the `kms:Decrypt` the policy below
   grants, where an advanced parameter uses `kms:GenerateDataKey`.

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

   `Principal.Federated` is the OIDC provider, which represents **GitHub Actions as a
   whole** - every repository on github.com - so the `Condition` block is the entire
   security boundary. The two `StringLike` conditions each pin one half: `sub` holds the
   ref to a version tag in this repository, and `job_workflow_ref` holds the workflow to
   this file.

   **The key is `job_workflow_ref`.** AWS maps the claims its condition-key reference
   lists: `actor`, `actor_id`, `job_workflow_ref`, `repository`, `repository_id`,
   `repository_owner_id`, `workflow`, `ref`, `environment` and `enterprise_id`, beside
   `sub` and `aud`, so those are the keys a condition here can read. A `StringLike` on a
   name outside that list leaves the one `Allow` statement unmatched, and STS answers
   `Not authorized to perform sts:AssumeRoleWithWebIdentity`, naming no condition, with
   every other part of the exchange correct - which is what `workflow_ref` as a key name
   looks like. AWS describes `job_workflow_ref` as the *reusable* workflow's path; GitHub
   populates it on every job, equal to the `workflow_ref` claim wherever no reusable
   workflow is involved, and the claim dump carries both. **`release.yml` is now a called
   workflow**, invoked by `publish.yml`, so `job_workflow_ref` is its path rather than the
   caller's - which is exactly the value pinned here, and why the split needed no change
   to this policy. The `sub` claim is the caller's and is also unchanged. Moving or
   renaming `release.yml` is what would move this condition.

   **IAM Access Analyzer warns** that the `*` in `sub` "can allow requests from more
   sources than you intended" and recommends naming a branch. The check fires on a
   wildcard's presence; this one sits after the owner, the repository, the `ref:` claim
   type, `refs/tags/` and the `v`, so all it admits is which version number, and a release
   has a tag where the advice reads a branch. `StringLike` offers `*` and `?`, and `?`
   matches any character, so `v*.*.*` is the narrowest shape it can express. Save through
   it.

   Then one inline policy: `ssm:GetParameter` on the one ARN and `kms:Decrypt` via SSM, so
   the role reads that parameter and lists nothing under `/expense-tracker/`:

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
   carries a fixed policy granting `kms:Decrypt` to `"Principal": {"AWS": "*"}` for any
   caller in the account authorised for SSM, so the exact parameter path above - a literal
   rather than a prefix - is what holds this role to its own parameter and away from the
   smoke test's under the same key.

4. **GitHub repository variables and one secret.** `release.yml` reads none of these: it
   declares an input or a secret for each, and **`publish.yml` is the only file that names
   them**, so they feed the workflow rather than being read by it.

   - **Secret** `AWS_RELEASE_ROLE_ARN`, set to
     `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, passed as the
     `aws-role-arn` secret. A secret and not a variable because it is the only one of these
     carrying the account id, and these logs are world-readable: the runner echoes a step's
     `with:` block before the action runs, so a plain input would print the ARN on every
     release, where `mask-aws-account-id` cannot reach it. A fork's pull request gets no
     secrets, so it arrives empty there and nothing reads it - `push` runs on the release
     event alone. Note the name is one word away from the smoke test's own `AWS_ROLE_ARN`,
     a **variable** naming the **CI** role instead.
   - `DOCKERHUB_NAMESPACE`, set to `tomborglum`, passed as `dockerhub-namespace`. Has to be
     the account the PAT above belongs to, which nothing checks.
   - `AWS_REGION`, already present for the smoke test, passed as `aws-region`. It has two
     consumers: `publish.yml` fills the input from it, and `oidc-smoke-test.yml` - which is
     dispatched rather than called, so it has no caller to take inputs from - still reads
     it directly.

   The SSM path is neither. `publish.yml` passes it as the `aws-ssm-parameter` input, a
   literal beside the directory list, because a path is an address and this file publishes
   it verbatim above.

## The published stack

`compose.yaml` is published to the fourth repository as an OCI artifact of type
`application/vnd.docker.compose.project`, by `docker compose publish` in the `push` job
and **after** the images are copied - `--resolve-image-digests` reads each digest back out
of the registry, so they have to be there first.

It holds **two layers**, which was measured against a throwaway registry rather than taken
from the documentation:

| Layer | What it is |
|---|---|
| `compose.yaml` | The committed file, **byte for byte**, comments and all. |
| `image-digests.yaml` | A generated overlay restating all five `image:` keys as `<tag>@sha256:...`. |

The overlay is merged last, so `EXPENSE_TRACKER_IMAGE_PREFIX` and
`EXPENSE_TRACKER_VERSION` **have no effect on a deployment that loads the artifact**. They
exist for a checkout, and for telling the publish step which images to resolve - which is
why the artifact is published **once per tag**, each resolving against that tag's own
images, so the artifact tagged `2.1.0` names images spelled `2.1.0@sha256:...`. Every tag
resolves to the same digests; only the text beside them differs.

The published digest is then signed by `cosign`, keyless, on exactly the terms the images
are. cosign signs a digest, so the artifact's media type is nothing it has to know about.

Only the bind mount *declarations* travel - the two `source:` paths as the file spells
them, defaults included. **No directory contents are published**, and nothing in the
artifact is specific to a machine.

## Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*expense-tracker.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

The stack takes the same two commands against the suffixless repository, and
`docker compose config` is the third - it renders what a deployment would actually run:

```sh
docker compose -f oci://docker.io/tomborglum/expense-tracker:2.0.0 config
```

`cosign verify` is the only view of the signature from outside. `cosign-installer`'s
default is cosign 3 - v3.0.6 at `v2.0.0` - which attaches the signature as an **OCI 1.1
referrer** instead of writing a `sha256-<digest>.sig` tag, so a tag listing shows the four
published tags and nothing more. The sign step's log is terse for the same reason: the v3
bundle carries the Rekor entry, so no tlog index is printed. That version is the
installer's, not this repository's - the step pins the action by SHA and takes whatever
cosign it ships, unlike `regctl-installer` beside it.

The `push` job's log is the other half: the claim dump shows the `sub` and
`job_workflow_ref` the trust policy was written against, and it is the only place the
tag-shaped claims can be observed, the smoke test running on `workflow_dispatch` from a
branch and so seeing branch-shaped ones.

**If the exchange is refused**, read the claim dump, correct the trust policy in the
console and re-run the failed job: the AWS side lives outside the tag, so that loop is
free. **If the workflow file itself is wrong**, a `release` event runs the file as it
exists on the tag, so the fix is a `fix:` PR and the patch release it cuts. The
`pull_request` trigger is what exercises the file ahead of that: every pull request builds,
scans and gates all three images, with the `push` job held back by
`if: github.event_name == 'release'`, so the change that touches the file runs it. The
trigger covers every path, keeping what it watches in one place with what the Dockerfiles
read.

**A release run is never cancelled**, where a superseded pull request run is. The
concurrency group lives in `publish.yml` rather than `release.yml`, because GitHub cancels
the *caller* when caller and called share a group, and `cancel-in-progress` is therefore
conditioned on the event: a run stopped partway through `push` can leave one image
published and another not, which is worse than a slow queue, while a pull request has
nothing to leave half-done - it never reaches `push`.
