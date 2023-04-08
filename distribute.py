#!/usr/bin/env python3

from io import BytesIO
import os
import platform
import requests
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

"""
Setup environment
"""

_ARCH = platform.architecture()[0]
_CWD = os.getcwd()
_PROCESSOR = platform.processor()
_SYSTEM = platform.system()

PY_CMD = "python3"
_PYINSTALLER_SPEC_PATH = f"pyinstaller_{_SYSTEM}.spec"
if _SYSTEM == "Darwin":
    _NUITKA_CMD = [
        PY_CMD,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--macos-create-app-bundle",
        "--macos-app-icon=./data/AppIcon_a.icns",
        "--enable-plugin=pyside6",
        "--include-data-dir=./data/=data",
        f"--include-data-file=./SteamworksPy_{_PROCESSOR}.dylib=SteamworksPy.dylib",
        "--include-data-file=./libsteam_api.dylib=libsteam_api.dylib",
        "--include-data-file=./steam_appid.txt=steam_appid.txt",
        "RimSort.py",
        "--output-dir=./dist/",
    ]
elif _SYSTEM == "Linux":
    _NUITKA_CMD = [
        PY_CMD,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--enable-plugin=pyside6",
        "--include-data-dir=./data/=data",
        f"--include-data-file=./SteamworksPy_{_PROCESSOR}.so=SteamworksPy.so",
        "--include-data-file=./libsteam_api.so=libsteam_api.so",
        "--include-data-file=./steam_appid.txt=steam_appid.txt",
        "RimSort.py",
        "--output-dir=./dist/",
    ]
elif _SYSTEM == "Windows" and _ARCH == "64bit":
    PY_CMD = "py"
    _NUITKA_CMD = [
        PY_CMD,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--windows-icon-from-ico=./data/AppIcon_a.png",
        "--enable-plugin=pyside6",
        "--include-data-dir=./data/=data",
        "--include-data-file=./SteamworksPy64.dll=SteamworksPy64.dll",
        "--include-data-file=./steam_api64.dll=steam_api64.dll",
        "--include-data-file=./steam_appid.txt=steam_appid.txt",
        "RimSort.py",
        "--output-dir=./dist",
    ]
    _PYINSTALLER_SPEC_PATH = f"pyinstaller_{_SYSTEM}_{_ARCH}.spec"
else:
    print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
    print("Exiting...")
GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
STEAMFILES_SRC = os.path.join(_CWD, "steamfiles")
STEAMWORKSPY_BUILD_CMD = [PY_CMD, "build_steamworkspy.py"]
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def build_steamworkspy() -> None:
    # Setup environment

    print("Setting up environment...")
    MODULE_SRC_PATH = os.path.join(_CWD, "SteamworksPy", "steamworks")
    MODULE_DEST_PATH = os.path.join(_CWD, "steamworks")
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
    STEAMWORKS_SDK_URL = "https://github.com/oceancabbage/RimSort/raw/steamworks-sdk/steamworks_sdk_155.zip"  # "https://partner.steamgames.com/downloads/steamworks_sdk_155.zip"
    SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]
    STEAMWORKS_PY_PATH = os.path.join(_CWD, "SteamworksPy", "library")
    STEAMWORKS_MODULE_PATH = os.path.join(_CWD, "SteamworksPy", "steamworks")
    STEAMWORKS_MODULE_FIN = os.path.join(_CWD, "steamworks")
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


def freeze_application() -> None:
    # Nuitka
    print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")
    _execute(_NUITKA_CMD)

    # PyInstaller
    # if _SYSTEM != "Linux":
    #     _PYINSTALLER_CMD = [PY_CMD, "-m", "PyInstaller", _PYINSTALLER_SPEC_PATH]
    # else:
    #     _PYINSTALLER_CMD = ["pyinstaller", _PYINSTALLER_SPEC_PATH]

    # print(f"Creating binary for {_ARCH} {_SYSTEM} {_PROCESSOR} in dist/")
    # _execute(_PYINSTALLER_CMD)


def _execute(cmd: list[str]) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()


"""
Do stuff!
"""

# RimSort dependencies
print("Installing core RimSort requirements")
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

# Build SteamworksPy
print("Building SteamworksPy library...")
build_steamworkspy()
# Copy libs
if _SYSTEM != "Windows":
    if _SYSTEM == "Darwin":
        STEAMWORKSPY_BUILT_LIB = os.path.join(_CWD, f"SteamworksPy_{_PROCESSOR}.dylib")
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
    os.symlink(
        MODULE_SRC_PATH,
        MODULE_DEST_PATH,
        target_is_directory=True,
    )
except FileExistsError:
    print(
        f"Unable to create symlink from source: {MODULE_SRC_PATH} to destination: {MODULE_DEST_PATH}"
    )
    print(
        "Destination already exists, or you don't have permission. You can safely ignore this as long as you are able to run RimSort after completing runtime setup."
    )

# Build Nuitka distributable binary
_execute(_NUITKA_CMD)
