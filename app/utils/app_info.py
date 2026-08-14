import os
import sys
from pathlib import Path

from loguru import logger
from lxml import etree, objectify
from platformdirs import PlatformDirs

from app.utils.constants import DEFAULT_USER_RULES
from app.utils.json_utils import atomic_json_dump


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

    _instance: "None | AppInfo" = None

    def __new__(cls) -> "AppInfo":
        """
        Create a new instance or return the existing singleton instance of the `AppInfo` class.
        """
        if not cls._instance:
            cls._instance = super(AppInfo, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def _resolve_dev_mode() -> bool:
        """Determine whether the application is running in development mode.

        Dev mode is only active when explicitly requested via the ``--dev``
        CLI flag (which sets ``RIMSORT_DEV=1``) or the ``RIMSORT_DEV`` env
        var directly.

        ``RIMSORT_DEV`` values: ``"1"`` / ``"true"`` -> True;
        ``"0"`` / ``"false"`` -> False.  Default (unset): False.
        """
        env = os.environ.get("RIMSORT_DEV", "").lower()
        if env in ("1", "true"):
            return True
        if env in ("0", "false"):
            return False
        if env:
            logger.warning(
                f"Unrecognized RIMSORT_DEV value '{env}' — expected 1/true/0/false"
            )
        return False

    def __init__(self) -> None:
        """
        Initialize the `AppInfo` instance, setting application metadata and determining important directories.

        Raises:
            Exception: If the main file path cannot be determined.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return

        main_file = getattr(sys.modules.get("__main__"), "__file__", None)

        if main_file is None:
            # Spawned child processes (e.g. multiprocessing on Windows) may not
            # have __main__.__file__.  Default to the working directory, which
            # is inherited from the parent process (the project root).
            self._application_folder = Path.cwd()
        else:
            # Need to go one up if we are running from source
            self._application_folder = (
                Path(main_file).resolve().parent
                if "__compiled__" in globals()
                # __compiled__ will be present if Nuitka has frozen this
                else Path(main_file).resolve().parent.parent
            )

        self._is_dev_mode = self._resolve_dev_mode()

        # Application metadata
        self._app_name = "RimSort"
        self._app_copyright = ""

        self._app_version = "Unknown version"
        version_file = str(self._application_folder / "version.xml")
        if os.path.exists(version_file):
            root = objectify.parse(version_file, parser=etree.XMLParser(recover=True))
            ver = root.find("version")
            if ver is not None and ver.text is not None:
                self._app_version = ver.text

            # If edge in version_string, append short sha
            if "edge" in self._app_version.lower():
                commit = root.find("commit")
                if commit is not None and commit.text is not None:
                    self._app_version += f"+{commit[:7]}"

        # Define important directories — dev mode redirects to a local folder
        # so that running from source never touches production data.
        if self._is_dev_mode:
            dev_dir_env = os.environ.get("RIMSORT_DEV_DIR")
            dev_root = (
                Path(dev_dir_env).resolve()
                if dev_dir_env
                else self._application_folder / "dev"
            )
            self._dev_root: Path | None = dev_root
            self._app_storage_folder: Path = dev_root / "data"
            self._user_log_folder: Path = dev_root / "logs"
        else:
            platform_dirs = PlatformDirs(appname=self._app_name, appauthor=False)
            self._dev_root = None
            self._app_storage_folder = Path(platform_dirs.user_data_dir)
            self._user_log_folder = Path(platform_dirs.user_log_dir)

        # Derive some secondary directory paths
        self._databases_folder: Path = self._app_storage_folder / "dbs"
        self._saved_modlists_folder: Path = self._app_storage_folder / "modlists"
        self._theme_storage_folder: Path = self._app_storage_folder / "themes"
        self._theme_data_folder: Path = self._application_folder / "themes"
        self._settings_file: Path = self._app_storage_folder / "settings.json"
        self._user_rules_file = self.databases_folder / "userRules.json"
        self._ignore_mods_file: Path = self.databases_folder / "ignore.json"
        self._language_data_folder: Path = self._application_folder / "locales"
        self._browser_profile_folder: Path = self._app_storage_folder / "browser"
        self._setup_web_channel_script_file: Path = (
            self._application_folder / "setup_web_channel_script.js"
        )

        # Backup directories
        self._backups_folder: Path = self._app_storage_folder / "backups"
        self._game_saves_backups_folder: Path = self._backups_folder / "saves"
        self._settings_backups_folder: Path = self._backups_folder / "settings"
        self._application_backups_folder: Path = (
            self._backups_folder / "rimsort_installation"
        )

        # Make sure important directories exist
        self._app_storage_folder.mkdir(parents=True, exist_ok=True)
        self._user_log_folder.mkdir(parents=True, exist_ok=True)
        self._saved_modlists_folder.mkdir(parents=True, exist_ok=True)

        self._databases_folder.mkdir(parents=True, exist_ok=True)
        self._theme_storage_folder.mkdir(parents=True, exist_ok=True)

        # Create backup directories
        self._backups_folder.mkdir(parents=True, exist_ok=True)
        self._game_saves_backups_folder.mkdir(parents=True, exist_ok=True)
        self._settings_backups_folder.mkdir(parents=True, exist_ok=True)
        self._application_backups_folder.mkdir(parents=True, exist_ok=True)

        # Initialize user rules file if it does not exist
        if not self._user_rules_file.exists():
            self._user_rules_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_json_dump(DEFAULT_USER_RULES, str(self._user_rules_file), indent=4)

        # AppImage: clean up .bak from a previous successful update
        self._cleanup_appimage_backup()

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
    def is_dev_mode(self) -> bool:
        """Whether the application is running in development mode."""
        return self._is_dev_mode

    @property
    def dev_root(self) -> Path | None:
        """The dev data root directory, or None if not in dev mode."""
        return self._dev_root if self._is_dev_mode else None

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
    def libs_folder(self) -> Path:
        """
        Get the path to the folder containing prebuilt Steamworks libraries.

        In compiled (Nuitka) builds, libraries are placed at the application folder root:
        - macOS: Inside the ``.app`` bundle at ``RimSort.app/Contents/MacOS/``
        - Linux: Alongside the executable
        - Windows: Alongside the executable

        In source/development mode, they reside in the ``libs/`` subdirectory.

        Returns:
            Path: The path to the prebuilt libraries folder.
        """
        if "__compiled__" in globals():
            return self._application_folder
        return self._application_folder / "libs"

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
    def saved_modlists_folder(self) -> Path:
        """
        Get the path to the folder where user modlists are saved.

        This directory is determined using platform-specific conventions.

        Returns:
            Path: The path to the saved modlists folder.
        """
        return self._saved_modlists_folder

    @property
    def app_settings_file(self) -> Path:
        """
        Get the path to the file where user-specific data for the application is stored.

        This directory is determined using platform-specific conventions.

        Returns:
            Path: The path to the user-specific data file.
        """
        return self._settings_file

    @property
    def user_rules_file(self) -> Path:
        """
        Get the path to the user-specific rules file.

        May or may not exist.
        """
        return self._user_rules_file

    @property
    def ignore_mods_file(self) -> Path:
        """
        Get the path to the file where ignored mods are stored.

        May or may not exist.
        """
        return self._ignore_mods_file

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
        Get the path to the folder where application Themes / Stylesheets are stored.
        """
        return self._theme_data_folder

    @property
    def theme_storage_folder(self) -> Path:
        """
        Get the path to the user folder where Themes / Stylesheets are stored.
        """
        return self._theme_storage_folder

    @property
    def databases_folder(self) -> Path:
        """
        Get the path to the folder where application databases are stored.
        """
        return self._databases_folder

    @property
    def language_data_folder(self) -> Path:
        """
        Get the path to the folder where application language data is stored.
        """
        return self._language_data_folder

    @property
    def setup_web_channel_script_file(self) -> Path:
        """
        Get the path to the file where _setup_web_channel_script_file exists
        """
        return self._setup_web_channel_script_file

    @property
    def backups_folder(self) -> Path:
        """
        Get the path to the folder where various backups are stored.

        This is the main backups folder, which contains subfolders for different types of backups (e.g., saves, settings, installation).
        """
        return self._backups_folder

    @property
    def settings_backups_folder(self) -> Path:
        """
        Get the path to the folder where settings backups are stored.
        """
        return self._settings_backups_folder

    @property
    def game_saves_backups_folder(self) -> Path:
        """
        Get the path to the folder where game save backups are stored.
        """
        return self._game_saves_backups_folder

    @property
    def application_backups_folder(self) -> Path:
        """
        Get the path to the folder where application backups are stored.
        """
        return self._application_backups_folder

    @property
    def is_appimage(self) -> bool:
        """
        Check if the application is running from an AppImage.

        The ``$APPIMAGE`` environment variable is set automatically by the
        AppImage runtime and contains the absolute path to the ``.AppImage`` file.
        """
        return bool(os.environ.get("APPIMAGE"))

    @property
    def appimage_path(self) -> Path | None:
        """
        Get the path to the running AppImage file, or ``None`` if not an AppImage.
        """
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return Path(appimage)
        return None

    def _cleanup_appimage_backup(self) -> None:
        """Remove leftover ``.bak`` file from a previous AppImage update."""
        appimage = self.appimage_path
        if appimage is None:
            return
        bak = appimage.with_suffix(appimage.suffix + ".bak")
        if bak.exists():
            try:
                bak.unlink()
                logger.info(f"Cleaned up old AppImage backup: {bak}")
            except OSError as e:
                logger.warning(f"Failed to clean up AppImage backup {bak}: {e}")
