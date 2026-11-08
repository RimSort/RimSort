"""Headless process bootstrap for the RimSort MCP server.

``--mcp`` must be able to serve JSON-RPC on ``sys.stdout``, so this module owns
three responsibilities the GUI path does not need:

* route every log sink to ``sys.stderr`` *before* any import can print;
* bring up the Qt **core** object (no GUI application object and no main
  window) because ``Settings``/``MetadataController`` are QObjects and the
  parser uses ``QThreadPool``;
* load the bound instance's settings and populate metadata synchronously, so the
  first tool call never races a background scan.

Importing this module does the Qt import work, so ``app.__main__`` only imports
it once it knows ``--mcp`` was requested.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.mcp.core import RimSortMcpCore
from app.mcp.server import build_server
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface

_LOG_FILE_NAME = "RimSortMCPServer.log"


def _configure_stdio_logging() -> Path:
    """Send every log record to stderr and a file, never to stdout.

    ``sys.stdout`` carries the MCP frames; a single stray write corrupts the
    session. ``logger.remove()`` also drops loguru's default stderr sink so the
    configuration is deterministic regardless of what ran before.

    :return: Path of the log file being written
    """
    log_dir = AppInfo().user_log_folder
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / _LOG_FILE_NAME

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
    )
    logger.add(
        log_file,
        level="DEBUG",
        rotation="10 MB",
        retention=3,
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process.id} | "
            "{thread.name} | {name}:{function}:{line} - {message}"
        ),
    )
    return log_file


def _select_instance(settings: Settings, instance: str | None) -> None:
    """Bind the server to an instance, validating the requested name.

    :param settings: Loaded application settings
    :param instance: Instance name from ``--instance``, or None for the active one
    :raises SystemExit: When the named instance is not configured
    """
    if instance is None:
        logger.info(f"MCP server bound to active instance: {settings.current_instance}")
        return
    if instance not in settings.instances:
        logger.error(
            f"Instance {instance!r} is not configured. Available instances: "
            f"{', '.join(sorted(settings.instances)) or '(none)'}"
        )
        raise SystemExit(2)
    settings.current_instance = instance
    logger.info(f"MCP server bound to instance: {instance}")


def _bootstrap_core(instance: str | None) -> RimSortMcpCore:
    """Load settings and metadata for the bound instance.

    :param instance: Optional instance name to override the active one
    :return: A core object whose metadata is already populated
    """
    settings = Settings()
    settings.load()
    _select_instance(settings, instance)

    active = settings.instances[settings.current_instance]
    if not active.game_folder or not active.local_folder:
        logger.warning(
            "The bound instance is missing a game folder or local mods folder; "
            "metadata will be incomplete. Configure it in the RimSort GUI first."
        )

    # The GUI does this in AppController; the metadata stack reads
    # SteamcmdInterface.instance() directly, so it must exist before refresh.
    SteamcmdInterface.instance(active.steamcmd_install_path, False)

    metadata_db_controller = AuxMetadataController.get_or_create_cached_instance(
        settings.aux_db_path
    )
    metadata_controller = MetadataController.instance(
        settings=settings,
        get_active_instance=lambda: settings.instances[settings.current_instance],
        metadata_db_controller=metadata_db_controller,
    )
    metadata_controller.reset_paths()
    metadata_controller.metadata_mediator.refresh_metadata(
        prefer_versioned=settings.prefer_versioned_about_tags,
        case_insensitive_about_xml=settings.case_insensitive_about_xml_lookup,
    )

    logger.info(
        f"MCP metadata ready: {len(metadata_controller.mods_metadata)} entries, "
        f"game version {metadata_controller.game_version}"
    )
    return RimSortMcpCore(settings, metadata_controller)


def run_mcp_server(instance: str | None = None) -> int:
    """Create the Qt core object, load metadata and serve MCP over stdio.

    :param instance: Optional instance name from ``--instance``
    :return: Process exit code
    """
    qt_app = QCoreApplication.instance() or QCoreApplication([sys.argv[0]])

    log_file = _configure_stdio_logging()
    logger.info(f"Starting RimSort MCP server (logs: {log_file})")

    core = _bootstrap_core(instance)
    server = build_server(core)

    logger.info("Serving MCP over stdio")
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        logger.info("MCP server interrupted")
    finally:
        logger.info("MCP server stopped")
        qt_app.quit()
    return 0
