import os
import platform
import subprocess

CWD = os.getcwd()
if platform.system() == "Windows":
    PY_CMD = "py"
else:
    PY_CMD = "python3"
STEAMFILES_BUILD_CMD = [PY_CMD, "setup.py", "build"]
STEAMFILES_GET_REQ_CMD = [PY_CMD, "-m", "pip", "install", "-r", "requirements.txt"]
STEAMFILES_SRC = os.path.join(CWD, "steamfiles")
SUBMODULE_UPDATE_INIT_CMD = ["git", "submodule", "update", "--init", "--recursive"]


def _execute(cmd: list) -> None:
    print(f"\nExecuting command: {cmd}\n")
    p = subprocess.Popen(cmd)
    p.wait()
    


print("Ensuring we have steamfiles submodule initiated & up-to-date...")
_execute(SUBMODULE_UPDATE_INIT_CMD)

print(f"Changing directory to {STEAMFILES_SRC}")
os.chdir(STEAMFILES_SRC)

print("Building steamfiles module...")
_execute(STEAMFILES_BUILD_CMD)
_execute(STEAMFILES_GET_REQ_CMD)

print(f"Leaving {STEAMFILES_SRC}")
os.chdir(CWD)

print("Done! Exiting...")
