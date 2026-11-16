"""Bootstrap a packaged GUI to exercise its real AppImage update orchestration."""

import json
import os
import sys
import traceback
from pathlib import Path
from types import TracebackType


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def report(root: Path, name: str, data: dict[str, object]) -> None:
    destination = root / "events" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(destination)


def configure(root: Path) -> None:
    from app.models.settings import Settings
    from app.utils import app_info

    require(hasattr(app_info, "__compiled__"), "Probe imported source application")
    info = app_info.AppInfo()
    image = info.appimage_path
    if image is None or not image.is_relative_to(root):
        raise RuntimeError("Wrong AppImage path")
    require(info.app_storage_folder.is_relative_to(root), "Profile escaped test root")
    require(info.user_log_folder.is_relative_to(root), "Logs escaped test root")
    require(Path(os.environ["APPDIR"]).is_relative_to(root), "Mount escaped test root")
    require(
        image.with_suffix(".AppImage.bak").is_file(), "Helper deleted recovery copy"
    )
    settings = Settings()
    settings.language = "en_US"
    settings.check_for_update_startup = False
    settings.update_databases_on_startup = False
    settings.github_update_check_enabled = False
    settings.steam_mods_update_check = False
    settings.watchdog_toggle = False
    settings.auto_load_player_log_on_startup = False
    settings.debug_logging_enabled = True
    instance = settings.instances[settings.current_instance]
    instance.initial_setup = False
    instance.steamcmd_ignore = True
    for name, directory in (
        ("game_folder", "game"),
        ("config_folder", "config"),
        ("local_folder", "local"),
        ("workshop_folder", "workshop"),
        ("steamcmd_install_path", "steamcmd"),
    ):
        folder = root / "fixture" / directory
        folder.mkdir(parents=True, exist_ok=True)
        setattr(instance, name, str(folder))
    core = root / "fixture/game/Data/Core/About"
    core.mkdir(parents=True)
    (core / "About.xml").write_text(
        "<ModMetaData><name>Core</name><packageId>ludeon.rimworld</packageId>"
        "<supportedVersions><li>1.6</li></supportedVersions></ModMetaData>"
    )
    (root / "fixture/game/Version.txt").write_text("1.6.0 rev0")
    (root / "fixture/config/ModsConfig.xml").write_text(
        "<ModsConfigData><version>1.6.0</version><activeMods>"
        "<li>ludeon.rimworld</li></activeMods></ModsConfigData>"
    )
    settings.save()
    report(
        root,
        "configured.json",
        {
            "version": info.app_version,
            "database": str(settings.aux_db_path),
            "mount": os.environ["APPDIR"],
        },
    )


def update(root: Path, url: str) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox

    from app.controllers.app_controller import AppController
    from app.utils import update_utils
    from app.views import dialogue

    require(hasattr(update_utils, "__compiled__"), "Updater is not compiled")
    controller = AppController()
    original = controller.main_window.initialize_content
    command_timer = QTimer(controller)
    command_timer.setInterval(25)

    def unexpected(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"Unexpected bootstrap dialog: {args}, {kwargs}")

    def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        require(kwargs.get("title") == "Update downloaded", "Unexpected confirmation")
        report(root, "confirmed.json", {"accepted": True})
        return QMessageBox.StandardButton.Yes

    dialogue.show_warning = unexpected
    dialogue.show_fatal_error = unexpected
    dialogue.show_dialogue_conditional = confirm

    def begin_update() -> None:
        if not (root / "events/begin").exists():
            return
        command_timer.stop()
        content = controller.main_window.main_content_panel
        manager = update_utils.UpdateManager(
            controller.settings, content, content.mod_info_panel
        )
        try:
            manager._perform_update(url, "v99.0.0", False, is_appimage=True)
        except SystemExit as error:
            require(error.code in (None, 0), "Updater requested an error exit")
            controller.app.quit()
        else:
            raise RuntimeError("Update returned without installer handoff")

    command_timer.timeout.connect(begin_update)

    def ready() -> None:
        require(controller.main_window.isVisible(), "Bootstrap window is closed")
        require(controller.metadata_controller.mods_metadata, "Core was not scanned")
        report(root, "ready.json", {"pid": os.getpid()})
        command_timer.start()

    def initial_content(is_initial: bool = True) -> None:
        original(is_initial=is_initial)
        QTimer.singleShot(0, ready)

    def watchdog() -> None:
        raise RuntimeError("Packaged update bootstrap timed out")

    setattr(controller.main_window, original.__name__, initial_content)
    QTimer.singleShot(120000, watchdog)
    result = controller.run()
    controller.shutdown_watchdog()
    require(result == 0, "Bootstrap exited with a nonzero GUI result")


def fail_fast(
    kind: type[BaseException], error: BaseException, trace: TracebackType | None
) -> None:
    traceback.print_exception(kind, error, trace)
    sys.stderr.flush()
    os._exit(73)


if __name__ == "__main__":
    sys.excepthook = fail_fast
    require(sys.platform == "linux", "Packaged AppImage probe requires Linux")
    mode, root_arg, *rest = sys.argv[1:]
    case_root = Path(root_arg).resolve()
    # The existing helper entrypoint executes this file as __main__.
    sys.modules["__main__"].__file__ = str(Path("/proc/self/exe").resolve())
    sys.argv = [str(Path("/proc/self/exe").resolve()), "--dev", "--disable-updater"]
    if mode == "configure":
        configure(case_root)
    elif mode == "update":
        update(case_root, rest[0])
    else:
        raise ValueError(f"Unknown probe mode: {mode}")
