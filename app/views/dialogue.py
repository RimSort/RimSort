import os
from pathlib import Path
from typing import List, Optional, Tuple

from deprecated import deprecated
from loguru import logger
from PySide6.QtCore import QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

import app.utils.generic as generic
from app.utils.app_info import AppInfo

# Constants
DEFAULT_TITLE = "RimSort"


def show_dialogue_confirmation(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
    button_text: Optional[str] = "Yes",
) -> str:
    """
    Displays a dialogue with a single custom button (defaulting to "Yes").
    :param title: text to pass to setWindowTitle
    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    """
    logger.info(
        f"Showing dialogue box with input: [{title}], [{text}], [{information}] [{details}]"
    )

    # Set up the message box
    dialogue = _setup_messagebox(title)

    # Remove standard buttons
    dialogue.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    dialogue.setDefaultButton(QMessageBox.StandardButton.Cancel)

    # Add data
    if text:
        dialogue.setText(text)
    if information:
        dialogue.setInformativeText(information)
    if details:
        dialogue.setDetailedText(details)

    # Show the message box & return response
    dialogue.exec_()
    response = dialogue.clickedButton()
    return response.text()


def show_dialogue_conditional(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
    button_text_override: Optional[List[str]] = None,
) -> str:
    """
    Displays a dialogue, prompting the user for input

    :param title: text to pass to setWindowTitle
    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    :param button_text_override: list of strings to override the default button texts
    """
    logger.info(
        f"Showing dialogue box with input: [{title}], [{text}], [{information}] [{details}] BTN OVERRIDES: [{button_text_override}]"
    )

    # Set up the message box
    dialogue = _setup_messagebox(title)

    # Create our buttons (accommodate any overrides passed)
    if button_text_override:
        # Remove standard buttons
        dialogue.setStandardButtons(QMessageBox.StandardButton.Cancel)

        # Add custom buttons
        custom_btns = []
        for btn_text in button_text_override:
            custom_btn = QPushButton(btn_text)
            custom_btn.setFixedWidth(custom_btn.sizeHint().width())
            custom_btns.append(custom_btn)
            dialogue.addButton(custom_btn, QMessageBox.ButtonRole.ActionRole)
    else:
        # Configure buttons
        dialogue.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dialogue.setEscapeButton(QMessageBox.StandardButton.No)

    # Add data
    if text:
        dialogue.setText(text)
    if information:
        dialogue.setInformativeText(information)
    if details:
        dialogue.setDetailedText(details)

    # Show the message box & return response
    dialogue.exec_()
    response = dialogue.clickedButton()
    return response.text()


@deprecated(reason="Just use QInputDialog().getText() instead")
def show_dialogue_input(
    title: str = "",
    label: str = "",
    text: str = "",
    parent: QWidget | None = None,
) -> Tuple[str, bool]:
    return QInputDialog().getText(parent, title, label, text=text)  # type: ignore # Is okay to set parent to None


def show_dialogue_file(
    mode: str,
    caption: str = "",
    _dir: str = "",
    _filter: str = "",
) -> Optional[str]:
    path = None
    if mode == "open":
        path, _ = QFileDialog.getOpenFileName(caption=caption, dir=_dir, filter=_filter)
    elif mode == "open_dir":
        path = QFileDialog.getExistingDirectory(caption=caption, dir=_dir)
    elif mode == "save":
        path, _ = QFileDialog.getSaveFileName(caption=caption, dir=_dir, filter=_filter)
    else:
        # Handle error or unknown mode
        logger.error("File dialogue mode not implemented.")
        return None
    return str(Path(os.path.normpath(path)).resolve()) if path != "" else None

# jscpd:ignore-start
def show_information(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
    parent: QWidget | None = None,
) -> None:
    """
    Creates a message box dialogue. Has no icon.

    :param title: Window title, defaults to None
    :type title: Optional[str], optional
    :param text: Short text description, defaults to None
    :type text: Optional[str], optional
    :param information: Long form information, defaults to None
    :type information: Optional[str], optional
    :param details: Optional details that are hidden in a sub menu, defaults to None
    :type details: Optional[str], optional
    :param parent: The parent widget, defaults to None
    :type parent: QWidget | None, optional
    """
    # jscpd:ignore-end
    logger.info(
        f"Showing information box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    info_message_box = QMessageBox(parent=parent)
    info_message_box.setTextFormat(Qt.TextFormat.RichText)
    info_message_box.setIcon(QMessageBox.Icon.Information)
    info_message_box.setObjectName("dialogue")
    if title:
        info_message_box.setWindowTitle(title)
    else:
        info_message_box.setWindowTitle(DEFAULT_TITLE)

    # Add data
    if text:
        info_message_box.setText(text)
    if information:
        info_message_box.setInformativeText(information)
    if details:
        info_message_box.setDetailedText(details)

    # Show the message box
    logger.debug("Finished showing information box")
    info_message_box.exec_()


# jscpd:ignore-start
def show_warning(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
    parent: QWidget | None = None,
) -> None:
    """Creates a warning dialogue. Utilizes the warning icon.

    :param title: Window title, defaults to None
    :type title: Optional[str], optional
    :param text: Short text description, defaults to None
    :type text: Optional[str], optional
    :param information: Long form information, defaults to None
    :type information: Optional[str], optional
    :param details: Optional details that are hidden in a sub menu, defaults to None
    :type details: Optional[str], optional
    :param parent: The parent widget, defaults to None
    :type parent: QWidget | None, optional
    """
    # jscpd:ignore-end
    logger.info(
        f"Showing warning box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    warning_message_box = QMessageBox(parent=parent)
    warning_message_box.setTextFormat(Qt.TextFormat.RichText)
    warning_message_box.setIcon(QMessageBox.Icon.Warning)
    warning_message_box.setObjectName("dialogue")
    if title:
        warning_message_box.setWindowTitle(title)
    else:
        warning_message_box.setWindowTitle(DEFAULT_TITLE)

    # Add data
    if text:
        warning_message_box.setText(text)
    if information:
        warning_message_box.setInformativeText(information)
    if details:
        warning_message_box.setDetailedText(details)

    # Show the message box
    logger.debug("Finished showing warning box")
    warning_message_box.exec_()


def show_fatal_error(
    title: str = "Fatal Error",
    text: str = "A fatal error has occurred!",
    information: str = "Please report the error to the developers.",
    details: str = "",
) -> None:
    """
    Displays a critical error message box, containing text,
    information, and details. Currently only called if there
    are any hard exceptions that cause the main app exec
    loop to stop functioning.

    :param title: text to pass to setWindowTitle
    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    """
    logger.info(
        f"Showing fatal error box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    diag = FatalErrorDialog(title, text, information, details)
    diag.exec_()


class FatalErrorDialog(QDialog):
    """Custom dialog to display fatal errors.

    Has button to show more details, open the log directory, and upload the log file to 0x0.
    """

    def __init__(
        self,
        title: str = "Fatal Error",
        text: str = "A fatal error has occurred!",
        information: str = "Please report the error to the developers.",
        details: str = "",
    ) -> None:
        super().__init__()

        # Set up the message box
        self.setWindowTitle(title)
        self.setModal(True)
        self.setObjectName("dialogue")

        # Dynamic sizing
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )

        # Add data
        self.text = text
        self.information = information
        self.details = details

        # Buttons
        self.details_btn = QPushButton("Show Details")
        self.close_btn = QPushButton("Close")
        self.open_log_btn = QPushButton("Open Log Directory")
        self.upload_log_btn = QPushButton("Upload Log")
        self.upload_log_btn.setToolTip("Upload the log file to 0x0.st")

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.open_log_btn)
        btn_layout.addWidget(self.upload_log_btn)
        btn_layout.addWidget(self.close_btn)

        # Details
        self.details_edit = QPlainTextEdit()
        self.details_edit.setPlainText(self.details)
        self.details_edit.setMaximumHeight(150)
        self.details_edit.setReadOnly(True)
        self.details_edit.setHidden(True)

        # Set up the layout
        layout = QVBoxLayout()
        main_layout = QHBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Left-side
        l_layout = QVBoxLayout()
        # Icon
        piximap = getattr(QStyle, "SP_MessageBoxCritical")
        icon = self.style().standardIcon(piximap)
        label = QLabel()
        label.setPixmap(icon.pixmap(64, 64))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l_layout.addWidget(label)

        l_layout.addWidget(self.details_btn)
        l_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addLayout(l_layout)

        # Center spacer
        main_layout.addItem(QSpacerItem(20, 20))

        # Right-side
        r_layout = QVBoxLayout()

        txt = QLabel(self.text)
        txt.setWordWrap(True)
        r_layout.addWidget(QLabel(self.text))

        info = QLabel(self.information)
        info.setWordWrap(True)
        r_layout.addWidget(info)

        r_layout.addLayout(btn_layout)
        main_layout.addLayout(r_layout)

        layout.addLayout(main_layout)
        layout.addWidget(self.details_edit)

        self.setLayout(layout)
        self.setFixedWidth(self.sizeHint().width())

        # Connect buttons
        def _toggle_details() -> None:
            self.details_edit.setHidden(not self.details_edit.isHidden())
            if self.details_edit.isHidden():
                self.details_btn.setText("Show Details")
            else:
                self.details_btn.setText("Hide Details")
            self.adjustSize()

        self.close_btn.clicked.connect(self.close)
        self.open_log_btn.clicked.connect(
            lambda: generic.platform_specific_open(AppInfo().user_log_folder)
        )

        def _upload_log(parent: FatalErrorDialog) -> None:
            """Helper function to upload the log file to 0x0. Displays a loading dialog while doing so. When finished, copy the URL to the clipboard and display the link."""
            progress_diag = _UploadLogDialog(parent)
            progress_diag.show()

            task = UploadLogTask(progress_diag)
            QThreadPool.globalInstance().start(task)

        self.upload_log_btn.clicked.connect(lambda: _upload_log(self))
        self.details_btn.clicked.connect(lambda: _toggle_details())


class _UploadLogDialog(QDialog):
    _upload_finished_signal = Signal(bool, str)

    def __init__(self, parent: QWidget):
        super().__init__(parent=parent)

        self.setWindowTitle("Uploading Log...")
        self.setObjectName("dialogue")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        layout = QVBoxLayout()
        layout.addWidget(self.progress)
        self.setLayout(layout)

        def _on_upload_finished(result: bool, url: str) -> None:
            self.close()

            if result:
                # Show the URL
                generic.copy_to_clipboard_safely(url)
                show_information(
                    title="Log Upload Successful",
                    text="Log file uploaded successfully! Copied URL to clipboard.",
                    information=f"URL: <a href='{url}'>{url}</a>",
                    parent=parent,
                )
            else:
                show_warning(
                    title="Log Upload Failed",
                    text="Log file upload failed!",
                    information="Please check your internet connection and try again.",
                    parent=parent,
                )

        self._upload_finished_signal.connect(_on_upload_finished)


class UploadLogTask(QRunnable):
    def __init__(self, parent: _UploadLogDialog):
        super().__init__()
        self.parent = parent

    @Slot()
    def run(self) -> None:
        # Perform the upload task
        result, url = generic.upload_data_to_0x0_st(
            str(AppInfo().user_log_folder / "RimSort.log")
        )

        # Emit signal on completion
        self.parent._upload_finished_signal.emit(result, url)


def _setup_messagebox(title: str | None) -> QMessageBox:
    """Helper function to setup the message box

    :param title: The title of the message box
    :type title: str | None
    :return: The message box object
    :rtype: QMessageBox
    """
    dialogue = QMessageBox()
    dialogue.setTextFormat(Qt.TextFormat.RichText)
    dialogue.setIcon(QMessageBox.Icon.Question)
    dialogue.setObjectName("dialogue")
    if title:
        dialogue.setWindowTitle(title)
    else:
        dialogue.setWindowTitle(DEFAULT_TITLE)

    return dialogue
