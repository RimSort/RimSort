"""Asynchronous process transport for conflict detector workers."""

import json
import sys
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTimer, Signal

from app.services.conflict_detector_worker import _validate_report


class ConflictDetectorRunner(QObject):
    # Qt's int signal type narrows Python integers to signed 32 bits.
    progress = Signal(str, object, object, str)
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._request_id = ""
        self._stdout = bytearray()
        self.stderr = bytearray()
        self._pending = b""
        self._terminal: dict[str, Any] | None = None
        self._problem = ""
        self._cancelled = False
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown)

    def _command(self) -> tuple[str, list[str]]:
        compiled = "__compiled__" in globals() or bool(getattr(sys, "frozen", False))
        return sys.executable, ["--rcd-worker"] if compiled else [
            "-m",
            "app",
            "--rcd-worker",
        ]

    def start(self, request: dict[str, object]) -> None:
        if self._process is not None:
            raise RuntimeError("A conflict detector worker is already active")
        request_id = request.get("id")
        if not isinstance(request_id, str):
            raise TypeError("Worker request id must be a string")
        pending = json.dumps(request, ensure_ascii=False).encode("utf-8")
        self._request_id = request_id
        self._stdout = bytearray()
        self.stderr = bytearray()
        self._pending = pending
        self._terminal = None
        self._problem = ""
        self._cancelled = False
        process = QProcess(self)
        self._process = process
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.started.connect(lambda: self._write(process, request_id))
        process.bytesWritten.connect(lambda _: self._write(process, request_id))
        process.readyReadStandardOutput.connect(
            lambda: self._drain(process, request_id)
        )
        process.readyReadStandardError.connect(lambda: self._drain(process, request_id))
        process.finished.connect(
            lambda code, status: self._finished(process, request_id, code, status)
        )
        process.errorOccurred.connect(
            lambda error: self._error(process, request_id, error)
        )
        program, args = self._command()
        process.start(program, args)

    def _matches(self, process: QProcess, request_id: str) -> bool:
        return self._process is process and self._request_id == request_id

    def _write(self, process: QProcess, request_id: str) -> None:
        if not self._matches(process, request_id) or self._cancelled:
            return
        if self._pending:
            count = process.write(self._pending)
            if count < 0:
                self._problem = process.errorString()
                process.kill()
                return
            self._pending = self._pending[count:]
        if not self._pending:
            process.closeWriteChannel()

    def _drain(self, process: QProcess, request_id: str) -> None:
        if not self._matches(process, request_id):
            return
        self.stderr.extend(process.readAllStandardError().data())
        chunk = bytes(process.readAllStandardOutput().data())
        start = 0
        while True:
            end = chunk.find(b"\n", start)
            if end < 0:
                self._stdout.extend(chunk[start:])
                break
            self._stdout.extend(chunk[start:end])
            line = bytes(self._stdout)
            self._stdout.clear()
            start = end + 1
            if self._cancelled or self._problem:
                continue
            try:
                frame = json.loads(line)
                if (
                    not isinstance(frame, dict)
                    or frame.get("protocol") != 1
                    or frame.get("id") != request_id
                    or self._terminal is not None
                ):
                    raise ValueError("Invalid, duplicate or mismatched worker frame")
                kind = frame.get("kind")
                if kind == "progress":
                    current, total, phase = (
                        frame.get("current"),
                        frame.get("total"),
                        frame.get("phase"),
                    )
                    if (
                        type(current) is not int
                        or type(total) is not int
                        or not isinstance(phase, str)
                    ):
                        raise ValueError("Invalid progress frame")
                    self.progress.emit(request_id, current, total, phase)
                elif kind == "report" and isinstance(frame.get("report"), dict):
                    _validate_report(frame["report"])
                    self._terminal = frame
                elif kind == "error" and isinstance(frame.get("error"), str):
                    self._terminal = frame
                else:
                    raise ValueError("Invalid worker frame")
            except (TypeError, ValueError, UnicodeError) as exc:
                self._problem = str(exc)
                process.kill()

    def _finished(
        self, process: QProcess, request_id: str, code: int, status: QProcess.ExitStatus
    ) -> None:
        if not self._matches(process, request_id):
            return
        self._drain(process, request_id)
        terminal = self._terminal
        problem = self._problem
        if self._stdout:
            problem = problem or "Incomplete worker frame"
        stderr = bytes(self.stderr).decode("utf-8", errors="replace")
        cancelled = self._cancelled
        self._process = None
        process.deleteLater()
        if cancelled:
            self.cancelled.emit(request_id)
        elif problem:
            self.failed.emit(request_id, problem + ("\n" + stderr if stderr else ""))
        elif terminal is not None and terminal["kind"] == "error":
            self.failed.emit(
                request_id, terminal["error"] + ("\n" + stderr if stderr else "")
            )
        elif (
            status == QProcess.ExitStatus.NormalExit
            and code == 0
            and terminal is not None
        ):
            self.succeeded.emit(request_id, terminal["report"])
        else:
            self.failed.emit(
                request_id,
                f"Worker exited without a successful report (exit {code})"
                + ("\n" + stderr if stderr else ""),
            )

    def _error(
        self, process: QProcess, request_id: str, error: QProcess.ProcessError
    ) -> None:
        if (
            self._matches(process, request_id)
            and error == QProcess.ProcessError.FailedToStart
        ):
            self._process = None
            message = process.errorString()
            process.deleteLater()
            if self._cancelled:
                self.cancelled.emit(request_id)
            else:
                self.failed.emit(request_id, message)

    def cancel(self) -> None:
        process = self._process
        if process is None or self._cancelled:
            return
        request_id = self._request_id
        self._cancelled = True
        process.terminate()
        QTimer.singleShot(2000, lambda: self._kill_if_current(process, request_id))

    def _kill_if_current(self, process: QProcess, request_id: str) -> None:
        if (
            self._matches(process, request_id)
            and process.state() != QProcess.ProcessState.NotRunning
        ):
            process.kill()

    def _shutdown(self) -> None:
        if self._process is not None:
            self._cancelled = True
            self._process.kill()
