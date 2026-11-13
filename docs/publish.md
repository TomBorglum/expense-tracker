# Publishing

`.github/workflows/publish.yml` publishes all three images to Docker Hub when
release-please's GitHub Release is published. It holds the triggers, the concurrency group
and the values describing this repository's environment; `.github/docker-hub-publish.yml`
declares what is published and the scan policy applied to it. The work is done by the
reusable `docker-hub-publish.yml` in [TomBorglum/workflows][workflows], pinned at an exact
version.

```
tomborglum/expense-tracker-backend
tomborglum/expense-tracker-database
tomborglum/expense-tracker-frontend
tomborglum/expense-tracker-stack      <- the stack, not an image
```

**No one of those names is written down.** Each is `<namespace>/<repository>-<directory>`,
composed at release time from the directories the config file names. **So renaming this
GitHub repository renames what a release publishes to.** The fourth is the stack rather
than an image; see [The published stack](#the-published-stack).

[`docs/docker-hub-publish.md`][reference] documents the called workflow: what a caller
must provide, the AWS objects to create, the credential path, the trust policy to put on
the role and the tag rulesets that keep it trustworthy.

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

## The vulnerability gate

Each image is scanned by Trivy before anything is published. A HIGH or CRITICAL finding
fails a release. On a pull request the same finding is advisory: it goes to the run's job
summary and the leg passes. `images.gates.vulnerability: release` is what splits the two,
and a contributor who cannot fix drift in an upstream base is the reason for the split.
**The key defaults to `always`**, which fails a pull request on the same finding, so
dropping it is what reinstates that. The check that Trivy scanned this image, and not
something else, fails under either value.
[The reference][reference] records how the scan is made trustworthy.

### Where a finding is recorded

Two properties decide the file: whether the image can execute the vulnerable code, and
whether a fix is published. Each image carries its own pair, under its own directory.

| | Fix available | No fix available |
| --- | --- | --- |
| **Not reachable** | VEX, no date | VEX, no date |
| **Reachable** | Ignore file, dated to the base bump | Ignore file, review-by date |

**`<dir>/.vex/<dir>.openvex.json`** holds that image's unreachable set, each statement
carrying the measurement that puts the vulnerable code out of reach. Unreachability is a
property of the image rather than a wait, so no statement carries a date. `trivy --vex`
suppresses `not_affected` and `fixed` only, so an `affected` statement documents a
finding without hiding it and never clears the gate.

**A statement's product is a bare package PURL**, such as `pkg:apk/alpine/libxslt`. The
gate scans a local OCI layout, which carries neither a repository name nor a digest, so a
`pkg:oci/...` product matches nothing and the statement is silently inert - the finding
is still reported and nothing says the document was ignored. One PURL covers a
package's subpackages: the statement on `pkg:apk/alpine/curl` clears `libcurl` as well.
A document reaches one image's scan, so a rationale has to hold for that image alone,
and a package both alpine images carry is stated in both documents.

**`<dir>/.trivyignore.yaml`** holds that image's reachable set, so every entry in it is
a finding that ships. Each carries `expired_at`, and each file's header states the two
meanings a date has.

**A file is found only because `.github/docker-hub-publish.yml` names it**, under its
image's directory key and relative to that directory. `trivyignores` and `vex-documents`
default to empty, so dropping an entry applies that file to nothing and fails the release
on every finding it covers.

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
