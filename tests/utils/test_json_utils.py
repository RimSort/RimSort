import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.json_utils import atomic_json_dump


def test_atomic_json_dump_retries_transient_replace_permission_error(
    tmp_path: Path,
) -> None:
    target = tmp_path / "settings.json"
    real_replace = os.replace
    attempts = 0

    def flaky_replace(source: str, destination: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporarily locked")
        real_replace(source, destination)

    with (
        patch("app.utils.json_utils.os.replace", side_effect=flaky_replace),
        patch("app.utils.json_utils.time.sleep") as sleep,
    ):
        atomic_json_dump({"language": "en"}, str(target))

    assert attempts == 2
    sleep.assert_called_once_with(0.05)
    assert json.loads(target.read_text(encoding="utf-8")) == {"language": "en"}


def test_atomic_json_dump_cleans_temp_file_after_persistent_permission_error(
    tmp_path: Path,
) -> None:
    target = tmp_path / "settings.json"

    with (
        patch(
            "app.utils.json_utils.os.replace",
            side_effect=PermissionError("still locked"),
        ),
        patch("app.utils.json_utils.time.sleep") as sleep,
        pytest.raises(PermissionError, match="still locked"),
    ):
        atomic_json_dump({"language": "en"}, str(target))

    assert list(tmp_path.iterdir()) == []
    assert sleep.call_count == 4
