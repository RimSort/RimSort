import os
import sys
from pathlib import Path
from typing import Tuple

from loguru import logger
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
    Slot,
)
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
from typing_extensions import deprecated

import app.utils.generic as generic
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus

# Constants
DEFAULT_TITLE = "RimSort"


def show_dialogue_conditional(
    title: str | None = None,
    text: str | None = None,
    information: str | None = None,
    details: str | None = None,
    button_text_override: list[str] | None = None,
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
        dialogue.button(QMessageBox.StandardButton.Cancel).setText(
            QCoreApplication.translate("show_dialogue_conditional", "Cancel")
        )

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


@deprecated("Just use QInputDialog().getText() instead")
def show_dialogue_input(
    title: str = "",
    label: str = "",
    text: str = "",
    parent: QWidget | None = None,
) -> Tuple[str, bool]:
    actual_parent = parent if parent is not None else QWidget()
    return QInputDialog().getText(actual_parent, title, label, text=text)


def show_dialogue_file(
    mode: str,
    caption: str = "",
    _dir: str = "",
    _filter: str = "",
) -> str | None:
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
    title: str | None = None,
    text: str | None = None,
    information: str | None = None,
    details: str | None = None,
    parent: QWidget | None = None,
) -> None:
    """
    Creates a message box dialogue. Has no icon.

    :param title: Window title
    :type title: str | None
    :param text: Short text description
    :type text: str | None
    :param information: Long form information
    :type information: str | None
    :param details: Optional details that are hidden in a sub menu
    :type details: str | None
    :param parent: The parent widget
    :type parent: QWidget | None
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
    info_message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    info_message_box.button(QMessageBox.StandardButton.Ok).setText(
        QCoreApplication.translate("show_dialogue_information", "OK")
    )
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
    title: str | None = None,
    text: str | None = None,
    information: str | None = None,
    details: str | None = None,
    parent: QWidget | None = None,
) -> None:
    """Creates a warning dialogue. Utilizes the warning icon.

    :param title: Window title
    :type title: str | None
    :param text: Short text description
    :type text: str | None
    :param information: Long form information
    :type information: str | None
    :param details: Optional details that are hidden in a sub menu
    :type details: str | None
    :param parent: The parent widget
    :type parent: QWidget | None
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

    warning_message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    warning_message_box.button(QMessageBox.StandardButton.Ok).setText(
        QCoreApplication.translate("show_warning", "OK")
    )

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


class _BaseDialogue(QDialog):
    """Base dialogue class for all custom dialogues."""

    _dialogue_type = "base dialogue box"

    def __init__(
        self,
        title: str,
        modal: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)

        # Set up the message box
        self.setWindowTitle(title)
        self.setModal(modal)
        self.setObjectName("dialogue")

        # Dynamic sizing
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )

    def exec(self) -> int:
        """Executes the message box and returns the result.

        :return: The result of the message box
        :rtype: int
        """
        logger.info(f"Showing {self._dialogue_type} with title: {self.windowTitle()}")
        result = super().exec()
        logger.info(
            f"Finished showing {self._dialogue_type} [{self.windowTitle()}] with result: {result}"
        )
        return result

    def exec_(self) -> int:
        """Executes the message box and returns the result.

        :return: The result of the message box
        :rtype: int
        """
        return self.exec()


class _BaseMessageBox(QMessageBox):
    """Base message box class for all custom message boxes."""

    _dialogue_type = "base message box"

    def __init__(
        self,
        title: str,
        text: str,
        information: str,
        icon: QMessageBox.Icon,
        details: str | None = None,
        text_format: Qt.TextFormat = Qt.TextFormat.RichText,
        modal: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(modal)
        self.setObjectName("dialogue")
        self.setTextFormat(text_format)
        self.setIcon(icon)
        # Set text to be bold via rich text
        if text_format == Qt.TextFormat.RichText:
            text = f"<b>{text}</b>"
        self.setText(text)
        self.setInformativeText(information)
        if details is not None:
            self.setDetailedText(details)

        # Dynamic sizing
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        self.setMinimumWidth(400)

    def exec(self) -> int:
        """Executes the message box and returns the result.

        :return: The result of the message box
        :rtype: int
        """
        logger.info(
            f"Showing {self._dialogue_type} with title: [{self.windowTitle()}], text: [{self.text()}], information: [{self.informativeText()}], details: [{self.detailedText()}]"
        )
        result = super().exec()
        logger.info(
            f"Finished showing {self._dialogue_type} [{self.windowTitle()}] with result: {result}"
        )
        return result

    def exec_(self) -> int:
        """Executes the message box and returns the result.

        :return: The result of the message box
        :rtype: int
        """
        return self.exec()


class InformationBox(_BaseMessageBox):
    """Custom message box to display an information message box. Only has an OK button."""

    def __init__(
        self,
        title: str = "",
        text: str = "",
        information: str = "",
        details: str | None = None,
        icon: QMessageBox.Icon = QMessageBox.Icon.Information,
        modal: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the information box.
        Used to display an information message box.
        Only has an OK button.

        :param title: The title of the message box
        :type title: str, optional
        :param text: The main text of the message box
        :type text: str, optional
        :param information: The informative text of the message box
        :type information: str, optional
        :param details: The detailed text of the message box. If not None, a button will be displayed to show/hide this text.
        :type details: str | None, optional
        :param icon: The icon to display in the message box. Defaults to an information icon.
        :type icon: QMessageBox.Icon, optional
        :param modal: Whether the message box is modal. Defaults to True.
        :type modal: bool, optional
        :param parent: The parent widget
        :type parent: QWidget | None, optional
        """
        super().__init__(
            title, text, information, icon, details, modal=modal, parent=parent
        )

        self.setStandardButtons(QMessageBox.StandardButton.Ok)
        self.setDefaultButton(QMessageBox.StandardButton.Ok)


class BinaryChoiceDialog(_BaseMessageBox):
    """Custom message box to display a binary choice message box."""

    def __init__(
        self,
        title: str = "",
        text: str = "",
        information: str = "",
        details: str | None = None,
        positive_text: str | None = None,
        negative_text: str | None = None,
        positive_btn: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes,
        negative_btn: QMessageBox.StandardButton = QMessageBox.StandardButton.Cancel,
        default_negative: bool = True,
        icon: QMessageBox.Icon = QMessageBox.Icon.Question,
        modal: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the binary choice dialog.
        Used to display a binary choice message box.
        Always has two buttons, one positive and one negative.
        These buttons cannot be the same type.

        :param title: The title of the message box
        :type title: str, optional
        :param text: The main text of the message box
        :type text: str, optional
        :param information: The informative text of the message box
        :type information: str, optional
        :param details: The detailed text of the message box. If not None, a button will be displayed to show/hide this text.
        :type details: str | None, optional
        :param positive_text: The text to display on the positive button. If None, the default text of the positive button will be used.
        :type positive_text: str | None, optional
        :param negative_text: The text to display on the negative button. If None, the default text of the negative button will be used.
        :type negative_text: str | None, optional
        :param positive_btn: The type of the positive button
        :type positive_btn: QMessageBox.StandardButton, optional
        :param negative_btn: The type of the negative button
        :type negative_btn: QMessageBox.StandardButton, optional
        :param default_negative: Whether the default button is the negative button. If False, the positive button will be the default button.
        :type default_negative: bool, optional
        :param icon: The icon to display in the message box. Defaults to a question mark.
        :type icon: QMessageBox.Icon, optional
        :param parent: The parent widget
        :type parent: QWidget | None, optional
        :raises ValueError: If the positive and negative buttons are the same
        """
        super().__init__(
            title, text, information, icon, details, modal=modal, parent=parent
        )

        if positive_btn == negative_btn:
            raise ValueError("Positive and negative buttons cannot be the same")

        # Configure buttons
        self.__positive_btn = positive_btn
        self.__negative_btn = negative_btn

        self.setStandardButtons(self.positive_btn | self.negative_btn)

        if default_negative:
            self.setDefaultButton(self.negative_btn)
        else:
            self.setDefaultButton(self.positive_btn)

        # Set button text where necessary
        if positive_text is not None:
            self.button(self.positive_btn).setText(positive_text)
        if negative_text is not None:
            self.button(self.negative_btn).setText(negative_text)

    @property
    def positive_btn(self) -> QMessageBox.StandardButton:
        return self.__positive_btn

    @property
    def negative_btn(self) -> QMessageBox.StandardButton:
        return self.__negative_btn

    def exec_is_positive(self) -> bool:
        """Executes the dialog and returns whether the positive button was clicked.

        :return: True if the positive button was clicked, False otherwise.
        :rtype: bool
        """
        self.exec()
        response = self.clickedButton()
        return response == self.button(self.positive_btn)


class FatalErrorDialog(_BaseDialogue):
    """Custom dialog to display fatal errors.

    Has button to show more details, open the log directory, and upload the log file to 0x0.
    """

    def __init__(
        self,
        title: str = "Fatal Error",
        text: str = "A fatal error has occurred!",
        information: str = "Please report the error to the developers.",
        details: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent=parent)

        # Add data
        self.text = text
        self.information = information
        self.details = details

        # Buttons
        self.details_btn = QPushButton(self.tr("Show Details"))
        self.close_btn = QPushButton(self.tr("Close"))
        self.open_log_btn = QPushButton(self.tr("Open Log Directory"))
        self.upload_log_btn = QPushButton(self.tr("Upload Log"))
        self.upload_log_btn.setToolTip(self.tr("Upload the log file to 0x0.st"))

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
        l_layout = _setup_error_icon(self, self.details_btn)
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
                self.details_btn.setText(self.tr("Show Details"))
            else:
                self.details_btn.setText(self.tr("Hide Details"))
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

        self.setWindowTitle(self.tr("Uploading Log..."))
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
                    title=self.tr("Log Upload Successful"),
                    text=self.tr(
                        "Log file uploaded successfully! Copied URL to clipboard."
                    ),
                    information=f"URL: <a href='{url}'>{url}</a>",
                    parent=parent,
                )
            else:
                show_warning(
                    title=self.tr("Log Upload Failed"),
                    text=self.tr("Log file upload failed!"),
                    information=self.tr(
                        "Please check your internet connection and try again."
                    ),
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


def _setup_messagebox(
    title: str | None,
    icon: QMessageBox.Icon = QMessageBox.Icon.Question,
    parent: QWidget | None = None,
) -> QMessageBox:
    """Helper function to setup the message box

    :param title: The title of the message box
    :type title: str | None
    :return: The message box object
    :rtype: QMessageBox
    """
    dialogue = QMessageBox(parent)
    dialogue.setTextFormat(Qt.TextFormat.RichText)
    dialogue.setIcon(icon)
    dialogue.setObjectName("dialogue")
    if title:
        dialogue.setWindowTitle(title)
    else:
        dialogue.setWindowTitle(DEFAULT_TITLE)

    return dialogue


def show_settings_error() -> None:
    """
    Displays a fatal error box indicating the app was
    unable to start due to corrupt settings. Called if unable
    to parse the settings file.

    :param settings: settings model to allow resetting settings
    """
    logger.info("Showing settings failure box")
    diag = SettingsFailureDialog()
    diag.exec_()


class SettingsFailureDialog(QDialog):
    """Custom dialog to display fatal errors regarding settings parsing.

    Has buttons to open the settings file, open the settings folder, or reset settings.
    Exiting the dialog will terminate the application.
    """

    def __init__(self) -> None:
        super().__init__()

        # Set up the message box
        self.setWindowTitle("Unable to parse settings file!")
        self.setModal(True)
        self.setObjectName("dialogue")

        # Dynamic sizing
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )

        # Add data
        self.text = self.tr(
            "Your RimSort settings file is corrupt.\nPlease choose one of the following options to proceed."
        )

        # Buttons
        self.open_settings_file_btn = QPushButton(self.tr("Open Settings"))
        self.open_settings_folder_btn = QPushButton(self.tr("Open Settings Folder"))
        self.reset_settings_btn = QPushButton(self.tr("Reset Settings"))
        self.close_application_btn = QPushButton(self.tr("Exit RimSort"))

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.open_settings_file_btn)
        btn_layout.addWidget(self.open_settings_folder_btn)
        btn_layout.addWidget(self.reset_settings_btn)

        # Set up the layout
        layout = QVBoxLayout()
        main_layout = QHBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Left-side
        l_layout = _setup_error_icon(self)
        main_layout.addLayout(l_layout)

        # Center spacer
        main_layout.addItem(QSpacerItem(10, 0))

        # Right-side
        r_layout = QVBoxLayout()

        txt = QLabel(self.text)
        txt.setWordWrap(True)
        r_layout.addWidget(QLabel(self.text))

        r_layout.addItem(QSpacerItem(20, 20))

        r_layout.addLayout(btn_layout)

        r_layout.addWidget(self.close_application_btn)
        main_layout.addLayout(r_layout)

        layout.addLayout(main_layout)

        self.setLayout(layout)
        self.setFixedWidth(self.sizeHint().width())

        def _open_settings_file() -> None:
            generic.platform_specific_open(AppInfo().app_settings_file)

        def _open_settings_folder() -> None:
            generic.platform_specific_open(AppInfo().app_storage_folder)

        def _reset_settings_file() -> None:
            EventBus().reset_settings_file.emit
            self.accept()

        self.open_settings_file_btn.clicked.connect(lambda: _open_settings_file())
        self.open_settings_folder_btn.clicked.connect(lambda: _open_settings_folder())
        self.reset_settings_btn.clicked.connect(lambda: _reset_settings_file())
        self.close_application_btn.clicked.connect(lambda: sys.exit())

    def closeEvent(self, event: QEvent) -> None:
        sys.exit()


def _setup_error_icon(
    diag: QDialog, details_btn: QPushButton | None = None
) -> QVBoxLayout:
    l_layout = QVBoxLayout()
    piximap = getattr(QStyle, "SP_MessageBoxCritical")
    icon = diag.style().standardIcon(piximap)
    label = QLabel()
    label.setPixmap(icon.pixmap(64, 64))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    l_layout.addWidget(label)
    if details_btn is not None:
        l_layout.addWidget(details_btn)
    l_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return l_layout
