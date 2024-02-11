import os
import platform
import sys

from loguru import logger

from app.utils.app_info import AppInfo
from app.windows.runner_panel import RunnerPanel


class ToddsInterface:
    """
    Create ToddsInterface object to provide an interface for todds functionality
    """

    def __init__(self, preset="optimized", dry_run=False, overwrite=False) -> None:
        logger.info("ToddsInterface initilizing...")
        if overwrite:
            overwrite_flag = "-o"
        else:
            overwrite_flag = "-on"
        self.cwd = os.getcwd()
        self.system = platform.system()
        # Check if the preset is one of the old presets and change it to "optimized" if necessary
        if preset in ["low", "medium", "high"]:
            preset = "optimized"
        self.preset = preset
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
        }
        if dry_run:
            for preset in self.todds_presets:
                self.todds_presets[preset].remove("-p")
                self.todds_presets[preset].remove("-t")
                self.todds_presets[preset].append("-v")
                self.todds_presets[preset].append("-dr")

    def execute_todds_cmd(self, target_path: str, runner: RunnerPanel):
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
            logger.debug(f"Found todds executable at: {todds_exe_path}")
            args = self.todds_presets[self.preset]
            args.append(target_path)
            if not runner.todds_dry_run_support:
                runner.message("Initiating todds...")
                runner.message("Courtesy of joseasoler#1824")
                runner.message(f"Using configured preset: {self.preset}\n\n")
            runner.execute(todds_exe_path, args, -1)
        else:
            runner.message(
                "ERROR: todds was not found. If you are running from source, please ensure you have followed the correct steps in the Development Guide:\n"
                + "https://github.com/RimSort/RimSort/wiki/Development-Guide\n\nPlease reach out to us for support at: https://github.com/oceancabbage/RimSort/issues"
            )


if __name__ == "__main__":
    sys.exit()
