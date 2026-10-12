import pytest
from PySide6.QtWidgets import QAbstractButton, QApplication, QMessageBox

from app.views import dialogue


@pytest.mark.parametrize("choice", ["action", "cancel", "close"])
def test_only_explicit_action_overrides_safe_default(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
) -> None:
    clicked: list[QAbstractButton | None] = []

    def inspect_exec(box: QMessageBox) -> int:
        cancel = box.button(QMessageBox.StandardButton.Cancel)
        assert box.defaultButton() is cancel
        assert box.escapeButton() is cancel
        action = next(
            button for button in box.buttons() if button.text() == "Save anyway"
        )
        clicked.append(
            action if choice == "action" else cancel if choice == "cancel" else None
        )
        return 1

    monkeypatch.setattr(QMessageBox, "exec", inspect_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: clicked[0])
    assert dialogue.confirm_content_discovery_override(
        title="Missing content",
        text="Check paths",
        action_text="Save anyway",
        details="Data/Core",
    ) is (choice == "action")
