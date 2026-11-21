---
title: Nix
layout: default
nav_order: 6
description: "How RimSort defines, caches, and checks its Nix build"
---

# Nix

RimSort ships a [Nix](https://nixos.org/) flake: a pinned build definition that
produces the packaged application, a development shell with the exact locked
dependencies, and the lint and test checks used in continuous integration. The
flake reads `uv.lock`, so a Nix build and a `uv` build compile against the same
Python packages.

```shell
nix run github:RimSort/RimSort#rimsort     # run the packaged application
nix build github:RimSort/RimSort#rimsort   # build only
nix develop                                # development shell with the locked environment
```

The rest of this page records why the build is shaped the way it is, so a
reader can tell a deliberate choice from an accident before changing it.

## Decision record

| Decision | What this repository does | Why |
| --- | --- | --- |
| Build definition | `flake.nix` composes small modules from `nix/parts/`, one file per concern: package, Python environment, development shell, checks, tools. | Each concern is written once and reused, so the package and the checks cannot drift apart. |
| Package set | Pins `nixos-unstable` and lets Dependabot open a weekly pull request to move it. | One rolling base stays current without manual bumps; CI also rejects a pin that is not NixOS-owned, on a supported ref, or older than 30 days. |
| Supported systems | Builds for `x86_64-linux`, `aarch64-linux`, and `aarch64-darwin`. | These are the platforms the application is released for; `x86_64-darwin` is deprecated upstream, and Windows does not run Nix. |
| Python dependencies | Converts `uv.lock` with uv2nix into an application environment and a separate development environment. | Nix and non-Nix developers install from the same lock file, so versions cannot diverge. |
| Development shell | `nix develop` puts the locked environment on `PATH` and sets `UV_NO_SYNC` and `UV_PROJECT_ENVIRONMENT`, so `uv run` cannot create a second environment. | There is exactly one set of installed packages, so a command cannot behave differently inside and outside the shell. |
| SteamworksPy | Fetches the `SteamworksPy` submodule from GitHub at a pinned revision and copies it into `submodules/` during the build. | Flake source snapshots omit submodule contents, but the application imports the module at runtime. |
| Steam libraries | Loads `libsteam_api.so` from the repository's `libs/` directory instead of copying it to the source root. | The packaged layout and the tested layout stay identical, so what is tested is what is shipped. |
| Unfree packages | Allows only `rimsort`, `rimsort-tests`, `steam`, and `steam-unwrapped` through the unfree check. | The application bundles the Valve Steamworks runtime, and nothing else in the build needs an unfree package. |
| Package sources | Copies only the files the application reads at runtime into the build. | Editing documentation or tooling does not rebuild the package or change its hash. |
| Version string | Derives `0.0.0+git.<revision>` from the checked-out revision, and lets a release override it with `RIMSORT_VERSION`. | A development build reports its exact commit; a release reports the public version. |
| Overlay | Exposes `overlays.default` for NixOS and home-manager configurations. | Downstream users install the package from their own pinned package set without adding a second copy of it. |
| Non-flake entry points | `default.nix` and `shell.nix` load the flake through the compatibility shim. | `nix-build` and `nix-shell` keep working on machines with flakes disabled. |
| Single package set | Every input that needs nixpkgs, including the flake-parts library input, follows the one `nixpkgs` input. | The lock file then contains exactly one copy of the package set and its library. |
| Validation | `nix flake check` builds the package, runs the full test suite in the Nix environment, and runs the repository's lint hooks. | A pull request that breaks any of those fails before merge instead of at release time. |
| Lint hooks | Runs the same hook set as `just check`, through `git-hooks.nix`, with tool versions taken from the lock file. | Local runs and CI use identical versions, so a clean local run means a clean CI run. |
| Infrastructure policy hook | The YAML and JSON structural checks, `gitleaks`, `actionlint`, and the rest run at the pre-commit stage; `checkov` is switched off for now. | `checkov` cannot currently build against the pinned package set because one of its own dependencies fails its test suite. |
| Binary cache | Publishes build results to `https://rimsort.cachix.org` and reads from that cache through `nixConfig` in `flake.nix`. | Pull requests reuse merged build results instead of rebuilding the Python environment and tool set on every run. |

## Binary cache

The cache is a public [Cachix](https://www.cachix.org/) cache named `rimsort`,
reachable at `https://rimsort.cachix.org`.

- **Who publishes:** the `publish` job in `.github/workflows/nix-cache.yml`,
  authenticated with the `CACHIX_AUTH_TOKEN` repository secret. The job refuses
  to run when that secret is missing rather than silently "publishing"
  nothing.
- **From which branch:** only pushes to `main` or `master`, plus a manual run
  that is triggered on `main`. The job is also restricted to the
  `RimSort/RimSort` repository, so forks and pull requests never publish.
- **What it uploads:** `nix build .#rimsort` (the packaged application) and
  `nix flake check` (the check environments, which carry the Python environment
  and the pinned tool set). Every store path is pushed as it is produced.

Consumers do not configure anything. `flake.nix` declares the substituter and
its public key in `nixConfig`, but Nix only applies that configuration after a
`--accept-flake-config` flag or an interactive approval. Without either, the
build still succeeds, just from source. The pull-request workflow
`.github/workflows/nix.yml` reads the cache without a token, so a pull request
can only download and never upload.

## Continuous integration

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `.github/workflows/nix.yml` | Every pull request, merge queue entry, and push to `main` or `master`. | Checks the lock file policy, then runs `nix flake check`, which builds the package, runs the test suite, and runs the lint hooks. Reads the cache without a token. |
| `.github/workflows/nix-cache.yml` | Push to `main` or `master`, or a manual run on `main`. | Builds the package and the check environments and publishes them to the cache. |

## Checking a change locally

`nix flake check` runs the same gate as CI. A full run builds the package and
executes the test suite, so it is slower than the lint-only loop used during
development.
