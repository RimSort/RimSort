---
title: Development Setup & Building
nav_order: 1
layout: default
parent: Development Guide
permalink: development-guide/development-setup
---
# Development Setup & Building

{: .no_toc }

## Table of Contents

{: .no_toc .text-delta }

1. TOC
{:toc}

### Introduction

RimSort is built in Python using the [PySide6](https://pypi.org/project/PySide6/) module, as well as several others. Some modules require special care in order to be built. It is compiled and packaged using [Nuikta](https://nuitka.net/).

## Prerequisites

### OS

RimSort presently runs on Windows, MacOS, and Linux, though we presently only create builds for Ubuntu. It may work for other Linux distributions, but Ubuntu is our baseline.

Your OS needs to be one that PySide6 supports. As an example, we use the following GitHub runners to make our release builds:

- Linux:
  - `ubuntu-22.04`
  - `ubuntu-24.04`
- macOS builds:
  - `macos-15-intel` (i386)
  - `macos-latest` (arm)
- Windows:
  - `windows-latest` (Windows 2022 at the time of writing)

### Tools and Software

**Required:**

- [git](https://git-scm.com/)
- [Python](https://python.org/) 3.12 (Can be installed with uv if you'd like)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [just](https://just.systems/man/en/installation.html) — task runner for development commands

**For code quality checks** (used by `just check` and CI):

- [Node.js / npx](https://nodejs.org/) — needed for [JSCPD](https://github.com/kucherenko/jscpd) copy-paste detection (`just jscpd`)
- [shfmt](https://github.com/mvdan/sh#shfmt) — shell script formatter (`just shfmt`)

Python linters (ruff, mypy) are installed automatically by `uv sync` — no manual setup needed.

### Cloning the repository

RimSort uses a submodule hosted in another repository that needs to be cloned.

- [steamfiles](https://github.com/RimSort/steamfiles): used to parse Steam client acf/appinfo/manifest information

RimSort also uses **rimsort_steam**, a custom C++ shim for the [Steamworks API](https://partner.steamgames.com/doc/api), located in `libs/rimsort_steam/`. Pre-built binaries are committed to `libs/` for all platforms, so most developers do not need to build it from source.

To clone with submodules run:

```shell
git clone --recurse-submodules -j8 https://github.com/RimSort/RimSort
```

Should you need to update the steamfiles submodule, or you forgot to clone with `--recurse-submodules`, run:

```shell
git submodule update --init --recursive
```

## Set up your environment

RimSort uses the Python package and project manager [uv](https://docs.astral.sh/uv/).

The easiest way to set up everything (submodules, venv, dev + build dependencies) is:

```shell
just dev-setup
```

This runs `uv sync --locked --dev --group build`, which installs all runtime, dev, and build dependencies (including linters like ruff and mypy).

After setup, install the shared git hooks so that `just check` runs automatically before each commit:

```shell
just install-hooks
```

If you prefer to do it manually:

```shell
uv sync --dev            # install runtime + dev dependencies (linters, test tools)
uv sync --group build    # also install build dependencies (nuitka, etc.)
```

## Automated build process

- For a (mostly automated) experience building RimSort, please execute the provided script:
  - Run `uv run python distribute.py`
    - This will build RimSort for your platform and output a build for your platform (Including all requirements and submodules)
    - For additional options such as disabling certain steps, see `uv run python distribute.py --help`

## Manually building

Ensure that build requirements are installed by running `uv sync --group build`.

### Setting up additional dependencies

 RimSort uses Python, and depends on several Python modules. You can install/view most of the above dependencies via `pyproject.toml`. These would have been set up in the prior environment setup step.

See their respective sections for information on how to set them up. Alternatively, use `distribute.py` to do so automatically. By default, the script will build RimSort, but it can be configured to enable or disable various steps including building. See `uv run python distribute.py --help` for more info.

- If you are using a Mac with an Apple M1/M2 CPU, the following instructions also work for i386, if you would rather use MacPorts over Homebrew or another method. Consider the following:
  - `sudo port select --set pip3 pip39`
  - `sudo port select --set python python9`

- Mac users should also keep in mind that Apple has its own Runtime Protection called [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
  - This can cause issues when trying to run RimSort (or execute dependent libs)!
  - You can circumvent this issue by using `xattr` command to manually whitelist:
    - `xattr -d com.apple.quarantine /path/to/RimSort.app`
    - `xattr -d com.apple.quarantine /path/to/libsteam_api.dylib`
  - Replace `/path/to/` with the actual path where the file/folder is, example:
    - `xattr -d com.apple.quarantine /Users/John/Downloads/RimSort.app`

### Using rimsort_steam binaries

RimSort uses **rimsort_steam**, a lightweight C++ shim that wraps the [Steamworks API](https://partner.steamgames.com/doc/api). Pre-built binaries and Steam SDK redistributables are committed to `libs/` for all platforms. Most developers do not need to do anything beyond cloning the repository.

### Building rimsort_steam from source

This is an _**OPTIONAL**_ step. You do not _**NEED**_ to do this -- pre-built binaries are already committed to `libs/` for all platforms. Only rebuild if you are modifying the native shim or updating the Steamworks SDK.

To build from source:

1. Download and extract the [Steamworks SDK](https://partner.steamgames.com/).
2. Set the `STEAMWORKS_SDK_PATH` environment variable to the extracted SDK root.
3. Run `make` inside `libs/rimsort_steam/`.

Platform requirements:

- On Linux, you need `g++`. It works out of the box on Ubuntu.
- On macOS, you need Xcode command line tools (`xcode-select --install`).
- On Windows, use the provided `build_windows.bat` (requires MSVC / Visual Studio Build Tools).

Please do not attempt to commit/PR an update for these binaries without maintainer consent -- such requests will not be approved otherwise.

### Texture optimization (todds)

- RimSort uses [todds](https://github.com/joseasoler/todds) as a dependency for texture optimization. It is shipped with RimSort, archived into the binary releases. If you are building/running from source, you will want to place a todds binary at `./todds/todds` (for Linux/Mac) OR `.\todds\todds.exe` (for Windows)

### Running RimSort from source

1. Clone this repository to a local directory with submodules.
2. Ensure you have completed the prerequisite steps above.
3. From the project root, execute `uv run python -m app`

### Packaging RimSort

After following all the prior steps, from the RimSort project root directory, build with nuitka:

```shell
uv run nuitka app/__main__.py
```
