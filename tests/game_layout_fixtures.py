from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


def make_mods_config(path: Path, package_ids: list[str]) -> Path:
    root = ElementTree.Element("ModsConfigData")
    ElementTree.SubElement(root, "version").text = "1.7.4976"
    active = ElementTree.SubElement(root, "activeMods")
    for package_id in package_ids:
        ElementTree.SubElement(active, "li").text = package_id
    ElementTree.ElementTree(root).write(path, encoding="utf-8")
    return path


@dataclass(frozen=True)
class GameInstall:
    launch_location: Path
    content_root: Path
    mods_path: Path
    data_path: Path


def make_game_install(
    root: Path,
    layout: str,
    version: str = "1.7.4976 rev1043",
    dlcs: tuple[str, ...] = (),
) -> GameInstall:
    root.mkdir(parents=True, exist_ok=True)
    launch = root
    if layout.startswith("mac-"):
        launch = root / "RimWorld.app"
        (launch / "Contents").mkdir(parents=True, exist_ok=True)
    content = launch if layout == "mac-internal" else root
    mods = content / "Mods"
    mods.mkdir(exist_ok=True)
    data = content / "Data"
    data.mkdir(exist_ok=True)
    (content / "Version.txt").write_text(version, encoding="utf-8")
    order = ("Core", "Royalty", "Ideology", "Biotech", "Anomaly", "Odyssey")
    package_ids = (
        "Ludeon.RimWorld",
        *(f"Ludeon.RimWorld.{name}" for name in order[1:]),
    )
    for name in ("Core", *dlcs):
        about = data / name / "About"
        about.mkdir(parents=True, exist_ok=True)
        position = order.index(name)
        metadata = ElementTree.Element("ModMetaData")
        ElementTree.SubElement(metadata, "packageId").text = package_ids[position]
        supported = ElementTree.SubElement(metadata, "supportedVersions")
        ElementTree.SubElement(supported, "li").text = "1.7"
        if name != "Core":
            for tag, ids in (
                ("forceLoadAfter", package_ids[:position]),
                ("forceLoadBefore", package_ids[position + 1 :]),
            ):
                rules = ElementTree.SubElement(metadata, tag)
                for package_id in ids:
                    ElementTree.SubElement(rules, "li").text = package_id
        ElementTree.ElementTree(metadata).write(about / "About.xml", encoding="utf-8")
    if layout in ("linux", "windows"):
        binary = root / ("RimWorld" if layout == "linux" else "RimWorld.exe")
        binary.write_bytes(b"game")
        binary.chmod(0o755)
    return GameInstall(launch, content, mods, data)
