# Releases

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published. It holds the triggers, the concurrency group
and every value belonging to this repository; the work is done by the reusable
`docker-hub-publish.yml` in [TomBorglum/workflows][workflows], pinned at an exact version.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker-stack      <- the stack, not an image
```

**No one of those names is written down.** Each is `<namespace>/<repository>-<directory>`,
composed at release time from the directories `publish.yml` names. **So renaming this
GitHub repository renames what a release publishes to.** The fourth is the stack rather
than an image; see [The published stack](#the-published-stack).

[`docs/docker-hub-publish.md`][reference] documents the called workflow: what a caller
must provide, the credential path, the vulnerability gate and the trust policy in general
form.

## The version pin

`publish.yml` pins the called workflow at an exact `vX.Y.Z` tag. The release role's trust
policy conditions `job_workflow_ref` on
`TomBorglum/workflows/.github/workflows/docker-hub-publish.yml@refs/tags/v*.*.*`, and an
AWS `StringLike` `*` matches dots, so two literal dots admit the immutable `vX.Y.Z` tags
alone. The moving `v1` and `v1.1` tags carry at most one dot and match nothing.

**Pinning `@v1` fails every release** at `Configure AWS credentials`, with `Not authorized
to perform sts:AssumeRoleWithWebIdentity` naming no condition. The exclusion is the
security property: a caller pinned at a moving tag can be handed new workflow content by
whoever moves it. Dependabot bumps the pin to the next exact version, which matches
already, so a bump needs no AWS change.

## Concurrency

The group is declared in `publish.yml` because GitHub cancels the *caller* when caller and
called share a group. `cancel-in-progress` is conditioned on the event: **a release run is
never cancelled**, where a superseded pull request run is. A run stopped partway through
publishing can leave one image published and another not.

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
trustworthy.

Suppressions live in **`.trivyignore.yaml`**, which records what each one covers and why
it is unreachable.

**The file is found only because `publish.yml` names it.** The `trivyignores` input
defaults to empty, and an empty value configures no ignore file at all, so dropping that
one line applies no suppression and fails the release on all five findings.

## The AWS objects

Created once, by hand, in region `eu-north-1`. [The reference][reference] carries the
runbook in general form. `<account-id>` is the 12-digit AWS account id, which never
appears in this repository, the ARN carrying it being a repository **secret**.

- **SSM parameter** `/expense-tracker/release/dockerhub-pat`, SecureString, **standard
  tier**, encrypted with the default `alias/aws/ssm`.
- **IAM role** `gha-expense-tracker-release`, trusting the pair below, and granting
  `ssm:GetParameter` on that one parameter's ARN as a literal plus `kms:Decrypt` on the
  `aws/ssm` key under a `kms:ViaService` condition. **With a shared key the literal
  parameter ARN is the whole isolation boundary.**
- **Secret** `AWS_RELEASE_ROLE_ARN` =
  `arn:aws:iam::<account-id>:role/gha-expense-tracker-release`, passed as the
  `aws-role-arn` secret. A fork's pull request gets no secrets, and a release is the only
  event that publishes.
- `DOCKERHUB_NAMESPACE` = `tomborglum`, passed as `dockerhub-namespace`. Has to be the
  account the PAT belongs to, which nothing checks.
- `AWS_REGION`, passed as `aws-region`.

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
taking the old name. `job_workflow_ref` carries no IDs under that setting.

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
`application/vnd.docker.compose.project`, after the images it names are copied. It holds
**two layers**:

| Layer | What it is |
|---|---|
| `compose.yaml` | The committed file, **byte for byte**, comments and all. |
| `image-digests.yaml` | Overlay restating the five `image:` keys as `<tag>@sha256:...` |

The overlay is merged last and wins, which is why `stack/compose.yaml` guards
`IMAGE_PREFIX` and `IMAGE_TAG` with a `:-` rather than a `:?`; that file's header carries
the reasoning. The artifact is published **once per tag**, and every tag resolves to the
same digests. The published digest is signed by `cosign`, keyless, as the images are. Only
the bind mount *declarations* travel: **no directory contents are published.**

`stack/.env` reaches neither end of a release: the release sets `IMAGE_PREFIX` and
`IMAGE_TAG` itself, and `image-digests.yaml` wins at deploy.

## Verifying a release

```sh
docker buildx imagetools inspect tomborglum/expense-tracker-backend:2.0.0
cosign verify tomborglum/expense-tracker-backend@sha256:<digest> \
  --certificate-identity-regexp '.*/workflows/.*/docker-hub-publish\.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker compose -f oci://docker.io/tomborglum/expense-tracker-stack:2.0.0 config
```

The stack takes the same two verifications against its own repository.

**The signing identity is the called workflow, not this repository.** Fulcio puts
`job_workflow_ref` in the certificate's SAN, so the identity to match is
`TomBorglum/workflows/.github/workflows/docker-hub-publish.yml@refs/tags/vX.Y.Z`. A
regexp written against `expense-tracker` matches nothing.

**If the credential exchange is refused**, read the claim dump the run logs before its
first AWS call, correct the trust policy in the console and re-run the failed job: the AWS
side lives outside the tag, so that loop is free.

**If the called workflow itself is wrong**, the fix is a release in `workflows` and a pin
bump here: a `release` event runs `publish.yml` as it exists on the tag, and that file
names an exact version. Every pull request builds, scans and gates all three images, and
publishes nothing.

[workflows]: https://github.com/TomBorglum/workflows
[reference]: https://github.com/TomBorglum/workflows/blob/main/docs/docker-hub-publish.md
