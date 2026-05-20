"""Centralized loguru logging configuration for RimSort."""

from __future__ import annotations

import sys
from pathlib import Path


def _rotate_session_logs(
    log_dir: Path, base_name: str, session_history: int
) -> None:
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
                    print(f"Warning: failed to rotate log {source} -> {target}", file=sys.stderr)

    # Move current log to .1
    current = log_dir / base_name
    first_rotated = log_dir / f"{stem}.1{suffix}"
    if current.exists():
        try:
            current.rename(first_rotated)
        except OSError:
            print(f"Warning: failed to rotate log {current} -> {first_rotated}", file=sys.stderr)

    # Now handle legacy .old.log — place it after the newly rotated current
    if old_legacy.exists():
        for i in range(2, session_history + 1):
            slot = log_dir / f"{stem}.{i}{suffix}"
            if not slot.exists():
                try:
                    old_legacy.rename(slot)
                except OSError:
                    print(f"Warning: failed to migrate legacy log {old_legacy}", file=sys.stderr)
                break
        else:
            try:
                old_legacy.unlink()
            except OSError:
                pass
