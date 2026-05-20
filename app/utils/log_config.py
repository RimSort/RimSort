"""Centralized loguru logging configuration for RimSort."""

from __future__ import annotations

import atexit
import json
import platform
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import IO, TYPE_CHECKING

from loguru import logger

from app.utils.obfuscate_message import obfuscate_message

if TYPE_CHECKING:
    import loguru as loguru_module


def _formatter(record: "loguru_module.Record") -> str:
    """Custom formatter for loguru logger with obfuscation and exception support."""
    format_string = (
        "[{level}][{time:YYYY-MM-DD HH:mm:ss}][{process.id}][{thread.name}][{module}][{function}][{line}] : "
    )
    record["extra"]["obfuscated_message"] = obfuscate_message(record["message"])
    return format_string + "{extra[obfuscated_message]}\n{exception}"


def _suppress_noisy_loggers() -> None:
    """Suppress verbose third-party loggers that use stdlib logging."""
    from logging import WARNING, getLogger

    system = platform.system()
    if system == "Darwin":
        getLogger("watchdog.observers.fsevents").setLevel(WARNING)
    elif system == "Linux":
        getLogger("watchdog.observers.inotify_buffer").setLevel(WARNING)
    getLogger("urllib3").setLevel(WARNING)


def _rotate_session_logs(log_dir: Path, base_name: str, session_history: int) -> None:
    """
    Rotate session-based log files using numbered suffixes.

    Cascades existing logs upward (RimSort.log -> RimSort.1.log -> RimSort.2.log)
    and deletes logs beyond the history limit. Migrates legacy .old.log files.

    :param log_dir: Directory containing log files
    :param base_name: Base log filename (e.g., "RimSort.log")
    :param session_history: Maximum number of past session logs to keep
    """
    stem = Path(base_name).stem
    suffix = "".join(Path(base_name).suffixes)

    # Migrate legacy .old.log format if present
    old_legacy = log_dir / f"{stem}.old{suffix}"

    # Cascade: move from highest to lowest, deleting if target would exceed history limit
    # We need to scan higher than session_history to catch any that may exist
    for i in range(session_history + 10, 0, -1):
        source = log_dir / f"{stem}.{i}{suffix}"
        if source.exists():
            target_index = i + 1
            if target_index >= session_history:
                # This file would be moved to or beyond the history limit, delete it
                try:
                    source.unlink()
                except OSError:
                    print(f"Warning: failed to delete old log {source}", file=sys.stderr)
            else:
                # Move it up one position
                target = log_dir / f"{stem}.{target_index}{suffix}"
                try:
                    if target.exists():
                        target.unlink()
                    source.rename(target)
                except OSError:
                    print(
                        f"Warning: failed to rotate log {source} -> {target}",
                        file=sys.stderr,
                    )

    # Move current log to .1
    current = log_dir / base_name
    first_rotated = log_dir / f"{stem}.1{suffix}"
    if current.exists():
        try:
            current.rename(first_rotated)
        except OSError:
            print(
                f"Warning: failed to rotate log {current} -> {first_rotated}",
                file=sys.stderr,
            )

    # Now handle legacy .old.log — place it after the newly rotated current
    if old_legacy.exists():
        for i in range(2, session_history + 1):
            slot = log_dir / f"{stem}.{i}{suffix}"
            if not slot.exists():
                try:
                    old_legacy.rename(slot)
                except OSError:
                    print(
                        f"Warning: failed to migrate legacy log {old_legacy}",
                        file=sys.stderr,
                    )
                break
        else:
            try:
                old_legacy.unlink()
            except OSError:
                pass


def _make_json_sink(json_file: IO[str]) -> Callable[["loguru_module.Message"], None]:
    """Create a JSON sink closure that obfuscates before serializing."""

    def _json_sink(message: "loguru_module.Message") -> None:
        record = message.record
        serialized: dict[str, object] = {
            "time": record["time"].isoformat(),
            "level": record["level"].name,
            "module": record["module"],
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "process": record["process"].id,
            "thread": record["thread"].name,
            "message": obfuscate_message(record["message"]),
        }
        if record["exception"] is not None:
            serialized["exception"] = obfuscate_message(
                "".join(
                    traceback.format_exception(
                        record["exception"].type,
                        record["exception"].value,
                        record["exception"].traceback,
                    )
                )
            )
        json_file.write(json.dumps(serialized) + "\n")
        json_file.flush()

    return _json_sink


def setup_logging(
    log_dir: Path,
    debug: bool = False,
    session_history: int = 5,
    json_logging: bool = True,
    file_logging: bool = True,
) -> None:
    """
    Configure loguru sinks for the application.

    :param log_dir: Directory for log files
    :param debug: Enable DEBUG level logging (otherwise INFO)
    :param session_history: Number of past session logs to keep
    :param json_logging: Enable JSON log file alongside human-readable
    :param file_logging: Enable file sinks (False for CLI-only mode)
    """
    logger.remove()

    file_level = "DEBUG" if debug else "INFO"

    if file_logging:
        log_dir.mkdir(parents=True, exist_ok=True)

        # Rotate session logs
        _rotate_session_logs(log_dir, "RimSort.log", session_history)
        if json_logging:
            _rotate_session_logs(log_dir, "RimSort.json.log", session_history)

        # Human-readable file sink
        log_file = log_dir / "RimSort.log"
        logger.add(
            log_file,
            level=file_level,
            format=_formatter,
            enqueue=True,
        )

        # JSON file sink
        if json_logging:
            json_log_path = log_dir / "RimSort.json.log"
            json_file = open(json_log_path, "w", encoding="utf-8")  # noqa: SIM115
            atexit.register(json_file.close)
            logger.add(
                _make_json_sink(json_file),
                level="DEBUG",
                enqueue=True,
            )

    # stderr sink
    stderr_level = "DEBUG" if (debug and not file_logging) else "WARNING"
    logger.add(
        sys.stderr,
        level=stderr_level,
        format=_formatter,
        colorize=False,
    )

    _suppress_noisy_loggers()
