import json
import os
import sys
import time
from collections.abc import Buffer
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from tests.conflict_detector_fixtures import make_report


def test_runner_is_available() -> None:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    assert ConflictDetectorRunner is not None


def run_child(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    script: str,
    request: dict[str, object],
) -> tuple[Any, list[Any], list[Any], list[Any]]:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "child.py"
    child.write_text(script)
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    success: list[Any] = []
    failure: list[Any] = []
    progress: list[Any] = []
    runner.succeeded.connect(lambda *args: success.append(args))
    runner.failed.connect(lambda *args: failure.append(args))
    runner.progress.connect(lambda *args: progress.append(args))
    runner.start(request)
    qtbot.waitUntil(lambda: bool(success or failure), timeout=20000)
    return runner, success, failure, progress


def test_split_coalesced_large_report_and_stderr(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = make_report("error", False)
    report["padding"] = "a" * (24 * 1024 * 1024)
    payload = json.dumps(report)
    script = f"""import sys,json
req=json.load(sys.stdin)
sys.stderr.write('x'*100000); sys.stderr.flush()
progress=json.dumps(dict(protocol=1,id=req['id'],kind='progress',current=1,total=2,phase='xml'))+'\\n'
sys.stdout.write(progress[:9]);sys.stdout.flush()
sys.stdout.write(progress[9:]+json.dumps(dict(protocol=1,id=req['id'],kind='report',report=json.loads({payload!r})))+'\\n');sys.stdout.flush()
"""
    runner, success, failure, progress = run_child(
        qtbot,
        monkeypatch,
        tmp_path,
        script,
        {"protocol": 1, "id": "scan", "config": {"mod_paths": [], "ordered": True}},
    )
    assert not failure
    assert progress == [("scan", 1, 2, "xml")]
    assert len(success[0][1]["padding"]) == 24 * 1024 * 1024
    assert len(runner.stderr) == 100000


def test_framing_does_not_rescan_or_repartition_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conflict_detector_runner as module

    work: list[int] = []

    class TrackingBuffer(bytearray):
        def __contains__(self, item: Any) -> bool:
            work.append(len(self))
            return super().__contains__(item)

        def partition(self, sep: Buffer, /) -> Any:
            work.append(len(self))
            return super().partition(sep)

    class Result:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def data(self) -> bytes:
            return self._data

    class FakeProcess:
        chunk = b""

        def readAllStandardOutput(self) -> Result:
            return Result(self.chunk)

        def readAllStandardError(self) -> Result:
            return Result(b"")

        def kill(self) -> None:
            raise AssertionError("unexpected kill")

    monkeypatch.setattr(module, "bytearray", TrackingBuffer, raising=False)
    runner = module.ConflictDetectorRunner()
    process = FakeProcess()
    monkeypatch.setattr(runner, "_process", process)
    runner._request_id = "linear"
    message = (
        json.dumps(
            {
                "protocol": 1,
                "id": "linear",
                "kind": "progress",
                "current": 0,
                "total": 1,
                "phase": "x" * 4096,
            }
        ).encode()
        + b"\n"
    )
    for byte in message:
        process.chunk = bytes([byte])
        runner._drain(process, "linear")  # type: ignore[arg-type]
    frame = (
        json.dumps(
            {
                "protocol": 1,
                "id": "linear",
                "kind": "progress",
                "current": 0,
                "total": 1,
                "phase": "x",
            }
        ).encode()
        + b"\n"
    )
    process.chunk = frame * 2000
    runner._drain(process, "linear")  # type: ignore[arg-type]
    assert sum(work) <= 4 * (len(message) + len(process.chunk))


def test_progress_u32_values_are_not_truncated(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = """import sys,json
r=json.load(sys.stdin)
for n in (0,2147483647,2147483648,4294967295):
 print(json.dumps(dict(protocol=1,id=r['id'],kind='progress',current=n,total=n,phase='scan')))
print(json.dumps(dict(protocol=1,id=r['id'],kind='error',error='done')))
"""
    _, success, failure, progress = run_child(
        qtbot, monkeypatch, tmp_path, script, {"protocol": 1, "id": "u32", "config": {}}
    )
    assert not success and failure[0][1] == "done"
    assert progress == [
        ("u32", n, n, "scan") for n in (0, 2147483647, 2147483648, 4294967295)
    ]
    assert all(type(item[1]) is int and type(item[2]) is int for item in progress)


def test_malformed_nested_report_never_succeeds(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = make_report("error", False)
    report["diagnostics"][0]["message"] = {}
    payload = json.dumps(report)
    script = f"import sys,json; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id=r['id'],kind='report',report=json.loads({payload!r}))))"
    _, success, failure, _ = run_child(
        qtbot, monkeypatch, tmp_path, script, {"protocol": 1, "id": "bad", "config": {}}
    )
    assert not success and len(failure) == 1


def test_large_request_and_progress(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = """import sys,json
req=json.load(sys.stdin)
print(json.dumps(dict(protocol=1,id=req['id'],kind='progress',current=len(req['config']['mod_paths'][0]),total=1,phase='x'*9000000)))
print(json.dumps(dict(protocol=1,id=req['id'],kind='error',error='done')))
"""
    _, success, failure, progress = run_child(
        qtbot,
        monkeypatch,
        tmp_path,
        script,
        {
            "protocol": 1,
            "id": "large",
            "config": {"mod_paths": ["/" + "x" * 9000000], "ordered": True},
        },
    )
    assert not success and failure[0][1] == "done"
    assert progress[0][1] == 9000001 and len(progress[0][3]) == 9000000


@pytest.mark.parametrize(
    "script",
    [
        "import sys; sys.stdin.read(); sys.exit(13)",
        "import sys; sys.stdin.read(); print('bad')",
        "import sys,json; r=json.load(sys.stdin); m=dict(protocol=1,id=r['id'],kind='error',error='bad'); print(json.dumps(m));print(json.dumps(m))",
        "import sys,json; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id='old',kind='error',error='bad')))",
        "import sys,json; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id=r['id'],kind='report',report={})))",
    ],
)
def test_bad_child_fails_once(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, script: str
) -> None:
    _, success, failure, _ = run_child(
        qtbot,
        monkeypatch,
        tmp_path,
        script,
        {"protocol": 1, "id": "current", "config": {}},
    )
    assert not success and len(failure) == 1 and failure[0][0] == "current"


def test_cancel_and_stale_timer(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "wait.py"
    child.write_text("import sys,time; sys.stdin.read(); time.sleep(30)")
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    cancelled: list[str] = []
    runner.cancelled.connect(cancelled.append)
    runner.start({"protocol": 1, "id": "old", "config": {}})
    old = runner._process
    assert old is not None
    runner.cancel()
    qtbot.waitUntil(lambda: cancelled == ["old"], timeout=10000)
    runner.start({"protocol": 1, "id": "new", "config": {}})
    runner._drain(old, "old")
    runner._kill_if_current(old, "old")
    assert runner._process is not None
    runner.cancel()
    qtbot.waitUntil(lambda: cancelled == ["old", "new"], timeout=10000)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX signals")
def test_real_child_crash_reports_crash_exit(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtCore import QProcess

    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "crash.py"
    child.write_text(
        "import os,signal,sys; sys.stdin.read(); os.kill(os.getpid(), signal.SIGKILL)"
    )
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    failures: list[object] = []
    exits: list[object] = []
    runner.failed.connect(lambda *args: failures.append(args))
    runner.start({"protocol": 1, "id": "crash", "config": {}})
    process = runner._process
    assert process is not None
    process.finished.connect(lambda code, status: exits.append((code, status)))
    qtbot.waitUntil(lambda: bool(failures) and bool(exits), timeout=10000)
    assert len(failures) == 1
    assert exits[0][1] == QProcess.ExitStatus.CrashExit  # type: ignore[index]


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX SIGTERM semantics")
def test_escalation_kills_only_cancelled_child(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtCore import QProcess

    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "ignore_term.py"
    child.write_text("""import json,signal,sys,time
r=json.load(sys.stdin)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print(json.dumps(dict(protocol=1,id=r['id'],kind='progress',current=0,total=1,phase='ready')),flush=True)
time.sleep(30)
""")
    first = ConflictDetectorRunner()
    other = ConflictDetectorRunner()
    monkeypatch.setattr(first, "_command", lambda: (sys.executable, [str(child)]))
    monkeypatch.setattr(other, "_command", lambda: (sys.executable, [str(child)]))
    ready: list[str] = []
    cancelled: list[str] = []
    exits: list[object] = []
    first.progress.connect(lambda request_id, *_: ready.append(request_id))
    other.progress.connect(lambda request_id, *_: ready.append(request_id))
    first.cancelled.connect(cancelled.append)
    first.start({"protocol": 1, "id": "first", "config": {}})
    other.start({"protocol": 1, "id": "other", "config": {}})
    first_process = first._process
    other_process = other._process
    assert first_process is not None and other_process is not None
    first_process.finished.connect(lambda code, status: exits.append((code, status)))
    try:
        qtbot.waitUntil(lambda: len(ready) == 2, timeout=10000)
        started = time.monotonic()
        first.cancel()
        qtbot.waitUntil(lambda: bool(cancelled) and bool(exits), timeout=10000)
        assert time.monotonic() - started >= 1.7
        assert cancelled == ["first"]
        assert exits[0][1] == QProcess.ExitStatus.CrashExit  # type: ignore[index]
        assert other._process is other_process
        assert other_process.state() == QProcess.ProcessState.Running
    finally:
        other._shutdown()
        first._shutdown()
        qtbot.waitUntil(
            lambda: other._process is None and first._process is None, timeout=10000
        )


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX termination semantics")
def test_stale_real_timer_cannot_kill_replacement(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtCore import QProcess, QTimer

    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "ready.py"
    child.write_text(
        "import json,sys,time; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id=r['id'],kind='progress',current=0,total=1,phase='ready')),flush=True); time.sleep(30)"
    )
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    ready: list[str] = []
    cancelled: list[str] = []
    expired: list[bool] = []
    runner.progress.connect(lambda request_id, *_: ready.append(request_id))
    runner.cancelled.connect(cancelled.append)
    try:
        runner.start({"protocol": 1, "id": "old", "config": {}})
        qtbot.waitUntil(lambda: ready == ["old"], timeout=10000)
        runner.cancel()
        qtbot.waitUntil(lambda: cancelled == ["old"], timeout=10000)
        runner.start({"protocol": 1, "id": "new", "config": {}})
        qtbot.waitUntil(lambda: ready == ["old", "new"], timeout=10000)
        replacement = runner._process
        assert replacement is not None
        QTimer.singleShot(2400, lambda: expired.append(True))
        qtbot.waitUntil(lambda: bool(expired), timeout=10000)
        assert runner._process is replacement
        assert replacement.state() == QProcess.ProcessState.Running
    finally:
        runner._shutdown()
        qtbot.waitUntil(lambda: runner._process is None, timeout=10000)


def test_shutdown_kills_and_reaps_worker(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "wait.py"
    child.write_text(
        "import json,sys,time; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id=r['id'],kind='progress',current=0,total=1,phase='ready')),flush=True); time.sleep(30)"
    )
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    ready: list[object] = []
    cancelled: list[str] = []
    runner.progress.connect(lambda *args: ready.append(args))
    runner.cancelled.connect(cancelled.append)
    runner.start({"protocol": 1, "id": "shutdown", "config": {}})
    try:
        qtbot.waitUntil(lambda: bool(ready), timeout=10000)
        runner._shutdown()
        qtbot.waitUntil(lambda: runner._process is None, timeout=10000)
        assert cancelled == ["shutdown"]
    finally:
        if runner._process is not None:
            runner._shutdown()
            qtbot.waitUntil(lambda: runner._process is None, timeout=10000)


def test_cancel_with_partial_frame_and_reject_overlapping_start(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    child = tmp_path / "partial.py"
    child.write_text("""import sys,json,time
r=json.load(sys.stdin)
print(json.dumps(dict(protocol=1,id=r['id'],kind='progress',current=1,total=2,phase='xml')), flush=True)
sys.stdout.write('{"protocol":1');sys.stdout.flush()
time.sleep(30)
""")
    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (sys.executable, [str(child)]))
    progress: list[object] = []
    cancelled: list[str] = []
    failed: list[object] = []
    runner.progress.connect(lambda *args: progress.append(args))
    runner.cancelled.connect(cancelled.append)
    runner.failed.connect(lambda *args: failed.append(args))
    request = {"protocol": 1, "id": "a", "config": {}}
    runner.start(request)
    with pytest.raises(RuntimeError):
        runner.start(request)
    qtbot.waitUntil(lambda: bool(progress), timeout=10000)
    runner.cancel()
    qtbot.waitUntil(lambda: bool(cancelled), timeout=10000)
    assert cancelled == ["a"] and not failed


def test_nonzero_error_keeps_stderr(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = "import sys,json; r=json.load(sys.stdin); sys.stderr.write('x'*100000); sys.stderr.flush(); print(json.dumps(dict(protocol=1,id=r['id'],kind='error',error='native error'))); sys.exit(7)"
    runner, success, failure, _ = run_child(
        qtbot, monkeypatch, tmp_path, script, {"protocol": 1, "id": "x", "config": {}}
    )
    assert not success and failure[0][1] == "native error\n" + "x" * 100000
    assert len(runner.stderr) == 100000


def test_failed_start(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.services.conflict_detector_runner import ConflictDetectorRunner

    runner = ConflictDetectorRunner()
    monkeypatch.setattr(runner, "_command", lambda: (str(tmp_path / "missing"), []))
    errors: list[tuple[str, str]] = []
    runner.failed.connect(lambda *args: errors.append(args))
    runner.start({"protocol": 1, "id": "missing", "config": {}})
    qtbot.waitUntil(lambda: bool(errors), timeout=10000)
    assert len(errors) == 1 and errors[0][0] == "missing"


def test_nonzero_report_rejected(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = json.dumps(make_report("error", False))
    script = f"import sys,json; r=json.load(sys.stdin); print(json.dumps(dict(protocol=1,id=r['id'],kind='report',report=json.loads({report!r})))); sys.exit(4)"
    _, success, failure, _ = run_child(
        qtbot, monkeypatch, tmp_path, script, {"protocol": 1, "id": "x", "config": {}}
    )
    assert not success and failure[0][0] == "x"
