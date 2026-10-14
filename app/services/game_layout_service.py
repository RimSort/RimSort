"""Resolve RimWorld launch locations independently of game content."""

import os
import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from xml.etree import ElementTree

LINUX_NATIVE_EXECUTABLES = ("RimWorld", "RimWorldLinux64", "RimWorldLinux")
WINDOWS_EXECUTABLES = ("RimWorld.exe", "RimWorldWin64.exe", "RimWorldWin.exe")
LINUX_EXECUTABLES = LINUX_NATIVE_EXECUTABLES + WINDOWS_EXECUTABLES


@dataclass(frozen=True)
class GameLayout:
    launch_location: Path
    content_root: Path

    @property
    def data_path(self) -> Path:
        return self.content_root / "Data"

    @property
    def local_mods_path(self) -> Path:
        return self.content_root / "Mods"

    @property
    def version_path(self) -> Path:
        return self.content_root / "Version.txt"


def get_game_content_candidates(game_path: Path) -> tuple[Path, ...]:
    """Consider only the configured directory and an existing bundle's parent."""
    try:
        if game_path.suffix == ".app" and game_path.is_dir():
            return game_path, game_path.parent
    except OSError:
        pass
    return (game_path,)


def has_game_version_file(path: Path, *, allow_symlink: bool = True) -> bool:
    """Check a bounded version marker without reading the whole file."""
    version = path / "Version.txt"
    try:
        if not version.is_file() or (not allow_symlink and version.is_symlink()):
            return False
        with version.open(encoding="utf-8-sig", errors="replace") as stream:
            first_line = stream.read(256).splitlines()
        return bool(first_line and re.match(r"^\d+\.\d+", first_line[0].strip()))
    except OSError:
        return False


def _find_named_child(directory: Path, name: str) -> Path | None:
    candidate = directory / name
    if candidate.exists():
        return candidate
    return next(
        (
            p
            for p in islice(directory.iterdir(), 500)
            if p.name.casefold() == name.casefold()
        ),
        None,
    )


def _has_core_metadata(path: Path) -> bool:
    try:
        about = _find_named_child(path / "Data" / "Core", "About")
        if about is None or not about.is_dir():
            return False
        metadata = _find_named_child(about, "About.xml")
        if (
            metadata is None
            or not metadata.is_file()
            or metadata.stat().st_size > 1048576
        ):
            return False
        root = ElementTree.parse(metadata).getroot()
        if root.tag.casefold() != "modmetadata":
            return False
        return any(
            child.tag.casefold() == "packageid"
            and (child.text or "").strip().casefold() == "ludeon.rimworld"
            for child in root
        )
    except OSError, ElementTree.ParseError, ValueError:
        return False


def resolve_game_layout(game_path: Path) -> GameLayout | None:
    """Select one validated content root without changing the configured path."""
    for candidate in get_game_content_candidates(game_path):
        try:
            if (
                candidate.is_dir()
                and (candidate / "Data").is_dir()
                and (has_game_version_file(candidate) or _has_core_metadata(candidate))
            ):
                return GameLayout(game_path, candidate)
        except OSError:
            continue
    return None


def find_game_executable(game_path: Path, system_name: str) -> Path | None:
    """Find a launchable binary or the selected macOS bundle."""
    try:
        if system_name == "Darwin":
            return (
                game_path if game_path.suffix == ".app" and game_path.is_dir() else None
            )
        names = {
            "Linux": LINUX_EXECUTABLES,
            "Windows": WINDOWS_EXECUTABLES,
        }.get(system_name, ())
        for name in names:
            executable = game_path / name
            if not executable.is_file():
                continue
            if (
                system_name == "Linux"
                and name in LINUX_NATIVE_EXECUTABLES
                and not os.access(executable, os.X_OK)
            ):
                continue
            return executable
    except OSError:
        return None
    return None
