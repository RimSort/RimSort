from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from app.ai.chat_store import ChatStore
from app.models.settings import Settings
from app.windows.ai_assistant_panel import AiAssistantPanel


@pytest.fixture()
def _mock_settings_deps() -> Generator[None, None, None]:
    with (
        patch("app.models.settings.QApplication") as mock_qapp,
        patch("app.models.settings.AppInfo") as mock_app_info,
    ):
        mock_qapp.font.return_value.family.return_value = "monospace"
        mock_app_info.return_value.app_storage_folder = MagicMock()
        mock_app_info.return_value.app_settings_file = MagicMock()
        yield


@pytest.fixture()
def settings(_mock_settings_deps: None) -> Settings:
    model = Settings()
    model.save = MagicMock()  # type: ignore[method-assign]
    return model


@pytest.fixture()
def panel(settings: Settings, qtbot: QtBot) -> AiAssistantPanel:
    metadata_controller = MagicMock()
    metadata_controller.game_version = "1.6"
    with patch("app.windows.ai_assistant_panel.ChatStore") as mock_store:
        mock_store.return_value.as_list.return_value = []
        widget = AiAssistantPanel(
            settings,
            metadata_controller,
            lambda: [],
        )
        qtbot.addWidget(widget)
        yield widget


class TestAiAssistantPanelCredentials:
    def test_persist_ai_credentials_saves_api_key_and_proxy(
        self, panel: AiAssistantPanel, settings: Settings
    ) -> None:
        panel.api_key_edit.setText("secret-key")
        panel.proxy_edit.setText("127.0.0.1:8080")

        panel._persist_ai_credentials()

        assert settings.ai_api_key == "secret-key"
        assert settings.ai_proxy == "127.0.0.1:8080"
        assert settings.ai_model == panel._current_model_id()
        settings.save.assert_called_once()

    def test_close_event_persists_credentials(
        self, panel: AiAssistantPanel, settings: Settings, qtbot: QtBot
    ) -> None:
        panel.api_key_edit.setText("another-key")
        panel.proxy_edit.setText("socks5://127.0.0.1:1080")

        panel.close()

        assert settings.ai_api_key == "another-key"
        assert settings.ai_proxy == "socks5://127.0.0.1:1080"
        settings.save.assert_called_once()

    def test_clear_chat_clears_store_and_history(
        self, panel: AiAssistantPanel, tmp_path: Path
    ) -> None:
        panel._store = ChatStore(path=tmp_path / "ai_chat.json")
        panel._store.append("user", "hello")
        panel._store.append("assistant", "world")
        panel._render_history()

        assert panel._MESSAGE_SEPARATOR in panel.history.toPlainText()

        panel._clear_chat()

        assert panel._store.as_list() == []
        assert panel.history.toPlainText() == ""
        assert not (tmp_path / "ai_chat.json").exists() or panel._store.as_list() == []
