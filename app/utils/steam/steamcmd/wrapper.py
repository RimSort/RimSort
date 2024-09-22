import os
import platform
import shutil
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Optional
from zipfile import ZipFile

import requests
from loguru import logger

from app.utils.event_bus import EventBus
from app.utils.system_info import SystemInfo
from app.views.dialogue import show_dialogue_conditional, show_fatal_error, show_warning
from app.windows.runner_panel import RunnerPanel


class SteamcmdInterface:
    """
    Create SteamcmdInterface object to provide an interface for SteamCMD functionality
    """

    _instance: Optional["SteamcmdInterface"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "SteamcmdInterface":
        if cls._instance is None:
            cls._instance = super(SteamcmdInterface, cls).__new__(cls)
        return cls._instance

    def __init__(self, steamcmd_prefix: str, validate: bool) -> None:
        if not hasattr(self, "initialized"):
            self.initialized = True
            self.setup = False
            self.steamcmd_prefix = steamcmd_prefix
            super(SteamcmdInterface, self).__init__()
            logger.debug("Initializing SteamcmdInterface")
            self.initialize_prefix(steamcmd_prefix, validate)
            logger.debug("Finished SteamcmdInterface initialization")

    def initialize_prefix(self, steamcmd_prefix: str, validate: bool) -> None:
        self.steamcmd_prefix = steamcmd_prefix
        self.steamcmd_install_path = str(Path(self.steamcmd_prefix) / "steamcmd")
        self.steamcmd_steam_path = str(Path(self.steamcmd_prefix) / "steam")
        self.system = platform.system()
        self.validate_downloads = validate

        if self.system == "Darwin":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz"
            )
            self.steamcmd = str((Path(self.steamcmd_install_path) / "steamcmd.sh"))
        elif self.system == "Linux":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            )
            self.steamcmd = str((Path(self.steamcmd_install_path) / "steamcmd.sh"))
        elif self.system == "Windows":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            )
            self.steamcmd = str((Path(self.steamcmd_install_path) / "steamcmd.exe"))
        else:
            show_fatal_error(
                "SteamcmdInterface",
                f"Found platform {self.system}. steamcmd is not supported on this platform.",
            )
            return

        if not os.path.exists(self.steamcmd_install_path):
            os.makedirs(self.steamcmd_install_path)
            logger.debug(
                f"SteamCMD does not exist. Creating path for installation: {self.steamcmd_install_path}"
            )

        if not os.path.exists(self.steamcmd_steam_path):
            os.makedirs(self.steamcmd_steam_path)
        self.steamcmd_appworkshop_acf_path = str(
            (
                Path(self.steamcmd_steam_path)
                / "steamapps"
                / "workshop"
                / "appworkshop_294100.acf"
            )
        )
        self.steamcmd_content_path = str(
            (Path(self.steamcmd_steam_path) / "steamapps" / "workshop" / "content")
        )

    @classmethod
    def instance(cls, *args: Any, **kwargs: Any) -> "SteamcmdInterface":
        if cls._instance is None:
            cls._instance = cls(*args, **kwargs)
        elif args or kwargs:
            raise ValueError("SteamcmdInterface instance has already been initialized.")
        return cls._instance

    def check_symlink(self, link_path: str, target_local_folder: str) -> None:
        """Checks if the link path exists. If it does, recreate the link/junction to target_local_folder.
        Otherwise, create the link/junction.

        Requires the root of the link_path to exist.

        :param link_path: Where the symlink should be created
        :type link_path: str
        :param target_local_folder: Where the symlink/junction should point to
        :type target_local_folder: str
        """
        logger.debug(
            "Checking for SteamCMD <-> Local mods symlink, and recreating if it exists"
        )
        logger.debug(f"Link path: {link_path}")
        if os.path.exists(link_path):
            logger.debug(
                f"Removing existing link at {link_path} and recreating link to {target_local_folder}"
            )
            # Remove by type
            if os.path.islink(link_path) or os.path.ismount(link_path):
                os.unlink(link_path)
            elif os.path.isdir(link_path):
                os.rmdir(link_path)
            else:
                os.remove(link_path)
        # Recreate the link
        if SystemInfo().operating_system != SystemInfo.OperatingSystem.WINDOWS:
            os.symlink(
                target_local_folder,
                link_path,
                target_is_directory=True,
            )
        elif sys.platform == "win32":
            from _winapi import CreateJunction

            CreateJunction(target_local_folder, link_path)

    def create_symlink(self, runner: RunnerPanel, symlink_source_path: str, symlink_destination_path: str) -> None:
        try:
            runner.message(
                f"[{symlink_source_path}] -> " + symlink_destination_path
            )
            if os.path.exists(symlink_destination_path):
                logger.debug(
                    f"Removing existing link at {symlink_destination_path} and recreating link to {symlink_source_path}"
                )
                # Remove by type
                if self.is_junction_or_link(
                    symlink_destination_path
                ) or os.path.ismount(symlink_destination_path):
                    os.unlink(symlink_destination_path)
                elif os.path.isdir(symlink_destination_path):
                    shutil.rmtree(symlink_destination_path)
                else:
                    os.remove(symlink_destination_path)
            if self.system != "Windows":
                os.symlink(
                    symlink_source_path,
                    symlink_destination_path,
                    target_is_directory=True,
                )
            elif sys.platform == "win32":
                from _winapi import CreateJunction

                CreateJunction(
                    symlink_source_path, symlink_destination_path
                )
            self.setup = True
            runner.message(
                "Finished creating symlink\n"
            )
        except Exception as e:
            runner.message(
                f"Failed to create symlink. Error: {type(e).__name__}: {str(e)}"
            )
            show_warning(
                "SteamcmdInterface",
                f"Failed to create symlink for {self.system}",
                f"Error: {type(e).__name__}: {str(e)}",
            )
            
    def is_junction_or_link(self, path: str) -> bool:
        """
        This checks if a path is a symlink.
        
        Additionally on Windows it checks if the path is a junction.
        
        If the path does not exist or is not a symlink/junction, 
        it will catch an OSError, and return false.
        
        :param path: The path to check
        """
        try:
            return bool(os.readlink(path))
        except OSError:
            return False


    def download_mods(self, publishedfileids: list[str], runner: RunnerPanel) -> None:
        """
        This function downloads a list of mods from a list publishedfileids

        https://developer.valvesoftware.com/wiki/SteamCMD

        :param appid: a Steam AppID to pass to steamcmd
        :param publishedfileids: list of publishedfileids
        :param runner: a RimSort RunnerPanel to interact with
        """
        runner.message("Checking for steamcmd...")
        if self.setup:
            runner.message(
                f"Got it: {self.steamcmd}\n"
                + f"Downloading list of {str(len(publishedfileids))} "
                + f"publishedfileids to: {self.steamcmd_steam_path}"
            )
            script = [
                f'force_install_dir "{self.steamcmd_steam_path}"',
                "login anonymous",
            ]
            download_cmd = "workshop_download_item 294100"
            for publishedfileid in publishedfileids:
                if self.validate_downloads:
                    script.append(f"{download_cmd} {publishedfileid} validate")
                else:
                    script.append(f"{download_cmd} {publishedfileid}")
            script.extend(["quit\n"])
            script_path = str((Path(gettempdir()) / "steamcmd_script.txt"))
            with open(script_path, "w", encoding="utf-8") as script_output:
                script_output.write("\n".join(script))
            runner.message(f"Compiled & using script: {script_path}")
            runner.execute(
                self.steamcmd,
                [f'+runscript "{script_path}"'],
                len(publishedfileids),
            )
        else:
            runner.message("SteamCMD was not found. Please setup SteamCMD first!")
            self.on_steamcmd_not_found(runner=runner)

    def check_for_steamcmd(self, prefix: str) -> bool:
        executable_name = os.path.split(self.steamcmd)[1] if self.steamcmd else None
        if executable_name is None:
            return False
        return os.path.exists(str(Path(prefix) / "steamcmd" / executable_name))

    def on_steamcmd_not_found(self, runner: RunnerPanel | None = None) -> None:
        answer = show_dialogue_conditional(
            title="RimSort - SteamCMD setup",
            text="RimSort was unable to find SteamCMD installed in the configured prefix:\n",
            information=f"{self.steamcmd_prefix if self.steamcmd_prefix else '<None>'}\n\n"
            + "Do you want to setup SteamCMD?",
        )
        if answer == "&Yes":
            EventBus().do_install_steamcmd.emit()
        if runner:
            runner.close()

    def setup_steamcmd(
        self, symlink_source_path: str, reinstall: bool, runner: RunnerPanel
    ) -> None:
        installed = None
        if reinstall:
            runner.message("Existing steamcmd installation found!")
            runner.message(
                f"Deleting existing installation from: {self.steamcmd_install_path}"
            )
            shutil.rmtree(self.steamcmd_install_path)
            os.makedirs(self.steamcmd_install_path)
        if not self.check_for_steamcmd(prefix=self.steamcmd_prefix):
            try:
                runner.message(
                    f"Downloading & extracting steamcmd release from: {self.steamcmd_url}"
                )
                if ".zip" in self.steamcmd_url:
                    with ZipFile(
                        BytesIO(requests.get(self.steamcmd_url).content)
                    ) as zipobj:
                        zipobj.extractall(self.steamcmd_install_path)
                    runner.message("Installation completed")
                    installed = True
                elif ".tar.gz" in self.steamcmd_url:
                    with (
                        requests.get(self.steamcmd_url, stream=True) as rx,
                        tarfile.open(
                            fileobj=BytesIO(rx.content), mode="r:gz"
                        ) as tarobj,
                    ):
                        tarobj.extractall(self.steamcmd_install_path)
                    runner.message("Installation completed")
                    installed = True
            except Exception as e:
                runner.message("Installation failed")
                show_fatal_error(
                    "SteamcmdInterface",
                    f"Failed to download steamcmd for {self.system}",
                    "Did the file/url change?\nDoes your environment have access to the internet?",
                    details=f"Error: {type(e).__name__}: {str(e)}",
                )
        else:
            runner.message("SteamCMD already installed...")
            show_warning(
                "SteamcmdInterface",
                f"A steamcmd runner already exists at: {self.steamcmd}",
            )
            answer = show_dialogue_conditional(
                "Reinstall?",
                "Would you like to reinstall SteamCMD?",
                f"Existing install: {self.steamcmd_install_path}",
            )
            if answer == "&Yes":
                runner.message(f"Reinstalling SteamCMD: {self.steamcmd_install_path}")
                self.setup_steamcmd(symlink_source_path, True, runner)
        if installed:
            if not os.path.exists(self.steamcmd_content_path):
                os.makedirs(self.steamcmd_content_path)
                runner.message(
                    f"Workshop content path does not exist. Creating for symlinking:\n\n{self.steamcmd_content_path}\n"
                )
            symlink_destination_path = str(
                (Path(self.steamcmd_content_path) / "294100")
            )
            runner.message(f"Symlink source : {symlink_source_path}")
            runner.message(f"Symlink destination: {symlink_destination_path}")
            if self.is_junction_or_link(symlink_destination_path): # Symlink/junction exists
                runner.message(
                    f"Symlink destination already exists! Please remove existing destination:\n\n{symlink_destination_path}\n"
                )
                answer = show_dialogue_conditional(
                "Re-create Symlink?",
                "An existing symlink already exists."
                " Would you like to delete and re-create the symlink?",
                "The symlink makes SteamCMD download mods to the local mods folder"
                + " and is required for SteamCMD mod downloads to work correctly.",
                f"Existing symlink: {symlink_destination_path}"
                "\n\nNew symlink:"
                f"\n[{symlink_source_path}] -> " + symlink_destination_path,
            )
                if answer == "&Yes": # Re-create symlink
                    self.create_symlink(runner, symlink_source_path, symlink_destination_path)
            elif os.path.exists(symlink_destination_path): # A dir exists (not a symlink/junction)
                runner.message(
                    f"Symlink destination already exists! Please remove existing destination:\n\n{symlink_destination_path}\n"
                )
                answer = show_dialogue_conditional(
                "Create Symlink?",
                "The symlink destination path already exists."
                " Would you like to remove the existing destination and create a new symlink in it's place?",
                "The symlink makes SteamCMD download mods to the local mods folder"
                + " and is required for SteamCMD mod downloads to work correctly.",
                f"Existing destination: {symlink_destination_path}"
                "\n\nNew symlink:"
                f"\n[{symlink_source_path}] -> " + symlink_destination_path,
            )
                if answer == "&Yes": # Re-create symlink/junction
                    self.create_symlink(runner, symlink_source_path, symlink_destination_path)
            else: # Symlink/junction does not exist
                answer = show_dialogue_conditional(
                    "Create Symlink?",
                    "Do you want to create a symlink?",
                    "The symlink makes SteamCMD download mods to the local mods folder"
                    + " and is required for SteamCMD mod downloads to work correctly.",
                    "New symlink:"
                    f"\n[{symlink_source_path}] -> " + symlink_destination_path,
                )
                if answer == "&Yes":
                    self.create_symlink(runner, symlink_source_path, symlink_destination_path)


if __name__ == "__main__":
    sys.exit()
