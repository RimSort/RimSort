"""Drive the compiled updater with fixtures and supervised external processes."""

import os
import runpy
import shlex
import subprocess
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

PROBE_DIRECTORY = Path(__file__).resolve().parent
SHARED = runpy.run_path(str(PROBE_DIRECTORY / "appimage_probe.py"))
require = SHARED["require"]


def msi_process(root: Path, create: Callable[..., object]) -> Callable[..., object]:
    def supervised(command: object, **kwargs: object) -> object:
        if isinstance(command, list) and command and command[0] == "msiexec":
            require(not kwargs, "Unexpected MSI process options")
            require(
                command[1:2] == ["/i"]
                and command[3:]
                == [
                    "/passive",
                    "/norestart",
                    "/log",
                    str(root / "profile/logs/updater.log"),
                ],
                f"Unexpected MSI handoff: {command}",
            )
            staged = Path(command[2]).resolve(strict=True)
            require(staged.is_relative_to(root), "MSI staging escaped root")
            SHARED["report"](root, "msi-handoff.json", {"command": command})
            return create(
                [
                    os.environ["RIMSORT_UPGRADE_TEST_PYTHON"],
                    "-I",
                    str(PROBE_DIRECTORY / "upgrade_process.py"),
                    "msi",
                    str(root),
                    str(staged),
                ]
            )
        return create(command, **kwargs)

    return supervised


def linux_process(root: Path, create: Callable[..., object]) -> Callable[..., object]:
    def supervised(command: object, **kwargs: object) -> object:
        parts = (
            shlex.split(command)
            if isinstance(command, str) and "update.sh" in command
            else command
        )
        scripts = (
            [
                part
                for part in parts
                if isinstance(part, str) and Path(part).name == "update.sh"
            ]
            if isinstance(parts, list)
            else []
        )
        if scripts:
            require(
                Path(scripts[0]).resolve().is_relative_to(root),
                "Installer escaped root",
            )
            require(set(kwargs) <= {"shell", "cwd"}, "Unexpected installer options")
            request = root / "events/installer-command.json"
            SHARED["report"](
                root, request.name, {"command": command, "options": kwargs}
            )
            return create(
                [
                    os.environ["RIMSORT_UPGRADE_TEST_PYTHON"],
                    "-I",
                    str(PROBE_DIRECTORY / "upgrade_process.py"),
                    "installer",
                    str(root),
                    str(request),
                ],
                cwd=str(root),
            )
        return create(command, **kwargs)

    return supervised


def main(root: Path, executable: Path, mode: str, arguments: list[str]) -> None:
    from app.utils import app_info, update_utils

    shared = SHARED
    require = shared["require"]
    require(hasattr(app_info, "__compiled__"), "Application came from source")
    require(hasattr(update_utils, "__compiled__"), "Updater came from source")
    info = app_info.AppInfo()
    require(info.application_folder == executable.parent, "Wrong installation folder")
    require(info.app_storage_folder.is_relative_to(root), "Settings escaped test root")
    require(info.user_log_folder.is_relative_to(root), "Logs escaped test root")
    if mode == "configure":
        shared["configure_settings"](root)
        shared["report"](
            root,
            "configured.json",
            {
                "version": info.app_version,
                "backups": str(info.application_backups_folder),
            },
        )
        return

    if mode == "backup":
        source, destination = map(Path, arguments)
        require(source.resolve().is_relative_to(root), "Backup source escaped root")
        require(destination.resolve().is_relative_to(root), "Backup escaped root")
        update_utils._create_application_backup(source, destination)
        return

    kind, url, fault = arguments
    original_launch = update_utils.UpdateManager._launch_update_script

    def observed_launch(
        manager: update_utils.UpdateManager,
        source: Path,
        log: Path,
        elevation: bool,
        is_msi: bool = False,
    ) -> None:
        shared["report"](
            root, "handoff-requested.json", {"source": str(source), "is_msi": is_msi}
        )
        original_launch(manager, source, log, elevation, is_msi)

    setattr(update_utils.UpdateManager, original_launch.__name__, observed_launch)
    if kind == "msi":
        # mypy rejects directly replacing a class with a callable test boundary.
        setattr(subprocess, "Popen", msi_process(root, subprocess.Popen))  # noqa: B010
    elif sys.platform == "linux":
        setattr(subprocess, "Popen", linux_process(root, subprocess.Popen))  # noqa: B010
    shared["update"](root, url, kind, rejected=fault == "corrupt")


if __name__ == "__main__":
    mode_arg, root_arg, executable_arg, *remaining = sys.argv[1:]
    case_root = Path(root_arg).resolve(strict=True)
    installed = Path(executable_arg).resolve(strict=True)
    if not installed.is_relative_to(case_root):
        raise RuntimeError("Executable escaped test root")
    sys.modules["__main__"].__file__ = str(installed)
    sys.argv = [str(installed), "--dev", "--disable-updater"]
    common = SHARED

    def failed(
        kind: type[BaseException], error: BaseException, trace: TracebackType | None
    ) -> None:
        common["report"](
            case_root,
            "probe-error.json",
            {"traceback": "".join(traceback.format_exception(kind, error, trace))},
        )
        common["fail_fast"](kind, error, trace)

    sys.excepthook = failed
    main(case_root, installed, mode_arg, remaining)
