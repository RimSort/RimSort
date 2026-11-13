"""Tests for the duplicate mods prompt skipping ignored package IDs."""

from unittest.mock import MagicMock

import pytest

from app.views import main_content_panel
from app.views.main_content_panel import MainContent


@pytest.fixture
def prompt_context(
    main_content: tuple[MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MainContent, MagicMock]:
    mc, _calls = main_content
    panel_cls = MagicMock()
    monkeypatch.setattr(main_content_panel, "DuplicateModsPanel", panel_cls)
    monkeypatch.setattr(mc, "window_manager", MagicMock())
    mc.settings.duplicate_mods_warning = True
    mc.settings.ignored_duplicate_mods = {"a.mod": ["/x", "/y"]}
    return mc, panel_cls


def _prompt(mc: MainContent) -> None:
    mc._MainContent__duplicate_mods_prompt()  # type: ignore[attr-defined]


def test_all_ignored_does_not_open_panel(
    prompt_context: tuple[MainContent, MagicMock],
) -> None:
    mc, panel_cls = prompt_context
    mc.duplicate_mods = {"A.Mod": ["/y", "/x"]}

    _prompt(mc)

    panel_cls.assert_not_called()


def test_changed_copies_open_panel_with_visible_groups_only(
    prompt_context: tuple[MainContent, MagicMock],
) -> None:
    mc, panel_cls = prompt_context
    mc.duplicate_mods = {"a.mod": ["/x", "/y", "/z"], "b.mod": ["/p", "/q"]}

    _prompt(mc)

    panel_cls.assert_called_once()
    assert panel_cls.call_args.args[0] == {
        "a.mod": ["/x", "/y", "/z"],
        "b.mod": ["/p", "/q"],
    }
