#!/usr/bin/env python3
"""
Post-build optimization for macOS .app bundles.

1. Thins universal (fat) Mach-O binaries in Contents/Resources/ to the
   target architecture (~267 MB savings).
2. Deduplicates data files in framework Versions/A/Resources/ directories
   that are already present at the framework top-level Resources/ (~110 MB).
3. Removes .ts translation source files from the locales/ directory,
   keeping only compiled .qm files (~2 MB).
4. Re-signs the bundle after all modifications.

Usage:
    python packaging/optimize_macos_bundle.py <path-to.app> [--arch arm64|x86_64]
"""

import argparse
import os
import platform
import shutil
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


def _get_dir_size(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp) and not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total


def thin_fat_binaries(app_path: str, target_arch: str) -> int:
    """Thin universal Mach-O binaries in Contents/Resources/ to a single arch."""
    resources_dir = os.path.join(app_path, "Contents", "Resources")
    if not os.path.isdir(resources_dir):
        return 0

    total_saved = 0
    thinned_count = 0

    for root, _dirs, files in os.walk(resources_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            if not os.path.isfile(filepath) or os.path.islink(filepath):
                continue
            if not os.access(filepath, os.X_OK) and not filename.endswith(
                (".dylib", ".so")
            ):
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
                print(
                    f"  Thinned {relpath}: {original_size:,} -> {new_size:,} (saved {saved:,})"
                )

    if thinned_count > 0:
        print(
            f"  Thinned {thinned_count} binaries, saved {total_saved:,} bytes ({total_saved // 1048576} MB)"
        )
    else:
        print("  No fat binaries found to thin")

    return total_saved


def deduplicate_framework_data(app_path: str) -> int:
    """Remove duplicated data in framework Versions/A/Resources/ directories.

    macOS framework bundles normally use symlinks (Resources/ -> Versions/A/Resources/)
    but Nuitka flattens these into real copies. Since the top-level Resources/ directory
    is the one actually referenced, the Versions/A/Resources/ copy can be safely removed
    and replaced with a symlink.
    """
    resources_dir = os.path.join(app_path, "Contents", "Resources")
    if not os.path.isdir(resources_dir):
        return 0

    total_saved = 0

    for fw_dir in _find_frameworks(resources_dir):
        top_resources = os.path.join(fw_dir, "Resources")
        versioned_resources = os.path.join(fw_dir, "Versions", "A", "Resources")

        if not os.path.isdir(top_resources) or not os.path.isdir(versioned_resources):
            continue
        if os.path.islink(top_resources) or os.path.islink(versioned_resources):
            continue

        size_before = _get_dir_size(versioned_resources)
        fw_name = os.path.basename(fw_dir)

        shutil.rmtree(versioned_resources)
        os.symlink("../../Resources", versioned_resources)

        total_saved += size_before
        print(
            f"  Deduplicated {fw_name}/Versions/A/Resources/ -> symlink (saved {size_before:,} bytes)"
        )

        top_helpers = os.path.join(fw_dir, "Helpers")
        versioned_helpers = os.path.join(fw_dir, "Versions", "A", "Helpers")

        if (
            os.path.isdir(top_helpers)
            and os.path.isdir(versioned_helpers)
            and not os.path.islink(top_helpers)
            and not os.path.islink(versioned_helpers)
        ):
            size_before = _get_dir_size(versioned_helpers)
            shutil.rmtree(versioned_helpers)
            os.symlink("../../Helpers", versioned_helpers)
            total_saved += size_before
            print(
                f"  Deduplicated {fw_name}/Versions/A/Helpers/ -> symlink (saved {size_before:,} bytes)"
            )

    if total_saved > 0:
        print(
            f"  Deduplicated framework data, saved {total_saved:,} bytes ({total_saved // 1048576} MB)"
        )

    return total_saved


def _find_frameworks(search_dir: str) -> list[str]:
    frameworks: list[str] = []
    for root, dirs, _ in os.walk(search_dir):
        for d in dirs:
            if d.endswith(".framework"):
                frameworks.append(os.path.join(root, d))
    return frameworks


def remove_locale_sources(app_path: str) -> int:
    """Remove .ts translation source files, keeping only compiled .qm files."""
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    total_saved = 0
    removed_count = 0

    for root, _dirs, files in os.walk(macos_dir):
        for filename in files:
            if not filename.endswith(".ts"):
                continue
            filepath = os.path.join(root, filename)
            if os.path.islink(filepath):
                continue
            qm_path = filepath[:-3] + ".qm"
            if os.path.exists(qm_path):
                size = os.path.getsize(filepath)
                os.remove(filepath)
                total_saved += size
                removed_count += 1

    if removed_count > 0:
        print(
            f"  Removed {removed_count} .ts source files, saved {total_saved:,} bytes ({total_saved // 1024} KB)"
        )

    return total_saved


def fixup_steamworkspy(app_path: str) -> None:
    """Ensure generic-named SteamworksPy.dylib exists in the bundle.

    Nuitka bundles the arch-suffixed variant (e.g. SteamworksPy_arm.dylib) but
    the runtime expects ``SteamworksPy.dylib``.  Copy the suffixed file to the
    generic name if it is missing.
    """
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    generic = os.path.join(macos_dir, "SteamworksPy.dylib")
    if os.path.exists(generic):
        print("  SteamworksPy.dylib already exists")
        return

    candidates = [
        os.path.join(macos_dir, f)
        for f in os.listdir(macos_dir)
        if f.startswith("SteamworksPy_") and f.endswith(".dylib")
    ]
    if candidates:
        shutil.copyfile(candidates[0], generic)
        print(f"  Created SteamworksPy.dylib from {os.path.basename(candidates[0])}")
    else:
        print("  WARNING: No SteamworksPy dylib found in bundle")


def optimize_bundle(app_path: str, target_arch: str) -> None:
    total_saved = 0

    print("\n[1/4] Fixing up SteamworksPy...")
    fixup_steamworkspy(app_path)

    print("\n[2/4] Thinning fat binaries...")
    total_saved += thin_fat_binaries(app_path, target_arch)

    print("\n[3/4] Deduplicating framework data files...")
    total_saved += deduplicate_framework_data(app_path)

    print("\n[4/4] Removing locale source files...")
    total_saved += remove_locale_sources(app_path)

    if total_saved > 0:
        print(f"\nTotal saved: {total_saved:,} bytes ({total_saved // 1048576} MB)")
    _sign_bundle(app_path)


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
