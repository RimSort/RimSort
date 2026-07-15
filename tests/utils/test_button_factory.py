from unittest.mock import MagicMock, call

from PySide6.QtCore import QCoreApplication, QObject
from PySide6.QtWidgets import QApplication

from app.utils.button_factory import ButtonFactory


class _FakePanel(QObject):
    """Minimal real QObject test double.

    QAction requires its parent to be an actual initialized QObject, so a
    bare MagicMock (or an uninitialized QObject subclass) won't do as the
    ``panel`` passed to ButtonFactory.
    """

    def __init__(self) -> None:
        super().__init__()
        self._create_update_callback = MagicMock(return_value=MagicMock())
        self._set_all_checkbox_rows = MagicMock()


def _menu_action_texts(button: object) -> list[str]:
    menu = button.menu()  # type: ignore[attr-defined]
    assert menu is not None
    return [action.text() for action in menu.actions()]


class TestButtonFactory:
    def test_create_refresh_button_uses_translated_text(
        self, qapp: QApplication
    ) -> None:
        factory = ButtonFactory(_FakePanel())

        button = factory.create_refresh_button()

        assert button.text() == QCoreApplication.translate("BaseModsPanel", "Refresh")

    def test_create_refresh_button_wires_callback(self, qapp: QApplication) -> None:
        factory = ButtonFactory(_FakePanel())
        callback = MagicMock()

        button = factory.create_refresh_button(callback)
        button.click()

        callback.assert_called_once()

    def test_create_steamcmd_button_labels(self, qapp: QApplication) -> None:
        factory = ButtonFactory(_FakePanel())

        button = factory.create_steamcmd_button(pfid_column=0)

        assert button.text() == "SteamCMD"
        assert _menu_action_texts(button) == ["Download with SteamCMD"]

    def test_create_select_all_button_labels(self, qapp: QApplication) -> None:
        factory = ButtonFactory(_FakePanel())

        button = factory.create_select_all_button()

        assert button.text() == "Select"
        assert _menu_action_texts(button) == ["Select all", "Deselect all"]

    def test_create_select_all_button_menu_actions_invoke_panel(
        self, qapp: QApplication
    ) -> None:
        panel = _FakePanel()
        factory = ButtonFactory(panel)

        button = factory.create_select_all_button()
        menu = button.menu()
        assert menu is not None
        actions = menu.actions()

        actions[0].trigger()
        actions[1].trigger()
        assert panel._set_all_checkbox_rows.call_args_list == [call(True), call(False)]

    def test_create_steam_button_labels(self, qapp: QApplication) -> None:
        factory = ButtonFactory(_FakePanel())

        button = factory.create_steam_button(pfid_column=0)

        assert button.text() == "Steam"
        assert _menu_action_texts(button) == [
            "Subscribe selected",
            "Unsubscribe selected",
        ]

    def test_create_dropdown_button_does_not_require_panel_tr(
        self, qapp: QApplication
    ) -> None:
        """Regression test: create_dropdown_button previously called
        self.panel.tr(...), which broke lupdate's static string extraction
        because the literal text lived at the caller, not here. It should
        render whatever pre-translated text/labels it is given verbatim,
        without needing a .tr() method on panel at all."""
        panel = QObject()  # deliberately has no .tr() method
        factory = ButtonFactory(panel)

        button = factory.create_dropdown_button(
            "Custom Label",
            "actionButton",
            [("Menu Item", MagicMock())],
        )

        assert button.text() == "Custom Label"
        assert _menu_action_texts(button) == ["Menu Item"]

    def test_create_custom_button(self, qapp: QApplication) -> None:
        factory = ButtonFactory(_FakePanel())
        callback = MagicMock()

        button = factory.create_custom_button("Do Thing", callback)
        button.click()

        assert button.text() == "Do Thing"
        callback.assert_called_once()
