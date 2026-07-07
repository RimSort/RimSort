"""Parser for the startup impact report written by the "Loading Progress" mod.

The mod (https://github.com/ilyvion/loading-progress) can profile RimWorld's
loading pipeline and save a per-mod timing report to
``<RimWorld save data folder>/StartupImpactData.xml`` — the folder that also
contains ``Config/`` and ``Saves/``. RimSort already knows the ``Config``
folder per instance, so the report path is derived from its parent.

The file is produced by RimWorld's Scribe serializer:

.. code-block:: xml

    <StartupImpactSession>
      <sessionData>
        <loadingTime>42500.5</loadingTime>
        <mods>
          <li>
            <modName>Some Mod</modName>
            <modPackageId>author.somemod</modPackageId>  <!-- optional -->
            <metrics>
              <keys><li>...category...</li></keys>
              <values><li>1230.5</li></values>
            </metrics>
            <totalImpact>1230.5</totalImpact>
            <offThreadMetrics>...</offThreadMetrics>
            <offThreadTotalImpact>500</offThreadTotalImpact>
          </li>
        </mods>
      </sessionData>
    </StartupImpactSession>

All timing values in the file are **milliseconds** (the mod's profilers
report ``Stopwatch.Elapsed.TotalMilliseconds``); this module converts them
to seconds at the parse boundary, so everything it exposes is in seconds.

Scribe omits elements whose value equals the type default (e.g. a float of
``0``), so every field must tolerate being absent. ``modPackageId`` only
exists in reports written by mod versions that include it; older reports are
matched by mod display name instead.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from app.utils.xml import xml_path_to_json

STARTUP_IMPACT_FILENAME = "StartupImpactData.xml"

# Absolute thresholds (seconds) for coloring a mod's startup impact
IMPACT_WARN_THRESHOLD_S = 1.0
IMPACT_HIGH_THRESHOLD_S = 5.0

# Cache of parsed reports keyed by file path. Each entry stores the file
# mtime it was parsed at, so an updated file is re-parsed transparently.
# Parse failures are cached as None per-mtime and retried when the file
# changes.
_report_cache: dict[str, tuple[float, "StartupImpactReport | None"]] = {}


@dataclass(frozen=True)
class StartupImpactMod:
    """Per-mod timing data from a startup impact report."""

    mod_name: str
    # Normalized (lowercase, no "_steam" suffix) packageId, None on reports
    # from mod versions that don't include it
    package_id: str | None
    total_impact_s: float
    off_thread_total_impact_s: float
    metrics: dict[str, float] = field(default_factory=dict)
    off_thread_metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class StartupImpactReport:
    """A parsed startup impact report file."""

    path: str
    file_mtime: float
    loading_time_s: float
    mods: tuple[StartupImpactMod, ...]

    def find(
        self, package_id: str | None, mod_name: str | None
    ) -> StartupImpactMod | None:
        """Find a mod's entry, preferring packageId over display name.

        :param package_id: The mod's packageId (any case, "_steam" suffix ok).
        :param mod_name: The mod's display name.
        :return: The matching entry, or None.
        """
        if package_id:
            normalized = normalize_package_id(package_id)
            for mod in self.mods:
                if mod.package_id == normalized:
                    return mod
        if mod_name:
            name_lower = mod_name.lower()
            for mod in self.mods:
                if mod.mod_name.lower() == name_lower:
                    return mod
        return None


def normalize_package_id(package_id: str) -> str:
    """Lowercase a packageId and strip the Steam copy disambiguation suffix."""
    normalized = package_id.lower()
    if normalized.endswith("_steam"):
        normalized = normalized[: -len("_steam")]
    return normalized


def get_startup_impact_file_path(config_folder: str) -> Path:
    """Resolve the report path from an instance's Config folder path."""
    return Path(config_folder).parent / STARTUP_IMPACT_FILENAME


def load_startup_impact_report(config_folder: str) -> "StartupImpactReport | None":
    """Load the startup impact report for an instance, if one exists.

    Results are cached by file mtime: the file is only re-parsed after it
    changes on disk. Returns None when the file is missing or unparseable.

    :param config_folder: The instance's RimWorld Config folder path.
    """
    if not config_folder:
        return None
    path = get_startup_impact_file_path(config_folder)
    path_str = str(path)
    try:
        mtime = os.path.getmtime(path_str)
    except OSError:
        _report_cache.pop(path_str, None)
        return None

    cached = _report_cache.get(path_str)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    report = _parse_report(path_str, mtime)
    _report_cache[path_str] = (mtime, report)
    return report


def invalidate_startup_impact_cache() -> None:
    """Drop all cached reports so the next load re-reads from disk."""
    _report_cache.clear()


def format_impact(seconds: float) -> str:
    """Format a duration in seconds as whole milliseconds (e.g. "36387ms")."""
    return f"{round(seconds * 1000)}ms"


def _parse_report(path: str, mtime: float) -> "StartupImpactReport | None":
    data = xml_path_to_json(path)
    session = data.get("StartupImpactSession")
    if not isinstance(session, dict):
        logger.warning(f"Startup impact report has unexpected structure: {path}")
        return None
    session_data = session.get("sessionData")
    if not isinstance(session_data, dict):
        logger.warning(f"Startup impact report has no session data: {path}")
        return None

    mods: list[StartupImpactMod] = []
    for entry in _as_list(_get_dict(session_data, "mods").get("li")):
        if not isinstance(entry, dict):
            continue
        mod_name = entry.get("modName")
        if not isinstance(mod_name, str) or not mod_name:
            continue
        raw_package_id = entry.get("modPackageId")
        package_id = (
            normalize_package_id(raw_package_id)
            if isinstance(raw_package_id, str) and raw_package_id
            else None
        )
        mods.append(
            StartupImpactMod(
                mod_name=mod_name,
                package_id=package_id,
                total_impact_s=_as_seconds(entry.get("totalImpact")),
                off_thread_total_impact_s=_as_seconds(
                    entry.get("offThreadTotalImpact")
                ),
                metrics=_parse_scribe_dict(entry.get("metrics")),
                off_thread_metrics=_parse_scribe_dict(entry.get("offThreadMetrics")),
            )
        )

    return StartupImpactReport(
        path=path,
        file_mtime=mtime,
        loading_time_s=_as_seconds(session_data.get("loadingTime")),
        mods=tuple(mods),
    )


def _as_list(value: Any) -> list[Any]:
    """Normalize etree_to_dict output, where a single <li> is not a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_dict(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _as_float(value: Any) -> float:
    """Parse a Scribe float; absent elements (Scribe omits defaults) are 0."""
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _as_seconds(value: Any) -> float:
    """Parse a Scribe timing value (milliseconds in the file) as seconds."""
    return _as_float(value) / 1000.0


def _parse_scribe_dict(value: Any) -> dict[str, float]:
    """Parse a Scribe-serialized timing dict (parallel <keys>/<values> li
    lists); values are converted from milliseconds to seconds."""
    if not isinstance(value, dict):
        return {}
    keys = _as_list(_get_dict(value, "keys").get("li"))
    values = _as_list(_get_dict(value, "values").get("li"))
    return {
        key: _as_seconds(val)
        for key, val in zip(keys, values)
        if isinstance(key, str) and key
    }
