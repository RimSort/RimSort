from loguru import logger

from app.windows.base_mods_panel import (
    BaseModsPanel,
    ButtonConfig,
    ButtonType,
)


class GitHubModsPanel(BaseModsPanel):
    """Panel for managing GitHub mods -- view installed, check updates, switch versions."""

    def __init__(self) -> None:
        logger.debug("Initializing GitHubModsPanel")

        super().__init__(
            object_name="githubModsPanel",
            window_title=self.tr("RimSort - GitHub Mods"),
            title_text=self.tr("GitHub Mods"),
            details_text=self.tr("\nManage mods installed from GitHub releases."),
            additional_columns=[
                "Mod Name",
                "Repository",
                "Installed Version",
                "Latest Version",
                "Auto-Update",
            ],
        )

        button_configs = [
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Check for Updates"),
                custom_callback=self._on_check_updates,
            ),
            ButtonConfig(
                button_type=ButtonType.CUSTOM,
                text=self.tr("Update Selected"),
                custom_callback=self._on_update_selected,
            ),
        ]

        self._setup_buttons_from_config(button_configs)
        self._populate_from_mods()
        self._reconfigure_table_sorting(sorting_enabled=True)

    def _populate_from_mods(self) -> None:
        """Populate table from per-instance github_mods table."""
        self._clear_table_model()

    def _on_check_updates(self) -> None:
        """Trigger update check for all GitHub mods."""
        logger.debug("Check for updates requested")

    def _on_update_selected(self) -> None:
        """Update selected mods to their latest versions."""
        logger.debug("Update selected requested")
