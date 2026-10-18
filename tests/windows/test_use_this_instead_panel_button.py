from PySide6.QtWidgets import QApplication, QWidget

from app.windows.use_this_instead_panel import UseThisInsteadPanel


class _SelectButtonHost(QWidget):
    """Qt-valid stand-in exposing the panel's button-building methods.

    PySide6 6.12 aborts when ``QWidget.__init__`` is called on an instance
    created via ``__new__`` for a widget subclass, so borrow the methods
    under test onto a properly constructed widget instead. They need
    ``self`` only as the QAction parent and for the menu callbacks, which
    are connected but never invoked here.
    """

    get_button_factory = UseThisInsteadPanel.get_button_factory
    _create_custom_select_button = UseThisInsteadPanel._create_custom_select_button
    _select_all_originals = UseThisInsteadPanel._select_all_originals
    _select_all_replacements = UseThisInsteadPanel._select_all_replacements


class TestUseThisInsteadPanelCustomSelectButton:
    def test_custom_select_button_labels(self, qapp: QApplication) -> None:
        """Regression test: the dropdown button used to be built via
        self.panel.tr(...) inside ButtonFactory, relying on dynamic
        context resolution. It's now built with explicit
        QCoreApplication.translate("UseThisInsteadPanel", ...) calls at the
        call site, so labels must still render correctly."""
        host = _SelectButtonHost()
        button = host._create_custom_select_button()  # type: ignore

        assert button.text() == "Select"
        menu = button.menu()
        assert menu is not None
        assert [action.text() for action in menu.actions()] == [
            "Select all Originals",
            "Select all Replacements",
        ]
