from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.utils.mod_utils import get_mod_name_from_pfid, get_mod_paths_from_uuids


@pytest.fixture
def metadata_manager_mock() -> Generator[MagicMock, None, None]:
    with patch("app.utils.metadata.MetadataManager.instance") as mock_instance:
        mock = MagicMock()
        mock.internal_local_metadata = {
            "uuid1": {
                "publishedfileid": "123",
                "name": "Mod One",
                "path": "/path/to/mod1",
            },
            "uuid2": {
                "publishedfileid": "456",
                "name": "Mod Two",
                "path": "/path/to/mod2",
            },
        }
        mock.external_steam_metadata = {"789": {"name": "External Mod"}}
        mock_instance.return_value = mock
        yield mock


def test_get_mod_name_from_pfid_valid_internal(
    metadata_manager_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("123") == "Mod One"
    assert get_mod_name_from_pfid(123) == "Mod One"


def test_get_mod_name_from_pfid_valid_external(
    metadata_manager_mock: MagicMock,
) -> None:
    assert get_mod_name_from_pfid("789") == "External Mod"


def test_get_mod_name_from_pfid_invalid(metadata_manager_mock: MagicMock) -> None:
    assert get_mod_name_from_pfid("999") == "Invalid ID: 999"
    assert get_mod_name_from_pfid("abc") == "Invalid ID: abc"
    assert get_mod_name_from_pfid(None) == "Unknown Mod"


def test_get_mod_paths_from_uuids(metadata_manager_mock: MagicMock) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.side_effect = lambda path: path in ["/path/to/mod1", "/path/to/mod2"]
        paths = get_mod_paths_from_uuids(["uuid1", "uuid2", "uuid3"])
        assert "/path/to/mod1" in paths
        assert "/path/to/mod2" in paths
        assert len(paths) == 2


def test_get_mod_paths_from_uuids_with_nonexistent_path(
    metadata_manager_mock: MagicMock,
) -> None:
    with patch("os.path.isdir") as isdir_mock:
        isdir_mock.return_value = False
        paths = get_mod_paths_from_uuids(["uuid1"])
        assert paths == []
