"""Centralized loguru logging configuration for RimSort."""

from __future__ import annotations

import re


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
