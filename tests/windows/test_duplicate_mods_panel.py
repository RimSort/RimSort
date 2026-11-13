"""Tests for ignoring duplicate mods in the Duplicate Mods panel."""

from unittest.mock import MagicMock

from app.windows.duplicate_mods_panel import (
    DuplicateModsPanel,
    filter_ignored_duplicates,
)


class _PanelStandIn:
    """Plain stand-in carrying only the state ``_ignore_selected`` uses."""

    def __init__(
        self, duplicate_mods: dict[str, list[str]], checked_paths: list[str]
    ) -> None:
        self.duplicate_mods = duplicate_mods
        self._rows = checked_paths
        self.settings = MagicMock()
        self.settings.ignored_duplicate_mods = {}
        self._populate_from_metadata = MagicMock()
        self.close = MagicMock()

    def _get_selected_row_indices(self) -> set[int]:
        return set(range(len(self._rows)))

    def _get_key_from_row(self, row: int) -> str | None:
        return self._rows[row]


def _ignore(panel: _PanelStandIn) -> None:
    DuplicateModsPanel._ignore_selected(panel)  # type: ignore[arg-type]


class TestFilterIgnoredDuplicates:
    def test_no_ignores_returns_all(self) -> None:
        dupes = {"a.mod": ["/x", "/y"]}

        assert filter_ignored_duplicates(dupes, {}) == dupes

    def test_matching_paths_are_hidden(self) -> None:
        dupes = {"A.Mod": ["/y", "/x"], "b.mod": ["/p", "/q"]}

        result = filter_ignored_duplicates(dupes, {"a.mod": ["/x", "/y"]})

        assert result == {"b.mod": ["/p", "/q"]}

    def test_new_copy_shows_warning_again(self) -> None:
        dupes = {"a.mod": ["/x", "/y", "/z"]}

        result = filter_ignored_duplicates(dupes, {"a.mod": ["/x", "/y"]})

        assert result == dupes

    def test_input_is_not_mutated(self) -> None:
        dupes = {"a.mod": ["/x", "/y"]}

        filter_ignored_duplicates(dupes, {"a.mod": ["/x", "/y"]})

        assert dupes == {"a.mod": ["/x", "/y"]}


class TestIgnoreSelected:
    def test_saves_lowercased_id_with_sorted_paths_and_closes(self) -> None:
        panel = _PanelStandIn({"Mss.Pack": ["/steam", "/git"]}, ["/git"])

        _ignore(panel)

        assert panel.settings.ignored_duplicate_mods == {"mss.pack": ["/git", "/steam"]}
        panel.settings.save.assert_called_once()
        panel.close.assert_called_once()
        panel._populate_from_metadata.assert_not_called()

    def test_remaining_groups_are_repopulated(self) -> None:
        panel = _PanelStandIn({"a.mod": ["/x", "/y"], "b.mod": ["/p", "/q"]}, ["/x"])

        _ignore(panel)

        assert panel.duplicate_mods == {"b.mod": ["/p", "/q"]}
        panel._populate_from_metadata.assert_called_once()
        panel.close.assert_not_called()

    def test_no_selection_changes_nothing(self) -> None:
        panel = _PanelStandIn({"a.mod": ["/x", "/y"]}, [])

        _ignore(panel)

        assert panel.settings.ignored_duplicate_mods == {}
        panel.settings.save.assert_not_called()
        panel.close.assert_not_called()
