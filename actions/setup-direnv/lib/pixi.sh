#!/bin/bash
# use_pixi
#
# CI-only (GitHub Actions) direnv directive for a pixi workspace. The action
# installs this file onto the runner's ~/.config/direnv/lib; it is never run
# outside GitHub Actions. Self-contained by design: it sources no other file.
#
# CI activates a workspace the repo already commits, so a missing manifest is a
# hard error, not a convenience to paper over. pixi has no canonical <TOOL>_HOME
# convention, so this exports only bin dirs to $GITHUB_PATH (no $GITHUB_ENV).
use_pixi() {
  # Install pixi under an explicit home rather than relying on the installer's
  # default: PIXI_HOME pins the location (binary at $PIXI_HOME/bin/pixi), and this
  # one variable drives the guard, PATH, and $GITHUB_PATH below. Value stays
  # ~/.pixi to match action.yml's cache path.
  local pixi_home="$HOME/.pixi"

  # Guard on the install dir only, to skip re-downloading on a warm rerun / full
  # cache hit. --proto '=https' --tlsv1.2 pins the transfer to HTTPS/TLS 1.2+ (no
  # plaintext redirects); PIXI_NO_PATH_UPDATE=1 stops the installer editing shell
  # rc files, a no-op in CI since we put pixi on PATH ourselves.
  if [[ ! -d "$pixi_home" ]]; then
    curl -fsSL --proto '=https' --tlsv1.2 https://pixi.sh/install.sh \
      | PIXI_HOME="$pixi_home" PIXI_NO_PATH_UPDATE=1 bash
  fi
  # Put pixi on PATH (CI has no shell integration) so it is callable below.
  export PATH="$pixi_home/bin:$PATH"

  # Install the workspace's environment. `pixi install` is idempotent: it reuses an
  # environment that already exists (e.g. restored from cache) and only solves what
  # is missing. It returns non-zero on real failure, so gate on its exit code
  # directly; this catches both a failed install and a missing manifest, which pixi
  # rejects more accurately than a pixi.toml/pyproject.toml file test would.
  if ! pixi install; then
    echo "use_pixi: pixi install failed in $(pwd)" >&2
    # exit, not return: direnv silently ignores a directive that `return`s a
    # non-zero code (the job would go green with nothing installed), whereas a
    # non-zero `exit` from the .envrc propagates and fails the step.
    exit 1
  fi

  # Resolve the environment's prefix via pixi itself rather than hardcoding
  # .pixi/envs/default — `pixi run` activates the default environment and exports
  # the conda-style $CONDA_PREFIX, so this tracks wherever the environment actually
  # lives (a detached-environments config or a cache-restored prefix).
  local env_prefix
  env_prefix="$(pixi run bash -c 'printf %s "$CONDA_PREFIX"' 2>/dev/null || true)"
  if [[ -z "$env_prefix" || ! -d "$env_prefix/bin" ]]; then
    echo "use_pixi: failed to resolve pixi environment prefix in $(pwd)" >&2
    exit 1
  fi

  # Expose the runtime to subsequent workflow steps: the environment's bin, plus
  # pixi's own bin ($pixi_home/bin) so `pixi` stays callable in later steps.
  echo "$env_prefix/bin" >> "$GITHUB_PATH"
  echo "$pixi_home/bin" >> "$GITHUB_PATH"
  return 0
}
