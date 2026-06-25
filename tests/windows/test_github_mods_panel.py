from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from app.windows.github_mods_panel import GitHubModsPanel


class TestGitHubModsPanel:
    def test_panel_creates_without_error(self, qapp: QApplication) -> None:
        with patch("app.windows.github_mods_panel.GitHubModsPanel._populate_from_mods"):
            panel = GitHubModsPanel.__new__(GitHubModsPanel)
            assert panel is not None
