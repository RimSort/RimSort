#!/usr/bin/env python3

import os
import platform
import shutil
import subprocess

_ARCH = platform.architecture()[0]
_CWD = os.getcwd()
_PROCESSOR = platform.processor()
_SYSTEM = platform.system()
if _SYSTEM == "Windows":
    PY_CMD = "py"
    _PYINSTALLER_SPEC_PATH = f"pyinstaller_{_SYSTEM}_{_ARCH}.spec"
else:
    PY_CMD = "python3"
    _PYINSTALLER_SPEC_PATH = f"pyinstaller_{_SYSTEM}.spec"

GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
GET_REQ_DARWIN_ARM_CMD = [
    PY_CMD,
    "-m",
    "pip",
    "install",
    "-r",
    "requirements_darwin_arm64.txt",
]
STEAMFILES_BUILD_CMD = [PY_CMD, "build_steamfiles.py"]
STEAMWORKSPY_BUILD_CMD = [PY_CMD, "build_steamworkspy.py"]
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def _execute(cmd: list) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()


print("Installing requirements")
if _SYSTEM == "Darwin" and _PROCESSOR == "arm":
    _execute(GET_REQ_DARWIN_ARM_CMD)
else:
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
if _SYSTEM != "Linux":
    _PYINSTALLER_CMD = [PY_CMD, "-m", "PyInstaller", _PYINSTALLER_SPEC_PATH]
else:
    _PYINSTALLER_CMD = ["pyinstaller", _PYINSTALLER_SPEC_PATH]

print(f"Creating binary for {_ARCH} {_SYSTEM} {_PROCESSOR} in dist/")
_execute(_PYINSTALLER_CMD)
