from pathlib import Path
from re import compile
from typing import Any
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QProcess

from app.windows.runner_panel import RunnerPanel


def _make_steamcmd_panel(tmp_path: Path, *, system: str = "Windows") -> Any:
    panel = RunnerPanel.__new__(RunnerPanel)
    panel.ansi_escape = compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    panel.system = system
    panel.previous_line = ""
    panel.steamcmd_current_pfid = ""
    panel.steamcmd_download_tracking = []
    panel.login_error = False
    panel.text = MagicMock()
    panel.progress_bar = MagicMock()
    panel.progress_bar.value.return_value = 0
    panel.process = MagicMock()
    panel.process.state.return_value = QProcess.ProcessState.Running
    panel.process.program.return_value = "C:/steamcmd/steamcmd.exe"
    panel._steamcmd_console_log_path = str(tmp_path / "console_log.txt")
    panel._steamcmd_log_timer = None
    panel._steamcmd_log_offset = 0
    panel._steamcmd_log_partial = ""
    panel._is_process_running = lambda name: name == "steamcmd"  # type: ignore[method-assign, assignment]
    panel._handle_steamcmd_output = lambda line: False  # type: ignore[method-assign]
    panel._handle_query_output = lambda line: False  # type: ignore[method-assign]
    return panel


class TestRunnerPanelSteamcmdLogging:
    @patch("app.windows.runner_panel.logger")
    def test_steamcmd_lines_logged_at_info(self, mock_logger: MagicMock) -> None:
        panel = RunnerPanel.__new__(RunnerPanel)
        panel.process = MagicMock()
        panel.process.state.return_value = QProcess.ProcessState.Running
        panel.process.program.return_value = "/usr/bin/steamcmd"
        panel.text = MagicMock()
        panel.previous_line = ""
        panel.steamcmd_current_pfid = ""
        panel.steamcmd_download_tracking = []
        panel.login_error = False
        panel.progress_bar = MagicMock()
        panel.progress_bar.value.return_value = 0

        panel._is_process_running = lambda name: name == "steamcmd"  # type: ignore[method-assign, assignment]
        panel._handle_steamcmd_output = lambda line: False  # type: ignore[method-assign]
        panel._handle_query_output = lambda line: False  # type: ignore[method-assign]

        panel.message("  Downloading item 123...  ")

        mock_logger.info.assert_called_with("[SteamCMD] Downloading item 123...")


class TestRunnerPanelSteamcmdLogTail:
    def test_poll_steamcmd_log_parses_new_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "console_log.txt"
        log_path.write_text("Loading Steam API...ok\n", encoding="utf-8")

        panel = _make_steamcmd_panel(tmp_path)
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._poll_steamcmd_log()

        assert messages == ["Loading Steam API...ok"]

        log_path.write_text(
            "Loading Steam API...ok\nDownloading item 123...\n",
            encoding="utf-8",
        )
        panel._poll_steamcmd_log()

        assert messages == [
            "Loading Steam API...ok",
            "Downloading item 123...",
        ]

    def test_poll_steamcmd_log_partial_line_buffering(self, tmp_path: Path) -> None:
        log_path = tmp_path / "console_log.txt"
        log_path.write_bytes(b"Success. Downloaded item 12")

        panel = _make_steamcmd_panel(tmp_path)
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._poll_steamcmd_log()
        assert messages == []
        assert panel._steamcmd_log_partial == "Success. Downloaded item 12"

        with log_path.open("ab") as log_file:
            log_file.write(b"345\n")
        panel._poll_steamcmd_log()

        assert messages == ["Success. Downloaded item 12345"]
        assert panel._steamcmd_log_partial == ""

    def test_poll_steamcmd_log_final_flush(self, tmp_path: Path) -> None:
        log_path = tmp_path / "console_log.txt"
        log_path.write_bytes(b"partial line without newline")

        panel = _make_steamcmd_panel(tmp_path)
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._poll_steamcmd_log()
        assert messages == []

        panel._poll_steamcmd_log(final=True)
        assert messages == ["partial line without newline"]
        assert panel._steamcmd_log_partial == ""

    def test_poll_steamcmd_log_missing_file_noop(self, tmp_path: Path) -> None:
        panel = _make_steamcmd_panel(tmp_path)
        panel._steamcmd_console_log_path = str(tmp_path / "missing_log.txt")
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._poll_steamcmd_log()
        assert messages == []

    def test_poll_steamcmd_log_missing_file_final_flush_partial(
        self, tmp_path: Path
    ) -> None:
        panel = _make_steamcmd_panel(tmp_path)
        panel._steamcmd_console_log_path = str(tmp_path / "missing_log.txt")
        panel._steamcmd_log_partial = "leftover bytes"
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._poll_steamcmd_log(final=True)
        assert messages == ["leftover bytes"]
        assert panel._steamcmd_log_partial == ""

    def test_start_steamcmd_log_tail_empty_path_noop(self, tmp_path: Path) -> None:
        panel = _make_steamcmd_panel(tmp_path)
        panel._steamcmd_console_log_path = ""

        panel._start_steamcmd_log_tail()
        assert panel._steamcmd_log_timer is None

    @patch("app.windows.runner_panel.QTimer")
    def test_stop_steamcmd_log_tail_without_flush(
        self, mock_qtimer: MagicMock, tmp_path: Path
    ) -> None:
        mock_timer = MagicMock()
        mock_qtimer.return_value = mock_timer

        panel = _make_steamcmd_panel(tmp_path)
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel._start_steamcmd_log_tail()
        panel._stop_steamcmd_log_tail(flush=False)

        mock_timer.stop.assert_called_once()
        assert panel._steamcmd_log_timer is None
        assert messages == []

    @patch("app.windows.runner_panel.QProcess")
    @patch("app.windows.runner_panel.QTimer")
    def test_steamcmd_log_timer_start_on_execute(
        self, mock_qtimer: MagicMock, mock_qprocess: MagicMock, tmp_path: Path
    ) -> None:
        mock_timer = MagicMock()
        mock_qtimer.return_value = mock_timer
        mock_process = MagicMock()
        mock_qprocess.return_value = mock_process

        panel = RunnerPanel.__new__(RunnerPanel)
        panel.system = "Windows"
        panel.todds_dry_run_support = False
        panel.process_last_command = ""
        panel.process_last_args = []
        panel.restart_process_button = MagicMock()
        panel.kill_process_button = MagicMock()
        panel.progress_bar = MagicMock()
        panel.message = MagicMock()  # type: ignore[method-assign]
        panel._steamcmd_console_log_path = str(tmp_path / "console_log.txt")
        panel._steamcmd_log_timer = None
        panel._steamcmd_log_offset = 0
        panel._steamcmd_log_partial = ""

        panel.execute("C:/steamcmd/steamcmd.exe", ['+runscript "script.txt"'], 3)

        mock_qtimer.assert_called_once()
        mock_timer.setInterval.assert_called_once_with(150)
        mock_timer.timeout.connect.assert_called_once()
        mock_timer.start.assert_called_once()
        mock_process.start.assert_called_once()

    @patch("app.windows.runner_panel.QTimer")
    def test_steamcmd_log_timer_stop_on_finished(
        self, mock_qtimer: MagicMock, tmp_path: Path
    ) -> None:
        mock_timer = MagicMock()
        mock_qtimer.return_value = mock_timer

        panel = _make_steamcmd_panel(tmp_path)
        panel.todds_dry_run_support = False
        panel.process_killed = False
        panel.redownloading = False
        panel._pending_steamcmd_batches = []
        panel.windowTitle = MagicMock(return_value="SteamCMD Downloader")
        panel._handle_steamcmd_completion = MagicMock()
        panel.process_complete = MagicMock()
        panel.message = MagicMock()
        panel.process.terminate = MagicMock()

        panel._start_steamcmd_log_tail()
        assert panel._steamcmd_log_timer is mock_timer

        panel.finished()

        mock_timer.stop.assert_called_once()
        mock_timer.deleteLater.assert_called_once()
        assert panel._steamcmd_log_timer is None
        panel._handle_steamcmd_completion.assert_called_once()

    @patch("app.windows.runner_panel.QTimer")
    def test_steamcmd_log_timer_stop_on_kill(
        self, mock_qtimer: MagicMock, tmp_path: Path
    ) -> None:
        mock_timer = MagicMock()
        mock_qtimer.return_value = mock_timer

        panel = _make_steamcmd_panel(tmp_path)
        panel.process_killed = False
        panel.process.state.return_value = QProcess.ProcessState.Running
        panel.process.processId.return_value = 1234
        panel.process.waitForFinished.return_value = True

        panel._start_steamcmd_log_tail()
        assert panel._steamcmd_log_timer is mock_timer

        with patch("app.windows.runner_panel.psutil.Process") as mock_psutil:
            mock_parent = MagicMock()
            mock_parent.children.return_value = []
            mock_psutil.return_value = mock_parent
            panel._do_kill_process()

        mock_timer.stop.assert_called_once()
        mock_timer.deleteLater.assert_called_once()
        assert panel._steamcmd_log_timer is None

    def test_handle_output_bypasses_pipe_on_windows_for_steamcmd(
        self, tmp_path: Path
    ) -> None:
        panel = _make_steamcmd_panel(tmp_path, system="Windows")
        panel.process.readAll = MagicMock()
        panel.message = MagicMock()

        panel.handle_output()

        panel.process.readAll.assert_not_called()
        panel.message.assert_not_called()

    def test_handle_output_uses_pipe_on_linux_for_steamcmd(
        self, tmp_path: Path
    ) -> None:
        panel = _make_steamcmd_panel(tmp_path, system="Linux")
        panel.process.readAll.return_value = MagicMock(
            data=MagicMock(return_value=b"line one\nline two\n")
        )
        messages: list[str] = []
        panel.message = lambda line: messages.append(line)

        panel.handle_output()

        assert messages == ["line one", "line two"]
