import os
import platform
import sys
import traceback
from logging import getLogger, WARNING
from multiprocessing import freeze_support, set_start_method
from pathlib import Path
from tempfile import gettempdir
from types import TracebackType
from typing import Type, Optional

from PySide6.QtWidgets import QApplication
from loguru import logger

from controller.app_controller import AppController
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
        app_controller = AppController()
        sys.exit(app_controller.run())
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
        if "app_controller" in locals():
            try:
                logger.debug("Stopping watchdog...")
                app_controller.shutdown_watchdog()
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

    # Set the log level from the presence (or absence) of a "DEBUG" file in the app_data_folder
    debug_file_path = AppInfo().app_data_folder / "DEBUG"
    if debug_file_path.exists() and debug_file_path.is_file():
        DEBUG_MODE = True
        log_level = "DEBUG"
    else:
        DEBUG_MODE = False
        log_level = "INFO"

    # We have log_file (foo.log) and old_log_file (foo.old.log). If old_log_file exists,
    # remove it. If log_file exists, rename it to old_log_file. When we pass log_file to
    # the logger as an argument, it will automatically be created.
    log_file = AppInfo().user_log_folder / (AppInfo().app_name + ".log")
    old_log_file = AppInfo().user_log_folder / (AppInfo().app_name + ".old.log")
    if old_log_file.exists() and old_log_file.is_file():
        old_log_file.unlink()
    if log_file.exists() and log_file.is_file():
        log_file.rename(old_log_file)

    # Define the log format string
    format_string = (
        "{time} {level:<8} {thread.name:<10} {file}:{function}:{line} {message}"
    )

    # Remove the default stderr logger
    logger.remove()

    # Create the file logger
    logger.add(log_file, level="DEBUG" if DEBUG_MODE else "INFO", format=format_string)

    # Add as stdout logger if we're running from the Python interpreter
    if not "__compiled__" in globals():
        logger.add(
            sys.stdout,
            level="DEBUG" if DEBUG_MODE else "INFO",
            format=format_string,
            colorize=False,
        )

    # Setup Environment
    if "__compiled__" in globals():
        os.environ[
            "QTWEBENGINE_LOCALES_PATH"
        ] = f'{str(Path(os.path.join(os.path.dirname(__file__), "qtwebengine_locales")).resolve())}'

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
