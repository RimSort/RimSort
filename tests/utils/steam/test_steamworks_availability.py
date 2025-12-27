"""
Tests for Steam availability notifications and signals.
"""

from unittest.mock import Mock, patch

import pytest

from app.utils.event_bus import EventBus
from app.utils.steam.steamworks.wrapper import SteamworksInterface


@pytest.fixture
def reset_steamworks_singleton() -> None:
    """
    Reset SteamworksInterface singleton between tests.

    This ensures each test starts with a clean slate.
    """
    SteamworksInterface._instance = None
    yield
    SteamworksInterface._instance = None


class TestSteamInitializationSignals:
    """Tests for Steam initialization and signal emission."""

    def test_signal_emitted_on_init_failure(
        self, qtbot, reset_steamworks_singleton
    ) -> None:
        """Verify steam_not_running signal emitted when Steamworks init fails."""
        # Setup signal spy
        event_bus = EventBus()

        with qtbot.waitSignal(event_bus.steam_not_running, timeout=2000):
            # Mock STEAMWORKS to fail initialization
            with patch(
                "app.utils.steam.steamworks.wrapper.STEAMWORKS"
            ) as mock_steamworks_class:
                mock_steamworks = Mock()
                mock_steamworks.initialize.side_effect = Exception("Steam not running")
                mock_steamworks.loaded.return_value = False
                mock_steamworks_class.return_value = mock_steamworks

                # This should emit signal
                steamworks = SteamworksInterface(_libs="/fake/libs")

                assert steamworks.steam_not_running is True

    def test_no_signal_on_successful_init(
        self, qtbot, reset_steamworks_singleton
    ) -> None:
        """Verify no signal emitted when Steamworks initializes successfully."""
        # Setup signal spy to ensure signal is NOT emitted
        event_bus = EventBus()
        signal_emitted = False

        def mark_signal_emitted() -> None:
            nonlocal signal_emitted
            signal_emitted = True

        event_bus.steam_not_running.connect(mark_signal_emitted)

        # Mock STEAMWORKS to succeed initialization
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.return_value = None
            mock_steamworks.loaded.return_value = True
            mock_steamworks_class.return_value = mock_steamworks

            # Initialize should succeed
            steamworks = SteamworksInterface(_libs="/fake/libs")

            assert steamworks.steam_not_running is False
            assert signal_emitted is False  # No signal should be emitted


class TestSteamOperationFailureSignals:
    """Tests for Steam operation failure signals."""

    def test_signal_on_subscribe_failure(self, qtbot, reset_steamworks_singleton) -> None:
        """Verify steam_operation_failed signal emitted when subscribe fails."""
        # Setup signal spy
        event_bus = EventBus()

        # Initialize with Steam not running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.side_effect = Exception("Steam not running")
            mock_steamworks.loaded.return_value = False
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is True

        # Now try to subscribe - should emit steam_operation_failed
        with qtbot.waitSignal(event_bus.steam_operation_failed, timeout=2000) as blocker:
            steamworks.subscribe_to_mods(12345)

        # Verify signal carried correct reason message
        assert "subscribe to mods" in blocker.args[0]
        assert "Steam client is not running" in blocker.args[0]

    def test_signal_on_download_failure(self, qtbot, reset_steamworks_singleton) -> None:
        """Verify steam_operation_failed signal emitted when download fails."""
        # Setup signal spy
        event_bus = EventBus()

        # Initialize with Steam not running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.side_effect = Exception("Steam not running")
            mock_steamworks.loaded.return_value = False
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is True

        # Try to download - should emit steam_operation_failed
        with qtbot.waitSignal(event_bus.steam_operation_failed, timeout=2000) as blocker:
            steamworks.download_items(12345)

        # Verify signal message
        assert "download items" in blocker.args[0]
        assert "Steam client is not running" in blocker.args[0]


class TestCheckSteamAvailability:
    """Tests for check_steam_availability method."""

    def test_check_availability_when_already_available(
        self, reset_steamworks_singleton
    ) -> None:
        """Test check returns True when Steam already available."""
        # Initialize with Steam running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.return_value = None
            mock_steamworks.loaded.return_value = True
            mock_steamworks.IsSteamRunning.return_value = True
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is False

            # Check should return True immediately
            result = steamworks.check_steam_availability()
            assert result is True
            assert steamworks.steam_not_running is False

            # Initialize should only be called once (in __init__)
            assert mock_steamworks.initialize.call_count == 1
            # IsSteamRunning should be called once in check_steam_availability
            assert mock_steamworks.IsSteamRunning.call_count == 1

    def test_check_availability_steam_becomes_available(
        self, reset_steamworks_singleton
    ) -> None:
        """Test check returns True when Steam becomes available."""
        call_count = 0

        def init_side_effect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Steam not running")
            # Second call succeeds

        # Initialize with Steam not running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.side_effect = init_side_effect
            mock_steamworks.loaded.return_value = True
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is True
            assert call_count == 1

            # Check availability - should succeed on retry
            result = steamworks.check_steam_availability()
            assert result is True
            assert steamworks.steam_not_running is False
            assert call_count == 2

    def test_check_availability_steam_still_unavailable(
        self, qtbot, reset_steamworks_singleton
    ) -> None:
        """Test check returns False and emits signal when Steam still unavailable."""
        # Setup signal spy
        event_bus = EventBus()

        # Initialize with Steam not running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.side_effect = Exception("Steam not running")
            mock_steamworks.loaded.return_value = False
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is True

            # Check availability - should fail and emit signal
            with qtbot.waitSignal(event_bus.steam_not_running, timeout=2000):
                result = steamworks.check_steam_availability()

            assert result is False
            assert steamworks.steam_not_running is True
            # Initialize called twice: once in __init__, once in check_steam_availability
            assert mock_steamworks.initialize.call_count == 2

    def test_check_availability_detects_steam_shutdown(
        self, qtbot, reset_steamworks_singleton
    ) -> None:
        """Test check detects when Steam closes after being available."""
        # Setup signal spy
        event_bus = EventBus()

        # Initialize with Steam running
        with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as mock_steamworks_class:
            mock_steamworks = Mock()
            mock_steamworks.initialize.return_value = None
            mock_steamworks.loaded.return_value = True
            # Initially Steam is running
            mock_steamworks.IsSteamRunning.return_value = True
            mock_steamworks_class.return_value = mock_steamworks

            steamworks = SteamworksInterface(_libs="/fake/libs")
            assert steamworks.steam_not_running is False

            # First check - Steam still running
            result = steamworks.check_steam_availability()
            assert result is True

            # Simulate Steam being closed
            mock_steamworks.IsSteamRunning.return_value = False
            mock_steamworks.initialize.side_effect = Exception("Steam not running")

            # Check availability - should detect Steam is no longer running
            with qtbot.waitSignal(event_bus.steam_not_running, timeout=2000):
                result = steamworks.check_steam_availability()

            assert result is False
            assert steamworks.steam_not_running is True
            # IsSteamRunning should have been called twice (once per check)
            assert mock_steamworks.IsSteamRunning.call_count == 2
