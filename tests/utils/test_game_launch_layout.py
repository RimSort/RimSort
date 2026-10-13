from pathlib import Path
from unittest.mock import Mock

import pytest

from app.utils import generic
from tests.game_layout_fixtures import make_game_install


@pytest.fixture
def launch_spy(monkeypatch: pytest.MonkeyPatch) -> Mock:
    spy = Mock(return_value=(123, ["mock process"]))
    monkeypatch.setattr(generic, "launch_process", spy)
    return spy


@pytest.mark.parametrize(
    ("system", "executable_name"), [("Linux", "RimWorld"), ("Windows", "RimWorld.exe")]
)
def test_native_17_launch_uses_new_executable_and_content_cwd(
    launch_spy: Mock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    executable_name: str,
) -> None:
    install = make_game_install(
        tmp_path / "RimWorld", "linux" if system == "Linux" else "windows"
    )
    monkeypatch.setattr(generic.platform, "system", lambda: system)
    generic.launch_game_process(install.launch_location, "--test")
    assert launch_spy.call_args.args[:3] == (
        str(install.content_root / executable_name),
        ["--test"],
        str(install.content_root),
    )


def test_direct_process_cwd_uses_resolver_not_raw_launch_location(
    launch_spy: Mock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    binary = install.launch_location / "RimWorld"
    binary.write_bytes(b"synthetic native executable")
    binary.chmod(0o755)
    monkeypatch.setattr(generic.platform, "system", lambda: "Linux")
    generic.launch_game_process(install.launch_location)
    assert launch_spy.call_args.args[0] == str(binary)
    assert launch_spy.call_args.args[2] == str(install.content_root)


def test_unresolved_content_uses_only_validated_executable_parent(
    launch_spy: Mock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = tmp_path / "Selected"
    game.mkdir()
    binary = game / "RimWorld"
    binary.write_bytes(b"game")
    binary.chmod(0o755)
    monkeypatch.setattr(generic.platform, "system", lambda: "Linux")
    generic.launch_game_process(game)
    assert launch_spy.call_args.args[2] == str(binary.parent)


def test_macos_keeps_selected_bundle_and_open_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    monkeypatch.setattr(generic.platform, "system", lambda: "Darwin")
    process = Mock(pid=123)
    popen = Mock(return_value=process)
    monkeypatch.setattr(generic.subprocess, "Popen", popen)
    generic.launch_game_process(install.launch_location, "--test")
    assert popen.call_args.args[0] == [
        "open",
        str(install.launch_location),
        "--args",
        "--test",
    ]
    assert "cwd" not in popen.call_args.kwargs
