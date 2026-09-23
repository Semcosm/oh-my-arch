# Oh My Arch

Oh My Arch — A composable Arch image build system.

Oh My Arch is a declarative, multi-architecture image build framework for
Arch Linux. It models an image as the composition of a profile, components,
an architecture, and a platform, then delegates the low-level live-image
assembly to archiso and its mkarchiso backend.

It is deliberately more than a collection of archiso profile files. The
project owns the build model, package composition, support matrix, artifact
naming, and build manifest. mkarchiso is a replaceable backend boundary.

## Project status

This repository is in early development. The only implemented and verified
combination is:

| Architecture | Profile | Platform | Status |
| --- | --- | --- | --- |
| x86_64 | minimal | generic | Implemented |
| aarch64, armv7h, riscv64 | minimal | generic | Planned |
| x86_64 | desktop, installer, rescue | generic | Planned |

Other architectures are not assumed to be x86_64 with a different name. Each
will eventually define its own repositories, kernel, bootloader, firmware,
platform variants, and image formats.

## Repository model

The build graph is intentionally layered:

    Profile + Components + Architecture + Platform
                             |
                        Build System
                             |
                           archiso
                             |
                        Image artifacts

Package manifests are composed in this order and de-duplicated while keeping
the first declaration as the owner:

    profiles/base/packages/common
    + profiles/<profile>/packages/profile-<profile>
    + architectures/<architecture>/packages
    + platforms/<platform>/packages
    + components/<component>/packages

The main extension points are:

    profiles/       image behavior and profile-specific files
    architectures/  architecture repositories, kernels, boot, and patches
    platforms/      hardware variants within an architecture
    components/     optional package and filesystem capabilities
    config/         project defaults, mirrors, signing, and support matrix
    scripts/        CLI implementation and independently testable helpers

## Build dependencies

Release and main-branch ISO builds run remotely in GitHub Actions. The
workflow uses an Arch Linux container and publishes the ISO artifacts for
download; local builds are optional development checks only.

Build on a standard Arch Linux x86_64 host. The backend requires the official
archiso package, which provides mkarchiso:

    sudo pacman -S --needed archiso git python

The command does not require a Python package installation. The repository
root contains the oma launcher.

## Build the first ISO remotely

    git clone <repository-url> oh-my-arch
    cd oh-my-arch
    gh workflow run oma-build.yml --repo Semcosm/oh-my-arch

Open the Actions run for oma-build and download the uploaded ISO artifact.
The workflow verifies SHA256SUMS before publishing the artifact bundle.

For local development on Arch Linux, the same command remains available:

    oma build --arch x86_64 --profile minimal

The public CLI resolves the build model first and then invokes mkarchiso:

    oma --help
    oma build --help
    oma build --arch x86_64 --profile minimal --dry-run

Optional components can be added without copying a profile:

    oma build --arch x86_64 --profile minimal --component networking

The default mirror is configured in config/mirrors.conf. Change it for a
local mirror before building. Package signing policy is documented in
config/signing.conf; signing keys are intentionally not embedded in the
repository.

## Artifacts

Builds are written to output/ with predictable names:

    output/oh-my-arch-minimal-x86_64-<version>.iso
    output/SHA256SUMS
    output/oh-my-arch-minimal-x86_64-<version>.manifest.json

The manifest records the architecture, profile, platform, version, Git
revision, UTC build timestamp, resolved package ownership, backend command,
artifact size, and SHA-256 digest. Set SOURCE_DATE_EPOCH for a stable build
timestamp when producing reproducible artifacts.

## Development checks

These checks do not require mkarchiso:

    oma check
    make check

An actual ISO build must run on Arch Linux with mkarchiso installed. The
first release does not claim support for other architecture/profile/platform
combinations until they have a real backend path and verification.

## Roadmap

1. Stabilize the x86_64 minimal ISO and artifact verification.
2. Add explicit architecture backends and package repositories, starting with
   aarch64 rather than copying x86_64 assumptions.
3. Add desktop, installer, and rescue profiles as independently tested layers.
4. Add platform variants such as Raspberry Pi, Rockchip, and Qualcomm only
   with validated firmware, boot, and image-format definitions.
5. Extend the artifact model to EFI images, netboot, bootstrap/rootfs
   tarballs, and disk images.
