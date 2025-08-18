import os
import platform
import shlex
import sys

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.windows.runner_panel import RunnerPanel


class ToddsInterface:
    """
    Create ToddsInterface object to provide an interface for todds functionality
    """

    def __init__(
        self,
        preset: str = "",
        dry_run: bool = False,
        overwrite: bool = False,
        custom_command: str = "",
    ) -> None:
        logger.info("ToddsInterface initilizing...")
        self.custom_command = custom_command
        if overwrite:
            overwrite_flag = "-o"
        else:
            overwrite_flag = "-on"
        self.cwd = os.getcwd()
        self.system = platform.system()
        if "custom" in preset:
            preset = "custom"
            settings: Settings = Settings()
            settings.load()
            self.custom_command = settings.todds_custom_command
        elif "clean" in preset:
            preset = "clean"
        else:
            preset = "optimized"
        self.preset = preset
        self.dry_run = dry_run

        # Always initialize custom_args to avoid AttributeError
        self.custom_args = []

        if self.custom_command:
            # Split the custom command string into individual arguments
            self.custom_args = shlex.split(self.custom_command)
            logger.info(f"Custom command set: {self.custom_args}")

        self.todds_presets = {
            "clean": [
                "-cl",
                "-o",
                "-ss",
                "Textures",
                "-p",
                "-t",
            ],
            "optimized": [
                "-f",
                "BC1",
                "-af",
                "BC7",
                overwrite_flag,
                "-vf",
                "-fs",
                "-ss",
                "Textures",
                "-t",
                "-p",
            ],
            "custom": self.custom_args,
        }
        if self.dry_run and self.preset != "custom":
            for preset in self.todds_presets:
                # Safely remove arguments that might not exist
                if "-p" in self.todds_presets[preset]:
                    self.todds_presets[preset].remove("-p")
                if "-t" in self.todds_presets[preset]:
                    self.todds_presets[preset].remove("-t")
                # Add dry run arguments
                self.todds_presets[preset].append("-v")
                self.todds_presets[preset].append("-dr")

    def execute_todds_cmd(self, target_path: str, runner: RunnerPanel) -> None:
        """
        This function launches a todds command using a RunnerPanel (uses QProcess)

        https://github.com/joseasoler/todds/wiki/Example:-RimWorld

        :param todds_arguments: list of todds args to be passed to the todds executable
        """

        if self.system == "Windows":
            todds_executable = "todds.exe"
        else:
            todds_executable = "todds"
        todds_exe_path = str(AppInfo().application_folder / "todds" / todds_executable)
        logger.info("Checking for todds...")
        if os.path.exists(todds_exe_path):
            logger.info(f"Found todds executable at: {todds_exe_path}")
            args = self.todds_presets[self.preset]
            if self.preset != "custom":
                args.append(os.path.abspath(target_path))
            if self.preset == "custom" and "-p" in args:
                args = self.custom_args
                if self.dry_run:
                    args.remove("-p")
                    args.append("-v")
                    args.append("-dr")
            if self.preset == "custom" and "-p" not in args:
                if self.dry_run:
                    args.append("-v")
                    args.append("-dr")
                else:
                    args.append("-p")
                args.append(os.path.abspath(target_path))

            if not runner.todds_dry_run_support:
                runner.message("Initiating todds...")
                runner.message("Courtesy of joseasoler#1824")
                runner.message(f"Using configured preset: {self.preset}\n\n")
            runner.execute(todds_exe_path, args, -1)
            logger.warning(f"Executing todds with arguments: {args} in {self.cwd}")
        else:
            logger.error("Todds executable not found.")
            development_guide_url = (
                "https://rimsort.github.io/RimSort/development-guide/development-setup"
            )
            support_url = "https://github.com/RimSort/RimSort/issues"
            todds_error_message = QCoreApplication.translate(
                "ToddsInterface",
                "ERROR: todds was not found. If you are running from source, please ensure you have followed the correct steps in the {development_guide_url} \n\n"
                "Please reach out to us for support at: {support_url}",
            ).format(
                development_guide_url=development_guide_url,
                support_url=support_url,
            )
            runner.message(todds_error_message)


if __name__ == "__main__":
    sys.exit()
