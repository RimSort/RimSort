"""Tests for CompanionController signal wiring."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from app.controllers.companion_controller import CompanionController
from app.utils.event_bus import EventBus
from app.views.companion_panel import CompanionPanel


@pytest.fixture(autouse=True)
def _ensure_qapp() -> None:
    """Ensure a QApplication exists for the test session."""
    if QApplication.instance() is None:
        QApplication([])


@pytest.fixture()
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def panel() -> CompanionPanel:
    return CompanionPanel()


@pytest.fixture()
def server() -> MagicMock:
    mock = MagicMock()
    mock.send_request = MagicMock(return_value=1)
    return mock


@pytest.fixture()
def controller(
    server: MagicMock, panel: CompanionPanel, event_bus: EventBus
) -> CompanionController:
    return CompanionController(server=server, panel=panel)


class TestEventBusToPanelWiring:
    """Verify EventBus companion signals are routed to panel methods."""

    def test_companion_connected_shows_connected(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        handshake = {"game_version": "1.5.1234", "active_mods": ["Core", "Mod1"]}
        event_bus.companion_connected.emit(handshake)

        # Panel should switch to connected page (index 1)
        assert panel.stack.currentIndex() == 1

    def test_companion_disconnected_shows_disconnected(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        # First connect, then disconnect
        event_bus.companion_connected.emit({"game_version": "1.5", "active_mods": []})
        assert panel.stack.currentIndex() == 1

        event_bus.companion_disconnected.emit()

        # Should be back to disconnected page
        assert panel.stack.currentIndex() == 0

    def test_companion_disconnected_clears_apply_pending(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        # Set apply pending state
        panel.set_apply_pending(True)
        assert not panel.apply_mod_list_button.isEnabled()

        event_bus.companion_disconnected.emit()

        # Apply button should be re-enabled
        assert panel.apply_mod_list_button.isEnabled()

    def test_companion_heartbeat_updates_tps(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        event_bus.companion_heartbeat.emit({"tps": 60})

        assert "60" in panel.tps_label.text()

    def test_companion_state_changed_updates_label(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        event_bus.companion_state_changed.emit("in_game")

        assert "In Game" in panel.game_state_label.text()

    def test_companion_state_initializing_disables_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        event_bus.companion_state_changed.emit("initializing")

        assert not panel.fetch_load_order_button.isEnabled()
        assert not panel.fetch_mod_errors_button.isEnabled()
        assert not panel.fetch_harmony_button.isEnabled()

    def test_companion_state_non_initializing_enables_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        # Disable first
        event_bus.companion_state_changed.emit("initializing")
        assert not panel.fetch_load_order_button.isEnabled()

        # Transition out of initializing
        event_bus.companion_state_changed.emit("playing_map")

        assert panel.fetch_load_order_button.isEnabled()
        assert panel.fetch_mod_errors_button.isEnabled()
        assert panel.fetch_harmony_button.isEnabled()

    def test_auto_fetch_on_state_transition_from_initializing(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
        event_bus: EventBus,
    ) -> None:
        controller.set_auto_fetch_enabled(True)

        # Transition into initializing
        event_bus.companion_state_changed.emit("initializing")
        server.send_request.assert_not_called()

        # Transition out of initializing — should auto-fetch
        event_bus.companion_state_changed.emit("playing_map")
        server.send_request.assert_called_once_with("get.load_order")

    def test_no_auto_fetch_when_disabled(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
        event_bus: EventBus,
    ) -> None:
        controller.set_auto_fetch_enabled(False)

        event_bus.companion_state_changed.emit("initializing")
        event_bus.companion_state_changed.emit("playing_map")

        server.send_request.assert_not_called()

    def test_companion_server_error_shows_disconnected_with_error(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        event_bus.companion_server_error.emit("Port already in use")

        assert panel.stack.currentIndex() == 0
        # error_label.isVisible() requires the entire parent chain to be shown,
        # so check that it's not explicitly hidden instead
        assert not panel.error_label.isHidden()
        assert "Port already in use" in panel.error_label.text()

    def test_companion_load_order_received_displays_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        data = {"mods": ["Core", "HugsLib"]}
        event_bus.companion_load_order_received.emit(data)

        text = panel.diagnostics_output.toPlainText()
        assert "Load Order" in text
        assert "Core" in text

    def test_companion_mod_errors_received_displays_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        data = {"errors": ["Missing dep"]}
        event_bus.companion_mod_errors_received.emit(data)

        text = panel.diagnostics_output.toPlainText()
        assert "Mod Errors" in text

    def test_companion_mod_details_received_displays_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        data = {"details": "some info"}
        event_bus.companion_mod_details_received.emit(data)

        text = panel.diagnostics_output.toPlainText()
        assert "Mod Details" in text

    def test_companion_harmony_patches_received_displays_diagnostics(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        data = {"patches": []}
        event_bus.companion_harmony_patches_received.emit(data)

        text = panel.diagnostics_output.toPlainText()
        assert "Harmony Patches" in text

    def test_companion_apply_result_clears_pending(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        panel.set_apply_pending(True)
        assert not panel.apply_mod_list_button.isEnabled()

        event_bus.companion_apply_result.emit({"accepted": True})

        assert panel.apply_mod_list_button.isEnabled()

    def test_companion_apply_result_declined_remains_enabled(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        event_bus: EventBus,
    ) -> None:
        panel.set_apply_pending(True)

        event_bus.companion_apply_result.emit(
            {"accepted": False, "message": "User cancelled"}
        )

        assert panel.apply_mod_list_button.isEnabled()


class TestPanelButtonToServerWiring:
    """Verify panel button clicks send the correct server requests."""

    def test_fetch_load_order_button_sends_request(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        panel.fetch_load_order_button.click()
        server.send_request.assert_called_once_with("get.load_order")

    def test_fetch_mod_errors_button_sends_request(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        panel.fetch_mod_errors_button.click()
        server.send_request.assert_called_once_with("get.mod_errors")

    def test_fetch_harmony_button_sends_request(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        panel.fetch_harmony_button.click()
        server.send_request.assert_called_once_with("get.harmony_patches")

    def test_apply_mod_list_button_sets_pending(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        # Provide a mod list so the apply goes through
        with patch.object(
            controller, "_get_current_mod_list", return_value=[{"packageId": "core"}]
        ):
            panel.apply_mod_list_button.click()

        assert not panel.apply_mod_list_button.isEnabled()
        assert "Applying" in panel.apply_mod_list_button.text()

    def test_apply_mod_list_button_sends_request(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        mod_list = [{"packageId": "core"}, {"packageId": "hugslib"}]
        with patch.object(controller, "_get_current_mod_list", return_value=mod_list):
            panel.apply_mod_list_button.click()

        server.send_request.assert_called_once_with(
            "apply.mod_list", {"mod_list": mod_list}
        )

    def test_apply_mod_list_no_list_does_not_send(
        self,
        controller: CompanionController,
        panel: CompanionPanel,
        server: MagicMock,
    ) -> None:
        # Default stub returns None
        panel.apply_mod_list_button.click()

        server.send_request.assert_not_called()
        # Button should NOT be in pending state
        assert panel.apply_mod_list_button.isEnabled()


class TestAutoFetchAndMetadata:
    """Test auto-fetch preference and metadata/mod-list wiring."""

    def test_set_auto_fetch_enabled(self, controller: CompanionController) -> None:
        controller.set_auto_fetch_enabled(True)
        assert controller._auto_fetch_enabled is True

        controller.set_auto_fetch_enabled(False)
        assert controller._auto_fetch_enabled is False

    def test_set_metadata_manager(self, controller: CompanionController) -> None:
        mock_mm = MagicMock()
        controller.set_metadata_manager(mock_mm)
        assert controller._metadata_manager is mock_mm

    def test_set_active_uuids_fn(self, controller: CompanionController) -> None:
        def get_uuids() -> list[str]:
            return ["uuid-1", "uuid-2"]

        controller.set_active_uuids_fn(get_uuids)
        assert controller._active_uuids_fn is get_uuids

    def test_get_current_mod_list_returns_none_without_dependencies(
        self, controller: CompanionController
    ) -> None:
        """Returns None when metadata_manager or active_uuids_fn are missing."""
        assert controller._get_current_mod_list() is None

        # Only metadata_manager set — still None
        controller.set_metadata_manager(MagicMock())
        assert controller._get_current_mod_list() is None

    def test_get_current_mod_list_returns_ordered_package_ids(
        self, controller: CompanionController
    ) -> None:
        """Returns correctly ordered list of package_id dicts."""
        mock_mm = MagicMock()
        mock_mm.internal_local_metadata = {
            "uuid-1": {"packageid": "brrainz.harmony"},
            "uuid-2": {"packageid": "Ludeon.RimWorld"},
            "uuid-3": {"packageid": "author.SomeMod"},
        }
        controller.set_metadata_manager(mock_mm)
        controller.set_active_uuids_fn(lambda: ["uuid-1", "uuid-2", "uuid-3"])

        result = controller._get_current_mod_list()
        assert result == [
            {"package_id": "brrainz.harmony"},
            {"package_id": "ludeon.rimworld"},
            {"package_id": "author.somemod"},
        ]

    def test_get_current_mod_list_skips_missing_uuids(
        self, controller: CompanionController
    ) -> None:
        """Skips UUIDs not found in metadata."""
        mock_mm = MagicMock()
        mock_mm.internal_local_metadata = {
            "uuid-1": {"packageid": "brrainz.harmony"},
        }
        controller.set_metadata_manager(mock_mm)
        controller.set_active_uuids_fn(lambda: ["uuid-1", "uuid-missing"])

        result = controller._get_current_mod_list()
        assert result == [{"package_id": "brrainz.harmony"}]

    def test_get_current_mod_list_skips_mods_without_packageid(
        self, controller: CompanionController
    ) -> None:
        """Skips mods that have no packageid field."""
        mock_mm = MagicMock()
        mock_mm.internal_local_metadata = {
            "uuid-1": {"packageid": "brrainz.harmony"},
            "uuid-2": {"name": "No PackageId Mod"},
        }
        controller.set_metadata_manager(mock_mm)
        controller.set_active_uuids_fn(lambda: ["uuid-1", "uuid-2"])

        result = controller._get_current_mod_list()
        assert result == [{"package_id": "brrainz.harmony"}]

    def test_get_current_mod_list_returns_none_for_empty_list(
        self, controller: CompanionController
    ) -> None:
        """Returns None when active list has no resolvable mods."""
        mock_mm = MagicMock()
        mock_mm.internal_local_metadata = {}
        controller.set_metadata_manager(mock_mm)
        controller.set_active_uuids_fn(lambda: [])

        assert controller._get_current_mod_list() is None
