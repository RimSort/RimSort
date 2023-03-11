from io import BytesIO
import logging
import os
import platform
import requests
import subprocess
import sys
import tarfile
from zipfile import ZipFile
from typing import Any, Dict, List, Optional, Tuple

from util.error import show_fatal_error, show_information, show_warning
from window.runner_panel import RunnerPanel

import shutil

logger = logging.getLogger(__name__)


class SteamcmdInterface:
    """
    Create SteamcmdInterface object to provide an interface for steamcmd functionality
    """

    def __init__(self) -> None:
        logger.info("SteamcmdInterface initilizing...")
        self.cwd = os.getcwd()
        self.log = ""
        self.steamcmd_path = os.path.join(self.cwd, "steamcmd")
        self.system = platform.system()
        self.workshop_mods_path = os.path.join(self.cwd, "steam")

        if self.system == "Darwin":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz"
            )
        elif self.system == "Linux":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            )
        elif self.system == "Windows":
            self.steamcmd_url = (
                "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            )
        else:
            show_fatal_error(
                "SteamcmdInterface",
                f"Found platform {self.system}. steamcmd is not supported on this platform.",
            )
            return

        if not os.path.exists(self.steamcmd_path):
            os.makedirs(self.steamcmd_path)

        if not os.path.exists(self.workshop_mods_path):
            os.makedirs(self.workshop_mods_path)

    def download_publishedfileids(
        self, appid: str, publishedfileids: list, runner: RunnerPanel
    ):
        """
        This function downloads a list of mods from a list publishedfileids

        https://developer.valvesoftware.com/wiki/SteamCMD

        :param ids: list of publishedfileids
        """
        runner.message("Checking for steamcmd...")
        if self.steamcmd is not None:
            runner.message(
                f"Got it: {self.steamcmd}\n"
                + f"Downloading list of {str(len(publishedfileids))} "
                + f"publishedfileids to: {self.workshop_mods_path}"
            )
            script = [f"force_install_dir {self.workshop_mods_path}", "login anonymous"]
            for publishedfileid in publishedfileids:
                script.append(f"workshop_download_item {appid} " + publishedfileid)
            script.extend(
                [
                    # "validate",
                    "quit"
                ]
            )
            script_path = os.path.join(self.steamcmd_path, "script.txt")
            with open(script_path, "w") as script_output:
                script_output.write("\n".join(script))
            runner.message(
                f"Compiled & using script in {self.steamcmd_path}/script.txt"
            )
            runner.execute(self.steamcmd, [f"+runscript {script_path}"])
        else:
            runner.message("steamcmd was not found. Please setup steamcmd first!")

    def get_steamcmd(self, reinstall: bool, runner: RunnerPanel) -> None:
        if os.path.exists(self.steamcmd_path):
            if reinstall:
                logger.info(f"Reinstalling steamcmd at {self.steamcmd_path}")
                runner.message("Existing steamcmd installation found!")
                runner.message(
                    f"Deleting existing installation from: {self.steamcmd_path}"
                )
                shutil.rmtree(self.steamcmd_path)
                os.makedirs(self.steamcmd_path)
        if self.system == "Windows":  # Windows
            self.steamcmd = os.path.join(self.steamcmd_path, "steamcmd.exe")
            if not os.path.exists(self.steamcmd):
                try:
                    runner.message(
                        f"Downloading & extracting steamcmd release from: {self.steamcmd_url}"
                    )
                    with ZipFile(
                        BytesIO(requests.get(self.steamcmd_url).content)
                    ) as zipobj:
                        zipobj.extractall(self.steamcmd_path)
                    runner.message(f"Installation completed")
                except:
                    runner.message("Installation failed")
                    show_fatal_error(
                        "SteamcmdInterface",
                        f"Failed to download steamcmd for {self.system}",
                        f"Did the file/url change?\nDoes your environment have access to the internet?",
                    )
            else:
                runner.message("Steamcmd already installed...")
                show_warning(
                    "SteamcmdInterface",
                    f"A steamcmd runner already exists at: {self.steamcmd}",
                )
                # answer = QMessageBox(None, "Reinstall?", "Would you like to reinstall steamcmd?", QMessageBox.No, QMessageBox.Yes)
                # if answer == "Yes":
                #     self.get_steamcmd(True)
        else:  # Linux/MacOS
            self.steamcmd = os.path.join(self.steamcmd_path, "steamcmd.sh")
            if not os.path.exists(self.steamcmd):
                try:
                    runner.message(
                        f"Downloading & extracting steamcmd release from: {self.steamcmd_url}"
                    )
                    with requests.get(
                        self.steamcmd_url, stream=True
                    ) as rx, tarfile.open(fileobj=rx.raw, mode="r:gz") as tarobj:
                        tarobj.extractall(self.steamcmd_path)
                    runner.message(f"Installation completed")
                except:
                    runner.message("Installation failed")
                    show_fatal_error(
                        "SteamcmdInterface",
                        f"Failed to download steamcmd for {self.system}",
                        f"Did the file/url change?\nDoes your environment have access to the internet?",
                    )
            else:
                runner.message("Steamcmd already installed...")
                show_warning(
                    "SteamcmdInterface",
                    f"A steamcmd runner already exists at: {self.steamcmd}",
                )


if __name__ == "__main__":
    sys.exit()
