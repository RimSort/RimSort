from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from pytestqt import qtbot  # type: ignore #pytestqt is untyped and has no stubs

from app.views.dialogue import BinaryChoiceDialog


@pytest.fixture(scope="module")
def app() -> Generator[QApplication, None, None]:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()


class TestBinaryChoiceDialog:
    def test_initialization(
        self,
        app: Generator[QApplication, None, None],
    ) -> None:
        def _test_basics(
            title: str = "",
            text: str = "",
            information: str = "",
            details: str | None = None,
            positive_text: str | None = None,
            negative_text: str | None = None,
            positive_btn: QMessageBox.StandardButton | None = None,
            negative_btn: QMessageBox.StandardButton | None = None,
            default_negative: bool = True,
            icon: QMessageBox.Icon = QMessageBox.Icon.Question,
            parent: QWidget | None = None,
        ) -> BinaryChoiceDialog | None:
            # If a parameter is None, it should be in the construction
            try:
                dialog_args: dict[
                    str,
                    str
                    | QMessageBox.StandardButton
                    | bool
                    | QMessageBox.Icon
                    | QWidget
                    | None,
                ] = {
                    "title": title,
                    "text": text,
                    "information": information,
                    "details": details,
                    "positive_text": positive_text,
                    "negative_text": negative_text,
                    "default_negative": default_negative,
                    "icon": icon,
                    "parent": parent,
                }

                if positive_btn is not None:
                    dialog_args["positive_btn"] = positive_btn
                if negative_btn is not None:
                    dialog_args["negative_btn"] = negative_btn

                dialog = BinaryChoiceDialog(**dialog_args)  # type: ignore
            except ValueError:
                if positive_btn is not None and negative_btn is not None:
                    if positive_btn == negative_btn:
                        # Correct error
                        return None
                # Unexpected error
                raise

            assert dialog.windowTitle() == title
            if dialog.textFormat() == Qt.TextFormat.RichText:
                assert dialog.text() == f"<b>{text}</b>"
            else:
                assert dialog.text() == text
            assert dialog.informativeText() == information
            if positive_text is not None:
                assert dialog.button(dialog.positive_btn).text() == positive_text
            if negative_text is not None:
                assert dialog.button(dialog.negative_btn).text() == negative_text
            if positive_btn is not None:
                assert dialog.button(positive_btn)
            if negative_btn is not None:
                assert dialog.button(negative_btn)
            if default_negative:
                assert (
                    dialog.defaultButton().text()
                    == dialog.button(dialog.negative_btn).text()
                )
            else:
                assert (
                    dialog.defaultButton().text()
                    == dialog.button(dialog.positive_btn).text()
                )

            if details is not None:
                assert dialog.detailedText() == details
                for btn in dialog.buttons():
                    if btn.text() == "Show Details...":
                        assert btn.isEnabled()
                        break
            else:
                assert dialog.detailedText() == ""
                for btn in dialog.buttons():
                    if btn.text() == "Show Details...":
                        assert not btn.isEnabled()
                        break
            assert dialog.icon() == icon
            assert dialog.parent() == parent
            return dialog

        # With details
        assert (
            _test_basics(
                title="1Title",
                text="1Text",
                information="1Information",
                details="1Details",
                positive_text="1Positive",
                negative_text="1Negative",
                default_negative=False,
                icon=QMessageBox.Icon.Question,
            )
            is not None
        )

        assert (
            _test_basics(
                title="2Title",
                text="2Text",
                information="2Information",
                details=None,
                positive_text="2Positive",
                negative_text="2Negative",
                negative_btn=QMessageBox.StandardButton.Discard,
                default_negative=True,
                icon=QMessageBox.Icon.Information,
            )
            is not None
        )

        # ValueError
        assert (
            _test_basics(
                title="3Title",
                text="3Text",
                information="3Information",
                details=None,
                positive_text="3Positive",
                negative_text="3Negative",
                positive_btn=QMessageBox.StandardButton.Abort,
                negative_btn=QMessageBox.StandardButton.Abort,
                default_negative=True,
                icon=QMessageBox.Icon.Information,
            )
            is None
        )

        # Default btn text
        dialogue_1 = _test_basics(
            title="4Title",
            text="4Text",
            information="4Information",
            details=None,
            positive_btn=QMessageBox.StandardButton.Close,
            negative_btn=QMessageBox.StandardButton.Cancel,
            default_negative=True,
            icon=QMessageBox.Icon.Information,
        )

        assert dialogue_1 is not None
        assert dialogue_1.button(dialogue_1.positive_btn).text() == "Close"
        assert dialogue_1.button(dialogue_1.negative_btn).text() == "Cancel"

    def test_click(self, qtbot: qtbot) -> None:
        dialog1 = BinaryChoiceDialog()
        qtbot.addWidget(dialog1)
        qtbot.mouseClick(
            dialog1.button(dialog1.positive_btn), Qt.MouseButton.LeftButton
        )
        assert dialog1.result() == dialog1.positive_btn

        dialog2 = BinaryChoiceDialog()
        qtbot.addWidget(dialog2)
        qtbot.mouseClick(
            dialog2.button(dialog2.negative_btn), Qt.MouseButton.LeftButton
        )
        assert dialog2.result() == dialog2.negative_btn

    @patch.object(BinaryChoiceDialog, "exec")
    def test_exec_is_positive(self, mock_exec: MagicMock, qtbot: qtbot) -> None:
        def _test_exec_is_positive(
            dialog: BinaryChoiceDialog, positive_clicked: bool
        ) -> None:
            with patch.object(
                BinaryChoiceDialog, "clickedButton"
            ) as mock_clickedButton:
                mock_clickedButton.return_value = dialog.button(
                    dialog.positive_btn if positive_clicked else dialog.negative_btn
                )

                result = dialog.exec_is_positive()
                assert result == positive_clicked
                mock_exec.assert_called_once()
                mock_clickedButton.assert_called_once()

                mock_exec.reset_mock()

        dialog = BinaryChoiceDialog(positive_text="yayayay")
        _test_exec_is_positive(dialog, True)

        dialog = BinaryChoiceDialog(positive_text="yayayay", negative_text="naynaynay")
        _test_exec_is_positive(dialog, False)

        dialog = BinaryChoiceDialog(
            positive_btn=QMessageBox.StandardButton.No,
            negative_btn=QMessageBox.StandardButton.Yes,
        )
        _test_exec_is_positive(dialog, False)
