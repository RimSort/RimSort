#!/usr/bin/env python3
"""
Post-build optimization for macOS .app bundles.

Thins universal (fat) Mach-O binaries in Contents/Resources/ to the
target architecture, reducing bundle size by ~267 MB. Re-signs the
bundle after modification.

Usage:
    python scripts/optimize_macos_bundle.py <path-to.app> [--arch arm64|x86_64]
"""

import argparse
import os
import platform
import subprocess
import sys


def _get_native_arch() -> str:
    machine = platform.machine()
    if machine == "arm64":
        return "arm64"
    elif machine in ("x86_64", "i386", "AMD64"):
        return "x86_64"
    else:
        print(f"Warning: unrecognized machine type '{machine}', defaulting to arm64")
        return "arm64"


def _is_fat_binary(path: str) -> bool:
    try:
        result = subprocess.run(
            ["lipo", "-info", path],
            capture_output=True,
            text=True,
        )
        return "Architectures in the fat file" in result.stdout
    except Exception:
        return False


def _thin_binary(path: str, arch: str) -> bool:
    thin_path = path + ".thin"
    try:
        subprocess.run(
            ["lipo", "-thin", arch, path, "-output", thin_path],
            check=True,
            capture_output=True,
        )
        os.replace(thin_path, path)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Warning: failed to thin {path}: {e.stderr}")
        if os.path.exists(thin_path):
            os.remove(thin_path)
        return False


def _sign_bundle(app_path: str) -> None:
    print(f"Re-signing bundle: {app_path}")
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", app_path],
        check=True,
    )


def optimize_bundle(app_path: str, target_arch: str) -> None:
    resources_dir = os.path.join(app_path, "Contents", "Resources")
    if not os.path.isdir(resources_dir):
        print(f"No Resources directory found in {app_path}, skipping")
        return

    total_saved = 0
    thinned_count = 0

    for root, _dirs, files in os.walk(resources_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath) or os.path.islink(filepath):
                continue
            if not os.access(filepath, os.X_OK) and not filename.endswith((".dylib", ".so")):
                continue
            if not _is_fat_binary(filepath):
                continue

            original_size = os.path.getsize(filepath)
            relpath = os.path.relpath(filepath, app_path)

            if _thin_binary(filepath, target_arch):
                new_size = os.path.getsize(filepath)
                saved = original_size - new_size
                total_saved += saved
                thinned_count += 1
                print(f"  Thinned {relpath}: {original_size:,} -> {new_size:,} (saved {saved:,})")

    if thinned_count > 0:
        print(f"\nThinned {thinned_count} binaries, saved {total_saved:,} bytes ({total_saved // 1048576} MB)")
        _sign_bundle(app_path)
    else:
        print("No fat binaries found to thin")


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize macOS .app bundle size")
    parser.add_argument("app_path", help="Path to the .app bundle")
    parser.add_argument(
        "--arch",
        default=None,
        help="Target architecture (arm64 or x86_64). Defaults to native.",
    )
    args = parser.parse_args()

    if not args.app_path.endswith(".app") or not os.path.isdir(args.app_path):
        print(f"Error: {args.app_path} is not a valid .app bundle")
        sys.exit(1)

    target_arch = args.arch or _get_native_arch()
    print(f"Optimizing {args.app_path} for {target_arch}...")
    optimize_bundle(args.app_path, target_arch)


if __name__ == "__main__":
    main()
