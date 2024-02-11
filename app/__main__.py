import os
import platform
import sys
import traceback
from logging import getLogger, WARNING
from multiprocessing import freeze_support, set_start_method
from types import TracebackType
from typing import Type, Optional

from loguru import logger

from app.models.dialogue import show_fatal_error
from app.utils.app_info import AppInfo

# Initialize AppInfo class only if the script is run as the main module
if __name__ == "__main__":
    # One-time initialization of AppInfo class (this must be done in __main__ so we can use __file__)
    # Initialize as early as possible!
    AppInfo(main_file=__file__)

from app.controllers.app_controller import AppController

# Determine the operating system
SYSTEM = platform.system()

# Configure logging levels for different operating systems
if SYSTEM == "Darwin":
    # Suppress logging for watchdog handler on Darwin
    getLogger("watchdog.observers.fsevents").setLevel(WARNING)
elif SYSTEM == "Linux":
    # Suppress logging for watchdog handler on Linux
    getLogger("watchdog.observers.inotify_buffer").setLevel(WARNING)
elif SYSTEM == "Windows":
    pass
    # Stub for logging on Windows - not currently used
    # getLogger("").setLevel(WARNING)


def handle_exception(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_traceback: Optional[TracebackType],
) -> None:
    """
    Handle uncaught exceptions in the main application loop.

    Args:
        exc_type: Type of the exception.
        exc_value: Value of the exception.
        exc_traceback: Traceback information.
    """
    # Ignore KeyboardInterrupt exceptions, for when running through the terminal
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:
        # Log the error and notify the user
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


# Uncaught exceptions during the application loop are handled through the function above
sys.excepthook = handle_exception


def main_thread() -> None:
    """
    Main function for running the application.
    """
    try:
        app_controller = AppController()
        sys.exit(app_controller.run())
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        stacktrace: str = ""
        if isinstance(e, SystemExit):
            logger.warning("Exiting application")
        elif e.__class__.__name__ == "HTTPError" or e.__class__.__name__ == "SSLError":
            # Handle specific exceptions related to HTTP and SSL errors
            stacktrace = traceback.format_exc()
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
            except Exception:
                # Handle exceptions during watchdog shutdown
                stacktrace = traceback.format_exc()
                logger.warning(
                    f"watchdog received the following exception while exiting: {stacktrace}"
                )
        logger.info("Exiting application!")
        sys.exit()


if __name__ == "__main__":
    # Set the log level based on the presence of a "DEBUG" file in the app_data_folder
    debug_file_path = AppInfo().app_storage_folder / "DEBUG"
    debug_mode = debug_file_path.exists() and debug_file_path.is_file()

    # Remove old log files and configure loggers
    log_file = AppInfo().user_log_folder / (AppInfo().app_name + ".log")
    old_log_file = AppInfo().user_log_folder / (AppInfo().app_name + ".old.log")
    if old_log_file.exists() and old_log_file.is_file():
        old_log_file.unlink()
    if log_file.exists() and log_file.is_file():
        log_file.rename(old_log_file)

    # Define the log format string
    format_string = (
        "[{level}]"
        "[{time:YYYY-MM-DD HH:mm:ss}]"
        "[{process.id}]"
        "[{thread.name}]"
        "[{module}]"
        "[{function}][{line}]"
        " : "
        "{message}"
    )

    # Remove the default stderr logger
    logger.remove()

    # Create the file logger
    logger.add(log_file, level="DEBUG" if debug_mode else "INFO", format=format_string)

    # Add a "WARNING" or higher stderr logger
    logger.add(
        sys.stderr,
        level="WARNING",
        format=format_string,
        colorize=False,
    )

    if not "__compiled__" in globals():
        logger.debug("Running using Python interpreter")
    else:
        # Configure QtWebEngine locales path for Nuitka bundle
        os.environ["QTWEBENGINE_LOCALES_PATH"] = str(
            AppInfo().application_folder / "qtwebengine_locales"
        )

        # MacOS and Windows do not support fork, and can only use spawn
        if SYSTEM != "Linux":
            logger.warning(
                "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
            )
            freeze_support()
            set_start_method("spawn")

        logger.debug("Running using Nuitka bundle")

    logger.debug("Initializing RimSort application")
    main_thread()
