# The automation App

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
