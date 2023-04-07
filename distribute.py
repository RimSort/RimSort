#!/usr/bin/env python3

import os
import platform
import shutil
import subprocess

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
    print(
        f"Attempting to build on unsupported platform: {_SYSTEM} {_ARCH} with {_PROCESSOR}"
    )
    print("Exiting...")
GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
STEAMFILES_BUILD_CMD = [PY_CMD, "build_steamfiles.py"]
STEAMWORKSPY_BUILD_CMD = [PY_CMD, "build_steamworkspy.py"]
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def _execute(cmd: list) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()


print("Installing requirements")
_execute(GET_REQ_CMD)

print("Ensuring we have all submodules initiated & up-to-date...")
_execute(SUBMODULE_UPDATE_INIT_CMD)

print("Building submodules...")
print("Building steamfiles python module")
_execute(STEAMFILES_BUILD_CMD)
print("Building SteamworksPy library & symlinking python module...")
_execute(STEAMWORKSPY_BUILD_CMD)

if _SYSTEM != "Windows":
    if _SYSTEM == "Darwin":
        STEAMWORKSPY_BUILT_LIB = os.path.join(_CWD, f"SteamworksPy_{_PROCESSOR}.dylib")
        STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "SteamworksPy.dylib")
    elif _SYSTEM == "Linux":
        STEAMWORKSPY_BUILT_LIB = os.path.join(_CWD, f"SteamworksPy_{_PROCESSOR}.so")
        STEAMWORKSPY_LIB_FIN = os.path.join(_CWD, "SteamworksPy.so")
    print("Copying libs for non-Windows platform")
    shutil.copyfile(STEAMWORKSPY_BUILT_LIB, STEAMWORKSPY_LIB_FIN)

# Nuitka
_execute(_NUITKA_CMD)

# PyInstaller
# if _SYSTEM != "Linux":
#     _PYINSTALLER_CMD = [PY_CMD, "-m", "PyInstaller", _PYINSTALLER_SPEC_PATH]
# else:
#     _PYINSTALLER_CMD = ["pyinstaller", _PYINSTALLER_SPEC_PATH]

# print(f"Creating binary for {_ARCH} {_SYSTEM} {_PROCESSOR} in dist/")
# _execute(_PYINSTALLER_CMD)
