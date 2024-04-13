from pathlib import Path
from typing import Optional

from platformdirs import PlatformDirs


class AppInfo:
    """
    Singleton class that provides information about the application and its related directories.

    This class encapsulates metadata about the application and provides properties to
    access important directories such as user data and log folders. The directories are determined
    using the `platformdirs` package, ensuring platform-specific conventions are adhered to.

    Examples:
        >>> app_info = AppInfo(__file__)
        >>> print(app_info.app_name)
        >>> print(app_info.app_storage_folder)
    """

    _instance: Optional["AppInfo"] = None

    def __new__(cls, main_file: Optional[str] = None) -> "AppInfo":
        """
        Create a new instance or return the existing singleton instance of the `AppInfo` class.
        """
        if not cls._instance:
            cls._instance = super(AppInfo, cls).__new__(cls)
        return cls._instance

    def __init__(self, main_file: Optional[str] = None) -> None:
        """
        Initialize the `AppInfo` instance, setting application metadata and determining important directories.

        Args:
            main_file (Optional[str]): Path to the main application file (i.e., __file__ from __main__).

        Raises:
            ValueError: If `main_file` is not provided during the first initialization.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return

        if main_file is None:
            raise ValueError("AppInfo must be initialized once with __file__.")

        # Need to go one up if we are running from source
        self._application_folder = (
            Path(main_file).resolve().parent
            if "__compiled__" in globals()  # __compiled__ will be present if Nuitka has frozen this
            else Path(main_file).resolve().parent.parent
        )

        # Application metadata

        self._app_name = "RimSort"
        self._app_version = ""
        self._app_copyright = ""

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
