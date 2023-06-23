## Development

### Quick Start

#### Introduction

* RimSort is built in Python using the [PySide6](https://pypi.org/project/PySide6/) module, as well as several others. RimSort packaged for Mac, Linux, and Windows.

* For a (mostly automated) experience building RimSort, please execute the provided script:
    * Prerequisites:
        * Linux users need `g++` compiler (just get your distro's build tools - i.e. `build-essential`, etc)
        * MacOS users need Xcode command line tools
        * Windows users need to install VS build tools
        * See [Building SteamworksPy from Source](https://github.com/oceancabbage/RimSort/wiki/Development-Guide#building-steamworkspy-from-source) for supplemental information regarding this.
    * Run `python3 distribute.py`
        * This will build RimSort for your platform and output a build for your platform (Including all requirements and submodules)

### Manually building

* RimSort also depends on the following submodules (run `git submodule update --init --recursive` to initiate/update):
    * [steamfiles](https://github.com/twstagg/steamfiles): used to parse Steam client acf/appinfo/manifest information
    * [SteamworksPy](https://github.com/philippj/SteamworksPy): used for interactions with the local Steam client
        * SteamworksPy is a python module built to interface directly with the [Steamworks API](https://partner.steamgames.com/doc/api)
        * This allows certain interactions with the local Steam client to be initiated through the Steamworks API via Python (such as subscribing/unsubscribing to/from Steam mods via RimSort)

#### Setting up Python & dependencies

* RimSort uses Python, and depends on several Python modules:
    * [Python](https://www.python.org/): programming language used to develop RimSort. Install version `3.9.6` if possible. You can do this by first installing [HomeBrew](https://docs.brew.sh/Installation) and then running `brew install python@3.9`.
    * [natsort](https://pypi.org/project/natsort/): used for "naturally sorting" lists of folders
    * [Nuitka](https://nuitka.net/): packages application for distribution. Install version >= `1.6-4c6` if possible. You can do this by running `pip3 install nuitka`.
        * [This issue](https://github.com/Nuitka/Nuitka/issues/2154) was fixed in Nuitka 1.6
            * At this time (04/09/2023) you can install with nuitka factory using `pip install -U --force-reinstall "https://github.com/Nuitka/Nuitka/archive/factory.zip"`
    * [PySide6](https://pypi.org/project/PySide6/): GUI toolkit for building the application. Install version `5.15.2.1` if possible. You can do this by running `pip3 install PySide6==6.4.3`.
    * [steam](https://pypi.org/project/steam/): Steam module included to be used for the WebAPI calls in the "Dynamic Query" feature. You can do this by running `pip3 install steam`.
    * [toposort](https://pypi.org/project/toposort/): sort mods! Install version `1.9` if possible. You can do this by running `pip3 install toposort==1.9`.
    * [xmltodict](https://pypi.org/project/xmltodict/): parse RimWorld `xml` files. Install version `0.13.0` if possible. You can do this by running `pip3 install xmltodict==0.13.0`.

* You can install all of the above dependencies by executing the command at the project root: 
    * `pip install -r requirements.txt`

* If you are using a Mac with an Apple M1/M2 CPU, the following instructions also work for i386, if you would rather use MacPorts over Homebrew or another method. Consider the following:
    * `sudo port select --set pip3 pip39`
    * `sudo port select --set python3 python39`

* Mac users should also keep in mind that Apple has it's own Runtime Protection called [Gatekeeper](https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web)
    * This can cause issues when trying to run RimSort (or execute dependent libs)!
    * You can circumvent this issue by using `xattr` command to manually whitelist:
        * `xattr -d com.apple.quarantine RimSort.app`
        * `xattr -d com.apple.quarantine libsteam_api.dylib`

#### Setting up steamfiles module

* You can setup this module using the following commands:
    * `cd steamfiles`
    * `pip install -r requirements.txt`

#### Using SteamworksPy binaries:

* You can setup this module using the following commands:
    * `cd SteamworksPy`
    * `pip install -r requirements.txt`

* For RimSort to actually USE the SteamworksPy module, you need the compiled library for your platform, as well as the binaries from the steamworks SDK in the RimSort project root - in conjunction the python module included at: `SteamworksPy/steamworks`.
    * Repo maintainers will provide pre-built binaries for the `SteamworksPy` library, as well as the redistributables from the steamworks-sdk in-repo as well as in in each platform's respective Release.
    * On Linux, you will want to copy `SteamworksPy_*.so` (where * is your CPU) to `SteamworksPy.so`
    * On MacOS, you will want to copy `SteamworksPy_*.dylib` (where * is your CPU) to `SteamworksPy.dylib`

#### Building SteamworksPy from source:

This is an _**OPTIONAL**_ step. You do not _**NEED**_ to do this - there are already pre-built binaries available for usage in-repo as well as in each platform's respective Release. Please do not attempt to commit/PR an update for these binaries without maintainer consent - these will not be approved otherwise.

Reference: https://philippj.github.io/SteamworksPy/

* On Linux, you need `g++'. It worked right out of the box for me on Ubuntu.
    * Just run the included script: `python3 distribute.py`
        * OR see the commands I use to compile it automatically using the script

* On MacOS, you need Xcode command line tools. Then, you can compile directly with the script (without a full Xcode install):
    * Just run the included script: `python3 distribute.py`
        * OR see the commands I use to compile it automatically using the script

* On Windows, you need to get Visual Studio & Build Tools for Visual Studio:
    * https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
        * When you run the downloaded executable, it updates and runs the Visual Studio Installer. To install only the tools you need for C++ development, select the "Desktop development with C++" workload. Alternatively, just install VS Community 2022 with the standard loadset.
        * Just run the included script: `python3 distribute.py`
            * OR see the commands I use to compile it automatically using the script

#### Texture optimization (todds)
* RimSort uses [todds](https://github.com/joseasoler/todds) as a dependency for texture optimization. It is shipped with RimSort, archived into the binary releases. If you are building/running from source, you will want to place a todds binary at `./todds/todds` (for Linux/Mac) OR `.\todds\todds.exe` (for Windows)
* You can run `distribute.py` and this is automatically taken care of if you are building on a supported platform.
    * You need to enable this first. Edit the script and remove the comment for string `build_steamworkspy()`

#### Running RimSort from source
1. Clone this repository to a local directory.
2. Ensure you have completed the prerequisite steps above.
3. From the project root, execute `python3 RimSort.py`

#### Packaging RimSort

1. First, clone this repository to a local directory.
2. Packaging with `nuitka`:
    - Follow the prerequisite setup instructions, and then run `python distribute.py`
    - Alternatively, see the commands used by platform in the aforementioned script. 

#### Developing Features

Please make sure if you have any feature request to check if there is already something planned. We are tracking features and issues related to RimSort in the Github repo's "Issues" tab. If it is not already in the issues tab you can discuss this with maintainers first throught the RimSort discordserver. 

#### Misc Coding Style

* The preferred Python formatter is: black (`pip3 install black`)
    * Here is a nice little article for VSCode: https://dev.to/adamlombard/how-to-use-the-black-python-code-formatter-in-vscode-3lo0
* The preferred Docstring format is: [Sphinx reST](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html)
* Type annotations should be added to function/method signatures
* We use [Mypy](https://mypy.readthedocs.io/en/stable/) for static type checking.
    * Grab [this extension](https://marketplace.visualstudio.com/items?itemName=matangover.mypy) for VSCode/VSCodium!
* Autoflake is also really nice!
    * Grab [this extension](https://open-vsx.org/extension/mikoz/autoflake-extension) for VSCode/VSCodium
    * Set it up like such: https://stackoverflow.com/a/67941822
* For quick setup, you can install some of the dependencies described above to automate your development:
    * `pip install -r requirements_develop.txt`

#### Misc information

* On MacOS, to see open sockets, use: `netstat -anvp tcp | awk 'NR<3 || /LISTEN/'`
