# Development Guide

## Quick Start

### Introduction

- RimSort is built in Python using the [PySide6](https://pypi.org/project/PySide6/) module, as well as several others. RimSort packaged for Mac, Linux, and Windows.

## Cloning the repository

- RimSort uses submodules that are hosted in other repositories that also need to be cloned
- To clone (with submodules): `git clone --recurse-submodules -j8 https://github.com/RimSort/RimSort`

## Automated build process

- Prerequisites:
  - Run an OS that PySide6 supports
    - Example "minimmum requirements":
      - For our Linux builds, we target Ubuntu 22.04 and Ubuntu 24.04.
      - For our MacOS builds:
        - i386 utilizes GitHub's macos-13 runner
        - arm utilizes GitHub's macos-latest (macos-14 at the time of writing) runner
      - For Windows, we utilize Github's windows-latest (Windows 2022 at the time of writing) runner
  - Install the latest version of [Python](https://python.org/) 3.11 for your platform. (CPython recommended)
- For a (mostly automated) experience building RimSort, please execute the provided script:
  - Run `python distribute.py`
    - This will build RimSort for your platform and output a build for your platform (Including all requirements and submodules)
    - For additional options such as disabling certain steps, see `python distribute.py --help`

## Manually building

- It is recommended that you build inside a Python virtualenv:
  - From inside the RimSort project root, execute:
    - `python -m pip install virtualenv`
    - `python -m venv .`
    - To activate this:
      - Unix (`*sh`): `source bin/activate`
      - Windows (`powershell`): `.\Scripts\Activate.ps1`
  - Ensure that build requirements are installed `requirements_build.txt`
- RimSort also depends on the following submodules (run `git submodule update --init --recursive` to initiate/update):
  - [steamfiles](https://github.com/twstagg/steamfiles): used to parse Steam client acf/appinfo/manifest information
  - [SteamworksPy](https://github.com/philippj/SteamworksPy): used for interactions with the local Steam client
    - SteamworksPy is a python module built to interface directly with the [Steamworks API](https://partner.steamgames.com/doc/api)
    - This allows certain interactions with the local Steam client to be initiated through the Steamworks API via Python (such as subscribing/unsubscribing to/from Steam mods via RimSort)

### Setting up Python & dependencies

- RimSort uses Python, and depends on several Python modules. You can install/view most of the above dependencies via `requirements.txt`. You can install them all at once by executing the command at the project root:

  - `pip install -r requirements.txt`
  - Note that `requirements.txt`

- There are **steamfiles** and **SteamworksPy** dependencies can't be installed with just requirements.txt for various reasons

  - See their respective sections for information on how to set them up. Alternatively, use `distribute.py` to do so automatically. By default the script will build RimSort, but it can be configured to enable or disable various steps including building. See `python distribute.py --help` for more info.

- If you are using a Mac with an Apple M1/M2 CPU, the following instructions also work for i386, if you would rather use MacPorts over Homebrew or another method. Consider the following:

  - `sudo port select --set pip3 pip39`
  - `sudo port select --set python python9`

- Mac users should also keep in mind that Apple has it's own Runtime Protection called [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
  - This can cause issues when trying to run RimSort (or execute dependent libs)!
  - You can circumvent this issue by using `xattr` command to manually whitelist:
    - `xattr -d com.apple.quarantine RimSort.app`
    - `xattr -d com.apple.quarantine libsteam_api.dylib`

### Setting up steamfiles module

- You can setup this module by running pip install on the module
  - `pip install -e submodules/steamfiles`

### Using SteamworksPy binaries

- You can setup this module using the following commands:

  - `cd SteamworksPy`
  - `pip install -r requirements.txt`

- For RimSort to actually USE the SteamworksPy module, you need the compiled library for your platform, as well as the binaries from the steamworks SDK in the RimSort project root - in conjunction the python module included at: `SteamworksPy/steamworks`.
  - Repo maintainers will provide pre-built binaries for the `SteamworksPy` library, as well as the redistributables from the steamworks-sdk in-repo as well as in in each platform's respective Release.
  - On Linux, you will want to copy `SteamworksPy_*.so` (where \* is your CPU) to `SteamworksPy.so`
  - On MacOS, you will want to copy `SteamworksPy_*.dylib` (where \* is your CPU) to `SteamworksPy.dylib`

### Building SteamworksPy from source

This is an _**OPTIONAL**_ step. You do not _**NEED**_ to do this - there are already pre-built binaries available for usage in-repo as well as in each platform's respective release. Please do not attempt to commit/PR an update for these binaries without maintainer consent - these will not be approved otherwise.

Reference: [SteamworksPy](https://philippj.github.io/SteamworksPy/)

- On Linux, you need `g++`. It worked right out of the box for me on Ubuntu.
- On MacOS, you need Xcode command line tools. Then, you can compile directly with the script (without a full Xcode install):
- On Windows, you need to get Visual Studio & Build Tools for Visual Studio:
  - [MSVC](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
    - When you run the downloaded executable, it updates and runs the Visual Studio Installer. To install only the tools you need for C++ development, select the "Desktop development with C++" workload. Alternatively, just install VS Community 2022 with the standard loadset.

Execute: `python -c "from distribute import build_steamworkspy; build_steamworkspy()"`

### Texture optimization (todds)

- RimSort uses [todds](https://github.com/joseasoler/todds) as a dependency for texture optimization. It is shipped with RimSort, archived into the binary releases. If you are building/running from source, you will want to place a todds binary at `./todds/todds` (for Linux/Mac) OR `.\todds\todds.exe` (for Windows)

### Running RimSort from source

1. Clone this repository to a local directory with submodules.
2. Ensure you have completed the prerequisite steps above.
3. From the project root, execute `python -m app`

### Packaging RimSort

1. First, clone this repository to a local directory.
2. Packaging with `nuitka`:
   - Follow the prerequisite setup instructions, and then run `python distribute.py`
   - Alternatively, see the commands used by platform in the aforementioned script.

## Contributor Guidelines

1. Pull Requests need to be made AFTER all guidelines are met. It's OK to miss some stuff because we can catch it in review, but we should be proactive with docstrings, code formatting, etc. If not ready, use a draft.

2. Please submit Pull Requests which contain feature-specific changes only. PRs should not lump multiple changes into one thing. This so we can be more selective in discussion. This is a requirement, and deviation will cause PR to be closed.

3. There are GitHub Issue templates available on RimSort repository. Bug Reports and Feature Requests are to be submitted there, and if there is consensus on request, it will become an "Implement ...." Issue. Please do not deviate from template and allow maintainers to modify Issue to include relevant tasks and title information once consensus is reached.

   - Consensus = consensus between maintainers. That being said, we rely on your feedback, so you will have a say.
   - You are also welcome to fork this repository and make whatever changes you deem fit privately.

4. ALL PRs need to have a corresponding Issue and/or Issue sub-task(s) to reference. This is for transparency and overall will help anybody else helping to keep track of things.
   - Anybody can contribute to RimSort. That being said, we are a community and these guidelines will help encourage and enforce consistency with RimSort growth.
   - Maintainer or not - you do not have to be a maintainer to submit PR! Please don't hesitate to work from a fork or something if that's how you roll.

### Developing Features

Please ensure if you have any feature request to check if there is already something planned. We are tracking features and issues related to RimSort in the GitHub repo's "Issues" tab. If it is not already in the issues tab, you can discuss this with maintainers first through the RimSort Discord server.

### Misc Coding Style

- The preferred Python formatter is: black (`pip install black`)
  - Here is a nice little article for [VSCode](https://dev.to/adamlombard/how-to-use-the-black-python-code-formatter-in-vscode-3lo0)
- The preferred Docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
- Type annotations should be added to function/method signatures
- We use [Mypy](https://mypy.readthedocs.io/en/stable/) for static type checking.
  - Grab [this extension](https://marketplace.visualstudio.com/items?itemName=matangover.mypy) for VSCode/VSCodium!
- Autoflake is also really nice!
  - Grab [this extension](https://open-vsx.org/extension/mikoz/autoflake-extension) for VSCode/VSCodium
  - Set it up like such: [Stack Overflow](https://stackoverflow.com/a/67941822)
- For quick setup, you can install some of the dependencies described above to automate your development:
  - `pip install -r requirements_develop.txt`
- VSCode workspace settings are included
