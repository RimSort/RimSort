import json
import os
import tempfile
import time
from typing import Any

_REPLACE_ATTEMPTS = 5
_REPLACE_RETRY_DELAY = 0.05


def _replace_with_retry(source: str, destination: str) -> None:
    """Replace a file, tolerating short-lived Windows file locks."""
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY * 2**attempt)


def atomic_json_dump(data: Any, path: str, **kwargs: Any) -> None:
    dirpath = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=dirpath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **kwargs)
            f.flush()
            os.fsync(fd)
        _replace_with_retry(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
