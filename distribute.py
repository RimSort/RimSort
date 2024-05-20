#!/usr/bin/env python3

import argparse
from io import BytesIO
import os
from pathlib import Path
import platform
import requests
import shutil
from stat import S_IEXEC
import subprocess
import sys
from zipfile import ZipFile

"""
Setup environment
"""

_ARCH = platform.architecture()[0]
_CWD = os.getcwd()
_PROCESSOR = platform.processor()
if _PROCESSOR == "":
    _PROCESSOR = platform.machine()

_SYSTEM = platform.system()

PY_CMD = sys.executable

_NUITKA_CMD = [
    PY_CMD,
    "-m",
    "nuitka",
    "--assume-yes-for-downloads",
    "--standalone",
    "--enable-plugin=pyside6",
    "--include-data-file=./update.sh=update.sh",
    "--include-data-file=./update.sh=update.bat",
    "--include-data-file=./steam_appid.txt=steam_appid.txt",
    "--include-package=steamworks",
    "--user-package-configuration-file=./rimsort.nuitka-package.config.yml",
    "--noinclude-default-mode=error",
    "--disable-console",
    "--macos-create-app-bundle",
    "--macos-app-icon=./themes/default-icons/AppIcon_a.icns",
    "--windows-icon-from-ico=./themes/default-icons/AppIcon_a.png",
    "--file-description=An open source RimWorld mod manager.",
]

# If version.xml exists in root, add it to the Nuitka command
if os.path.exists("version.xml"):
    _NUITKA_CMD.append("--include-data-file=./version.xml=version.xml")

_NUITKA_CMD.extend(
    [
        "app/__main__.py",
        "--output-dir=./build/",
        "--output-filename=RimSort",
    ]
)

print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")

if _SYSTEM == "Darwin" and _PROCESSOR in ["i386", "arm"]:
    pass
elif _SYSTEM == "Linux":
    pass
elif _SYSTEM == "Windows" and _ARCH == "64bit":
    pass
else:
    print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
    print("Exiting...")
GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
GET_REQ_CMD_BUILD = [PY_CMD, "-m", "pip", "install", "-r", "requirements_build.txt"]
STEAMFILES_BUILD_CMD = [PY_CMD, "setup.py", "install"]
STEAMFILES_SRC = os.path.join(_CWD, "submodules", "steamfiles")
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def get_rimsort_pip(skip_build: bool = False) -> None:
    print("Installing core RimSort requirements with pip...")
    _execute(GET_REQ_CMD)

    if not skip_build:
        print("Installing RimSort build requirements with pip...")
        _execute(GET_REQ_CMD_BUILD)


def get_rimsort_submodules() -> None:
    print("Ensuring we have all submodules initiated & up-to-date...")
    _execute(SUBMODULE_UPDATE_INIT_CMD)
    # Get Steamfiles requirements
    print("Building submodules...")
    print(f"Changing directory to {STEAMFILES_SRC}")
    os.chdir(STEAMFILES_SRC)
    print("Building steamfiles module...")
    _execute(STEAMFILES_BUILD_CMD)
    print(f"Leaving {STEAMFILES_SRC}")
    os.chdir(_CWD)


def build_steamworkspy() -> None:
    # Setup environment
    print("Setting up environment...")
    STEAMWORKSPY_BIN_DARWIN = f"SteamworksPy_{_PROCESSOR}.dylib"
    STEAMWORKSPY_BIN_DARWIN_LINK_PATH = os.path.join(_CWD, "SteamworksPy.dylib")
    DARWIN_COMPILE_CMD = [
        "g++",
        "-std=c++11",
        "-o",
        f"{STEAMWORKSPY_BIN_DARWIN}",
        "-shared",
        "-fPIC",
        "SteamworksPy.cpp",
        "-l",
        "steam_api",
        "-L.",
    ]
    STEAMWORKSPY_BIN_LINUX = f"SteamworksPy_{_PROCESSOR}.so"
    STEAMWORKSPY_BIN_LINUX_LINK_PATH = os.path.join(_CWD, "SteamworksPy.so")
    LINUX_COMPILE_CMD = [
        "g++",
        "-std=c++11",
        "-o",
        f"{STEAMWORKSPY_BIN_LINUX}",
        "-shared",
        "-fPIC",
        "SteamworksPy.cpp",
        "-l",
        "steam_api",
        "-L.",
    ]
    STEAMWORKSPY_BIN_WIN32 = "SteamworksPy.dll"
    STEAMWORKS_COMPILE_CMD_WIN32 = [
        "cmd.exe",
        "/k",
        'C:\\"Program Files (x86)"\\"Microsoft Visual Studio"\\2022\\BuildTools\\VC\\Auxiliary\\Build\\vcvars64.bat',
        "&",
        "cl",
        "/D_USRDLL",
        "/D_WINDLL",
        "SteamworksPy.cpp",
        "steam_api.lib",
        "/link",
        "/DLL",
        f"/OUT:{STEAMWORKSPY_BIN_WIN32}",
        "&",
        "exit",
    ]
    STEAMWORKSPY_BIN_WIN64 = "SteamworksPy64.dll"
    STEAMWORKS_COMPILE_CMD_WIN64 = [
        "cmd.exe",
        "/k",
        'C:\\"Program Files (x86)"\\"Microsoft Visual Studio"\\2022\\BuildTools\\VC\\Auxiliary\\Build\\vcvars64.bat',
        "&",
        "cl",
        "/D_USRDLL",
        "/D_WINDLL",
        "SteamworksPy.cpp",
        "steam_api64.lib",
        "/link",
        "/DLL",
        f"/OUT:{STEAMWORKSPY_BIN_WIN64}",
        "&",
        "exit",
    ]
    # SOURCE: "https://partner.steamgames.com/downloads/steamworks_sdk_*.zip"
    STEAMWORKS_SDK_URL = "https://github.com/oceancabbage/RimSort/raw/steamworks-sdk/steamworks_sdk_155.zip"
    STEAMWORKS_PY_PATH = os.path.join(_CWD, "submodules", "SteamworksPy", "library")
    STEAMWORKS_SDK_PATH = os.path.join(STEAMWORKS_PY_PATH, "sdk")
    STEAMWORKS_SDK_HEADER_PATH = os.path.join(STEAMWORKS_SDK_PATH, "public", "steam")
    STEAMWORKS_SDK_HEADER_DEST_PATH = os.path.join(STEAMWORKS_PY_PATH, "sdk", "steam")
    STEAMWORKS_SDK_REDIST_BIN_PATH = os.path.join(
        STEAMWORKS_SDK_PATH, "redistributable_bin"
    )
    STEAMWORKS_SDK_APILIB_PATH = os.path.join(
        STEAMWORKS_SDK_REDIST_BIN_PATH, "steam_api.lib"
    )
    STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(STEAMWORKS_PY_PATH, "steam_api.lib")
    STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(_CWD, "libs", "steam_api.lib")

    print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")

    if _SYSTEM == "Darwin":
        if _ARCH == "64bit":
            STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "osx", "libsteam_api.dylib"
            )
        else:
            print(f"Unsupported ARCH: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
            sys.exit()
        STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "libsteam_api.dylib"
        )
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(
            _CWD, "libs", "libsteam_api.dylib"
        )
        COMPILE_CMD = DARWIN_COMPILE_CMD
        STEAMWORKSPY_BIN_PATH = os.path.join(
            STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_DARWIN
        )
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, "libs", STEAMWORKSPY_BIN_DARWIN)
    elif _SYSTEM == "Linux":
        if _ARCH == "32bit":
            STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "linux32", "libsteam_api.so"
            )

        elif _ARCH == "64bit":
            STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "linux64", "libsteam_api.so"
            )
        else:
            print(f"Unsupported ARCH: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
            sys.exit()
        STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "libsteam_api.so"
        )
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(_CWD, "libs", "libsteam_api.so")
        COMPILE_CMD = LINUX_COMPILE_CMD
        STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_LINUX)
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, "libs", STEAMWORKSPY_BIN_LINUX)
    elif _SYSTEM == "Windows":
        if _ARCH == "32bit":
            STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "steam_api.dll"
            )
            STEAMWORKS_SDK_APILIB_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "steam_api.lib"
            )
            STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api.dll"
            )
            STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(
                _CWD, "libs", "steam_api.dll"
            )
            STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api.lib"
            )
            STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(_CWD, "libs", "steam_api.lib")
            COMPILE_CMD = STEAMWORKS_COMPILE_CMD_WIN32
            STEAMWORKSPY_BIN_PATH = os.path.join(
                STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_WIN32
            )
            STEAMWORKSPY_BIN_FIN_PATH = os.path.join(
                _CWD, "libs", STEAMWORKSPY_BIN_WIN32
            )
        elif _ARCH == "64bit":
            STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "win64", "steam_api64.dll"
            )
            STEAMWORKS_SDK_APILIB_PATH = os.path.join(
                STEAMWORKS_SDK_REDIST_BIN_PATH, "win64", "steam_api64.lib"
            )
            STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api64.dll"
            )
            STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(
                _CWD, "libs", "steam_api64.dll"
            )
            STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api64.lib"
            )
            STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(
                _CWD, "libs", "steam_api64.lib"
            )
            COMPILE_CMD = STEAMWORKS_COMPILE_CMD_WIN64
            STEAMWORKSPY_BIN_PATH = os.path.join(
                STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_WIN64
            )
            STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, STEAMWORKSPY_BIN_WIN64)
        else:
            print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
            sys.exit()
    else:
        print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
        sys.exit()

    # Do stuff!
    print("Getting SteamworksPy requirements...")
    print(f"Entering directory {os.path.split(STEAMWORKS_PY_PATH)[0]}")
    os.chdir(os.path.split(STEAMWORKS_PY_PATH)[0])
    _execute(GET_REQ_CMD)
    print(f"Returning to cwd... {_CWD}")
    os.chdir(_CWD)

    print("Getting Steamworks SDK...")
    if os.path.exists(STEAMWORKS_SDK_PATH):
        print("Existing SDK found. Removing, and re-downloading fresh copy.")
        shutil.rmtree(STEAMWORKS_SDK_PATH)
    with ZipFile(BytesIO(handle_request(STEAMWORKS_SDK_URL).content)) as zipobj:
        zipobj.extractall(STEAMWORKS_PY_PATH)

    print("Getting Steam headers...")
    shutil.copytree(STEAMWORKS_SDK_HEADER_PATH, STEAMWORKS_SDK_HEADER_DEST_PATH)

    print("Getting Steam API lib file...")
    if os.path.exists(STEAMWORKS_SDK_APILIB_DEST_PATH):
        os.remove(STEAMWORKS_SDK_APILIB_DEST_PATH)
    shutil.copyfile(STEAMWORKS_SDK_APILIB_PATH, STEAMWORKS_SDK_APILIB_DEST_PATH)

    print(f"Getting libsteam_api for {_SYSTEM} {_ARCH}...")
    if os.path.exists(STEAMWORKS_SDK_LIBSTEAM_DEST_PATH):
        os.remove(STEAMWORKS_SDK_LIBSTEAM_DEST_PATH)
    shutil.copyfile(STEAMWORKS_SDK_LIBSTEAM_PATH, STEAMWORKS_SDK_LIBSTEAM_DEST_PATH)

    print(f"Building SteamworksPy for {_SYSTEM} {_ARCH}...")
    print(f"Entering directory {STEAMWORKS_PY_PATH}")
    os.chdir(STEAMWORKS_PY_PATH)
    # Compile SteamworksPy
    _execute(COMPILE_CMD)

    print(f"Returning to cwd... {_CWD}")
    os.chdir(_CWD)

    # APILIB
    print(
        f"Copying file {STEAMWORKS_SDK_APILIB_DEST_PATH} to: {STEAMWORKS_SDK_APILIB_FIN_PATH}"
    )
    shutil.copyfile(STEAMWORKS_SDK_APILIB_DEST_PATH, STEAMWORKS_SDK_APILIB_FIN_PATH)

    # LIBSTEAM
    print(
        f"Copying file {STEAMWORKS_SDK_LIBSTEAM_DEST_PATH} to: {STEAMWORKS_SDK_LIBSTEAM_FIN_PATH}"
    )
    shutil.copyfile(STEAMWORKS_SDK_LIBSTEAM_DEST_PATH, STEAMWORKS_SDK_LIBSTEAM_FIN_PATH)

    # STEAMWORKSPY
    print(f"Copying file {STEAMWORKSPY_BIN_PATH} to: {STEAMWORKSPY_BIN_FIN_PATH}")
    shutil.copyfile(STEAMWORKSPY_BIN_PATH, STEAMWORKSPY_BIN_FIN_PATH)
    if _SYSTEM == "Darwin":
        print(
            f"Copying file {STEAMWORKSPY_BIN_FIN_PATH} to: {STEAMWORKSPY_BIN_DARWIN_LINK_PATH}"
        )
        shutil.copyfile(STEAMWORKSPY_BIN_FIN_PATH, STEAMWORKSPY_BIN_DARWIN_LINK_PATH)
    elif _SYSTEM == "Linux":
        print(
            f"Copying file {STEAMWORKSPY_BIN_FIN_PATH} to: {STEAMWORKSPY_BIN_LINUX_LINK_PATH}"
        )
        shutil.copyfile(STEAMWORKSPY_BIN_FIN_PATH, STEAMWORKSPY_BIN_LINUX_LINK_PATH)


def copy_swp_libs() -> None:
    # Copy libs
    if _SYSTEM != "Windows":
        if _SYSTEM == "Darwin":
            STEAMWORKSPY_BUILT_LIB = os.path.join(
                _CWD, "libs", f"SteamworksPy_{_PROCESSOR}.dylib"
            )
            STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "libs", "SteamworksPy.dylib")
        elif _SYSTEM == "Linux":
            STEAMWORKSPY_BUILT_LIB = os.path.join(
                _CWD, "libs", f"SteamworksPy_{_PROCESSOR}.so"
            )
            STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "libs", "SteamworksPy.so")
        print("Copying libs for non-Windows platform")
        shutil.copyfile(STEAMWORKSPY_BUILT_LIB, STEAMWORKSPY_LIB_FIN)


def get_latest_todds_release() -> None:
    # Parse latest release
    headers = None
    if "GITHUB_TOKEN" in os.environ:
        headers = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}
    raw = handle_request(
        "https://api.github.com/repos/joseasoler/todds/releases/latest", headers=headers
    )

    json_response = raw.json()
    tag_name = json_response["tag_name"]
    todds_path = os.path.join(_CWD, "todds")
    todds_executable_name = "todds"
    print(f"Latest release: {tag_name}\n")
    # Setup environment
    if _SYSTEM == "Darwin":
        print(f"Darwin/MacOS system detected with a {_ARCH} {_PROCESSOR} CPU...")
        target_archive = f"todds_{_SYSTEM}_{_PROCESSOR}_{tag_name}.zip"
    elif _SYSTEM == "Linux":
        print(f"Linux system detected with a {_ARCH} {_PROCESSOR} CPU...")
        target_archive = f"todds_{_SYSTEM}_{_PROCESSOR}_{tag_name}.zip"
    elif _SYSTEM == "Windows":
        print(f"Windows system detected with a {_ARCH} {_PROCESSOR} CPU...")
        target_archive = f"todds_{_SYSTEM}_{tag_name}.zip"
        todds_executable_name = "todds.exe"
    else:
        print(f"Unsupported system {_SYSTEM} {_ARCH} {_PROCESSOR}")
        print(
            "Skipping todds download. The resultant RimSort build will not include todds!"
        )
        return
    # Try to find a valid release
    for asset in json_response["assets"]:
        if asset["name"] == target_archive:
            browser_download_url = asset["browser_download_url"]
    if "browser_download_url" not in locals():
        print(
            f"Failed to find valid joseasoler/todds release for {_SYSTEM} {_ARCH} {_PROCESSOR}"
        )
        return

    # Try to download & extract todds release from browser_download_url
    try:
        print(f"Downloading & extracting todds release from: {browser_download_url}")
        with ZipFile(BytesIO(handle_request(browser_download_url).content)) as zipobj:
            zipobj.extractall(todds_path)
        # Set executable permissions as ZipFile does not preserve this in the zip archive
        todds_executable_path = os.path.join(todds_path, todds_executable_name)
        if os.path.exists(todds_executable_path):
            original_stat = os.stat(todds_executable_path)
            os.chmod(todds_executable_path, original_stat.st_mode | S_IEXEC)
    except Exception as e:
        print(f"Failed to download: {browser_download_url}")
        print(
            "Did the file/url change?\nDoes your environment have access to the Internet?"
        )
        print(f"Error: {e}")


def freeze_application() -> None:
    # Nuitka
    print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")

    # Check if NUITKA_CACHE_DIR exists in environment
    if "NUITKA_CACHE_DIR" in os.environ:
        print(f"NUITKA_CACHE_DIR: {os.environ['NUITKA_CACHE_DIR']}")
    # Set the PYTHONPATH environment variable to include your submodules directory
    os.environ["PYTHONPATH"] = os.path.join(_CWD, "submodules", "SteamworksPy")

    _execute(_NUITKA_CMD, env=os.environ)


def _execute(cmd: list[str], env=None) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd, env=env)
    p.wait()
    if p.returncode != 0:
        print(f"Command failed: {cmd}")
        sys.exit(p.returncode)


def handle_request(url: str, headers: dict | None = None) -> requests.Response:
    raw = requests.get(url, headers=headers)
    if raw.status_code != 200:
        raise Exception(
            f"Failed to get latest release: {raw.status_code}" f"\nResponse: {raw.text}"
        )
    return raw


def make_args():
    # Create the parser
    parser = argparse.ArgumentParser(description="Distribute RimSort")

    # Skip dependencies
    parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip installing RimSort pip requirements",
    )

    parser.add_argument(
        "--skip-submodules",
        action="store_true",
        help="Skip installing RimSort submodules",
    )

    # Skip SteamworksPy Copy
    parser.add_argument(
        "--skip-steamworkspy",
        action="store_true",
        help="Skip copying SteamworksPy library",
    )

    # Skip SteamworksPy
    parser.add_argument(
        "--build-steamworkspy",
        action="store_true",
        help="Building SteamworksPy library instead of copying it",
    )

    # Skip todds
    parser.add_argument(
        "--skip-todds",
        action="store_true",
        help="Skip grabbing latest todds release",
    )

    # Don't build
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building RimSort application with Nuitka",
    )

    parser.add_argument(
        "--product-version",
        type=str,
        help="Product version to use for the build. Formatted as MAJOR.MINOR.PATCH.INCREMENT",
        required=False
    )

    return parser


def main():
    # Parse arguments
    parser = make_args()
    args = parser.parse_args()

    # RimSort dependencies
    if not args.skip_pip:
        print("Getting RimSort python requirements...")
        get_rimsort_pip(args.skip_build)
    else:
        print("Skipping getting python pip requirements...")

    if not args.skip_submodules:
        print("Getting RimSort submodules...")
        get_rimsort_submodules()
    else:
        print("Skipping getting submodules...")

    if args.build_steamworkspy:
        print("Building SteamworksPy library. Skipping copy...")
        build_steamworkspy()
    elif not args.skip_steamworkspy:
        print("Copying SteamworksPy library...")
        copy_swp_libs()

    # Grab latest todds release
    if not args.skip_todds:
        print("Grabbing latest todds release...")
        get_latest_todds_release()
    else:
        print("Skipping todds release...")

    # Build Nuitka distributable binary
    if not args.skip_build:
        if args.product_version:
            _NUITKA_CMD.extend(["--product-version", args.product_version])

        print("Building RimSort application with Nuitka...")
        freeze_application()
    else:
        print("Skipping distribute.py build...")


if __name__ == "__main__":
    """
    Do stuff!
    """
    main()
