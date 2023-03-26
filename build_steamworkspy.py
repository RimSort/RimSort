#!/usr/bin/env python3

"""
Platform-agnostic SteamworksPy setup script

Reference: 
https://github.com/philippj/SteamworksPy
https://philippj.github.io/SteamworksPy/
"""

from io import BytesIO
import os
import platform
import requests
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile


def _execute(cmd: list) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()


"""
Setup environment
"""

print("Setting up environment...")
ARCH = platform.architecture()[0]
CWD = os.getcwd()
MODULE_SRC_PATH = os.path.join(CWD, "SteamworksPy", "steamworks")
MODULE_DEST_PATH = os.path.join(CWD, "steamworks")
PROCESSOR = platform.processor()
STEAMWORKSPY_BIN_DARWIN = f"SteamworksPy_{PROCESSOR}.dylib"
STEAMWORKSPY_BIN_DARWIN_LINK_PATH = os.path.join(CWD, "SteamworksPy.dylib")
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
STEAMWORKSPY_BIN_LINUX = f"SteamworksPy_{PROCESSOR}.so"
STEAMWORKSPY_BIN_LINUX_LINK_PATH = os.path.join(CWD, "SteamworksPy.so")
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
    "cmd.exe", "/k", 'C:\\"Program Files (x86)"\\"Microsoft Visual Studio"\\2022\\BuildTools\\VC\\Auxiliary\\Build\\vcvars64.bat', "&",
    "cl",
    "/D_USRDLL",
    "/D_WINDLL",
    "SteamworksPy.cpp",
    "steam_api.lib",
    "/link",
    "/DLL",
    f"/OUT:{STEAMWORKSPY_BIN_WIN32}",
    "&", "exit"
]
STEAMWORKSPY_BIN_WIN64 = "SteamworksPy64.dll"
STEAMWORKS_COMPILE_CMD_WIN64 = [
    "cmd.exe", "/k", 'C:\\"Program Files (x86)"\\"Microsoft Visual Studio"\\2022\\BuildTools\\VC\\Auxiliary\\Build\\vcvars64.bat', "&",
    "cl",
    "/D_USRDLL",
    "/D_WINDLL",
    "SteamworksPy.cpp",
    "steam_api64.lib",
    "/link",
    "/DLL",
    f"/OUT:{STEAMWORKSPY_BIN_WIN64}",
    "&", "exit"
]
STEAMWORKS_SDK_URL = "https://github.com/oceancabbage/RimSort/raw/steamworks-sdk/steamworks_sdk_155.zip"  # "https://partner.steamgames.com/downloads/steamworks_sdk_155.zip"
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]
STEAMWORKS_PY_PATH = os.path.join(CWD, "SteamworksPy", "library")
STEAMWORKS_MODULE_PATH = os.path.join(CWD, "SteamworksPy", "steamworks")
STEAMWORKS_MODULE_FIN = os.path.join(CWD, "steamworks")
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
STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(CWD, "steam_api.lib")
SYSTEM = platform.system()

print(f"Running on {SYSTEM} {ARCH}...")

if SYSTEM == "Darwin":
    if ARCH == "64bit":
        STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "osx", "libsteam_api.dylib"
        )
    else:
        print(f"Unsupported ARCH: {ARCH}")
        sys.exit()
    STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
        STEAMWORKS_PY_PATH, "libsteam_api.dylib"
    )
    STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(CWD, "libsteam_api.dylib")
    COMPILE_CMD = DARWIN_COMPILE_CMD
    STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_DARWIN)
    STEAMWORKSPY_BIN_FIN_PATH = os.path.join(CWD, STEAMWORKSPY_BIN_DARWIN)
elif SYSTEM == "Linux":
    if ARCH == "32bit":
        STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "linux32", "libsteam_api.so"
        )

    elif ARCH == "64bit":
        STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "linux64", "libsteam_api.so"
        )
    else:
        print(f"Unsupported ARCH: {ARCH}")
        sys.exit()
    STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
        STEAMWORKS_PY_PATH, "libsteam_api.so"
    )
    STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(CWD, "libsteam_api.so")
    COMPILE_CMD = LINUX_COMPILE_CMD
    STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_LINUX)
    STEAMWORKSPY_BIN_FIN_PATH = os.path.join(CWD, STEAMWORKSPY_BIN_LINUX)
elif SYSTEM == "Windows":
    if ARCH == "32bit":
        STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "steam_api.dll"
        )
        STEAMWORKS_SDK_APILIB_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "steam_api.lib"
        )
        STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "steam_api.dll"
        )
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(CWD, "steam_api.dll")
        STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "steam_api.lib"
        )
        STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(CWD, "steam_api.lib")
        COMPILE_CMD = STEAMWORKS_COMPILE_CMD_WIN32
        STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_WIN32)
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(CWD, STEAMWORKSPY_BIN_WIN32)
    elif ARCH == "64bit":
        STEAMWORKS_SDK_LIBSTEAM_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "win64", "steam_api64.dll"
        )
        STEAMWORKS_SDK_APILIB_PATH = os.path.join(
            STEAMWORKS_SDK_REDIST_BIN_PATH, "win64", "steam_api64.lib"
        )
        STEAMWORKS_SDK_LIBSTEAM_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "steam_api64.dll"
        )
        STEAMWORKS_SDK_LIBSTEAM_FIN_PATH = os.path.join(CWD, "steam_api64.dll")
        STEAMWORKS_SDK_APILIB_DEST_PATH = os.path.join(
            STEAMWORKS_PY_PATH, "steam_api64.lib"
        )
        STEAMWORKS_SDK_APILIB_FIN_PATH = os.path.join(CWD, "steam_api64.lib")
        COMPILE_CMD = STEAMWORKS_COMPILE_CMD_WIN64
        STEAMWORKSPY_BIN_PATH = os.path.join(STEAMWORKS_PY_PATH, STEAMWORKSPY_BIN_WIN64)
        STEAMWORKSPY_BIN_FIN_PATH = os.path.join(CWD, STEAMWORKSPY_BIN_WIN64)
    else:
        print(f"Unsupported SYSTEM: {SYSTEM} {ARCH}")
        sys.exit()
else:
    print(f"Unsupported SYSTEM: {SYSTEM} {ARCH}")
    sys.exit()

"""
Do stuff!
"""

print("Ensuring we have SteamworksPy submodule initiated & up-to-date...")
_execute(SUBMODULE_UPDATE_INIT_CMD)

print("Getting Steamworks SDK...")
if not os.path.exists(STEAMWORKS_SDK_PATH):
    with ZipFile(BytesIO(requests.get(STEAMWORKS_SDK_URL).content)) as zipobj:
        zipobj.extractall(STEAMWORKS_PY_PATH)

print(f"Getting Steam headers...")
if os.path.exists(STEAMWORKS_SDK_HEADER_DEST_PATH):
    shutil.rmtree(STEAMWORKS_SDK_HEADER_DEST_PATH)
shutil.copytree(STEAMWORKS_SDK_HEADER_PATH, STEAMWORKS_SDK_HEADER_DEST_PATH)

print("Getting Steam API lib file...")
if os.path.exists(STEAMWORKS_SDK_APILIB_DEST_PATH):
    os.remove(STEAMWORKS_SDK_APILIB_DEST_PATH)
shutil.copyfile(STEAMWORKS_SDK_APILIB_PATH, STEAMWORKS_SDK_APILIB_DEST_PATH)

print(f"Getting libsteam_api for {SYSTEM} {ARCH}...")
if os.path.exists(STEAMWORKS_SDK_LIBSTEAM_DEST_PATH):
    os.remove(STEAMWORKS_SDK_LIBSTEAM_DEST_PATH)
shutil.copyfile(STEAMWORKS_SDK_LIBSTEAM_PATH, STEAMWORKS_SDK_LIBSTEAM_DEST_PATH)

print(f"Building SteamworksPy for {SYSTEM} {ARCH}...")
print(f"Entering directory {STEAMWORKS_PY_PATH}")
os.chdir(STEAMWORKS_PY_PATH)
_execute(COMPILE_CMD)

print(f"Returning to cwd... {CWD}")
os.chdir(CWD)

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
if SYSTEM == "Darwin":
    print(f"Copying file {STEAMWORKSPY_BIN_FIN_PATH} to: {STEAMWORKSPY_BIN_DARWIN_LINK_PATH}")
    shutil.copyfile(STEAMWORKSPY_BIN_FIN_PATH, STEAMWORKSPY_BIN_DARWIN_LINK_PATH)
elif SYSTEM == "Linux":
    print(f"Copying file {STEAMWORKSPY_BIN_FIN_PATH} to: {STEAMWORKSPY_BIN_LINUX_LINK_PATH}")
    shutil.copyfile(STEAMWORKSPY_BIN_FIN_PATH, STEAMWORKSPY_BIN_LINUX_LINK_PATH)

print("Creating symlink to built module...")
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
print("Done! Exiting...")
