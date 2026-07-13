import json
import os
import tempfile
from typing import Any


def atomic_json_dump(data: Any, path: str, **kwargs: Any) -> None:
    dirpath = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=dirpath)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **kwargs)
            f.flush()
            os.fsync(fd)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
