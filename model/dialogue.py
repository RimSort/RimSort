from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QMessageBox
from typing import Optional

from logger_tt import logger


def show_dialogue_conditional(title: str, text: str, information: str) -> str:
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
    dialogue.setWindowTitle(title)
    dialogue.setText(text)
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
        f"Showing information box with input: [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    info_message_box = QMessageBox()
    info_message_box.setIcon(QMessageBox.Warning)
    if title:
        info_message_box.setWindowTitle(title)
    else:
        info_message_box.setWindowTitle("Information")

    # Add text
    if text is None:
        info_message_box.setText("RimSort has alerted!")
    else:
        info_message_box.setText(text)
    if information is None:
        info_message_box.setInformativeText(
            "This is an informational alert. Nothing has gone wrong, but if "
            "you are seeing this message that means we forgot to put proper "
            "information here. Please let us know at https://github.com/oceancabbage/RimSort."
        )
    else:
        info_message_box.setInformativeText(information)

    if details is not None:
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
        f"Showing warning box with input: [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    warning_message_box = QMessageBox()
    warning_message_box.setIcon(QMessageBox.Warning)
    if title:
        warning_message_box.setWindowTitle(title)
    else:
        warning_message_box.setWindowTitle("Warning")

    # Add text
    if text is None:
        warning_message_box.setText("Unexpected Behavior")
    else:
        warning_message_box.setText(text)
    if information is None:
        warning_message_box.setInformativeText(
            "RimSort has encountered a non-fatal uncaught exception. "
            "Please reach out to us at https://github.com/oceancabbage/RimSort "
            "with the Stack Trace below."
        )
    else:
        warning_message_box.setInformativeText(information)

    if details is not None:
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
        f"Showing fatal error box with input: [{text}], [{information}], [{details}]"
    )
    # Set up the message box
    fatal_message_box = QMessageBox()
    fatal_message_box.setIcon(QMessageBox.Critical)
    if title:
        fatal_message_box.setWindowTitle(title)
    else:
        fatal_message_box.setWindowTitle("Fatal Error")

    # Add text
    if text is None:
        fatal_message_box.setText("Fatal Error")
    else:
        fatal_message_box.setText(text)
    if information is None:
        fatal_message_box.setInformativeText(
            "RimSort has encountered a fatal uncaught exception. "
            "Please reach out to us at https://github.com/oceancabbage/RimSort "
            "with the Stack Trace below and the application log file. You can "
            "find the log file (RimSort.log) in the RimSort folder."
        )
    else:
        fatal_message_box.setInformativeText(information)

    if details is not None:
        fatal_message_box.setDetailedText(details)

    # Show the message box
    logger.info("Finished showing fatal error box")
    fatal_message_box.exec_()
