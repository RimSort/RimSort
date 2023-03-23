import os
import platform
import subprocess

CWD = os.getcwd()
if platform.system() == "Windows":
    PY_CMD = "py"
else:
    PY_CMD = "python3"
STEAMFILES_SRC = os.path.join(CWD, "steamfiles")
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def _execute(cmd: list) -> None:
    print(f"\nExecuting command: {cmd}\n")
    subprocess.Popen(cmd)


print("Ensuring we have steamfiles submodule initiated & up-to-date...")
_execute(SUBMODULE_UPDATE_INIT_CMD)

print(f"Changing directory to {STEAMFILES_SRC}")
os.chdir(STEAMFILES_SRC)

print("Building steamfiles module...")
subprocess.run([PY_CMD, "setup.py", "build"])

print(f"Leaving {STEAMFILES_SRC}")
os.chdir(CWD)

print("Done! Exiting...")
