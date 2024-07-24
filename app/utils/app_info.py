import os
import sys
from pathlib import Path
from typing import Optional

from lxml import etree, objectify
from platformdirs import PlatformDirs


class AppInfo:
    """
    Singleton class that provides information about the application and its related directories.

    This class encapsulates metadata about the application and provides properties to
    access important directories such as user data and log folders. The directories are determined
    using the `platformdirs` package, ensuring platform-specific conventions are adhered to.

    Examples:
        >>> print(app_info.app_name)
        >>> print(app_info.app_storage_folder)
    """

    _instance: Optional["AppInfo"] = None

    def __new__(cls) -> "AppInfo":
        """
        Create a new instance or return the existing singleton instance of the `AppInfo` class.
        """
        if not cls._instance:
            cls._instance = super(AppInfo, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the `AppInfo` instance, setting application metadata and determining important directories.

        Raises:
            Exception: If the main file path cannot be determined.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return

        main_file = sys.modules["__main__"].__file__

        if main_file is None:
            raise Exception("Unable to get the main file path.")

        # Need to go one up if we are running from source
        self._application_folder = (
            Path(main_file).resolve().parent
            if "__compiled__" in globals()
            # __compiled__ will be present if Nuitka has frozen this
            else Path(main_file).resolve().parent.parent
        )

        # Application metadata

        self._app_name = "RimSort"
        self._app_copyright = ""

        self._app_version = "Unknown version"
        version_file = str(self._application_folder / "version.xml")
        if os.path.exists(version_file):
            root = objectify.parse(version_file, parser=etree.XMLParser(recover=True))
            self._app_version = root.find("version").text

            # If edge in version_string, append short sha
            if "edge" in self._app_version.lower():
                self._app_version += f"+{root.find('commit').text[:7]}"

        # Define important directories using platformdirs

        platform_dirs = PlatformDirs(appname=self._app_name, appauthor=False)
        self._app_storage_folder: Path = Path(platform_dirs.user_data_dir)
        self._user_log_folder: Path = Path(platform_dirs.user_log_dir)

        # Derive some secondary directory paths

        self._databases_folder: Path = self._app_storage_folder / "dbs"
        self._theme_data_folder: Path = self._application_folder / "themes"

        # Make sure important directories exist

        self._app_storage_folder.mkdir(parents=True, exist_ok=True)
        self._user_log_folder.mkdir(parents=True, exist_ok=True)

        self._databases_folder.mkdir(parents=True, exist_ok=True)

        self._is_initialized: bool = True

    @property
    def app_name(self) -> str:
        """
        Get the name of the application.

        Returns:
            str: The name of the application.
        """
        return self._app_name

    @property
    def app_version(self) -> str:
        """
        Get the application version string.

        Returns:
            str: The version of the application.
        """
        return self._app_version

    @property
    def app_copyright(self) -> str:
        """
        Get the copyright information for the application.

        Returns:
            str: The copyright information for the application.
        """
        return self._app_copyright

    @property
    def application_folder(self) -> Path:
        """
        Get the path to the folder where the main application file resides.

        Returns:
            Path: The path to the application's main folder.
        """
        return self._application_folder

    @property
    def app_storage_folder(self) -> Path:
        """
        Get the path to the folder where user-specific data for the application is stored.

        This directory is determined using platform-specific conventions.

        Returns:
            Path: The path to the user-specific data folder.
        """
        return self._app_storage_folder

    @property
    def user_log_folder(self) -> Path:
        """
        Get the path to the folder where application logs are stored for the user.

        This directory is determined using platform-specific conventions.

        Returns:
            Path: The path to the user-specific log folder.
        """
        return self._user_log_folder

    @property
    def theme_data_folder(self) -> Path:
        """
        Get the path to the folder where application-specific data is stored.
        """
        return self._theme_data_folder

    @property
    def databases_folder(self) -> Path:
        """
        Get the path to the folder where application databases are stored.
        """
        return self._databases_folder
