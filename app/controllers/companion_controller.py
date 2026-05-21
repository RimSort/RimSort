"""CompanionController — wires CompanionServer signals to CompanionPanel.

Thin coordinator that connects EventBus companion signals to panel display
methods, and panel button clicks to server request methods.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject

from app.utils.event_bus import EventBus
from app.views.companion_panel import CompanionPanel

if TYPE_CHECKING:
    from app.utils.metadata import MetadataManager


class CompanionController(QObject):
    """Coordinate between CompanionServer and CompanionPanel.

    Connects EventBus companion signals (emitted by the server) to panel
    display methods, and panel button clicks to server requests.

    :param server: the CompanionServer instance
    :param panel: the CompanionPanel widget
    :param parent: optional QObject parent
    """

    def __init__(
        self,
        server: Any,
        panel: CompanionPanel,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._server = server
        self._panel = panel
        self._event_bus = EventBus()
        self._auto_fetch_enabled = False
        self._last_state: str | None = None
        self._metadata_manager: MetadataManager | None = None
        self._active_uuids_fn: Callable[[], list[str]] | None = None

        self._connect_event_bus_signals()
        self._connect_panel_buttons()

    # ------------------------------------------------------------------
    # EventBus → Panel wiring
    # ------------------------------------------------------------------

    def _connect_event_bus_signals(self) -> None:
        """Wire EventBus companion signals to panel methods."""
        eb = self._event_bus

        eb.companion_connected.connect(self._on_connected)
        eb.companion_disconnected.connect(self._on_disconnected)
        eb.companion_heartbeat.connect(self._panel.update_heartbeat)
        eb.companion_state_changed.connect(self._on_state_changed)
        eb.companion_server_error.connect(self._on_server_error)

        eb.companion_load_order_received.connect(
            lambda data: self._panel.display_diagnostics("Load Order", data)
        )
        eb.companion_mod_errors_received.connect(
            lambda data: self._panel.display_diagnostics("Mod Errors", data)
        )
        eb.companion_mod_details_received.connect(
            lambda data: self._panel.display_diagnostics("Mod Details", data)
        )
        eb.companion_harmony_patches_received.connect(
            lambda data: self._panel.display_diagnostics("Harmony Patches", data)
        )
        eb.companion_apply_result.connect(self._on_apply_result)

    def _on_connected(self, handshake_data: dict) -> None:
        """Handle companion connection established."""
        self._panel.show_connected(handshake_data)

    def _on_disconnected(self) -> None:
        """Handle companion disconnection: reset UI state."""
        self._panel.set_apply_pending(False)
        self._last_state = None
        self._panel.show_disconnected()

    def _on_state_changed(self, state: str) -> None:
        """Handle game state transitions.

        Disables diagnostics during ``initializing`` and enables them
        otherwise. If auto-fetch is on and the game transitions out of
        ``initializing``, automatically requests the load order.
        """
        previous = self._last_state
        self._last_state = state

        self._panel.update_game_state(state)

        if state == "initializing":
            self._panel.set_diagnostics_enabled(False)
        else:
            self._panel.set_diagnostics_enabled(True)

            if self._auto_fetch_enabled and previous == "initializing":
                logger.info("Auto-fetching load order after initialization")
                self._server.send_request("get.load_order")

    def _on_server_error(self, error_msg: str) -> None:
        """Show the error on the panel's disconnected page."""
        self._panel.show_disconnected(error=error_msg)

    def _on_apply_result(self, result: dict) -> None:
        """Handle the apply.mod_list result notification."""
        self._panel.set_apply_pending(False)

        accepted = result.get("accepted", False)
        if not accepted:
            message = result.get("message", "Mod list apply was declined")
            logger.info("Apply mod list declined: {}", message)

    # ------------------------------------------------------------------
    # Panel buttons → Server wiring
    # ------------------------------------------------------------------

    def _connect_panel_buttons(self) -> None:
        """Wire panel button clicks to server requests."""
        self._panel.fetch_load_order_button.clicked.connect(
            lambda: self._server.send_request("get.load_order")
        )
        self._panel.fetch_mod_errors_button.clicked.connect(
            lambda: self._server.send_request("get.mod_errors")
        )
        self._panel.fetch_harmony_button.clicked.connect(
            lambda: self._server.send_request("get.harmony_patches")
        )
        self._panel.apply_mod_list_button.clicked.connect(self._on_apply_clicked)

    def _on_apply_clicked(self) -> None:
        """Gather the current mod list and send an apply request."""
        mod_list = self._get_current_mod_list()
        if mod_list is None:
            logger.warning("Cannot apply mod list: no mod list available")
            return

        self._panel.set_apply_pending(True)
        self._server.send_request("apply.mod_list", {"mod_list": mod_list})

    # ------------------------------------------------------------------
    # Public configuration
    # ------------------------------------------------------------------

    def set_auto_fetch_enabled(self, enabled: bool) -> None:
        """Store the auto-fetch preference.

        :param enabled: whether to auto-fetch load order after game init
        """
        self._auto_fetch_enabled = enabled

    def set_metadata_manager(self, metadata_manager: MetadataManager) -> None:
        """Store a reference to the MetadataManager.

        :param metadata_manager: the MetadataManager instance
        """
        self._metadata_manager = metadata_manager

    def set_active_uuids_fn(self, fn: Callable[[], list[str]]) -> None:
        """Provide a callable that returns the current active mod UUIDs in order.

        This decouples the controller from the view hierarchy — the caller
        wires in whatever data source is appropriate (typically the active
        mods list widget's ``.uuids`` property).

        :param fn: zero-arg callable returning ordered active UUIDs
        """
        self._active_uuids_fn = fn

    def _get_current_mod_list(self) -> list[dict] | None:
        """Return the current active mod list for apply requests.

        Reads the ordered active UUIDs, resolves each to its ``packageid``
        via MetadataManager, and returns them as a list of dicts suitable
        for the companion mod's ``apply.mod_list`` request.

        :return: list of ``{"package_id": "<id>"}`` dicts in load order,
                 or None if the required data sources are unavailable
        """
        if self._metadata_manager is None or self._active_uuids_fn is None:
            logger.warning(
                "Cannot build mod list: metadata_manager={}, active_uuids_fn={}",
                self._metadata_manager is not None,
                self._active_uuids_fn is not None,
            )
            return None

        uuids = self._active_uuids_fn()
        local_metadata = self._metadata_manager.internal_local_metadata

        mod_list: list[dict] = []
        for uuid in uuids:
            mod_data = local_metadata.get(uuid)
            if mod_data is None:
                logger.debug("Skipping unknown UUID in active list: {}", uuid)
                continue

            package_id = mod_data.get("packageid")
            if not package_id:
                logger.debug("Mod {} has no packageid, skipping", uuid)
                continue

            mod_list.append({"package_id": package_id.lower()})

        logger.info("Built companion mod list with {} entries", len(mod_list))
        return mod_list if mod_list else None
