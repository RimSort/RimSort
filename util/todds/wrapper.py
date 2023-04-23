from logger_tt import logger
import os
from pathlib import Path
import platform
import requests
import sys
from typing import Any, Dict, List, Optional, Tuple

from model.dialogue import (
    show_dialogue_conditional,
    show_fatal_error,
    show_information,
    show_warning,
)
from window.runner_panel import RunnerPanel

from PySide6.QtWidgets import QMessageBox

import shutil


class ToddsInterface:
    """
    Create ToddsInterface object to provide an interface for todds functionality
    """

    def __init__(self, overwrite=False) -> None:
        logger.info("ToddsInterface initilizing...")
        if overwrite:
            overwrite_flag = "-o"
        else:
            overwrite_flag = "-on"
        self.cwd = os.getcwd()
        self.system = platform.system()
        self.todds_presets = {
            "low": [
                "-f",
                "BC1_ALPHA_BC7",
                overwrite_flag,
                "-vf",
                "-fs",
                "-r",
                "Textures",
                "-p",
                "-t",
                "-v",
            ],
            "medium": [
                "-f",
                "BC7",
                overwrite_flag,
                "-vf",
                "-fs",
                "-r",
                "Textures",
                "-p",
                "-t",
                "-v",
            ],
            "high": [
                "-f",
                "BC7",
                "-q",
                "7",
                overwrite_flag,
                "-vf",
                "-fs",
                "-r",
                "Textures",
                "-p",
                "-t",
                "-v",
            ],
        }

    def execute_todds_cmd(
        self, todds_arguments: list, target_path: str, runner: RunnerPanel
    ):
        """
        This function launches a todds command using a RunnerPanel (uses QProcess)

        https://github.com/joseasoler/todds/wiki/Example:-RimWorld

        :param todds_arguments: list of todds args to be passed to the todds executable
        """

        if self.system == "Windows":
            todds_executable = "todds.exe"
        else:
            todds_executable = "todds"
        todds_exe_path = os.path.join(
            os.path.split(os.path.split(os.path.dirname(__file__))[0])[0],
            "todds",
            todds_executable,
        )
        logger.info("Checking for todds...")
        if os.path.exists(todds_exe_path):
            logger.warning(f"Found todds executable at: {todds_exe_path}")
            args = todds_arguments.copy()
            args.append(target_path)
            runner.execute(todds_exe_path, args)
        else:
            runner.message(
                "ERROR: todds was not found. If you are running from source, please ensure you have followed the correct steps in the Development Guide:\n"
                + "https://github.com/oceancabbage/RimSort/wiki/Development-Guide\n\nPlease reach out to us for support at: https://github.com/oceancabbage/RimSort/issues"
            )


if __name__ == "__main__":
    sys.exit()
