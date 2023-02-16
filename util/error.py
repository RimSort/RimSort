import sys

from PySide2.QtWidgets import *
from typing import Optional


def show_warning(
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """
    Displays a warning message box displaying the input string.

    :param warning_message: the warning message to display
    """
    # Set up the message box
    warning_message_box = QMessageBox()
    warning_message_box.setIcon(QMessageBox.Warning)
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
    warning_message_box.exec_()


def show_fatal(
    text: Optional[str] = None,
    information: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """
    Displays a critical error message box, containing text,
    information, and details. Currently only called if there
    are any hard exceptions that cause the main app exec
    loop to stop functoning.

    :param text: text to display
    :param information: more verbose, informational text to display
    :param details: details to show in a scroll box
    """
    # Set up the message box
    fatal_message_box = QMessageBox()
    fatal_message_box.setIcon(QMessageBox.Critical)
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
            "with the Stack Trace below."
        )
    else:
        fatal_message_box.setInformativeText(information)

    if details is not None:
        fatal_message_box.setDetailedText(details)

    # Show the message box
    fatal_message_box.exec_()
