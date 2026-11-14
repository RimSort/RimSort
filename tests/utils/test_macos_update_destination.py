"""Regression tests for macOS updater destinations after script relocation."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.utils.update_utils import ScriptConfig, UpdateManager


@pytest.mark.parametrize("needs_elevation", [False, True])
def test_macos_launcher_preserves_bundle_destination(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, needs_elevation: bool
) -> None:
    bundle = tmp_path / "Applications" / "Custom RimSort.app"
    executable = bundle / "Contents" / "MacOS" / "RimSort"
    executable.parent.mkdir(parents=True)
    script = executable.with_name("update.sh")
    script.write_text("#!/bin/bash\n")
    monkeypatch.setattr(sys, "argv", [str(executable)])
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    config = ScriptConfig("update.sh", None, "Darwin")
    build_args = MagicMock(wraps=config._build_platform_args)
    monkeypatch.setattr(config, "_build_platform_args", build_args)
    manager = MagicMock(spec=UpdateManager)
    manager._system = "Darwin"
    manager._script_configs = {"Darwin": config}
    source = tmp_path / "download"
    log = tmp_path / "update.log"

    script_path, args, _, install_dir = UpdateManager._get_script_info(
        manager, source, log, needs_elevation
    )
    popen = MagicMock()
    monkeypatch.setattr("app.utils.update_utils.subprocess.Popen", popen)
    UpdateManager._launch_posix_update_script(
        manager, script_path, args, needs_elevation, source, log, install_dir
    )

    command = popen.call_args.args[0]
    argv = shlex.split(command) if isinstance(command, str) else command
    assert argv[:2] == ["osascript", "-e"]
    assert len(argv) == 3
    launched_args = build_args.call_args.args[0]
    assert install_dir == bundle
    assert launched_args[1:] == [str(source), str(log), str(bundle)]
    launched_script = Path(launched_args[0])
    assert launched_script.read_bytes() == script.read_bytes()
    assert (launched_script != script) is needs_elevation


@pytest.fixture
def script_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    rsync = shutil.which("rsync")
    if os.name != "posix" or shutil.which("bash") is None or rsync is None:
        pytest.skip("Requires a POSIX shell and rsync")
    commands = tmp_path / "commands"
    commands.mkdir()
    trace = tmp_path / "commands.log"
    bodies = {
        "uname": "echo Darwin",
        "killall": "exit 1",
        "sleep": ":",
        "open": ":",
        "pgrep": ":",
        "rsync": f'exec {shlex.quote(rsync)} "$@"',
    }
    for name, body in bodies.items():
        command = commands / name
        command.write_text(
            '#!/bin/bash\nprintf "%s\\n" "$0" >> "$COMMAND_TRACE"\n' + body + "\n"
        )
        command.chmod(0o755)
    monkeypatch.delenv("APPIMAGE", raising=False)
    return {
        **os.environ,
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "COMMAND_TRACE": str(trace),
    }


def _bundle(path: Path, contents: str) -> Path:
    executable = path / "Contents" / "MacOS" / "RimSort"
    executable.parent.mkdir(parents=True)
    executable.write_text(contents)
    return executable


@pytest.mark.parametrize("relocated", [False, True])
@pytest.mark.parametrize(
    "name", ["RimSort.app", "Custom RimSort.app", "RimSort $ & ' \" \\.app"]
)
def test_script_updates_explicit_bundle(
    tmp_path: Path, script_environment: dict[str, str], relocated: bool, name: str
) -> None:
    destination = tmp_path / "installed apps" / name
    executable = _bundle(destination, "old")
    sibling = tmp_path / "installed apps" / "Another.app"
    sibling_executable = _bundle(sibling, "unrelated")
    source = tmp_path / "download"
    _bundle(source / "RimSort.app", "new")
    script_dir = (
        tmp_path / "relocated" / "nested" / "scripts"
        if relocated
        else executable.parent
    )
    script_dir.mkdir(parents=True, exist_ok=True)
    script = script_dir / "update.sh"
    shutil.copyfile(Path(__file__).parents[2] / "update.sh", script)

    result = subprocess.run(
        ["bash", str(script), str(source), "", str(destination)],
        check=False,
        env=script_environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert executable.read_text() == "new"
    assert sibling_executable.read_text() == "unrelated"
    assert not (tmp_path / "relocated" / "RimSort.app").exists()
    assert f"Target: {destination}" in result.stdout


@pytest.mark.parametrize(
    "invalid_destination",
    [
        "",
        "/",
        "/Applications",
        "relative/RimSort.app",
        "missing.app",
        "empty.app",
        "not-a-bundle",
    ],
)
def test_script_rejects_invalid_destination_before_stopping_app(
    tmp_path: Path,
    script_environment: dict[str, str],
    invalid_destination: str,
) -> None:
    source = tmp_path / "download"
    source.mkdir()
    (source / "marker").write_text("preserve")
    invalid = (
        str(tmp_path / invalid_destination)
        if invalid_destination in {"missing.app", "empty.app", "not-a-bundle"}
        else invalid_destination
    )
    if invalid_destination == "empty.app":
        Path(invalid).mkdir()
    elif invalid_destination == "not-a-bundle":
        _bundle(Path(invalid), "preserve")
    script = tmp_path / "relocated" / "nested" / "scripts" / "update.sh"
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[2] / "update.sh", script)

    result = subprocess.run(
        ["bash", str(script), str(source), "", invalid],
        check=False,
        env=script_environment,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode != 0
    trace = Path(script_environment["COMMAND_TRACE"]).read_text()
    assert "killall" not in trace
    assert "rsync" not in trace
    assert (source / "marker").read_text() == "preserve"


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native AppleScript")
@pytest.mark.parametrize("needs_elevation", [False, True])
@pytest.mark.parametrize(
    "bundle_name",
    [
        "RimSort.app",
        "Custom RimSort.app",
        "RimSort's.app",
        'RimSort "copy".app',
        "RimSort\\copy.app",
        "RimSort $ & $(touch injected).app",
    ],
)
def test_macos_serialized_command_preserves_arguments(
    tmp_path: Path, needs_elevation: bool, bundle_name: str
) -> None:
    commands = tmp_path / "commands"
    commands.mkdir()
    bodies = {
        "osascript": (
            '[ "$#" -eq 2 ] || exit 31\n'
            'expression="${2#tell app \\"Terminal\\" to do script }"\n'
            'command=$(/usr/bin/osascript -e "return $expression") || exit 32\n'
            'exec /bin/bash -c "$command"\n'
        ),
        "sudo": 'exec "$@"\n',
    }
    for name, body in bodies.items():
        command = commands / name
        command.write_text("#!/bin/bash\n" + body)
        command.chmod(0o755)
    script = tmp_path / "update 'script'.sh"
    script.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > "$ARG_CAPTURE"\n')
    capture = tmp_path / "arguments"
    source = tmp_path / "download"
    log = tmp_path / "update.log"
    destination = tmp_path / bundle_name
    config = ScriptConfig("update.sh", None, "Darwin")
    args = config.get_args(script, source, log, needs_elevation, destination)

    result = subprocess.run(
        args,
        shell=isinstance(args, str),
        check=False,
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "ARG_CAPTURE": str(capture),
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert capture.exists(), result.stdout + result.stderr
    assert capture.read_bytes().split(b"\0") == [
        os.fsencode(source),
        os.fsencode(log),
        os.fsencode(destination),
        b"",
    ]
    assert not (tmp_path / "injected").exists()
