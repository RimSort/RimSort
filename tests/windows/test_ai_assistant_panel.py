from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from app.ai.chat_store import ChatStore
from app.models.settings import Settings
from app.windows.ai_assistant_panel import (
    AiAssistantPanel,
    _extract_mod_links,
    _format_tool_tooltip,
    _infer_mod_name_before_url,
    _linkify,
    _looks_like_url,
)


@pytest.fixture()
def settings(_mock_settings_deps: None) -> Settings:
    model = Settings()
    model.save = MagicMock()  # type: ignore[method-assign]
    return model


@pytest.fixture()
def panel(settings: Settings, qtbot: QtBot) -> Generator[AiAssistantPanel, None, None]:
    metadata_controller = MagicMock()
    metadata_controller.game_version = "1.6"
    with patch("app.windows.ai_assistant_panel.ChatStore") as mock_store:
        mock_store.return_value.as_list.return_value = []
        widget = AiAssistantPanel(
            settings,
            metadata_controller,
            list,
        )
        qtbot.addWidget(widget)
        yield widget


class TestAiAssistantPanelCredentials:
    def test_persist_ai_credentials_saves_api_key_and_proxy(
        self, panel: AiAssistantPanel, settings: Settings
    ) -> None:
        panel.api_key_edit.setText("secret-key")
        panel.proxy_edit.setText("127.0.0.1:8080")
        lang_index = panel.localization_combo.findData("ru")
        panel.localization_combo.setCurrentIndex(lang_index)

        panel._persist_ai_credentials()

        assert settings.ai_api_key == "secret-key"
        assert settings.ai_proxy == "127.0.0.1:8080"
        assert settings.ai_model == panel._current_model_id()
        assert settings.ai_localization_language == "ru"
        settings.save.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_persists_credentials(
        self, panel: AiAssistantPanel, settings: Settings, qtbot: QtBot
    ) -> None:
        panel.api_key_edit.setText("another-key")
        panel.proxy_edit.setText("socks5://127.0.0.1:1080")

        panel.close()

        assert settings.ai_api_key == "another-key"
        assert settings.ai_proxy == "socks5://127.0.0.1:1080"
        settings.save.assert_called_once()  # type: ignore[attr-defined]

    def test_clear_chat_clears_store_and_history(
        self, panel: AiAssistantPanel, tmp_path: Path
    ) -> None:
        panel._store = ChatStore(path=tmp_path / "ai_chat.json")
        panel._store.append("user", "hello")
        panel._store.append("assistant", "world")
        panel._render_history()

        # 1 stretch + 2 message bubble rows
        assert panel._history_layout.count() == 3

        panel._clear_chat()

        assert panel._store.as_list() == []
        assert panel._history_layout.count() == 1
        assert not (tmp_path / "ai_chat.json").exists() or panel._store.as_list() == []


class TestAiAssistantPanelInputHistory:
    def test_up_arrow_recalls_older_messages(self, panel: AiAssistantPanel) -> None:
        panel._sent_history = ["first", "second"]
        panel.input_edit.setText("draft")

        panel._recall_older_message()
        assert panel.input_edit.text() == "second"

        panel._recall_older_message()
        assert panel.input_edit.text() == "first"

        # Already at the oldest message - stays put
        panel._recall_older_message()
        assert panel.input_edit.text() == "first"

    def test_down_arrow_steps_forward_and_restores_draft(
        self, panel: AiAssistantPanel
    ) -> None:
        panel._sent_history = ["first", "second"]
        panel.input_edit.setText("draft")

        panel._recall_older_message()
        panel._recall_older_message()
        assert panel.input_edit.text() == "first"

        panel._recall_newer_message()
        assert panel.input_edit.text() == "second"

        panel._recall_newer_message()
        assert panel.input_edit.text() == "draft"

    def test_down_arrow_without_active_recall_is_noop(
        self, panel: AiAssistantPanel
    ) -> None:
        panel.input_edit.setText("typing")

        panel._recall_newer_message()

        assert panel.input_edit.text() == "typing"


class TestLinkify:
    def test_plain_url_is_wrapped(self) -> None:
        result = _linkify("Check https://example.com/mod for details")
        assert '<a href="https://example.com/mod">https://example.com/mod</a>' in result

    def test_mod_name_with_brackets_in_label(self) -> None:
        # Mod names commonly carry a "[TAG]" prefix, which used to break the
        # markdown-link regex since it disallowed brackets inside the label.
        text = (
            "[[RH2] Uncle Boris' - Brainwash Chair (2885223720)]"
            "(https://steamcommunity.com/sharedfiles/filedetails/?id=2885223720)"
        )
        result = _linkify(text)
        assert (
            '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=2885223720">'
            "[RH2] Uncle Boris' - Brainwash Chair (2885223720)</a>" in result
        )
        assert "[[RH2]" not in result


class TestExtractModLinks:
    def test_extracts_pfid_and_label_from_markdown_link(self) -> None:
        content = (
            "Check out [Cool Mod (123456)]"
            "(https://steamcommunity.com/sharedfiles/filedetails/?id=123456)."
        )
        links = _extract_mod_links(content)
        assert links == [
            (
                "Cool Mod (123456)",
                "123456",
                "https://steamcommunity.com/sharedfiles/filedetails/?id=123456",
            )
        ]

    def test_deduplicates_by_pfid(self) -> None:
        content = (
            "[Mod A (1)](https://steamcommunity.com/sharedfiles/filedetails/?id=1) "
            "and again [Mod A (1)]"
            "(https://steamcommunity.com/sharedfiles/filedetails/?id=1)"
        )
        links = _extract_mod_links(content)
        assert len(links) == 1

    def test_ignores_non_workshop_links(self) -> None:
        content = "See [docs](https://example.com/docs) for details."
        assert _extract_mod_links(content) == []

    def test_bare_workshop_url_uses_empty_label_not_url(self) -> None:
        content = (
            "Download here:\n"
            "https://steamcommunity.com/sharedfiles/filedetails/?id=3294950775"
        )
        links = _extract_mod_links(content)
        assert links == [
            (
                "",
                "3294950775",
                "https://steamcommunity.com/sharedfiles/filedetails/?id=3294950775",
            )
        ]


class TestModLabelHelpers:
    def test_looks_like_url(self) -> None:
        assert _looks_like_url("https://steamcommunity.com/foo")
        assert not _looks_like_url("Cool Mod")

    def test_infer_mod_name_skips_generic_preface(self) -> None:
        content = (
            "Вы можете загрузить мод по следующей ссылке:\n"
            "https://steamcommunity.com/sharedfiles/filedetails/?id=1"
        )
        url_start = content.index("https://")
        assert _infer_mod_name_before_url(content, url_start) is None

    def test_register_mod_link_does_not_store_url_label(
        self, panel: AiAssistantPanel
    ) -> None:
        with patch.object(panel, "_queue_mod_title_fetch") as mock_fetch:
            panel._register_mod_link(
                "123",
                "https://steamcommunity.com/sharedfiles/filedetails/?id=123",
            )
        assert panel._mod_titles["123"] == "123"
        mock_fetch.assert_called_once_with("123")

    def test_display_mod_label_rejects_url(self, panel: AiAssistantPanel) -> None:
        panel._mod_titles["123"] = "https://example.com/mod"
        assert panel._display_mod_label("123") == "123"


class TestFormatToolTooltip:
    def test_search_workshop_mods_lists_matches(self) -> None:
        result = {
            "matches": [
                {"title": "Mod A", "publishedfileid": "1"},
                {"title": "Mod B", "publishedfileid": "2"},
            ]
        }
        tooltip = _format_tool_tooltip("search_workshop_mods", {}, result)
        assert "Mod A (1)" in tooltip
        assert "Mod B (2)" in tooltip

    def test_validate_workshop_ids_shows_valid_and_invalid(self) -> None:
        result = {"valid": ["1"], "invalid": ["2"]}
        tooltip = _format_tool_tooltip("validate_workshop_ids", {}, result)
        assert "Valid: 1" in tooltip
        assert "Invalid: 2" in tooltip

    def test_unknown_tool_falls_back_to_json(self) -> None:
        result = {"ok": True, "count": 3}
        tooltip = _format_tool_tooltip("some_other_tool", {}, result)
        assert '"ok": true' in tooltip
        assert '"count": 3' in tooltip


class TestModListToggle:
    def test_toggle_mod_link_adds_then_removes(self, panel: AiAssistantPanel) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=123"

        panel._toggle_mod_link(url)
        assert panel._download_list.has_mod("123")

        panel._toggle_mod_link(url)
        assert not panel._download_list.has_mod("123")

    def test_toggle_non_mod_link_opens_browser(
        self, panel: AiAssistantPanel
    ) -> None:
        with patch("app.windows.ai_assistant_panel.open_url_browser") as mock_open:
            panel._toggle_mod_link("https://example.com/not-a-mod")
        mock_open.assert_called_once_with("https://example.com/not-a-mod")


class TestCompatibilityCheck:
    def test_parse_compat_response_extracts_incompatible_list(
        self, panel: AiAssistantPanel
    ) -> None:
        text = '```json\n{"incompatible": [{"publishedfileid": "1", "reason": "conflict"}]}\n```'
        parsed = panel._parse_compat_response(text)
        assert parsed == [{"publishedfileid": "1", "reason": "conflict"}]

    def test_parse_compat_response_handles_garbage(
        self, panel: AiAssistantPanel
    ) -> None:
        assert panel._parse_compat_response("not json at all") == []

    def test_download_list_requested_skips_llm_check_without_api_key(
        self, panel: AiAssistantPanel, settings: Settings
    ) -> None:
        settings.ai_api_key = ""
        with patch.object(panel, "_start_download") as mock_start:
            panel._on_download_list_requested(["123"])
        mock_start.assert_called_once_with(["123"])

    def test_download_list_requested_noop_when_empty(
        self, panel: AiAssistantPanel
    ) -> None:
        with patch.object(panel, "_start_download") as mock_start:
            panel._on_download_list_requested([])
        mock_start.assert_not_called()
