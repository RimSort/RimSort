from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QMessageBox
from typing import Optional

from logger_tt import logger

DEFAULT_TITLE = "RimSort"


def show_dialogue_conditional(
    title: Optional[str] = None,
    text: Optional[str] = None,
    information: Optional[str] = None,
) -> str:
    """
    Displays a dialogue, prompting the user for input

    :param title: text to pass to setWindowTitle
    :param text: text to pass to setText
    :param information: text to pass to setInformativeText
    """
    logger.info(
        f"Showing dialogue box with input: [{title}], [{text}], [{information}]"
    )
    dialogue = QMessageBox()
    if title:
        dialogue.setWindowTitle(title)
    else:
        dialogue.setWindowTitle(DEFAULT_TITLE)
    if text:
        dialogue.setText(text)
    if information:
        dialogue.setInformativeText(information)
    dialogue.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    dialogue.exec_()
    response = dialogue.clickedButton()
    return response.text()


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
    info_message_box.setIcon(QMessageBox.Warning)
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
    logger.info("Finished showing information box")
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
    warning_message_box.setIcon(QMessageBox.Warning)
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
    logger.info("Finished showing warning box")
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
    fatal_message_box.setIcon(QMessageBox.Critical)
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
    logger.info("Finished showing fatal error box")
    fatal_message_box.exec_()
