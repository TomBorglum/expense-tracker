# Releases

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published, calling `.github/workflows/release.yml` to
do it. Four tags per image, derived once by `docker/metadata-action`: `1.1.0`, `1.1`,
`sha-<full commit>` and `latest`.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker-stack      <- the stack, not an image
```

**No one of those names is written down.** `publish.yml` names the image directories and
`release.yml`'s `meta` job composes `<namespace>/<repository>-<directory>`, the repository
read from `github.event.repository.name`. **So renaming this GitHub repository renames
what a release publishes to.** The fourth repository is composed by the same formula from
the compose directories `publish.yml` names, so `stack/` publishes to
`<namespace>/<repository>-stack`. See [The published stack](#the-published-stack).
`meta` refuses a directory listed twice in either input, which would otherwise race two
matrix legs on one artifact name, or publish one compose artifact twice.

`meta` also derives eight `org.opencontainers.image.*` values, carried as both labels and
manifest annotations. **`title` and `description` are each image's own**, declared in its
`docker-bake.hcl` and merged last, which is why `build` uses `docker buildx bake`. The
bake target is spelled `image` in five places: all three bake files, metadata-action's
`bake-target`, and the build step's `targets` and `set:` keys.

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

## The four jobs

```
publish.yml  ->  meta  ->  build (matrix: backend, database, frontend)  -\
                                                                          >-  push
                 compose  -----------------------------------------------/
                 \_____________________ release.yml _____________________/
```

`publish.yml` holds the triggers, the concurrency group and every value belonging to this
repository: the image directories, `aws-region`, `aws-ssm-parameter`,
`dockerhub-namespace` and the `aws-role-arn` secret. `release.yml` reads no `vars` and
names no AWS object.

**`build` and `compose` check out repository code and get `contents: read` with no
`id-token: write`.** `push` holds the credentials and **checks nothing out**, so
everything executing in it is a SHA-pinned action or a `run` block in the workflow file.
`CLAUDE.md` carries the split as an invariant.

`build` hands `push` an OCI archive and the digest it built, through an artifact.
**`push` re-derives the digest after staging and fails if it moved.** Each artifact also
carries the repository its image publishes to, so no step in `push` names a directory.
Before copying, `push` compares the two sets, catching a build that uploaded nothing or an
artifact that arrived twice.

`compose` loops over the compose directories rather than matrixing them, rendering only
and building nothing. Per directory it stages the whole directory, the `.env` included,
then renders it under `--profile '*'`. **The render proves the file loads, never that the
repository declares its own variables.** `config --variables` lists every name the file
interpolates without resolving any, and each gets a placeholder in a second env file
staged beside the first; `--env-file` turns the auto-loading of `.env` off, so both are
named explicitly and the directory's own file goes second, where the later file wins. A
bind source is the deployment's to name, and **the published artifact is the source file
byte for byte** - one layer, `application/vnd.docker.compose.file+yaml`, every `${...}`
intact, measured against a scratch registry - so no placeholder reaches what is published.
Nothing proves a name is declared at all; a missing one fails only a local `up`. One
artifact carries every directory, plus the manifest of directory names `push` reads. The
job also asserts `docker compose publish` exists on the runner. It carries no `if:` and so
never skips, which is what lets `push` keep a plain `needs` gate when no compose directory
is given.

**Moving or renaming `release.yml` breaks the AWS trust policy**, which pins
`job_workflow_ref` to its path. See [The AWS objects](#the-aws-objects).

## How the credential is reached

Docker Hub supports no OIDC for personal accounts, so AWS stands in: the job mints a
GitHub OIDC token, exchanges it for temporary credentials on a role whose trust policy
accepts only this repository's release workflow at a version tag, and reads a Docker Hub
PAT out of SSM Parameter Store.

- The **role ARN is a secret at both ends**, because the runner echoes a step's `with:`
  block before the action runs. `mask-aws-account-id: true` masks the account id and the
  `authenticated-arn` STS returns, so a wrong ARN logs as `***`.
- **`role-session-name` carries the run id and attempt**, OIDC auth dropping the action's
  own session tags, so it is the only channel by which a run reaches CloudTrail.
- `aws-actions/configure-aws-credentials` runs `output-credentials: true` and
  **`output-env-credentials: false`**, so credentials are step outputs rather than job
  environment variables.
- The PAT is piped **straight** from `aws ssm get-parameter` into `docker login
  --password-stdin`, never occupying a variable, step output or file. `regctl` and
  `cosign` both read what `docker login` wrote.
- **`cosign-installer` runs before `regctl-installer`.** The regctl installer verifies its
  download against regclient's cosign signature `if [ -x "$(command -v cosign)" ]`.
- **`regctl` does the push**, copying the OCI layout's index byte for byte, so one digest
  spans the scan, the push, the attestations and the signature.

**The published images are x86-64.** `pixi.toml`'s `platforms = ["linux-64"]` decides it
for two of the three under `pixi install --locked`; the database image installs no
environment, so the runner's architecture is what holds it. Adding `linux/arm64` starts
with the lock gaining that solve.

Each image carries an SBOM and a SLSA provenance attestation at `mode=max`, which records
the **whole GitHub event payload**, on a pull request including its body. It is published,
and holds here because this repository is public.

## The vulnerability gate

Each image is scanned by Trivy before anything is published, and a HIGH or CRITICAL
finding fails the release. The scan runs over the **unpacked** OCI layout: Trivy rejects
an archive outright, and a layout written by `regctl image import` leads with a referrers
index, which Trivy reads first, resolves nothing from, and then reports zero
vulnerabilities and success.

The gate therefore also asserts identity: **the `ImageID` Trivy reports has to name a
config present in the scanned layout and declaring a platform.** Pointed at a layout it
cannot walk, Trivy resolves the empty config `{}`, reports no findings and exits 0, and
`{}` declares no platform.

Suppressions live in **`.trivyignore.yaml`**, and every entry carries an `expired_at`
date. The five today are CVEs in the alpine bases, each fixed in a package version the
pinned digest does not yet resolve to, and none reachable: nothing loads a brotli module,
invokes curl, or parses XML with the expat sitting behind an nginx module never loaded.

## Residual risk

Trust is pinned to `release.yml` at a version tag, but that file is repository content, so
anyone able to create a matching tag carrying an altered `release.yml` could reach the
role. What bounds it: `main-protection` gates that file, and release-please makes tags.

## The AWS objects

Created once, by hand, in region `eu-north-1`. `<account-id>` is the 12-digit AWS account
id, which never appears in this repository, the ARN carrying it being a repository
**secret**. Everything here sits inside AWS's **always-free** tier: IAM, STS, the OIDC
provider, a standard-tier SSM parameter and the AWS-managed `aws/ssm` key.

1. **Docker Hub.** Both repositories created explicitly, so visibility is set before the
   first push, and both **public**. Then a personal access token with **Read & Write** and
   no Delete; a personal-account token's scope is the account.

2. **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
   tier**, encrypted with the default `alias/aws/ssm`. Standard tier is the free one, and
   it decrypts with the `kms:Decrypt` the policy below grants, where an advanced parameter
   uses `kms:GenerateDataKey`.

3. **IAM role** `gha-expense-tracker-release`, created as a Web identity role against the
   existing `token.actions.githubusercontent.com` provider with audience
   `sts.amazonaws.com` and nothing attached. Replace the trust policy the wizard generates
   wholesale:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "GitHubActionsReleaseTagsOnly",
         "Effect": "Allow",
         "Principal": {
           "Federated":
             "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub":
               "repo:TomBorglum/expense-tracker:ref:refs/tags/v*",
             "token.actions.githubusercontent.com:job_workflow_ref":
               "TomBorglum/expense-tracker/.github/workflows/release.yml@refs/tags/v*"
           }
         }
       }
     ]
   }
   ```

   `Principal.Federated` represents **every repository on github.com**, so the `Condition`
   block is the entire security boundary.

   **The key is `job_workflow_ref`.** AWS maps only the claims its condition-key reference
   lists, so a `StringLike` on a name outside that list leaves the one `Allow` statement
   unmatched and STS answers `Not authorized to perform sts:AssumeRoleWithWebIdentity`,
   naming no condition, with every other part correct. That is what `workflow_ref` as a
   key name looks like. AWS documents `job_workflow_ref` as the *reusable* workflow's
   path; GitHub populates it on every job, and `release.yml` is the called workflow, so it
   is its path rather than the caller's.

   **IAM Access Analyzer warns** that the `*` in `sub` "can allow requests from more
   sources than you intended" and recommends naming a branch. The check fires on a
   wildcard's presence; this one sits after the owner, the repository, the `ref:` claim
   type, `refs/tags/` and the `v`, so all it admits is which version number. Save through
   it.

   Then one inline policy:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "ReadDockerHubPat",
         "Effect": "Allow",
         "Action": "ssm:GetParameter",
         "Resource":
     "arn:aws:ssm:eu-north-1:<account-id>:parameter/expense-tracker/release/dockerhub-pat"
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
   grants `kms:Decrypt` to any caller in the account authorised for SSM, so the literal
   parameter path above, rather than a prefix, is what confines this role to the one
   parameter.

4. **Repository variables and one secret**, named only in `publish.yml`.

   - **Secret** `AWS_RELEASE_ROLE_ARN` =
     `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, passed as the
     `aws-role-arn` secret. A fork's pull request gets no secrets, and `push` runs on the
     release event alone.
   - `DOCKERHUB_NAMESPACE` = `tomborglum`, passed as `dockerhub-namespace`. Has to be the
     account the PAT belongs to, which nothing checks.
   - `AWS_REGION`, passed as `aws-region`.

   The SSM path is neither: `publish.yml` passes it as the `aws-ssm-parameter` input.

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

It also fails a file whose unguarded names are not declared in the directory's own `.env`.
An unguarded `${VAR}` renders blank rather than failing, and `up` then reports
`invalid reference format` without naming it, so the declaration is the only guard left.

## Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*expense-tracker.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker compose -f oci://docker.io/tomborglum/expense-tracker-stack:2.0.0 config
```

The stack takes the same two verifications against its own repository.
`cosign-installer`'s default is cosign 3, which attaches the signature as an **OCI 1.1
referrer** rather than a `sha256-<digest>.sig` tag, so a tag listing shows the four
published tags and nothing more.

**If the exchange is refused**, read the `push` job's claim dump, correct the trust policy
in the console and re-run the failed job: the AWS side lives outside the tag, so that loop
is free. **If the workflow file itself is wrong**, a `release` event runs the file as it
exists on the tag, so the fix is a `fix:` PR and the patch release it cuts. Every pull
request builds, scans and gates all three images, with `push` held back by `if:
github.event_name == 'release'`.

**A release run is never cancelled**, where a superseded pull request run is. The
concurrency group lives in `publish.yml`, because GitHub cancels the *caller* when caller
and called share a group, and `cancel-in-progress` is conditioned on the event: a run
stopped partway through `push` can leave one image published and another not.
