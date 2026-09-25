# Repository Guidelines

## Project Structure & Module Organization

Oh My Arch models images from profiles, components, architectures, and platforms.
Profiles live under `profiles/`; architecture definitions, kernels, boot files,
and patches under `architectures/`; hardware variants under `platforms/`; and
optional package/filesystem capabilities under `components/`. Project defaults
and the support matrix are in `config/`. The `oma` launcher and Python
implementation are at the repository root and in `scripts/`. Shell checks are in
`scripts/test/`, GitHub workflows in `.github/workflows/`, and generated files
belong in ignored `.oma/` and `output/` paths. Keep `output/.gitkeep` only.

## Build, Test, and Development Commands

- `make check` validates the build model and runs the CLI test script.
- `./oma check` performs the model check alone.
- `make dry-run` or `./oma build --arch x86_64 --profile minimal --dry-run`
  prints the resolved package and backend plan without building.
- `make build` performs a local ISO build on Arch Linux with `archiso` installed.
- `make clean` removes generated work and output artifacts.
- `gh workflow run oma-build.yml --repo Semcosm/oh-my-arch` runs the remote
  ISO build; releases require an annotated SSH-signed `vX.Y.Z` tag.

## CI-First Validation and Evidence

GitHub Actions is the authoritative verification environment for this
project. Local checks are useful for fast feedback, but a change is not
verified until the required CI workflows pass. Treat local ISO builds and
QEMU runs as optional diagnostics; do not represent them as release evidence.

For every change that is pushed or merged, record the CI workflow run IDs and
URLs, job conclusions, and relevant artifact or checksum results in the
change request's `Test Evidence` section. If CI is unavailable or a required
job fails, report the blocker and leave the change unverified rather than
inferring success from local results.

## Coding Style & Naming Conventions

Use Bash strict mode (`set -euo pipefail`) and quote paths and variables. Use
readable Python with four-space indentation and standard-library dependencies
only unless the build contract changes. Use lowercase, descriptive directory and
file names; keep profile, architecture, platform, and component names stable
because they are CLI selectors. Run `git diff --check` before committing.

## Testing Guidelines

Run `make check` locally for model, CLI, or signing changes. It covers help
output, package composition, unsupported architectures, and signature
fixtures, but does not replace the `oma-check` CI result. Changes to policy,
workflows, or repository layout should also pass
`scripts/validate_quality_profile.sh`,
`scripts/validate_supply_chain_profile.sh`, `scripts/validate_action_pinning.sh`,
and `scripts/validate_repository_shape.sh`. The required CI gates are
`oma-check`, `ugs-validate`, and the base-controlled `ugs-signatures`; changes
to the build path must also pass `oma-build`, including checksum and boot
smoke-test steps. Actual ISO verification runs in GitHub Actions on the Arch
Linux container.

## Commit Signing

Use the dedicated SSH key through an agent; never commit private material. Set
`gpg.format=ssh`, `user.signingkey=~/.ssh/oh-my-arch-signing.pub`,
`commit.gpgsign=true`, and `tag.gpgsign=true`. Verify a new range against the
trusted parent snapshot, for example
`scripts/validate_commit_signatures.sh HEAD^..HEAD HEAD^`. Release tags must
pass `scripts/validate_release_tag.sh vX.Y.Z`; it derives the tagged commit's
parent as the trust baseline. Add or revoke a signer in one signed push, then
use that signer only in a later push so the baseline cannot be self-authorized.

## Commit & Pull Request Guidelines

Use the existing Conventional Commit form, such as `build: update minimal
profile` or `ci: change remote build`. Keep commits focused. For changes merged
to `main`, add a populated `cr/CR-XXXX.md` record with summary, motivation,
CI test evidence, risk, rollback, and full commit OIDs. Pull requests should
explain the changed build model, include CI run links, and call out
support-matrix or artifact changes. Required checks include `oma-check`,
`ugs-validate`, and the base-controlled `ugs-signatures` PR check; build-path
changes also require `oma-build`. Do not commit ISO files, `.oma/` work
trees, package caches, or generated manifests.
