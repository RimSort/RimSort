"""Centralized loguru logging configuration for RimSort."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _obfuscate_message(message: str, anonymize_path: bool = True) -> str:
    """Obfuscate the message such that it does not reveal user information."""
    if anonymize_path:
        message = _anonymize_path(message)
    return message


def _anonymize_path(message: str) -> str:
    """Anonymize OS-specific user paths in log messages."""
    # Windows — keep drive letter, strip username
    message = re.sub(r"([A-Z]:\\Users\\)[^\\]+\\", r"\1...\\", message)
    # macOS — strip username (must come before Linux to avoid /Users matching /home)
    message = re.sub(r"/Users/[^/]+/", r"/Users/.../", message)
    # Linux — strip username
    message = re.sub(r"/home/[^/]+/", r"/home/.../", message)
    return message


_SESSION_HISTORY = 5  # TODO(debt): make session_history configurable via settings


def _rotate_session_logs(log_dir: Path, base_name: str) -> None:
    """
    Rotate session-based log files using numbered suffixes.

    Cascades existing logs upward (RimSort.log -> RimSort.1.log -> RimSort.2.log)
    and deletes logs beyond the history limit. Migrates legacy .old.log files.

    :param log_dir: Directory containing log files
    :param base_name: Base log filename (e.g., "RimSort.log")
    """
    stem = Path(base_name).stem
    suffix = "".join(Path(base_name).suffixes)

    old_legacy = log_dir / f"{stem}.old{suffix}"

    # Cascade numbered logs upward, deleting any that exceed the history limit
    for i in range(_SESSION_HISTORY + 10, 0, -1):
        source = log_dir / f"{stem}.{i}{suffix}"
        if not source.exists():
            continue
        target_index = i + 1
        if target_index >= _SESSION_HISTORY:
            try:
                source.unlink()
            except OSError:
                print(f"Warning: failed to delete old log {source}", file=sys.stderr)
        else:
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

    # Migrate legacy .old.log into the first available slot
    if old_legacy.exists():
        for i in range(2, _SESSION_HISTORY + 1):
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
