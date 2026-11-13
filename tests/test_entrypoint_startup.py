"""Exercise the real entrypoint with isolated multiprocessing state."""

import multiprocessing as mp
import os
import platform
import runpy
import subprocess
import sys
from logging import getLogger
from multiprocessing.context import DefaultContext
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.utils import log_setup
from app.views import dialogue


def _run_entrypoint(
    tmp_path: Path, compiled: bool, preset: str | None, system: str = "native"
) -> subprocess.CompletedProcess[str]:
    script = dedent(
        """
        import multiprocessing as mp
        import platform
        import runpy
        import sys
        import traceback
        import types

        compiled = sys.argv[1] == "compiled"
        preset = sys.argv[2]
        if sys.argv[3] != "native":
            platform.system = lambda: "Linux"
        system = platform.system()
        sys.argv = ["RimSort"]
        if preset != "unset":
            mp.set_start_method(preset)
        before = mp.get_start_method(allow_none=True)
        real_freeze_support = mp.freeze_support
        freeze_calls = []

        def freeze_support():
            freeze_calls.append(True)
            real_freeze_support()

        mp.freeze_support = freeze_support
        needs_freeze_support = compiled and system != "Linux"

        class Controller:
            def __init__(self):
                assert len(freeze_calls) == int(needs_freeze_support)
                after = mp.get_start_method(allow_none=True)
                if before is not None or not needs_freeze_support:
                    assert after == before
                else:
                    assert after in (None, mp.get_all_start_methods()[0])
                print("ENTRYPOINT_READY", flush=True)

            def run(self):
                if needs_freeze_support:
                    assert mp.get_start_method() == "spawn"
                    process = mp.Process(target=print, args=("SPAWN_CHILD_READY",))
                    process.start()
                    process.join(10)
                    if process.is_alive():
                        process.terminate()
                        process.join(5)
                        raise AssertionError("Spawned child did not exit")
                    assert process.exitcode == 0
                return 0

            def shutdown_watchdog(self):
                pass

        def fail_dialogue(*args, **kwargs):
            raise AssertionError("Startup attempted to display a fatal dialog")

        controller_module = types.ModuleType("app.controllers.app_controller")
        controller_module.AppController = Controller
        sys.modules[controller_module.__name__] = controller_module
        dialogue_module = types.ModuleType("app.views.dialogue")
        dialogue_module.show_fatal_error = fail_dialogue
        sys.modules[dialogue_module.__name__] = dialogue_module
        try:
            runpy.run_module(
                "app",
                run_name="__main__",
                init_globals={"__compiled__": True} if compiled else {},
                alter_sys=True,
            )
        except SystemExit as error:
            sys.exit(error.code)
        except BaseException:
            traceback.print_exc()
            sys.exit(1)
        """
    )
    env = os.environ.copy()
    env.update(RIMSORT_DEV="1", RIMSORT_DEV_DIR=str(tmp_path / "app-data"))
    for name in ("APPIMAGE", "APPDIR", "PYTHONPATH"):
        env.pop(name, None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "compiled" if compiled else "source",
            preset or "unset",
            system,
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("compiled", [False, True])
@pytest.mark.parametrize("preset", [None, "spawn"])
def test_entrypoint_preserves_context_and_reaches_controller(
    tmp_path: Path, compiled: bool, preset: str | None
) -> None:
    result = _run_entrypoint(tmp_path, compiled, preset)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ENTRYPOINT_READY" in result.stdout
    if compiled and sys.platform in ("darwin", "win32"):
        assert "SPAWN_CHILD_READY" in result.stdout


@pytest.mark.parametrize("preset", [None, "spawn"])
def test_linux_compiled_branch_leaves_context_untouched(
    tmp_path: Path, preset: str | None
) -> None:
    result = _run_entrypoint(tmp_path, True, preset, system="Linux")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ENTRYPOINT_READY" in result.stdout
    assert "SPAWN_CHILD_READY" not in result.stdout


@pytest.mark.parametrize("initialized", [False, True])
def test_compiled_entrypoint_uses_platform_context(
    monkeypatch: pytest.MonkeyPatch, initialized: bool
) -> None:
    global_method = mp.get_start_method(allow_none=True)
    locales_path = os.environ.get("QTWEBENGINE_LOCALES_PATH")
    exception_hook = sys.excepthook
    context = DefaultContext(mp.get_context("spawn"))
    if initialized:
        context.set_start_method("spawn")
    freeze = MagicMock(wraps=context.freeze_support)
    controller = MagicMock()
    controller.run.return_value = 0
    factory = MagicMock(return_value=controller)
    module = ModuleType("app.controllers.app_controller")
    fatal = MagicMock(side_effect=AssertionError("Unexpected fatal dialog"))

    with monkeypatch.context() as patch:
        patch.setattr(module, "AppController", factory, raising=False)
        patch.setitem(sys.modules, module.__name__, module)
        patch.setattr(sys, "argv", ["RimSort"])
        patch.setattr(sys, "excepthook", sys.excepthook)
        patch.setenv("QTWEBENGINE_LOCALES_PATH", "")
        patch.setattr(platform, "system", lambda: "Darwin")
        patch.setattr(mp, "freeze_support", freeze)
        patch.setattr(mp, "set_start_method", context.set_start_method)
        patch.setattr(log_setup, "setup_logging", MagicMock())
        patch.setattr(getLogger("watchdog.observers.fsevents"), "setLevel", MagicMock())
        patch.setattr(dialogue, "show_fatal_error", fatal)

        with pytest.raises(SystemExit) as result:
            runpy.run_module(
                "app",
                run_name="__main__",
                init_globals={"__compiled__": True},
                alter_sys=True,
            )

        assert result.value.code in (None, 0)
        freeze.assert_called_once_with()
        factory.assert_called_once_with()
        controller.run.assert_called_once_with()
        controller.shutdown_watchdog.assert_called_once_with()
        fatal.assert_not_called()
        assert context.get_start_method() == "spawn"

    assert mp.get_start_method(allow_none=True) == global_method
    assert os.environ.get("QTWEBENGINE_LOCALES_PATH") == locales_path
    assert sys.excepthook is exception_hook
