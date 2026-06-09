"""Tests for ctypes struct definitions and library loading behavior."""

import ctypes
from unittest.mock import patch

import pytest

from app.utils.steam.steamworks.bindings import (
    DownloadItemResult,
    GetAppDependenciesResult,
    ItemInstalledResult,
    SubscriptionResult,
    _load_library,
    _resolve_library_path,
)


class TestStructLayouts:
    def test_subscription_result_size(self) -> None:
        # int32 (4) + padding (4) + uint64 (8) = 16 bytes
        assert ctypes.sizeof(SubscriptionResult) == 16

    def test_subscription_result_fields(self) -> None:
        result = SubscriptionResult(result=1, published_file_id=12345)
        assert result.result == 1
        assert result.published_file_id == 12345

    def test_get_app_dependencies_result_has_unsigned_pointer(self) -> None:
        field_dict = {f[0]: f[1] for f in GetAppDependenciesResult._fields_}
        assert field_dict["array_app_dependencies"] == ctypes.POINTER(ctypes.c_uint32)

    def test_download_item_result_size(self) -> None:
        # uint32 (4) + padding (4) + uint64 (8) + int32 (4) + padding (4) = 24 bytes
        assert ctypes.sizeof(DownloadItemResult) == 24

    def test_download_item_result_field_order(self) -> None:
        field_names = [f[0] for f in DownloadItemResult._fields_]
        assert field_names == ["app_id", "published_file_id", "result"]

    def test_item_installed_result_size(self) -> None:
        # uint32 (4) + padding (4) + uint64 (8) + uint64 (8) + uint64 (8) = 32 bytes
        assert ctypes.sizeof(ItemInstalledResult) == 32

    def test_item_installed_result_field_order(self) -> None:
        field_names = [f[0] for f in ItemInstalledResult._fields_]
        assert field_names == [
            "app_id",
            "published_file_id",
            "legacy_content",
            "manifest_id",
        ]


class TestLibraryLoading:
    @patch(
        "app.utils.steam.steamworks.bindings._resolve_library_path",
        side_effect=OSError("Could not find rimsort_steam"),
    )
    def test_load_returns_none_when_library_missing(self, _mock: object) -> None:
        result = _load_library()
        assert result is None

    def test_resolve_raises_oserror_when_library_missing(self) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(OSError, match="Could not find"):
                _resolve_library_path()
