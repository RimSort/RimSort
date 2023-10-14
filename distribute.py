#!/usr/bin/env python3

from io import BytesIO
import os
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
# _ICON_EXT = "icns" if _SYSTEM == "Darwin" else "png"
_UPDATE_SCRIPT_EXT = "bat" if _SYSTEM == "Windows" else "sh"
_LIB_EXT = "dylib" if _SYSTEM == "Darwin" else "so" if _SYSTEM == "Linux" else "dll"
_STEAMWORKSPY_MAPPING = "SteamworksPy64.dll=SteamworksPy64.dll" if _SYSTEM == "Windows" else f"SteamworksPy_{_PROCESSOR}.{_LIB_EXT}=SteamworksPy.{_LIB_EXT}"
_LIBSTEAM_API_FILENAME = "steam_api64.dll" if _SYSTEM == "Windows" else f"libsteam_api.{_LIB_EXT}"
_COMMON_NUITKA_CMD = [
    PY_CMD,
    "-m",
    "nuitka",
    "--assume-yes-for-downloads",
    "--standalone",
    # "--onefile",
    "--enable-plugin=pyside6",
    "--include-data-dir=./data/=data",
    "--include-data-file=./steam_appid.txt=steam_appid.txt",
    "RimSort.py",
    "--output-dir=./dist/",
    f"--include-data-file=./update.{_UPDATE_SCRIPT_EXT}=update.{_UPDATE_SCRIPT_EXT}",
    f"--include-data-file=./{_STEAMWORKSPY_MAPPING}",
    f"--include-data-file=./{_LIBSTEAM_API_FILENAME}={_LIBSTEAM_API_FILENAME}",
]
if _SYSTEM == "Darwin" and _PROCESSOR == "arm":
    _NUITKA_CMD = _COMMON_NUITKA_CMD + [
        "--macos-create-app-bundle",
        "--macos-app-icon=./data/AppIcon_a.icns",
    ]
elif _SYSTEM == "Darwin" and _PROCESSOR == "i386":
    _NUITKA_CMD = _COMMON_NUITKA_CMD + [
        "--macos-create-app-bundle",
        "--macos-app-icon=./data/AppIcon_a.icns",
        "--include-data-dir=./todds/=todds",
    ]
elif _SYSTEM == "Linux":
    _NUITKA_CMD = _COMMON_NUITKA_CMD + [
        "--linux-icon=./data/AppIcon_a.png",
        "--include-data-dir=./todds/=todds",
    ]
elif _SYSTEM == "Windows" and _ARCH == "64bit":
    _NUITKA_CMD = _COMMON_NUITKA_CMD + [
        "--disable-console",
        "--windows-icon-from-ico=./data/AppIcon_a.png",
        "--include-data-dir=./todds/=todds",
    ]
else:
    print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
    print("Exiting...")
GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
STEAMFILES_SRC = os.path.join(_CWD, "steamfiles")
STEAMWORKSPY_BUILD_CMD = [PY_CMD, "build_steamworkspy.py"]
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def get_rimsort_deps() -> None:
    print("Installing core RimSort requirements with pip...")
    _execute(GET_REQ_CMD)
    print("Ensuring we have all submodules initiated & up-to-date...")
    _execute(SUBMODULE_UPDATE_INIT_CMD)
    # Get Steamfiles requirements
    print("Building submodules...")
    print(f"Changing directory to {STEAMFILES_SRC}")
    os.chdir(STEAMFILES_SRC)
    print("Building steamfiles module...")
    _execute(GET_REQ_CMD)
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
    STEAMWORKS_PY_PATH = os.path.join(_CWD, "SteamworksPy", "library")
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
    STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(_CWD, "steam_api.lib")

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
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(_CWD, "libsteam_api.dylib")
        COMPILE_CMD = DARWIN_COMPILE_CMD
        STEAMWORKSPY_BIN_PATH = os.path.join(
            STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_DARWIN
        )
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, STEAMWORKSPY_BIN_DARWIN)
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
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(_CWD, "libsteam_api.so")
        COMPILE_CMD = LINUX_COMPILE_CMD
        STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_LINUX)
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, STEAMWORKSPY_BIN_LINUX)
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
            STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(_CWD, "steam_api.dll")
            STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api.lib"
            )
            STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(_CWD, "steam_api.lib")
            COMPILE_CMD = STEAMWORKS_COMPILE_CMD_WIN32
            STEAMWORKSPY_BIN_PATH = os.path.join(
                STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_WIN32
            )
            STEAMWORKSPY_BIN_FIN_PATH = os.path.join(_CWD, STEAMWORKSPY_BIN_WIN32)
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
            STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(_CWD, "steam_api64.dll")
            STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
                STEAMWORKS_PY_PATH, "steam_api64.lib"
            )
            STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(_CWD, "steam_api64.lib")
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
    with ZipFile(BytesIO(requests.get(STEAMWORKS_SDK_URL).content)) as zipobj:
        zipobj.extractall(STEAMWORKS_PY_PATH)

    print(f"Getting Steam headers...")
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
                _CWD, f"SteamworksPy_{_PROCESSOR}.dylib"
            )
            STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "SteamworksPy.dylib")
        elif _SYSTEM == "Linux":
            STEAMWORKSPY_BUILT_LIB = os.path.join(_CWD, f"SteamworksPy_{_PROCESSOR}.so")
            STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "SteamworksPy.so")
        print("Copying libs for non-Windows platform")
        shutil.copyfile(STEAMWORKSPY_BUILT_LIB, STEAMWORKSPY_LIB_FIN)

    # Symlink built module
    print("Creating symlink to built module...")
    MODULE_SRC_PATH = os.path.join(_CWD, "SteamworksPy", "steamworks")
    MODULE_DEST_PATH = os.path.join(_CWD, "steamworks")
    try:
        if _SYSTEM != "Windows":
            os.symlink(
                MODULE_SRC_PATH,
                MODULE_DEST_PATH,
                target_is_directory=True,
            )
            print(f"Symlink created: [{MODULE_SRC_PATH}] -> {MODULE_DEST_PATH}")
        else:
            from _winapi import CreateJunction

            CreateJunction(MODULE_SRC_PATH, MODULE_DEST_PATH)
            print(f"Symlink created: [{MODULE_SRC_PATH}] -> {MODULE_DEST_PATH}")
    except FileExistsError:
        print(
            f"Unable to create symlink from source: {MODULE_SRC_PATH} to destination: {MODULE_DEST_PATH}"
        )
        print(
            "Destination already exists, or you don't have permission."
            + " You can safely ignore this as long as you are able to run RimSort after completing runtime setup."
        )


def get_latest_todds_release() -> None:
    # Parse latest release
    headers = None
    if "GITHUB_TOKEN" in os.environ:
        headers = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}
    raw = requests.get(
        "https://api.github.com/repos/joseasoler/todds/releases/latest", headers=headers
    )
    json_response = raw.json()
    tag_name = json_response["tag_name"]
    todds_path = os.path.join(_CWD, "todds")
    todds_executable_name = "todds"
    print(f"Latest release: {tag_name}\n")
    # Setup environment
    if _SYSTEM == "Darwin":
        if _PROCESSOR == "i386":
            print(f"Darwin/MacOS system detected with a {_ARCH} {_PROCESSOR} CPU...")
            target_archive = f"todds_{_SYSTEM}_{_PROCESSOR}_{tag_name}.zip"
        if _PROCESSOR == "arm":
            print(f"Darwin/MacOS system currently unsupported by todds.")
            print(
                "Skipping todds download. The resultant RimSort build will not include todds!"
            )
            return
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
    if not "browser_download_url" in locals():
        print(
            f"Failed to find valid joseasoler/todds release for {_SYSTEM} {_ARCH} {_PROCESSOR}"
        )
        return
    # Try to download & extract todds release from browser_download_url
    target_archive_extracted = target_archive.replace(".zip", "")
    try:
        print(f"Downloading & extracting todds release from: {browser_download_url}")
        with ZipFile(BytesIO(requests.get(browser_download_url).content)) as zipobj:
            zipobj.extractall(todds_path)
        # Set executable permissions as ZipFile does not preserve this in the zip archive
        todds_executable_path = os.path.join(todds_path, todds_executable_name)
        if os.path.exists(todds_executable_path):
            original_stat = os.stat(todds_executable_path)
            os.chmod(todds_executable_path, original_stat.st_mode | S_IEXEC)
    except:
        print(f"Failed to download: {browser_download_url}")
        print(
            "Did the file/url change?\nDoes your environment have access to the Internet?"
        )


def freeze_application() -> None:
    # Nuitka
    print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")
    _execute(_NUITKA_CMD)


def _execute(cmd: list[str]) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()


if __name__ == "__main__":
    """
    Do stuff!
    """

    # RimSort dependencies
    print("Getting RimSort dependencies...")
    get_rimsort_deps()

    # Build SteamworksPy
    # print("Building SteamworksPy library...")
    # build_steamworkspy()

    # Copy SteamworksPy prebuilt libs
    print("Copying SteamworksPy libs for release...")
    copy_swp_libs()

    # Grab latest todds release
    print("Grabbing latest todds release...")
    get_latest_todds_release()

    # Build Nuitka distributable binary
    print("Building RimSort application with Nuitka...")
    _execute(_NUITKA_CMD)
