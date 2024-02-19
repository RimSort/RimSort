from PySide6.QtWidgets import QFrame, QHBoxLayout
from loguru import logger

from app.models.animations import AnimationLabel


class Status:
    """
    This class controls the layout and functionality for
    the Status view on the bottom of the GUI.
    """

    def __init__(self) -> None:
        """
        Initialize the Status view. Construct the layout
        add the single fading text widget.
        """
        logger.info("Initializing Status")

        # This view is contained within a QFrame to allow for styling
        self.frame = QFrame()
        self.frame.setObjectName("StatusPanel")

        # Create the main layout for the view
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(10, 1, 0, 2)

        # The main layout is contained inside the QFrame
        self.frame.setLayout(self.layout)

        # Create the single fading text widget
        self.status_text = AnimationLabel()
        self.status_text.setObjectName("StatusLabel")

        # Add the widget to the base layout
        self.layout.addWidget(self.status_text)

        logger.debug("Finished Status initialization")

    def actions_slot(self, action: str) -> None:
        """
        Slot connecting to the action panel's `actions_signal`.
        Responsible for displaying the action that was just
        triggered on the bottom status bar and fading the text
        after some time.

        :param action: the specific action being triggered
        """
        logger.info(f"Displaying fading text for action: {action}")
        if action == "check_for_rs_update":
            self.status_text.start_pause_fade("Checking for RimSort updates")
        # actions panel actions
        elif action == "refresh":
            self.status_text.start_pause_fade(
                "Refreshed local metadata and repopulating info from external metadata"
            )
        elif action == "clear":
            self.status_text.start_pause_fade("Cleared active mods")
        elif action == "restore":
            self.status_text.start_pause_fade(
                "Restored mod list to last saved ModsConfig.xml state"
            )
        elif action == "sort":
            self.status_text.start_pause_fade("Sorted active mods list")
        elif action == "optimize_textures":
            self.status_text.start_pause_fade("Optimizing textures with todds")
        elif action == "delete_textures":
            self.status_text.start_pause_fade("Deleting .dds textures using todds")
        elif action == "add_git_mod":
            self.status_text.start_pause_fade("Added git mod repository to local mods")
        elif action == "browse_workshop":
            self.status_text.start_pause_fade("Launched Steam Workshop browser")
        elif action == "setup_steamcmd":
            self.status_text.start_pause_fade("SteamCMD setup completed")
        elif action == "import_steamcmd_acf_data":
            self.status_text.start_pause_fade(
                "Imported data from another SteamCMD instance"
            )
        elif action == "reset_steamcmd_acf_data":
            self.status_text.start_pause_fade("Deleted SteamCMD ACF data")
        elif action == "set_steamcmd_path":
            self.status_text.start_pause_fade("Configured SteamCMD prefix path")
        elif "import_list" in action:
            self.status_text.start_pause_fade("Imported active mods list")
        elif "export_list" in action:
            self.status_text.start_pause_fade("Exported active mods list")
        elif action == "upload_list_rentry":
            self.status_text.start_pause_fade(
                "Copied mod report to clipboard; uploaded to http://rentry.co"
            )
        elif action == "save":
            self.status_text.start_pause_fade("Active mods saved into ModsConfig.xml")
        elif action == "run":
            self.status_text.start_pause_fade("Starting RimWorld")
        elif action == "edit_run_args":
            self.status_text.start_pause_fade("Editing configured run arguments...")

        # settings panel actions
        elif action == "configure_github_identity":
            self.status_text.start_pause_fade("Configured Github identity")
        elif action == "configure_steam_database_path":
            self.status_text.start_pause_fade("Configured SteamDB file path")
        elif action == "configure_steam_database_repo":
            self.status_text.start_pause_fade("Configured SteamDB repository")
        elif action == "download_steam_database":
            self.status_text.start_pause_fade(
                "Downloaded SteamDB from configured repository"
            )
        elif action == "upload_steam_database":
            self.status_text.start_pause_fade(
                "Uploaded SteamDB to configured repository"
            )
        elif action == "configure_community_rules_db_path":
            self.status_text.start_pause_fade("Configured Community Rules DB file path")
        elif action == "configure_community_rules_db_repo":
            self.status_text.start_pause_fade(
                "Configured Community Rules DB repository"
            )
        elif action == "download_community_rules_database":
            self.status_text.start_pause_fade(
                "Downloaded Community Rules DB from configured repository"
            )
        elif action == "open_community_rules_with_rule_editor":
            self.status_text.start_pause_fade(
                "Opening Rule Editor with Community Rules DB context"
            )
        elif action == "upload_community_rules_database":
            self.status_text.start_pause_fade(
                "Uploaded Community Rules DB to configured repository"
            )
        elif action == "build_steam_database_thread":
            self.status_text.start_pause_fade("Building SteamDB with DB Builder")
        elif action == "merge_databases":
            self.status_text.start_pause_fade("Successfully merged supplied SteamDBs")
        elif action == "set_database_expiry":
            self.status_text.start_pause_fade("Edited configured SteamDB expiry...")
        elif action == "edit_steam_webapi_key":
            self.status_text.start_pause_fade("Edited configured Steam WebAPI key...")
        elif action == "comparison_report":
            self.status_text.start_pause_fade("Created SteamDB comparison report")
        elif "download_entire_workshop" in action:
            if "steamcmd" in action:
                self.status_text.start_pause_fade(
                    "Attempting to download all Workshop mods with SteamCMD"
                )
            elif "steamworks" in action:
                self.status_text.start_pause_fade(
                    "Attempting to subscribe to all Workshop mods with Steam"
                )
        else:  # Otherwise, just display whatever text is passed
            self.status_text.start_pause_fade(action)
