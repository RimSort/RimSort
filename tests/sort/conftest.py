from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest


def make_mod(
    packageid: str,
    name: str | None = None,
    load_these_before: list[tuple[str, bool]] | None = None,
    load_these_after: list[tuple[str, bool]] | None = None,
    load_top: bool = False,
    load_bottom: bool = False,
    dependencies: list[str | tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a mod metadata dict for sorting tests."""
    mod: dict[str, Any] = {
        "packageid": packageid,
        "name": name or packageid,
    }
    if load_these_before is not None:
        mod["loadTheseBefore"] = set(load_these_before)
    if load_these_after is not None:
        mod["loadTheseAfter"] = set(load_these_after)
    if load_top:
        mod["loadTop"] = True
    if load_bottom:
        mod["loadBottom"] = True
    if dependencies is not None:
        mod["dependencies"] = dependencies
    return mod


@pytest.fixture
def metadata_manager_mock() -> Generator[MagicMock, None, None]:
    """Mock MetadataManager.instance() for sorting tests.

    Sets up an empty internal_local_metadata dict. Tests should populate
    it via the returned mock: mock.internal_local_metadata = {...}
    """
    with patch("app.utils.metadata.MetadataManager.instance") as mock_instance:
        mock = MagicMock()
        mock.internal_local_metadata = {}
        mock_instance.return_value = mock
        yield mock
