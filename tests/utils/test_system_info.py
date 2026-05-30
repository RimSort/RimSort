from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.utils.system_info import (
    SystemInfo,
    UnsupportedArchitectureError,
    UnsupportedOperatingSystemError,
)


def _clear_singleton() -> None:
    """Clear all singleton state from SystemInfo."""
    instance = SystemInfo._instance
    if instance is not None and hasattr(instance, "_is_initialized"):
        del instance._is_initialized
    SystemInfo._instance = None
    SystemInfo._operating_system = None
    SystemInfo._architecture = None


@pytest.fixture(autouse=True)
def reset_singleton() -> Generator[None]:
    """Reset SystemInfo singleton between tests."""
    _clear_singleton()
    yield
    _clear_singleton()


class TestOperatingSystemDetection:
    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_linux(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        info = SystemInfo()
        assert info.operating_system == SystemInfo.OperatingSystem.LINUX

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_windows(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        info = SystemInfo()
        assert info.operating_system == SystemInfo.OperatingSystem.WINDOWS

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_macos(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        info = SystemInfo()
        assert info.operating_system == SystemInfo.OperatingSystem.MACOS

    @patch("platform.system", return_value="FreeBSD")
    @patch("platform.machine", return_value="x86_64")
    def test_unsupported_os_raises(
        self, _mock_machine: MagicMock, _mock_system: MagicMock
    ) -> None:
        with pytest.raises(UnsupportedOperatingSystemError):
            SystemInfo()


class TestArchitectureDetection:
    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_x64(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.X64

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="amd64")
    def test_amd64(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.X64

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="i686")
    def test_x86(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.X86

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_arm64(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.ARM64

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="aarch64")
    def test_aarch64(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.ARM64

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64e")
    def test_arm64e(self, _mock_machine: MagicMock, _mock_system: MagicMock) -> None:
        assert SystemInfo().architecture == SystemInfo.Architecture.ARM64

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="mips")
    def test_unsupported_arch_raises(
        self, _mock_machine: MagicMock, _mock_system: MagicMock
    ) -> None:
        with pytest.raises(UnsupportedArchitectureError):
            SystemInfo()


class TestSingleton:
    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    def test_same_instance_returned(
        self, _mock_machine: MagicMock, _mock_system: MagicMock
    ) -> None:
        a = SystemInfo()
        b = SystemInfo()
        assert a is b
