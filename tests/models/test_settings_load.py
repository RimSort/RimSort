"""Regression tests for the settings write performed during ``Settings.load()``."""

import builtins
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.models.settings import Settings
from app.utils.constants import DEFAULT_INSTANCE_NAME


def _make_settings(settings_file: Path) -> Settings:
    """Create a Settings instance that reads and writes ``settings_file``."""
    settings = Settings()
    settings._settings_file = settings_file
    settings._debug_file = settings_file.parent / "DEBUG"
    return settings


def test_load_closes_settings_file_before_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-time save must run once the settings file is closed.

    Windows cannot replace a file that is still open, so a save triggered
    while loading used to raise ``PermissionError [WinError 5]`` and abort
    startup (issue #2317).
    """
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    settings = _make_settings(settings_file)

    open_handles: list[Any] = []
    real_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        handle = real_open(*args, **kwargs)
        if Path(args[0]) == settings_file:
            open_handles.append(handle)
        return handle

    save_saw_open_handle: list[bool] = []

    def fake_save(_settings: Settings) -> None:
        save_saw_open_handle.append(any(not h.closed for h in open_handles))

    monkeypatch.setattr(builtins, "open", recording_open)
    monkeypatch.setattr(Settings, "save", fake_save)

    settings.load()

    assert open_handles
    assert save_saw_open_handle == [False]


@pytest.mark.parametrize(
    "settings_text",
    [
        json.dumps(
            {
                "current_instance": DEFAULT_INSTANCE_NAME,
                "current_instance_path": "C:/instances/Default",
                "instances": {
                    DEFAULT_INSTANCE_NAME: {
                        "name": DEFAULT_INSTANCE_NAME,
                        "steam_client_integration": False,
                        "workshop_folder": "C:/Steam/steamapps/workshop/content/294100",
                    }
                },
            }
        ),
        None,
    ],
    ids=["config-fix", "first-save"],
)
def test_load_continues_when_load_time_save_fails(
    tmp_path: Path, settings_text: str | None
) -> None:
    """A failing load-time save must be logged, not crash startup (#2317).

    Covers the two writes that ``load()`` can trigger: saving either a
    mitigated config (``config-fix``) or the defaults of a first run
    (``first-save``). Both go through ``_save_after_load``, which catches
    ``OSError`` so the app keeps running with the in-memory configuration.
    """
    settings_file = tmp_path / "settings.json"
    if settings_text is not None:
        settings_file.write_text(settings_text, encoding="utf-8")
    settings = _make_settings(settings_file)

    with patch(
        "app.models.settings.Settings.save",
        side_effect=PermissionError("read-only settings file"),
    ):
        settings.load()

    assert settings.instances[DEFAULT_INSTANCE_NAME].workshop_folder == ""


def test_load_persists_steam_integration_fixes(tmp_path: Path) -> None:
    """The Steam integration fix path also writes during load (issue #2317).

    Mirrors the v1.13.2 crash: an invalid workshop folder is cleared while
    loading, so the settings file is rewritten before the app has started.
    """
    workshop_folder = tmp_path / "steamapps" / "workshop" / "content" / "294100"
    workshop_folder.mkdir(parents=True)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "current_instance": DEFAULT_INSTANCE_NAME,
                "current_instance_path": str(tmp_path / "instances" / "Default"),
                "instances": {
                    DEFAULT_INSTANCE_NAME: {
                        "name": DEFAULT_INSTANCE_NAME,
                        "steam_client_integration": True,
                        "workshop_folder": str(workshop_folder),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    settings = _make_settings(settings_file)

    settings.load()

    instance = settings.instances[DEFAULT_INSTANCE_NAME]
    assert instance.steam_client_integration is False
    assert instance.workshop_folder == ""
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["instances"][DEFAULT_INSTANCE_NAME]["workshop_folder"] == ""


def test_load_creates_missing_settings_file(tmp_path: Path) -> None:
    """A missing settings file is created from the defaults."""
    settings_file = tmp_path / "settings.json"
    settings = _make_settings(settings_file)

    settings.load()

    assert json.loads(settings_file.read_text(encoding="utf-8"))["instances"]


@pytest.mark.skipif(
    sys.platform != "win32", reason="Read-only file attribute is Windows-only"
)
def test_load_tolerates_read_only_settings_file(tmp_path: Path) -> None:
    """A read-only settings file must not crash startup (issue #2317)."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    os.chmod(settings_file, stat.S_IREAD)
    settings = _make_settings(settings_file)

    settings.load()

    assert json.loads(settings_file.read_text(encoding="utf-8"))["instances"]
