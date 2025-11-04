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
  - `macos-14` (i386)
  - `macos-latest` (arm)
- Windows:
  - `windows-latest` (Windows 2022 at the time of writing)

### Tools and Software 

- [git](https://git-scm.com/)
- [Python](https://python.org/) 3.12 (Can be installed with uv if you'd like)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Cloning the repository
RimSort uses submodules that are hosted in other repositories that need to be cloned. 
- [steamfiles](https://github.com/twstagg/steamfiles): used to parse Steam client acf/appinfo/manifest information
- [SteamworksPy](https://github.com/philippj/SteamworksPy): used for interactions with the local Steam client
  - SteamworksPy is a python module built to interface directly with the [Steamworks API](https://partner.steamgames.com/doc/api)
  - This allows certain interactions with the local Steam client to be initiated through the Steamworks API via Python (such as subscribing/unsubscribing to/from Steam mods via RimSort)

To clone with submodules run:
```shell
git clone --recurse-submodules -j8 https://github.com/RimSort/RimSort
```

Should you need to update these submodules, or you forgot to clone with `--recurse-submodules`, run:
```shell
git submodule update --init --recursive
```

## Set up your environment

RimSort uses the Python package and project manager [uv](https://docs.astral.sh/uv/).

To get started, in the project root, simply run: 
```shell
uv sync
```

Note that by default, `uv` will also install the dev dependency group.

If you wish to also build the executables locally, you'll need to also install the `build` dependency group:
```shell
uv sync --group build
```

## Automated build process
- For a (mostly automated) experience building RimSort, please execute the provided script:
  - Run `uv run python distribute.py`
    - This will build RimSort for your platform and output a build for your platform (Including all requirements and submodules)
    - For additional options such as disabling certain steps, see `uv run python distribute.py --help`

## Manually building
Ensure that build requirements are installed by running `uv sync --group build`.

### Setting up additional dependencies
 RimSort uses Python, and depends on several Python modules. You can install/view most of the above dependencies via `pyproject.tom`. These would have been set up in the prior environment setup step. However, the **SteamworksPy** dependency is a special case that has requires special handling. 

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

### Using SteamworksPy binaries

For RimSort to actually USE the SteamworksPy module, you need the compiled library for your platform, as well as the binaries from the steamworks SDK in the RimSort project root - in conjunction the python module included at: `SteamworksPy/steamworks`.
  - Repo maintainers will provide pre-built binaries for the `SteamworksPy` library, as well as the redistributables from the steamworks-sdk in-repo as well as in each platform's respective release.
  - On Linux, you will want to copy `SteamworksPy_*.so` (where \* is your CPU) to `SteamworksPy.so`
  - On macOS, you will want to copy `SteamworksPy_*.dylib` (where \* is your CPU) to `SteamworksPy.dylib`

### Building SteamworksPy from source

{: .note}
> At the time of writing, the SteamworksPy module can only be built using Python 11, differing from RimSort itself. You may need to use a different Python environment from the one you use to handle RimSort.

- You can set up this module using the following commands:

  - `cd SteamworksPy`
  - `pip install -r requirements.txt`

This is an _**OPTIONAL**_ step. You do not _**NEED**_ to do this - there are already pre-built binaries available for usage in-repo as well as in each platform's respective release. Please do not attempt to commit/PR an update for these binaries without maintainer consent - these will not be approved otherwise.

Reference: [SteamworksPy](https://philippj.github.io/SteamworksPy/)

- On Linux, you need `g++`. It worked right out of the box for me on Ubuntu.
- On macOS, you need Xcode command line tools. Then, you can compile directly with the script (without a full Xcode install):
- On Windows, you need to get Visual Studio & Build Tools for Visual Studio:
  - [MSVC](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
    - When you run the downloaded executable, it updates and runs the Visual Studio Installer. To install only the tools you need for C++ development, select the "Desktop development with C++" workload. Alternatively, just install VS Community 2022 with the standard load set.

Execute: `python -c "from distribute import build_steamworkspy; build_steamworkspy()"`

### Texture optimization (todds)

- RimSort uses [todds](https://github.com/joseasoler/todds) as a dependency for texture optimization. It is shipped with RimSort, archived into the binary releases. If you are building/running from source, you will want to place a todds binary at `./todds/todds` (for Linux/Mac) OR `.\todds\todds.exe` (for Windows)

### Running RimSort from source

1. Clone this repository to a local directory with submodules.
2. Ensure you have completed the prerequisite steps above.
3. From the project root, execute `uv run python -m app`

### Packaging RimSort

After following all the prior steps, from the RimSort project root directory, first add the `SteamworksPy` submodule to the Python path:

On Linux/macOS:
```shell
PYTHONPATH=./submodules/SteamworksPy
```

On Windows (Powershell):
```powershell
$env:PYTHONPATH = ".\submodules\SteamworksPy"
```

Then build with nuitka:
```shell
uv run nuitka app/__main__.py
```
