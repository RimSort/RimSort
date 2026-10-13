from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import game_layout_service
from app.services.path_autodetect_service import PathAutodetectService
from app.utils.generic import get_executable_path
from tests.game_layout_fixtures import make_game_install


@pytest.mark.parametrize(
    "system,new_name,old_names",
    [
        ("Linux", "RimWorld", ("RimWorldLinux64", "RimWorldLinux")),
        ("Windows", "RimWorld.exe", ("RimWorldWin64.exe", "RimWorldWin.exe")),
    ],
)
def test_new_executable_wins_over_leftover_legacy_files(
    tmp_path: Path, system: str, new_name: str, old_names: tuple[str, ...]
) -> None:
    for name in (new_name, *old_names):
        executable = tmp_path / name
        executable.write_bytes(b"game")
        executable.chmod(0o755)
    with patch("platform.system", return_value=system):
        assert get_executable_path(tmp_path) == str(tmp_path / new_name)


@pytest.mark.parametrize("name", ["RimWorld", "RimWorldLinux64", "RimWorld.exe"])
def test_directory_named_as_executable_is_not_launchable(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / name).mkdir()
    with patch("platform.system", return_value="Linux"):
        assert get_executable_path(tmp_path) is None


def test_native_new_executable_precedes_wine(tmp_path: Path) -> None:
    native = tmp_path / "RimWorld"
    native.write_bytes(b"game")
    native.chmod(0o755)
    (tmp_path / "RimWorldWin64.exe").write_bytes(b"game")
    with patch("platform.system", return_value="Linux"):
        assert get_executable_path(tmp_path) == str(native)


@pytest.mark.parametrize("name", ["RimWorld", "RimWorldLinux64", "RimWorldLinux"])
def test_native_executable_requires_execute_permission(
    tmp_path: Path, name: str
) -> None:
    binary = tmp_path / name
    binary.write_bytes(b"game")
    with (
        patch("platform.system", return_value="Linux"),
        patch("os.access", return_value=False),
    ):
        assert get_executable_path(tmp_path) is None


@pytest.mark.parametrize("kind", ["mac-internal", "mac-sibling", "linux", "windows"])
def test_content_root_matches_install(tmp_path: Path, kind: str) -> None:
    install = make_game_install(tmp_path / "RimWorld", kind)
    layout = game_layout_service.resolve_game_layout(install.launch_location)
    assert layout is not None
    assert layout.launch_location == install.launch_location
    assert layout.content_root == install.content_root
    assert layout.data_path == install.data_path
    assert layout.local_mods_path == install.mods_path
    assert layout.version_path == install.content_root / "Version.txt"


def test_internal_content_wins_when_both_roots_are_valid(tmp_path: Path) -> None:
    sibling = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    internal = make_game_install(tmp_path / "RimWorld", "mac-internal", "1.6.9999")
    layout = game_layout_service.resolve_game_layout(sibling.launch_location)
    assert layout is not None
    assert layout.content_root == internal.launch_location
    assert layout.version_path.read_text() == "1.6.9999"


@pytest.mark.parametrize("removed", ["Mods", "Data/Core"])
def test_missing_mods_or_core_does_not_hide_valid_version_root(
    tmp_path: Path, removed: str
) -> None:
    import shutil

    install = make_game_install(tmp_path / "RimWorld", "linux")
    shutil.rmtree(install.content_root / removed)
    layout = game_layout_service.resolve_game_layout(install.launch_location)
    assert layout is not None
    assert layout.content_root == install.content_root


def test_core_marker_with_case_varied_about_file_and_invalid_version(
    tmp_path: Path,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux", "not a version")
    about = install.data_path / "Core" / "About"
    (about / "About.xml").rename(about / "ABOUT.XML")
    about.rename(about.parent / "about")
    layout = game_layout_service.resolve_game_layout(install.launch_location)
    assert layout is not None
    assert layout.content_root == install.content_root


def test_non_app_child_does_not_inherit_parent_content(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    child = install.content_root / "Unrelated"
    child.mkdir()
    assert game_layout_service.resolve_game_layout(child) is None


def test_missing_app_does_not_inherit_parent_content(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    assert (
        game_layout_service.resolve_game_layout(install.content_root / "Missing.app")
        is None
    )


def test_data_without_either_marker_is_unresolved(tmp_path: Path) -> None:
    (tmp_path / "Data").mkdir()
    assert game_layout_service.resolve_game_layout(tmp_path) is None


def test_content_permission_errors_are_unresolved(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    with (
        patch.object(Path, "open", side_effect=PermissionError("denied")),
        patch("builtins.open", side_effect=PermissionError("denied")),
    ):
        assert game_layout_service.resolve_game_layout(install.launch_location) is None


def test_existing_mods_symlink_does_not_change_content_root(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    (install.launch_location / "Mods").symlink_to(
        install.mods_path, target_is_directory=True
    )
    layout = game_layout_service.resolve_game_layout(install.launch_location)
    assert layout is not None
    assert layout.local_mods_path == install.mods_path


def test_broken_configured_link_is_unresolved(tmp_path: Path) -> None:
    broken = tmp_path / "Missing.app"
    broken.symlink_to(tmp_path / "absent", target_is_directory=True)
    assert game_layout_service.resolve_game_layout(broken) is None


@pytest.mark.parametrize(
    "system,name", [("Linux", "RimWorld"), ("Windows", "RimWorld.exe")]
)
def test_non_steam_markers_accept_new_executables(
    tmp_path: Path, system: str, name: str
) -> None:
    (tmp_path / name).write_bytes(b"game")
    if system == "Linux":
        assert PathAutodetectService._looks_like_rimworld_dir(tmp_path)
    else:
        assert PathAutodetectService._looks_like_rimworld_windows_dir(tmp_path)


def test_mac_non_steam_markers_accept_sibling_content(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    assert PathAutodetectService._looks_like_rimworld_mac_app(install.launch_location)
