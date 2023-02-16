import sys

from PySide2.QtWidgets import *


def show_warning(warning_message: str) -> None:
    """
    Displays a warning message box displaying the input string.

    :param warning_message: the warning message to display
    """
    warning = QMessageBox()
    warning.setIcon(QMessageBox.Warning)
    warning.setText("Warning")
    warning.setInformativeText(warning_message)
    warning.setWindowTitle("Warning")
    warning.exec_()

def show_fatal_error(error_message: str) -> None:
    """
    Displays an error message box displaying the input string.

    :param error_message: the error message to display
    """
    error = QMessageBox()
    error.setIcon(QMessageBox.Critical)
    error.setText("Error")
    error.setInformativeText(error_message)
    error.setWindowTitle("Error")
    error.exec_()
