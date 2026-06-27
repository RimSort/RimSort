from typing import Callable

from PySide6.QtWidgets import QApplication

from app.controllers.settings_tabs.base_tab_controller import BaseTabController
from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.dialogue import show_dialogue_file
from app.views.settings_dialog import SettingsDialog


class DatabaseSourceGroup:
    """Encapsulates widget-to-model sync for one database source radio group.

    Each of the 4 database groups (Community Rules, Steam Workshop,
    No Version Warning, Use This Instead) follows an identical pattern
    of 4 radio buttons (none/github/url/local_file) plus sub-widgets
    that are enabled/disabled based on the active source.
    """

    _SOURCE_VALUES = {
        "none": "None",
        "github": "Configured git repository",
        "url": "Configured URL",
        "local_file": "Configured file path",
    }

    _ALL_WIDGETS = [
        "github_url",
        "github_download_button",
        "url_input",
        "url_download_button",
        "local_file",
        "local_file_choose_button",
    ]

    _ENABLED_WIDGETS = {
        "none": [],
        "github": ["github_url", "github_download_button"],
        "url": ["url_input", "url_download_button"],
        "local_file": ["local_file", "local_file_choose_button"],
    }

    def __init__(
        self,
        *,
        prefix: str,
        source_attr: str,
        file_path_attr: str,
        repo_attr: str,
        url_attr: str,
        display_name: str = "",
        upload_event: str = "",
        download_event: str = "",
        file_filter: str = "",
    ) -> None:
        self._prefix = prefix
        self._source_attr = source_attr
        self._file_path_attr = file_path_attr
        self._repo_attr = repo_attr
        self._url_attr = url_attr
        self._display_name = display_name
        self._upload_event = upload_event
        self._download_event = download_event
        self._file_filter = file_filter

    def connect_signals(
        self,
        dialog: SettingsDialog,
        http_download_callback: Callable[[str, str, str], None],
    ) -> None:
        for key in ("none", "github", "url", "local_file"):
            radio = getattr(dialog, f"{self._prefix}_{key}_radio")
            radio.clicked.connect(
                lambda checked, k=key: (
                    self._on_radio_clicked(dialog, k) if checked else None
                )
            )

        choose_btn = getattr(dialog, f"{self._prefix}_local_file_choose_button")
        choose_btn.clicked.connect(lambda: self._on_choose_clicked(dialog))

        if self._upload_event:
            upload_btn = getattr(dialog, f"{self._prefix}_github_upload_button")
            upload_btn.clicked.connect(getattr(EventBus(), self._upload_event))

        if self._download_event:
            download_btn = getattr(dialog, f"{self._prefix}_github_download_button")
            download_btn.clicked.connect(getattr(EventBus(), self._download_event))

        url_download_btn = getattr(dialog, f"{self._prefix}_url_download_button")
        url_download_btn.clicked.connect(
            lambda: http_download_callback(
                getattr(dialog, f"{self._prefix}_url_input").text(),
                getattr(dialog, f"{self._prefix}_github_url").text(),
                self._display_name,
            )
        )

    def update_view(self, dialog: SettingsDialog, settings: Settings) -> None:
        source = getattr(settings, self._source_attr)

        for key, value in self._SOURCE_VALUES.items():
            getattr(dialog, f"{self._prefix}_{key}_radio").setChecked(source == value)

        self._apply_enabled_state(dialog, source)

        getattr(dialog, f"{self._prefix}_local_file").setText(
            getattr(settings, self._file_path_attr)
        )
        getattr(dialog, f"{self._prefix}_local_file").setCursorPosition(0)

        getattr(dialog, f"{self._prefix}_github_url").setText(
            getattr(settings, self._repo_attr)
        )
        getattr(dialog, f"{self._prefix}_github_url").setCursorPosition(0)

        getattr(dialog, f"{self._prefix}_url_input").setText(
            getattr(settings, self._url_attr)
        )

    def update_model(self, dialog: SettingsDialog, settings: Settings) -> None:
        for key, value in self._SOURCE_VALUES.items():
            if getattr(dialog, f"{self._prefix}_{key}_radio").isChecked():
                setattr(settings, self._source_attr, value)
                break

        setattr(
            settings,
            self._file_path_attr,
            getattr(dialog, f"{self._prefix}_local_file").text(),
        )
        setattr(
            settings,
            self._repo_attr,
            getattr(dialog, f"{self._prefix}_github_url").text(),
        )
        setattr(
            settings,
            self._url_attr,
            getattr(dialog, f"{self._prefix}_url_input").text(),
        )

    def _on_radio_clicked(self, dialog: SettingsDialog, key: str) -> None:
        source_value = self._SOURCE_VALUES[key]
        self._apply_enabled_state(dialog, source_value)

        if key == "github":
            getattr(dialog, f"{self._prefix}_github_url").setFocus()
        elif key == "url":
            getattr(dialog, f"{self._prefix}_url_input").setFocus()
        elif key == "local_file":
            getattr(dialog, f"{self._prefix}_local_file").setFocus()
        elif key == "none":
            focused = QApplication.focusWidget()
            if focused is not None:
                focused.clearFocus()

    def _apply_enabled_state(self, dialog: SettingsDialog, source_value: str) -> None:
        enabled_widgets: list[str] = []
        for key, value in self._SOURCE_VALUES.items():
            if value == source_value:
                enabled_widgets = self._ENABLED_WIDGETS.get(key, [])
                break
        for widget_name in self._ALL_WIDGETS:
            getattr(dialog, f"{self._prefix}_{widget_name}").setEnabled(
                widget_name in enabled_widgets
            )

    def _on_choose_clicked(self, dialog: SettingsDialog) -> None:
        kwargs = {
            "mode": "open",
            "caption": f"Select {self._display_name} Database",
        }
        if self._file_filter:
            kwargs["_filter"] = self._file_filter
        file_path = show_dialogue_file(**kwargs)
        if file_path:
            getattr(dialog, f"{self._prefix}_local_file").setText(file_path)


class DatabasesTabController(BaseTabController):
    """Controller for the Databases settings tab.

    Manages: Community Rules DB, Steam Workshop DB, No Version Warning DB,
    Use This Instead DB, and database expiry.
    """

    def __init__(
        self,
        settings: Settings,
        dialog: SettingsDialog,
        http_download_callback: Callable[[str, str, str], None],
    ) -> None:
        super().__init__(settings, dialog)
        self._http_download_callback = http_download_callback
        self._groups = [
            DatabaseSourceGroup(
                prefix="community_rules_db",
                source_attr="external_community_rules_metadata_source",
                file_path_attr="external_community_rules_file_path",
                repo_attr="external_community_rules_repo",
                url_attr="external_community_rules_url",
                display_name="Community Rules",
                upload_event="do_upload_community_rules_db_to_github",
                download_event="do_download_community_rules_db_from_github",
            ),
            DatabaseSourceGroup(
                prefix="steam_workshop_db",
                source_attr="external_steam_metadata_source",
                file_path_attr="external_steam_metadata_file_path",
                repo_attr="external_steam_metadata_repo",
                url_attr="external_steam_metadata_url",
                display_name="Steam Workshop",
                upload_event="do_upload_steam_workshop_db_to_github",
                download_event="do_download_steam_workshop_db_from_github",
            ),
            DatabaseSourceGroup(
                prefix="no_version_warning_db",
                source_attr="external_no_version_warning_metadata_source",
                file_path_attr="external_no_version_warning_file_path",
                repo_attr="external_no_version_warning_repo_path",
                url_attr="external_no_version_warning_url",
                display_name="No Version Warning",
                upload_event="do_upload_no_version_warning_db_to_github",
                download_event="do_download_no_version_warning_db_from_github",
            ),
            DatabaseSourceGroup(
                prefix="use_this_instead_db",
                source_attr="external_use_this_instead_metadata_source",
                file_path_attr="external_use_this_instead_file_path",
                repo_attr="external_use_this_instead_repo_path",
                url_attr="external_use_this_instead_url",
                display_name="Use This Instead",
                upload_event="do_upload_use_this_instead_db_to_github",
                download_event="do_download_use_this_instead_db_from_github",
                file_filter="JSON Files (*.json *.json.gz)",
            ),
        ]

    def connect_signals(self) -> None:
        for group in self._groups:
            group.connect_signals(self.dialog, self._http_download_callback)

    def update_view_from_model(self) -> None:
        for group in self._groups:
            group.update_view(self.dialog, self.settings)

    def update_model_from_view(self) -> None:
        for group in self._groups:
            group.update_model(self.dialog, self.settings)
