import os
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
)

from logger_tt import logger

DEFAULT_TITLE = "RimSort"


def show_dialogue_conditional(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
    button_text_override: Optional[list] = None,
) -> str:
    """
    Displays a dialogue, prompting the user for input

    :param title: text to pass to setWindowTitle
    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    """
    logger.info(
        f"Showing dialogue box with input: [{title}], [{text}], [{information}] [{details}] BTN OVERRIDES: [{button_text_override}]"
    )

    # Set up the message box
    dialogue = QMessageBox()
    dialogue.setTextFormat(Qt.RichText)
    dialogue.setIcon(QMessageBox.Question)
    dialogue.setObjectName("dialogue")
    if title:
        dialogue.setWindowTitle(title)
    else:
        dialogue.setWindowTitle(DEFAULT_TITLE)

    # Create our buttons (accommodate any overrides passed)
    if button_text_override:
        # Remove standard buttons
        dialogue.setStandardButtons(QMessageBox.Cancel)

        # Add custom buttons

        # Custom 1
        custom_btn_1 = QPushButton(button_text_override[0])
        custom_btn_1.setFixedWidth(custom_btn_1.sizeHint().width())
        dialogue.addButton(custom_btn_1, QMessageBox.ActionRole)
        # Custom 2
        custom_btn_2 = QPushButton(button_text_override[1])
        custom_btn_2.setFixedWidth(custom_btn_2.sizeHint().width())
        dialogue.addButton(custom_btn_2, QMessageBox.ActionRole)
        dialogue.setEscapeButton(QMessageBox.Cancel)
    else:
        # Configure buttons
        dialogue.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialogue.setEscapeButton(QMessageBox.No)

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


def show_dialogue_input(
    title: Optional[str] = None,
    text: Optional[str] = None,
    value: Optional[str] = None,
) -> Tuple[str, bool]:
    # Set up the message box
    dialogue = QInputDialog()
    dialogue.setObjectName("dialogue")
    if title:
        dialogue.setWindowTitle(title)
    else:
        dialogue.setWindowTitle(DEFAULT_TITLE)
    # Add data
    if text:
        dialogue.setLabelText(text)
    if value:
        dialogue.setTextValue(value)

    # Show the message box & return response
    if dialogue.exec() == QInputDialog.Accepted:
        result = True
    else:
        result = False
    response = dialogue.textValue()
    return response, result


def show_dialogue_file(mode: str, caption=None, _dir=None, _filter=None) -> Optional[str]:
    path = None
    if mode == "open":
        path, _ = QFileDialog.getOpenFileName(
            caption=caption,
            dir=_dir,
            filter=_filter
        )
    elif mode == "open_dir":
        path, _ = QFileDialog.getExistingDirectory(caption=caption, dir=_dir)
    elif mode == "save":
        path, _ = QFileDialog.getSaveFileName(
            caption=caption,
            dir=_dir,
            filter=_filter
        )
    else:
        # Handle error or unknown mode
        logger.error("File dialogue mode not implemented.")
        return None
    return path if path != '' else None


def show_information(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """
    Displays an info message box using the input parameters

    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    """
    logger.info(
        f"Showing information box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    info_message_box = QMessageBox()
    info_message_box.setTextFormat(Qt.RichText)
    info_message_box.setIcon(QMessageBox.Information)
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


def show_warning(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """
    Displays a warning message box using the input parameters

    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    """
    logger.info(
        f"Showing warning box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    warning_message_box = QMessageBox()
    warning_message_box.setTextFormat(Qt.RichText)
    warning_message_box.setIcon(QMessageBox.Warning)
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
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """
    Displays a critical error message box, containing text,
    information, and details. Currently only called if there
    are any hard exceptions that cause the main app exec
    loop to stop functioning.

    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    :param details: text to pass to setDetailedText
    """
    logger.info(
        f"Showing fatal error box with input: [{title}], [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    fatal_message_box = QMessageBox()
    fatal_message_box.setTextFormat(Qt.RichText)
    fatal_message_box.setIcon(QMessageBox.Critical)
    fatal_message_box.setObjectName("dialogue")
    if title:
        fatal_message_box.setWindowTitle(title)
    else:
        fatal_message_box.setWindowTitle(DEFAULT_TITLE)

    # Add data
    if text:
        fatal_message_box.setText(text)
    if information:
        fatal_message_box.setInformativeText(information)
    if details:
        fatal_message_box.setDetailedText(details)

    # Show the message box
    logger.debug("Finished showing fatal error box")
    fatal_message_box.exec_()
