import sys

from multiprocessing import freeze_support, set_start_method

import os
from pathlib import Path
import platform
from tempfile import gettempdir
import traceback
from types import TracebackType
from typing import Type, Optional

from logger_tt import logger, setup_logging
from logging import getLogger, WARNING
from PySide6.QtWidgets import QApplication

from util.app_info import AppInfo
from view.main_window import MainWindow

SYSTEM = platform.system()
# Watchdog conditionals
if SYSTEM == "Darwin":
    # Comment to see logging for watchdog handler on Darwin
    getLogger("watchdog.observers.fsevents").setLevel(WARNING)
elif SYSTEM == "Linux":
    # Comment to see logging for watchdog handler on Linux
    getLogger("watchdog.observers.inotify_buffer").setLevel(WARNING)
elif SYSTEM == "Windows":
    pass

    # Comment to see logging for watchdog handler on Windows
    # This is a stub if it's ever even needed...
    # I still can't figure out why it won't log at all on Windows...?
    # getLogger("").setLevel(WARNING)

from model.dialogue import show_fatal_error
from util.proxy_style import ProxyStyle


def handle_exception(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_traceback: Optional[TracebackType],
) -> None:
    """
    This function is called (through excepthook) when the main application
    loop encounters an uncaught exception. When this happens, the error is
    logged to the log file and a Fatal QMessageBox is shown.
    """

    # Ignore KeyboardInterrupt exceptions, for when running through the terminal
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:  # Anything else, we want to log an error and notify the user
        logger.error(
            "The main application loop has failed with an uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        show_fatal_error(
            title="RimSort crashed",
            text="The RimSort application crashed! Sorry for the inconvenience!",
            information="Please contact us on the Discord/Github to report the issue.",
            details="".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            ),
        )

    sys.exit()


# Uncaught exceptions during the application loop are handled
# through the function above
sys.excepthook = handle_exception


def main_thread() -> None:
    try:
        # Create the application
        app = QApplication(sys.argv)
        app.setApplicationName("RimSort")
        # Get styling from game configuration
        logger.debug("Setting application style")
        app.setStyle(
            ProxyStyle()
        )  # Add proxy style for overriding some styling elements
        app.setStyleSheet(  # Add style sheet for styling layouts and widgets
            Path(
                os.path.join(os.path.dirname(__file__), "themes/RimPy/style.qss")
            ).read_text()
        )
        # Create the main window
        window = MainWindow(debug_mode=DEBUG_MODE)
        logger.info("Showing MainWindow")
        window.show()
        window.initialize_content()
        app.exec()
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        stacktrace: str = ""
        if isinstance(e, SystemExit):
            logger.warning("Exiting application")
        elif (
            e.__class__.__name__ == "HTTPError" or e.__class__.__name__ == "SSLError"
        ):  # requests.exceptions.HTTPError OR urllib3.exceptions.SSLError
            stacktrace = traceback.format_exc()
            # If an HTTPError from steam/urllib3 module(s) somehow is uncaught,
            # try to remove the Steam API key from the stacktrace
            pattern = "&key="
            stacktrace = stacktrace[
                : len(stacktrace)
                - (len(stacktrace) - (stacktrace.find(pattern) + len(pattern)))
            ]
        else:
            stacktrace = traceback.format_exc()
        logger.error(
            "The main application instantiation has failed with an uncaught exception:"
        )
        logger.error(stacktrace)
        show_fatal_error(details=stacktrace)
    finally:
        if "window" in locals():
            try:
                logger.debug("Stopping watchdog...")
                window.shutdown_watchdog()
            except:
                stacktrace = traceback.format_exc()
                logger.warning(
                    f"watchdog received the following exception while exiting: {stacktrace}"
                )
        logger.info("Exiting application!")
        sys.exit()


if __name__ == "__main__":
    # One-time initialization of AppInfo class (this must be done in __main__ so we can use __file__)
    AppInfo(main_file=__file__)

    # If RimSort is running from a --onefile Nuitka build, there are some nuances to consider:
    # https://nuitka.net/doc/user-manual.html#onefile-finding-files
    # You can override by passing --onefile-tempdir-spec to `nuitka`
    # See also: https://nuitka.net/doc/user-manual.html#use-case-4-program-distribution
    # Otherwise, use sys.argv[0] to get the actual relative path to the executable
    #########################################################################################
    #
    # Setup logging
    #
    data_path = str(Path(os.path.join(os.path.dirname(__file__), "data")).resolve())
    debug_file = str(Path(os.path.join(data_path, "DEBUG")).resolve())
    # Check if 'RimSort.log' exists and rename it to 'RimSort.old.log'
    log_file_path = str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve())
    log_old_file_path = str(
        Path(os.path.join(gettempdir(), "RimSort.old.log")).resolve()
    )
    # Rename old log if found
    if os.path.exists(log_file_path):
        os.replace(log_file_path, log_old_file_path)
    if os.path.exists(log_file_path):
        os.rename(log_file_path, log_old_file_path)
    # Enable logging options based on presence of DEBUG file
    if os.path.exists(debug_file):
        logging_config_path = str(
            Path(os.path.join(data_path, "logger_tt-DEBUG.json")).resolve()
        )
        DEBUG_MODE = True
    else:
        logging_config_path = str(
            Path(os.path.join(data_path, "logger_tt-INFO.json")).resolve()
        )
        DEBUG_MODE = False
    # Setup log file
    logging_file_path = str(Path(os.path.join(gettempdir(), "RimSort.log")).resolve())
    # Setup Environment
    if "__compiled__" in globals():
        os.environ[
            "QTWEBENGINE_LOCALES_PATH"
        ] = f'{str(Path(os.path.join(os.path.dirname(__file__), "qtwebengine_locales")).resolve())}'
    if SYSTEM == "Linux":
        # logger_tt
        setup_logging(
            config_path=logging_config_path,
            log_path=logging_file_path,
            use_multiprocessing="fork",
        )
        # Disable IBus integration on Linux
        os.environ["QT_IM_MODULE"] = ""
    else:
        # logger_tt
        setup_logging(
            config_path=logging_config_path,
            log_path=logging_file_path,
            use_multiprocessing="spawn",
        )
    # This check is used whether RimSort is running via Nuitka bundle
    if "__compiled__" in globals():
        logger.debug("Running using Nuitka bundle")
        if SYSTEM != "Linux":
            logger.warning(  # MacOS and Windows do not support fork, and can only use spawn
                "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
            )
            freeze_support()
            set_start_method("spawn")
    else:
        logger.debug("Running using Python interpreter")
    logger.debug("Initializing RimSort application")
    main_thread()
