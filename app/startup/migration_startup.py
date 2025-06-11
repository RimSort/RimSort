"""
This module checks if a migration is needed at startup and runs it if necessary.
"""

from app.controllers.settings_controller import SettingsController
from app.utils.migration_helper import run_migration_if_needed
from app.views.dialogue import show_dialogue_conditional


def check_and_run_migration(settings_controller: SettingsController) -> None:
    """Check if migration is needed and run it if so, then show security settings dialog."""

    if run_migration_if_needed():
        answer = show_dialogue_conditional(
            title="Security Upgrade",
            text="Your secrets have been migrated to secure storage!",
            information=(
                "GitHub tokens, Steam API keys, and other sensitive data "
                "are now stored securely using your system's credential manager.\n\n"
                "Would you like to view the security settings?"
            ),
        )

        if answer == "&Yes":
            settings_controller.show_settings_dialog("Security")
