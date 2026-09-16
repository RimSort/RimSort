import json
from pathlib import Path
from unittest.mock import patch

from app.services.path_autodetect_service import PathAutodetectService


def _vdf_escape(path: Path) -> str:
    """Escape backslashes for VDF format (matches real Steam VDF files on Windows)."""
    return str(path).replace("\\", "\\\\")


def _setup_steam_root(tmp_path: Path, subdir: str) -> Path:
    """Create a fake Steam root with steamapps dir at the given subdir under tmp_path."""
    steam_root = tmp_path / subdir
    steam_root.mkdir(parents=True)
    (steam_root / "steamapps" / "common" / "RimWorld").mkdir(parents=True)
    (steam_root / "steamapps" / "workshop" / "content" / "294100").mkdir(parents=True)
    return steam_root


def _make_service() -> PathAutodetectService:
    """Create a PathAutodetectService (no __init__ setup needed)."""
    return PathAutodetectService()


class TestFindSteamRoot:
    """Tests for PathAutodetectService._find_steam_root()."""

    def test_returns_first_valid_candidate_with_steamapps(self, tmp_path: Path) -> None:
        candidate = tmp_path / ".steam" / "steam"
        candidate.mkdir(parents=True)
        (candidate / "steamapps").mkdir()

        result = _make_service()._find_steam_root([candidate])
        assert result == candidate

    def test_returns_first_valid_candidate_with_vdf(self, tmp_path: Path) -> None:
        candidate = tmp_path / ".steam" / "steam"
        (candidate / "config").mkdir(parents=True)
        (candidate / "config" / "libraryfolders.vdf").touch()

        result = _make_service()._find_steam_root([candidate])
        assert result == candidate

    def test_skips_nonexistent_candidates(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        valid = tmp_path / "valid_steam"
        valid.mkdir()
        (valid / "steamapps").mkdir()

        result = _make_service()._find_steam_root([nonexistent, valid])
        assert result == valid

    def test_skips_candidates_without_steamapps_or_vdf(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = _make_service()._find_steam_root([empty_dir])
        assert result is None

    def test_returns_none_when_no_candidates_match(self, tmp_path: Path) -> None:
        result = _make_service()._find_steam_root([tmp_path / "a", tmp_path / "b"])
        assert result is None

    def test_respects_priority_order(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        first.mkdir()
        (first / "steamapps").mkdir()

        second = tmp_path / "second"
        second.mkdir()
        (second / "steamapps").mkdir()

        result = _make_service()._find_steam_root([first, second])
        assert result == first

    def test_returns_none_for_empty_list(self) -> None:
        result = _make_service()._find_steam_root([])
        assert result is None


class TestGetLinuxPaths:
    """Tests for PathAutodetectService.get_linux_paths()."""

    def _call(self) -> tuple[Path, Path, Path]:
        return _make_service().get_linux_paths()

    def test_debian_installation_path(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, ".steam/debian-installation")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"
        assert result[2] == steam_root / "steamapps" / "workshop" / "content" / "294100"

    def test_native_steam_path(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, ".steam/steam")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"

    def test_local_share_path(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, ".local/share/Steam")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"

    def test_flatpak_path(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(
            tmp_path,
            ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"

    def test_snap_path(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, "snap/steam/common/.local/share/Steam")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"

    def test_vdf_finds_rimworld_in_secondary_library(self, tmp_path: Path) -> None:
        steam_root = tmp_path / ".steam" / "steam"
        steam_root.mkdir(parents=True)
        (steam_root / "steamapps").mkdir()

        secondary_lib = tmp_path / "games" / "SteamLibrary"
        (secondary_lib / "steamapps" / "common" / "RimWorld").mkdir(parents=True)
        (secondary_lib / "steamapps" / "workshop" / "content" / "294100").mkdir(
            parents=True
        )

        vdf_dir = steam_root / "config"
        vdf_dir.mkdir(parents=True)
        vdf_content = f'"libraryfolders"\n{{\n    "0"\n    {{\n        "path"    "{_vdf_escape(steam_root)}"\n        "apps"\n        {{\n        }}\n    }}\n    "1"\n    {{\n        "path"    "{_vdf_escape(secondary_lib)}"\n        "apps"\n        {{\n            "294100"    "1234567890"\n        }}\n    }}\n}}\n'
        (vdf_dir / "libraryfolders.vdf").write_text(vdf_content)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == secondary_lib / "steamapps" / "common" / "RimWorld"
        assert (
            result[2] == secondary_lib / "steamapps" / "workshop" / "content" / "294100"
        )

    def test_proton_config_takes_priority(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, ".steam/steam")
        proton_config = (
            steam_root
            / "steamapps"
            / "compatdata"
            / "294100"
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
            / "AppData"
            / "LocalLow"
            / "Ludeon Studios"
            / "RimWorld by Ludeon Studios"
            / "Config"
        )
        proton_config.mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[1] == proton_config

    def test_native_config_when_no_proton(self, tmp_path: Path) -> None:
        _setup_steam_root(tmp_path, ".steam/steam")
        native_config = (
            tmp_path
            / ".config"
            / "unity3d"
            / "Ludeon Studios"
            / "RimWorld by Ludeon Studios"
            / "Config"
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[1] == native_config

    def test_no_steam_root_returns_fallback_paths(self, tmp_path: Path) -> None:
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert "steamapps" in str(result[0])
        assert "Config" in str(result[1])
        assert "294100" in str(result[2])

    def test_priority_debian_over_native(self, tmp_path: Path) -> None:
        debian_root = _setup_steam_root(tmp_path, ".steam/debian-installation")
        _setup_steam_root(tmp_path, ".steam/steam")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[0] == debian_root / "steamapps" / "common" / "RimWorld"


class TestGetDarwinPaths:
    """Tests for PathAutodetectService.get_darwin_paths().

    Note: macOS uses "Rimworld" (lowercase w) in hardcoded fallback paths,
    while VDF parsing returns "RimWorld" (capital W). This is fine because
    macOS has a case-insensitive filesystem by default. Tests assert the
    exact casing each code path produces.
    """

    def _call(self) -> tuple[Path, Path, Path]:
        return _make_service().get_darwin_paths()

    @staticmethod
    def _make_darwin_steam_root(tmp_path: Path) -> Path:
        """Create a minimal macOS Steam root directory tree."""
        steam_root = tmp_path / "Library" / "Application Support" / "Steam"
        steam_root.mkdir(parents=True)
        (steam_root / "steamapps").mkdir()
        return steam_root

    def test_vdf_based_detection(self, tmp_path: Path) -> None:
        steam_root = self._make_darwin_steam_root(tmp_path)
        (steam_root / "steamapps" / "common" / "RimWorld" / "RimworldMac.app").mkdir(
            parents=True
        )
        (steam_root / "steamapps" / "workshop" / "content" / "294100").mkdir(
            parents=True
        )
        vdf_dir = steam_root / "config"
        vdf_dir.mkdir(parents=True)
        vdf_content = f'"libraryfolders"\n{{\n    "0"\n    {{\n        "path"    "{_vdf_escape(steam_root)}"\n        "apps"\n        {{\n            "294100"    "1234567890"\n        }}\n    }}\n}}\n'
        (vdf_dir / "libraryfolders.vdf").write_text(vdf_content)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        # VDF returns "RimWorld" (capital W)
        assert (
            result[0]
            == steam_root / "steamapps" / "common" / "RimWorld" / "RimworldMac.app"
        )

    def test_fallback_when_no_vdf(self, tmp_path: Path) -> None:
        steam_root = self._make_darwin_steam_root(tmp_path)
        service = _make_service()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(service, "_macos_game_app_roots", return_value=()),
        ):
            result = service.get_darwin_paths()

        # Fallback uses canonical "RimWorld" casing when no .app bundle found on disk
        expected_game = (
            steam_root / "steamapps" / "common" / "RimWorld" / "RimWorldMac.app"
        )
        assert result[0] == expected_game

    def test_config_folder_unchanged(self, tmp_path: Path) -> None:
        self._make_darwin_steam_root(tmp_path)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        expected_config = (
            tmp_path / "Library" / "Application Support" / "Rimworld" / "Config"
        )
        assert result[1] == expected_config

    def test_workshop_folder_derived_from_game(self, tmp_path: Path) -> None:
        self._make_darwin_steam_root(tmp_path)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call()

        assert result[2].parts[-3:] == ("workshop", "content", "294100")

    def test_no_steam_root_returns_hardcoded_paths(self, tmp_path: Path) -> None:
        service = _make_service()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(service, "_macos_game_app_roots", return_value=()),
        ):
            result = service.get_darwin_paths()

        assert "RimWorldMac.app" in str(result[0])
        assert "Config" in str(result[1])
        assert "294100" in str(result[2])


class TestSnapWarning:
    """Tests for Snap detection via PathAutodetectService.detected_steam_root."""

    def test_snap_steam_root_detected(self, tmp_path: Path) -> None:
        _setup_steam_root(tmp_path, "snap/steam/common/.local/share/Steam")
        service = _make_service()

        with patch("pathlib.Path.home", return_value=tmp_path):
            service.get_linux_paths()

        assert service.detected_steam_root is not None
        assert "snap" in service.detected_steam_root.parts

    def test_native_steam_root_not_flagged(self, tmp_path: Path) -> None:
        _setup_steam_root(tmp_path, ".steam/steam")
        service = _make_service()

        with patch("pathlib.Path.home", return_value=tmp_path):
            service.get_linux_paths()

        assert service.detected_steam_root is not None
        assert "snap" not in service.detected_steam_root.parts

    def test_no_steam_root_not_flagged(self, tmp_path: Path) -> None:
        service = _make_service()

        with patch("pathlib.Path.home", return_value=tmp_path):
            service.get_linux_paths()

        assert service.detected_steam_root is None


class TestVdfEdgeCases:
    """Tests for VDF parsing edge cases in path autodetection."""

    def _call_linux(self) -> tuple[Path, Path, Path]:
        return _make_service().get_linux_paths()

    def test_malformed_vdf_falls_back_to_default(self, tmp_path: Path) -> None:
        steam_root = tmp_path / ".steam" / "steam"
        steam_root.mkdir(parents=True)
        (steam_root / "steamapps").mkdir()
        vdf_dir = steam_root / "config"
        vdf_dir.mkdir()
        (vdf_dir / "libraryfolders.vdf").write_text("this is not valid vdf {{{")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call_linux()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"
        assert result[2] == steam_root / "steamapps" / "workshop" / "content" / "294100"

    def test_vdf_without_rimworld_falls_back(self, tmp_path: Path) -> None:
        steam_root = tmp_path / ".steam" / "steam"
        steam_root.mkdir(parents=True)
        (steam_root / "steamapps").mkdir()
        vdf_dir = steam_root / "config"
        vdf_dir.mkdir()
        vdf_content = (
            '"libraryfolders"\n'
            "{\n"
            '    "0"\n'
            "    {\n"
            f'        "path"    "{_vdf_escape(steam_root)}"\n'
            '        "apps"\n'
            "        {\n"
            '            "730"    "12345"\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        (vdf_dir / "libraryfolders.vdf").write_text(vdf_content)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = self._call_linux()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"


class TestLooksLikeRimworldDir:
    """Tests for PathAutodetectService._looks_like_rimworld_dir()."""

    def test_accepts_parsable_version_txt(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "Version.txt").write_text("1.6.4871 rev573\n")

        assert _make_service()._looks_like_rimworld_dir(game_dir)

    def test_rejects_unparsable_version_txt(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "Version.txt").write_text("not a version\n")

        assert not _make_service()._looks_like_rimworld_dir(game_dir)

    def test_accepts_known_executable(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "RimWorldLinux64").write_bytes(b"\x7fELF")

        assert _make_service()._looks_like_rimworld_dir(game_dir)

    def test_rejects_lookalike_folder_without_markers(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "RimWorld"
        game_dir.mkdir()
        (game_dir / "readme.txt").write_text("hello")

        assert not _make_service()._looks_like_rimworld_dir(game_dir)

    def test_rejects_missing_directory(self, tmp_path: Path) -> None:
        assert not _make_service()._looks_like_rimworld_dir(tmp_path / "missing")

    def test_rejects_symlinked_directory(self, tmp_path: Path) -> None:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "Version.txt").write_text("1.6.4871 rev573\n")
        link = tmp_path / "link"
        link.symlink_to(real_dir)

        assert not _make_service()._looks_like_rimworld_dir(link)


class TestIterShallowDirs:
    """Tests for PathAutodetectService._iter_shallow_dirs()."""

    def test_yields_children_up_to_max_depth(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "d").mkdir()

        found = sorted(p.name for p in _make_service()._iter_shallow_dirs(tmp_path, 2))

        # "c" sits at depth 3 and is not yielded
        assert found == ["a", "b", "d"]

    def test_skips_hidden_entries(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        found = [p.name for p in _make_service()._iter_shallow_dirs(tmp_path, 1)]

        assert found == ["visible"]

    def test_skips_symlinked_dirs_without_following(self, tmp_path: Path) -> None:
        outside_target = tmp_path / "outside" / "target"
        outside_target.mkdir(parents=True)
        games_root = tmp_path / "Games"
        (games_root / "real").mkdir(parents=True)
        (games_root / "link").symlink_to(outside_target)

        found = [p.name for p in _make_service()._iter_shallow_dirs(games_root, 2)]

        assert found == ["real"]

    def test_missing_root_yields_nothing(self, tmp_path: Path) -> None:
        assert list(_make_service()._iter_shallow_dirs(tmp_path / "nope", 2)) == []


class TestNonSteamMacGameSearch:
    """Tests for the GOG-style .app search on macOS."""

    @staticmethod
    def _make_gog_bundle(apps_root: Path, name: str = "RimWorld.app") -> Path:
        """Create a Ludeon-layout RimWorld .app bundle inside apps_root."""
        bundle = apps_root / name
        (bundle / "Contents" / "Resources").mkdir(parents=True)
        (bundle / "Data").mkdir()
        (bundle / "Mods").mkdir()
        (bundle / "Version.txt").write_text("1.6.4871 rev573\n")
        return bundle

    def test_finds_gog_bundle_in_applications(self, tmp_path: Path) -> None:
        apps_root = tmp_path / "Applications"
        apps_root.mkdir()
        bundle = self._make_gog_bundle(apps_root)
        service = _make_service()

        with patch.object(service, "_macos_game_app_roots", return_value=(apps_root,)):
            result = service._find_non_steam_game_folder_macos()

        assert result == bundle

    def test_prefers_canonical_bundle_name(self, tmp_path: Path) -> None:
        apps_root = tmp_path / "Applications"
        apps_root.mkdir()
        self._make_gog_bundle(apps_root, name="RimWorldMac.app")
        canonical = self._make_gog_bundle(apps_root, name="RimWorld.app")
        service = _make_service()

        with patch.object(service, "_macos_game_app_roots", return_value=(apps_root,)):
            result = service._find_non_steam_game_folder_macos()

        assert result == canonical

    def test_rejects_lookalike_bundle_without_markers(self, tmp_path: Path) -> None:
        apps_root = tmp_path / "Applications"
        (apps_root / "RimWorld.app" / "Contents").mkdir(parents=True)
        service = _make_service()

        with patch.object(service, "_macos_game_app_roots", return_value=(apps_root,)):
            result = service._find_non_steam_game_folder_macos()

        assert result is None

    def test_get_darwin_paths_uses_gog_bundle_when_no_steam(
        self, tmp_path: Path
    ) -> None:
        apps_root = tmp_path / "Applications"
        bundle = self._make_gog_bundle(apps_root)
        service = _make_service()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(service, "_macos_game_app_roots", return_value=(apps_root,)),
        ):
            result = service.get_darwin_paths()

        assert result[0] == bundle

    def test_steam_installation_wins_over_gog_bundle(self, tmp_path: Path) -> None:
        steam_root = tmp_path / "Library" / "Application Support" / "Steam"
        steam_root.mkdir(parents=True)
        (steam_root / "steamapps").mkdir()
        steam_game = (
            steam_root / "steamapps" / "common" / "RimWorld" / "RimWorldMac.app"
        )
        steam_game.mkdir(parents=True)
        apps_root = tmp_path / "Applications"
        self._make_gog_bundle(apps_root)
        service = _make_service()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(service, "_macos_game_app_roots", return_value=(apps_root,)),
        ):
            result = service.get_darwin_paths()

        assert result[0] == steam_game


class TestNonSteamLinuxGameSearch:
    """Tests for the GOG-style game search on Linux."""

    @staticmethod
    def _make_game_dir(path: Path) -> Path:
        """Create a directory carrying RimWorld content markers."""
        path.mkdir(parents=True)
        (path / "Version.txt").write_text("1.6.4871 rev573\n")
        (path / "Data").mkdir()
        (path / "Mods").mkdir()
        return path

    @staticmethod
    def _write_heroic_metadata(tmp_path: Path, payload: str) -> None:
        heroic_config = tmp_path / ".config" / "heroic" / "gog_store"
        heroic_config.mkdir(parents=True)
        (heroic_config / "installed.json").write_text(payload)

    def test_finds_gog_games_layout(self, tmp_path: Path) -> None:
        game_dir = self._make_game_dir(tmp_path / "GOG Games" / "RimWorld" / "game")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        assert result[0] == game_dir

    def test_finds_games_root_layout(self, tmp_path: Path) -> None:
        game_dir = self._make_game_dir(tmp_path / "Games" / "Heroic" / "RimWorld")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        assert result[0] == game_dir

    def test_finds_heroic_metadata_custom_location(self, tmp_path: Path) -> None:
        custom_dir = self._make_game_dir(tmp_path / "custom" / "install")
        self._write_heroic_metadata(
            tmp_path,
            json.dumps([{"appName": "1207658924", "install_path": str(custom_dir)}]),
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        assert result[0] == custom_dir

    def test_ignores_malformed_heroic_metadata(self, tmp_path: Path) -> None:
        self._write_heroic_metadata(tmp_path, "this is not json")
        game_dir = self._make_game_dir(tmp_path / "GOG Games" / "RimWorld" / "game")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        # Malformed metadata is skipped and the roots search still runs
        assert result[0] == game_dir

    def test_steam_installation_wins_over_non_steam(self, tmp_path: Path) -> None:
        steam_root = _setup_steam_root(tmp_path, ".steam/steam")
        self._make_game_dir(tmp_path / "GOG Games" / "RimWorld" / "game")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        assert result[0] == steam_root / "steamapps" / "common" / "RimWorld"

    def test_symlinked_game_dir_not_detected(self, tmp_path: Path) -> None:
        real_game = self._make_game_dir(tmp_path / "elsewhere" / "game")
        (tmp_path / "GOG Games").mkdir(parents=True)
        (tmp_path / "GOG Games" / "RimWorld").symlink_to(real_game)

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = _make_service().get_linux_paths()

        assert "steamapps" in str(result[0])


class TestGetExecutablePathLinux:
    """Tests for the Linux executable lookup in app.utils.generic.get_executable_path."""

    @staticmethod
    def _call(game_dir: Path) -> str | None:
        from app.utils.generic import get_executable_path

        with patch("platform.system", return_value="Linux"):
            return get_executable_path(game_dir)

    @staticmethod
    def _make_executable(path: Path) -> None:
        """Create a fake game binary with the executable bit set."""
        path.write_bytes(b"placeholder")
        path.chmod(0o755)

    def test_accepts_modern_rimworld_linux64(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        self._make_executable(game_dir / "RimWorldLinux64")

        assert self._call(game_dir) == str(game_dir / "RimWorldLinux64")

    def test_accepts_legacy_rimworld_linux(self, tmp_path: Path) -> None:
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        self._make_executable(game_dir / "RimWorldLinux")

        assert self._call(game_dir) == str(game_dir / "RimWorldLinux")

    def test_accepts_non_executable_windows_binary_on_linux(
        self, tmp_path: Path
    ) -> None:
        """Windows .exe files are accepted without the executable bit (Wine/Proton)."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "RimWorldWin64.exe").write_bytes(b"MZ")

        assert self._call(game_dir) == str(game_dir / "RimWorldWin64.exe")

    def test_rejects_non_executable_linux_binary(self, tmp_path: Path) -> None:
        """A Linux binary without the executable bit is not launchable."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "RimWorldLinux64").write_bytes(b"placeholder")

        assert self._call(game_dir) is None
