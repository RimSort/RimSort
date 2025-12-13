"""
build-db subcommand for building Steam Workshop metadata databases.

This command allows headless operation of the DB builder functionality,
enabling use in scripts and containers without GUI dependencies.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from app.utils.app_info import AppInfo
from app.utils.db_builder_core import DBBuilderCore


@click.command("build-db")
@click.option(
    "--api-key",
    envvar="RIMSORT_STEAM_API_KEY",
    help="Steam WebAPI key (32 characters). Can also be set via RIMSORT_STEAM_API_KEY environment variable.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Output JSON file path for the database.",
)
@click.option(
    "--appid",
    type=int,
    default=294100,
    show_default=True,
    help="Steam AppID (294100 is RimWorld).",
)
@click.option(
    "--expiry",
    type=int,
    default=0,
    show_default=True,
    help="Database expiry time in seconds (0 = no expiry).",
)
@click.option(
    "--dlc-data/--no-dlc-data",
    default=True,
    show_default=True,
    help="Include DLC dependency data (requires Steamworks API).",
)
@click.option(
    "--update/--overwrite",
    default=False,
    show_default=True,
    help="Update existing database (merge) or overwrite completely.",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Suppress progress output (errors still shown).",
)
def build_db(
    api_key: Optional[str],
    output: Path,
    appid: int,
    expiry: int,
    dlc_data: bool,
    update: bool,
    quiet: bool,
) -> None:
    """Build Steam Workshop metadata database.

    This command queries the Steam WebAPI to build a comprehensive database
    of mod metadata for the specified AppID. The database includes mod names,
    URLs, dependencies, and optional DLC requirements.

    The API key can be provided in three ways (in priority order):

    \b
    1. --api-key command line argument
    2. RIMSORT_STEAM_API_KEY environment variable
    3. Fallback to settings.json (if RimSort GUI is configured)

    Examples:

    \b
      # Using environment variable (recommended for security)
      export RIMSORT_STEAM_API_KEY=your_32_character_key_here
      rimsort build-db --output workshop.json

    \b
      # Using command line argument
      rimsort build-db --api-key ABC123... --output workshop.json

    \b
      # Update existing database with new data
      rimsort build-db --output workshop.json --update

    \b
      # Skip DLC data for faster builds
      rimsort build-db --output workshop.json --no-dlc-data --quiet
    """
    # API key resolution (priority order)
    if not api_key:
        # Try to read from settings.json as fallback
        settings_path = AppInfo().app_storage_folder / "settings.json"
        if settings_path.exists():
            try:
                with open(settings_path) as f:
                    settings = json.load(f)
                    api_key = settings.get("steam_apikey")
                    if api_key and not quiet:
                        click.echo(
                            "Using Steam API key from settings.json", err=True
                        )
            except Exception as e:
                if not quiet:
                    click.echo(
                        f"Warning: Could not read settings.json: {e}",
                        err=True,
                    )

    # Validation: API key is required and must be 32 characters
    if not api_key:
        click.secho(
            "Error: Steam API key is required. Provide it via:",
            fg="red",
            err=True,
        )
        click.echo("  1. --api-key option", err=True)
        click.echo("  2. RIMSORT_STEAM_API_KEY environment variable", err=True)
        click.echo("  3. Configure in RimSort GUI (saved to settings.json)", err=True)
        sys.exit(1)

    if len(api_key) != 32:
        click.secho(
            f"Error: Invalid Steam WebAPI key! Key must be 32 characters (got {len(api_key)}).",
            fg="red",
            err=True,
        )
        click.echo(
            "Get your API key at: https://steamcommunity.com/dev/apikey",
            err=True,
        )
        sys.exit(1)

    # Validation: Output parent directory must exist
    output_parent = output.parent
    if output_parent != Path(".") and not output_parent.exists():
        click.secho(
            f"Error: Output directory does not exist: {output_parent}",
            fg="red",
            err=True,
        )
        sys.exit(1)

    # Validation: If update mode, output file must exist
    if update and not output.exists():
        click.secho(
            f"Error: Cannot update non-existent database: {output}",
            fg="red",
            err=True,
        )
        click.echo("Use --overwrite to create a new database.", err=True)
        sys.exit(1)

    # Create progress callback
    def progress_callback(msg: str) -> None:
        if not quiet:
            click.echo(msg, err=True)

    # Create and run DB builder
    if not quiet:
        click.echo(
            f"Starting database build for AppID {appid}...",
            err=True,
        )
        if dlc_data:
            click.echo(
                "DLC dependency data enabled (this may take longer).",
                err=True,
            )

    try:
        core = DBBuilderCore(
            apikey=api_key,
            appid=appid,
            database_expiry=expiry,
            output_database_path=str(output),
            get_appid_deps=dlc_data,
            update=update,
            progress_callback=progress_callback,
        )

        success = core.run()

        if success:
            click.secho(
                f"✓ Database successfully written to {output}",
                fg="green",
                err=True,
            )
            sys.exit(0)
        else:
            click.secho(
                "✗ Database build failed",
                fg="red",
                err=True,
            )
            sys.exit(1)

    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.", err=True)
        sys.exit(2)
    except Exception as e:
        click.secho(
            f"✗ Error: {e}",
            fg="red",
            err=True,
        )
        if not quiet:
            import traceback

            click.echo("\nFull traceback:", err=True)
            click.echo(traceback.format_exc(), err=True)
        sys.exit(1)
