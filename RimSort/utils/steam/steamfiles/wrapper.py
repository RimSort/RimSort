from typing import Any, Dict

from steamfiles.steamfiles import acf


def acf_to_dict(path: str) -> Dict[str, Any]:
    """
    Uses steamfiles module to load a Steam client .acf file to a Dict
    Example: "$STEAM_INSTALL/steamapps/workshop/appworkshop_294100.acfappworkshop_294100.acf"
    """
    with open(
        path,
        "rb",
    ) as f:
        return acf.loads(str(f.read(), encoding="utf=8"))


def dict_to_acf(data: Dict[str, Any], path: str) -> None:
    """
    Uses steamfiles module to dump a dict of data to a Steam client .acf file in a SteamCMD/Steam format
    """
    with open(path, "w") as f:
        acf.dump(data, f)
