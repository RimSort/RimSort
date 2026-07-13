from PySide6.QtWidgets import QApplication, QWidget

from app.windows.use_this_instead_panel import UseThisInsteadPanel


class TestUseThisInsteadPanelCustomSelectButton:
    def test_custom_select_button_labels(self, qapp: QApplication) -> None:
        """Regression test: the dropdown button used to be built via
        self.panel.tr(...) inside ButtonFactory, relying on dynamic
        context resolution. It's now built with explicit
        QCoreApplication.translate("UseThisInsteadPanel", ...) calls at the
        call site, so labels must still render correctly."""
        panel = UseThisInsteadPanel.__new__(UseThisInsteadPanel)
        # Only initialize the QWidget/QObject base so the instance is a
        # valid QAction parent; skip the heavy panel setup we don't need.
        QWidget.__init__(panel)

        button = panel._create_custom_select_button()

        assert button.text() == "Select"
        menu = button.menu()
        assert menu is not None
        assert [action.text() for action in menu.actions()] == [
            "Select all Originals",
            "Select all Replacements",
        ]
