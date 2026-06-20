import subprocess
from typing import Any, Generator, Union
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

_real_popen = subprocess.Popen


@pytest.fixture(autouse=True)
def _block_steam_urls(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Prevent tests from opening steam:// URLs on the host machine.

    Guards subprocess.Popen to block any steam:// URI regardless of
    which Python function initiated the call. This catches cases where
    platform_specific_open is patched at the wrong import location.
    """

    def _guarded_popen(*args: Any, **kw: Any) -> subprocess.Popen[Any]:
        popen_args = args[0] if args else kw.get("args", "")
        cmd_str = (
            " ".join(str(x) for x in popen_args)
            if isinstance(popen_args, (list, tuple))
            else str(popen_args)
        )
        if "steam://" in cmd_str:
            raise RuntimeError(
                f"Test {request.node.nodeid} tried to open a steam:// URL "
                f"via subprocess: {cmd_str}"
            )
        return _real_popen(*args, **kw)

    with patch.object(subprocess, "Popen", _guarded_popen):
        yield


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Automatically accept all QDialog exec_ calls during tests to prevent blocking.
    """

    def fake_exec(self: QDialog) -> int:
        # Return QDialog.Accepted constant value 1
        return 1

    monkeypatch.setattr(QDialog, "exec_", fake_exec)
    monkeypatch.setattr(QDialog, "exec", fake_exec)


@pytest.fixture(scope="function")
def qapp() -> Generator[Union[QApplication, QCoreApplication], None, None]:
    """Create a QApplication instance for Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def mock_app_info(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Redirect all AppInfo paths to a temp dir to prevent filesystem side effects.

    Uses ``tmp_path_factory`` instead of ``tmp_path`` so the mock's
    directories live in a *separate* temp folder, leaving the per-test
    ``tmp_path`` completely empty for tests that need it (e.g. git clone).

    Creates a real ``AppInfo`` instance (bypassing ``__init__``) so that
    @property descriptors on the class are preserved.  This lets tests
    override individual properties with ``PropertyMock`` as usual.
    """
    from app.utils.app_info import AppInfo

    original_instance = AppInfo._instance

    base = tmp_path_factory.mktemp("mock_app_info")

    storage = base / "app_storage"
    storage.mkdir()
    logs = base / "logs"
    logs.mkdir()

    # Build a real AppInfo without running __init__ (which reads
    # version.xml, creates platform dirs, etc.).
    stub = object.__new__(AppInfo)
    stub._is_initialized = True
    stub._app_name = "RimSort"
    stub._app_version = "0.0.0-test"
    stub._app_copyright = ""
    stub._application_folder = base / "app"
    stub._app_storage_folder = storage
    stub._user_log_folder = logs
    stub._databases_folder = storage / "dbs"
    stub._saved_modlists_folder = storage / "modlists"
    stub._theme_data_folder = base / "app" / "themes"
    stub._theme_storage_folder = storage / "themes"
    stub._settings_file = storage / "settings.json"
    stub._user_rules_file = storage / "dbs" / "userRules.json"
    stub._ignore_mods_file = storage / "dbs" / "ignore.json"
    stub._language_data_folder = base / "app" / "locales"
    stub._backups_folder = storage / "backups"
    stub._settings_backups_folder = storage / "backups" / "settings"
    stub._game_saves_backups_folder = storage / "backups" / "saves"
    stub._application_backups_folder = storage / "backups" / "rimsort_installation"
    stub._browser_profile_folder = storage / "browser"
    stub._setup_web_channel_script_file = base / "app" / "setup_web_channel_script.js"

    stub._databases_folder.mkdir(parents=True, exist_ok=True)
    (base / "app" / "themes").mkdir(parents=True, exist_ok=True)

    AppInfo._instance = stub

    yield

    AppInfo._instance = original_instance


@pytest.fixture
def fresh_event_bus() -> Generator[None, None, None]:
    """Reset the EventBus singleton so each test gets a clean instance."""
    from app.utils.event_bus import EventBus

    original_instance = EventBus._instance
    EventBus._instance = None

    yield

    EventBus._instance = original_instance


@pytest.fixture
def mock_metadata_controller(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch MetadataController.instance() to return a lightweight mock."""
    from app.controllers.metadata_controller import MetadataController

    controller = MagicMock(spec=MetadataController)
    controller.mods_metadata = {}
    controller.game_version = "1.5"
    controller.steam_db = None
    controller.community_rules = None
    controller.user_rules = None
    controller.packageid_to_paths = {}
    controller.workshop_acf_data = {}
    controller.steamcmd_acf_data = {}
    controller.workshop_acf_path = None
    controller.steamcmd_acf_path = ""
    controller.is_abort_requested = False

    # Mock the metadata_db_controller
    mock_aux = MagicMock()
    mock_session = MagicMock()
    mock_aux.Session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_aux.Session.return_value.__exit__ = MagicMock(return_value=False)
    controller.metadata_db_controller = mock_aux

    monkeypatch.setattr(
        MetadataController,
        "instance",
        classmethod(lambda cls, **kw: controller),
    )
    return controller


@pytest.fixture
def mock_steamcmd_interface(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch SteamcmdInterface.instance() to return a lightweight mock."""
    from app.utils.steam.steamcmd.wrapper import SteamcmdInterface

    mock_steamcmd = MagicMock(spec=SteamcmdInterface)
    mock_steamcmd.setup = True
    mock_steamcmd.steamcmd_appworkshop_acf_path = ""

    monkeypatch.setattr(
        SteamcmdInterface,
        "instance",
        classmethod(lambda cls: mock_steamcmd),
    )
    return mock_steamcmd
