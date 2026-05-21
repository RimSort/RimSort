#!/usr/bin/env python3
# Compilation mode
# nuitka-project: --assume-yes-for-downloads
# nuitka-project: --output-filename=RimSort
# nuitka-project: --output-dir={MAIN_DIRECTORY}/../build/
# nuitka-project: --windows-console-mode=attach
# nuitka-project: --noinclude-default-mode=error
# nuitka-project: --nofollow-import-to=numpy
# nuitka-project: --noinclude-data-files=*qtwebengine_devtools_resources.pak
# nuitka-project: --include-package=steamworks
# nuitka-project: --user-package-configuration-file={MAIN_DIRECTORY}/../rimsort.nuitka-package.config.yml
# nuitka-project: --include-data-file={MAIN_DIRECTORY}/../steam_appid.txt=steam_appid.txt
# nuitka-project: --windows-icon-from-ico={MAIN_DIRECTORY}/../themes/default-icons/AppIcon_alt.ico
# nuitka-project: --python-flag=no_asserts,no_docstrings

# The PySide6 plugin covers qt-plugins
# nuitka-project: --enable-plugin=pyside6

# OS-Specific options
# nuitka-project-if: {OS} == "Darwin":
#   nuitka-project: --mode=app
#   nuitka-project: --macos-app-icon={MAIN_DIRECTORY}/../themes/default-icons/AppIcon_a.icns
# nuitka-project-else:
#   nuitka-project: --mode=standalone

# nuitka-project-if: os.path.exists("{MAIN_DIRECTORY}/../version.xml"):
#   nuitka-project: --include-data-file={MAIN_DIRECTORY}/../version.xml=version.xml

import os
import platform
import re
import sys
import traceback
from multiprocessing import freeze_support, set_start_method
from types import TracebackType
from typing import Type

from loguru import logger

from app.controllers.app_controller import AppController
from app.utils.app_info import AppInfo
from app.views.dialogue import show_fatal_error

SYSTEM = platform.system()


def handle_exception(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
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
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).error(
            "The main application loop has failed with an uncaught exception"
        )
        show_fatal_error(
            title="RimSort crashed",
            text="The RimSort application crashed! Sorry for the inconvenience!",
            information="Please contact us on the Discord/Github to report the issue.",
            details="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )

    sys.exit()


# Uncaught exceptions during the application loop are handled
# through the function above
sys.excepthook = handle_exception


# Process --disable-updater flag if present (before any other initialization)
if "--disable-updater" in sys.argv:
    os.environ["RIMSORT_DISABLE_UPDATER"] = "1"
    # Remove all instances of the flag
    while "--disable-updater" in sys.argv:
        sys.argv.remove("--disable-updater")
    # Note: logger not yet configured, so can't log here

# Process --debug flag if present (before any other initialization)
DEBUG_MODE = "--debug" in sys.argv
while "--debug" in sys.argv:
    sys.argv.remove("--debug")


def main_thread() -> None:
    app_controller = None
    try:
        app_controller = AppController()
        sys.exit(app_controller.run())
    except Exception as e:
        # Catch exceptions during initial application instantiation
        # Uncaught exceptions during the application loop are caught with excepthook
        stacktrace: str = ""
        if isinstance(e, SystemExit):
            logger.warning("Exiting application")
        else:
            stacktrace = traceback.format_exc()
            stacktrace = re.sub(r"([?&])key=[^&\s\"']+", r"\1key=[REDACTED]", stacktrace)
        logger.error("The main application instantiation has failed with an uncaught exception:")
        logger.error(stacktrace)
        show_fatal_error(details=stacktrace)
    finally:
        if app_controller is not None and "app_controller" in locals():
            try:
                logger.debug("Stopping watchdog...")
                app_controller.shutdown_watchdog()
            except Exception as e:
                stacktrace = traceback.format_exc()
                logger.warning(f"Exception: {e}")
                logger.warning(f"watchdog received the following exception while exiting: {stacktrace}")
        logger.info("Exiting application!")
        sys.exit()


if __name__ == "__main__":
    # If RimSort is running from a --onefile Nuitka build, there are some nuances to consider:
    # https://nuitka.net/doc/user-manual.html#onefile-finding-files
    # You can override by passing --onefile-tempdir-spec to `nuitka`
    # See also: https://nuitka.net/doc/user-manual.html#use-case-4-program-distribution
    # Otherwise, use sys.argv[0] to get the actual relative path to the executable
    #########################################################################################

    # CRITICAL: Check for CLI mode BEFORE any imports that might use Qt
    # This must happen before AppInfo() or any other code that could trigger Qt initialization
    if len(sys.argv) > 1 and sys.argv[1] in ["build-db", "--help", "--version"]:
        # CLI mode - import and run without any GUI setup
        try:
            from app.utils.log_config import setup_logging

            setup_logging(
                log_dir=AppInfo().user_log_folder,
                debug=DEBUG_MODE,
                file_logging=DEBUG_MODE,
                json_logging=False,
            )

            from app.cli.main import cli

            cli()
        except Exception as e:
            # Handle CLI errors without Qt dialogs
            tb = traceback.format_exc()
            tb = re.sub(r"([?&])key=[^&\s\"']+", r"\1key=[REDACTED]", tb)
            print(f"Error: {e}", file=sys.stderr)
            print(tb, file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # GUI mode continues below with normal initialization
    # Compiled non-Linux builds must call freeze_support() and set_start_method()
    # BEFORE anything that touches multiprocessing (loguru's enqueue=True creates
    # an internal multiprocessing queue, locking in the start method context).
    if "__compiled__" in globals() and SYSTEM != "Linux":
        freeze_support()
        set_start_method("spawn")

    # Determine debug mode from --debug flag or DEBUG file
    debug_file_path = AppInfo().app_storage_folder / "DEBUG"
    if not DEBUG_MODE:
        DEBUG_MODE = debug_file_path.exists() and debug_file_path.is_file()

    from app.utils.log_config import setup_logging
    
    setup_logging(
        log_dir=AppInfo().user_log_folder,
        debug=DEBUG_MODE,
    )

    if "__compiled__" not in globals():
        logger.debug("Running using Python interpreter")
    else:
        # Configure QtWebEngine locales path
        os.environ["QTWEBENGINE_LOCALES_PATH"] = str(AppInfo().application_folder / "qtwebengine_locales")
        if SYSTEM != "Linux":
            logger.warning(
                "Non-Linux platform detected: using multiprocessing.freeze_support() & setting 'spawn' as MP method"
            )
        logger.debug("Running using Nuitka bundle")

    logger.info(f"Initializing RimSort application: {AppInfo().app_version}")
    main_thread()
