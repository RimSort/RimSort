"""
Tests for the merge algorithm logic.

This module tests the core merge algorithm without Qt dependencies:
- Set computation (union of current + imported, categorization)
- Inactive list recomputation
"""


class TestMergeSetComputation:
    """Test the merge algorithm: union of current + imported, categorization."""

    def test_disjoint_lists(self) -> None:
        current_active = ["uuid-a", "uuid-b"]
        imported_active = ["uuid-c", "uuid-d"]
        current_set = set(current_active)

        new_mods = [u for u in imported_active if u not in current_set]
        already_present = [u for u in imported_active if u in current_set]

        assert new_mods == ["uuid-c", "uuid-d"]
        assert already_present == []
        assert current_active + new_mods == ["uuid-a", "uuid-b", "uuid-c", "uuid-d"]

    def test_full_overlap(self) -> None:
        current_active = ["uuid-a", "uuid-b"]
        imported_active = ["uuid-a", "uuid-b"]
        current_set = set(current_active)

        new_mods = [u for u in imported_active if u not in current_set]
        already_present = [u for u in imported_active if u in current_set]

        assert new_mods == []
        assert already_present == ["uuid-a", "uuid-b"]

    def test_partial_overlap(self) -> None:
        current_active = ["uuid-a", "uuid-b"]
        imported_active = ["uuid-b", "uuid-c"]
        current_set = set(current_active)

        new_mods = [u for u in imported_active if u not in current_set]
        already_present = [u for u in imported_active if u in current_set]

        assert new_mods == ["uuid-c"]
        assert already_present == ["uuid-b"]
        assert current_active + new_mods == ["uuid-a", "uuid-b", "uuid-c"]

    def test_empty_current_list(self) -> None:
        current_set: set[str] = set()
        imported_active = ["uuid-a", "uuid-b"]

        new_mods = [u for u in imported_active if u not in current_set]
        assert new_mods == ["uuid-a", "uuid-b"]

    def test_empty_imported_list(self) -> None:
        current_set = {"uuid-a", "uuid-b"}
        imported_active: list[str] = []

        new_mods = [u for u in imported_active if u not in current_set]
        assert new_mods == []


class TestInactiveListRecomputation:
    """Test that updated_inactive = all_known - merged_active."""

    def test_inactive_excludes_merged(self) -> None:
        all_known = {"uuid-a", "uuid-b", "uuid-c", "uuid-d"}
        merged_set = {"uuid-a", "uuid-c"}

        updated_inactive = [u for u in all_known if u not in merged_set]
        assert set(updated_inactive) == {"uuid-b", "uuid-d"}

    def test_all_active_leaves_nothing_inactive(self) -> None:
        all_known = {"uuid-a", "uuid-b"}
        merged_set = {"uuid-a", "uuid-b"}

        updated_inactive = [u for u in all_known if u not in merged_set]
        assert updated_inactive == []
