#!/usr/bin/env python3
"""
This script is used to set up the environment and build the RimSort application.
It installs the required dependencies, initializes and updates submodules, and builds the rimsort_steam library.
The script supports different operating systems and architectures.

For arguments and usage, run the script with the --help flag.

Not meant to be imported as a module.
"""

import argparse
import glob
import os
import platform
import shutil
import subprocess
import sys
from io import BytesIO
from stat import S_IEXEC
from zipfile import ZipFile

import requests

"""
Setup environment
"""

_ARCH = platform.architecture()[0]
_CWD = os.getcwd()
_SYSTEM = platform.system()
_MACHINE = platform.machine() or platform.processor()
# Normalize to match pre-built binary and todds asset naming on macOS
if _SYSTEM == "Darwin":
    _PROCESSOR = {"arm64": "arm", "x86_64": "i386"}.get(_MACHINE, _MACHINE)
else:
    _PROCESSOR = _MACHINE

PY_CMD = sys.executable

_NUITKA_CMD = [
    PY_CMD,
    "-m",
    "nuitka",
    "app/",
    "--python-flag=-m",
    f"--include-data-dir={glob.glob('.venv/**/qtwebengine_locales', recursive=True)[0]}=qtwebengine_locales",
]

if _SYSTEM == "Darwin" and _PROCESSOR in ["i386", "arm"]:
    pass
elif _SYSTEM == "Linux":
    pass
elif _SYSTEM == "Windows" and _ARCH == "64bit":
    pass
else:
    print(f"Unsupported SYSTEM: {_SYSTEM} {_ARCH} with {_PROCESSOR}")
    print("Exiting...")

SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def get_rimsort_submodules() -> None:
    print("Ensuring we have all submodules initiated & up-to-date...")
    _execute(SUBMODULE_UPDATE_INIT_CMD)


def setup_uv() -> None:
    if shutil.which("uv"):
        print("uv already installed")
        return
    else:
        print("Installing uv to pip...")
        _execute([PY_CMD, "-m", "pip", "install", "uv"])


def build_rimsort_steam() -> None:
    """Build the rimsort_steam native library from source.

    Requires STEAMWORKS_SDK_PATH environment variable to be set.
    """
    sdk_path = os.environ.get("STEAMWORKS_SDK_PATH")
    if not sdk_path:
        print("STEAMWORKS_SDK_PATH not set -- skipping rimsort_steam build")
        print("Pre-built binaries in libs/ will be used if available.")
        return

    src_dir = os.path.join(_CWD, "libs", "rimsort_steam")
    if not os.path.exists(os.path.join(src_dir, "rimsort_steam.cpp")):
        print(f"rimsort_steam.cpp not found in {src_dir} -- skipping build")
        return

    print(f"Building rimsort_steam for {_SYSTEM}...")
    if _SYSTEM == "Windows":
        build_script = os.path.join(src_dir, "build_windows.bat")
        _execute(["cmd.exe", "/c", build_script], env=os.environ)
        output_name = "rimsort_steam.dll"
    else:
        _execute(["make", "-C", src_dir, f"STEAMWORKS_SDK_PATH={sdk_path}"])
        output_name = (
            "rimsort_steam.dylib" if _SYSTEM == "Darwin" else "rimsort_steam.so"
        )

    # Copy built library to libs/
    src = os.path.join(src_dir, output_name)
    dest = os.path.join(_CWD, "libs", output_name)
    if os.path.exists(src):
        shutil.copyfile(src, dest)
        print(f"Copied {output_name} to libs/")
    else:
        print(f"Warning: Expected output {src} not found after build")


def get_latest_todds_release() -> None:
    # Parse latest release
    headers = None
    browser_download_url = ""
    # If GITHUB_TOKEN is set, use it to authenticate the request
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
    """Build the RimSort application using Nuitka."""
    # Check if NUITKA_CACHE_DIR exists in environment
    if "NUITKA_CACHE_DIR" in os.environ:
        print(f"NUITKA_CACHE_DIR: {os.environ['NUITKA_CACHE_DIR']}")
    _execute(_NUITKA_CMD, env=os.environ)


def _find_macos_bundles(cwd: str) -> list[str]:
    bundles: list[str] = []
    for root, dirs, _ in os.walk(cwd):
        for d in dirs:
            if d.endswith(".app"):
                bundles.append(os.path.join(root, d))
    return bundles


def post_build_fixup_rimsort_steam() -> None:
    """Verify rimsort_steam.dylib exists in .app bundle after build on macOS."""
    if _SYSTEM != "Darwin":
        return
    try:
        bundles = _find_macos_bundles(_CWD)
        if not bundles:
            print("No .app bundle found -- skipping rimsort_steam fixup")
            return
        for bundle in bundles:
            macos_dir = os.path.join(bundle, "Contents", "MacOS")
            if not os.path.isdir(macos_dir):
                continue
            lib_path = os.path.join(macos_dir, "rimsort_steam.dylib")
            if os.path.exists(lib_path):
                print(f"  rimsort_steam.dylib found in bundle: {bundle}")
            else:
                print(f"  WARNING: rimsort_steam.dylib NOT found in bundle: {bundle}")
    except Exception as e:
        print(f"Warning: post_build_fixup_rimsort_steam failed: {e}")


def post_build_optimize_macos_bundle() -> None:
    """Thin fat binaries in macOS .app bundle to reduce size."""
    if _SYSTEM != "Darwin":
        return
    try:
        build_dir = os.path.join(_CWD, "build")
        bundles = _find_macos_bundles(build_dir)
        if not bundles:
            print("No .app bundle found in build/ — skipping bundle optimization")
            return
        for bundle in bundles:
            print(f"Optimizing macOS bundle: {bundle}")
            _execute(
                [
                    PY_CMD,
                    os.path.join(_CWD, "packaging", "optimize_macos_bundle.py"),
                    bundle,
                ]
            )
    except Exception as e:
        print(f"Warning: post_build_optimize_macos_bundle failed: {e}")


def _execute(cmd: list[str], env: os._Environ[str] | None = None) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd, env=env)
    p.wait()
    if p.returncode != 0:
        print(f"Command failed: {cmd}")
        sys.exit(p.returncode)


def handle_request(
    url: str, headers: dict[str, str] | None = None
) -> requests.Response:
    raw = requests.get(url, headers=headers, timeout=15)
    if raw.status_code != 200:
        raise Exception(
            f"Failed to get latest release: {raw.status_code}\nResponse: {raw.text}"
        )
    return raw


def make_args() -> argparse.ArgumentParser:
    """
    Create and configure the argument parser for the RimSort application setup script.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    description = """This script is used to set up the environment and build the RimSort application.
    It installs the required dependencies, initializes and updates submodules, and builds the rimsort_steam library.
    The script supports different operating systems and architectures."""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-d",
        "--dev",
        action="store_true",
        help="enables dev mode, installing dev requirements and enables application console if applicable",
    )

    parser.add_argument(
        "--skip-submodules",
        action="store_true",
        help="skip installing RimSort submodules using git",
    )

    parser.add_argument(
        "--build-rimsort-steam",
        action="store_true",
        help="Build rimsort_steam native library from source (requires STEAMWORKS_SDK_PATH)",
    )

    # Skip todds
    parser.add_argument(
        "--skip-todds",
        action="store_true",
        help="skip grabbing latest todds release",
    )

    # Don't build
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="skip building RimSort with Nuitka",
    )

    parser.add_argument(
        "--product-version",
        type=str,
        help="product version to use for the build formatted as MAJOR.MINOR.PATCH.INCREMENT",
        required=False,
    )

    return parser


def main() -> None:
    # Parse arguments
    parser = make_args()
    args = parser.parse_args()

    print(f"Running on {_SYSTEM} {_ARCH} {_PROCESSOR}...")
    if not args.skip_submodules:
        print("Getting RimSort submodules...")
        get_rimsort_submodules()
    else:
        print("Skipped getting submodules")

    if args.build_rimsort_steam:
        print("Building rimsort_steam library...")
        build_rimsort_steam()
    else:
        print("Skipping rimsort_steam build (using pre-built binaries from libs/)")

    # Grab latest todds release
    if not args.skip_todds:
        print("Grabbing latest todds release...")
        get_latest_todds_release()
    else:
        print("Skipped todds release")

    # Build Nuitka distributable binary
    if not args.skip_build:
        if args.product_version:
            version = "".join(args.product_version.split())
            _NUITKA_CMD.extend(
                [
                    "--file-description=RimSort",
                    f"--product-version={version}",
                ]
            )
        if args.dev:
            print("In dev mode, enabling console in build")
            _NUITKA_CMD.append("--windows-console-mode=force")

        print("Building RimSort application with Nuitka...")
        freeze_application()
        # After build, ensure the app bundle contains the generic Steamworks dylib
        post_build_fixup_rimsort_steam()
        post_build_optimize_macos_bundle()
    else:
        print("Skipped distribute.py build")


if __name__ == "__main__":
    """
    Do stuff!
    """
    main()
