from app.models.filter_state import FilterState


class TestFilterState:
    def test_default_has_no_active_filters(self) -> None:
        state = FilterState.default()
        assert not state.has_active_filters()
        assert state.active_category_count() == 0

    def test_source_filter_active_when_subset(self) -> None:
        state = FilterState(
            sources={"workshop", "local"},
            mod_type="all",
            tags=set(),
            tag_match_mode="or",
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_source_filter_inactive_when_all(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags=set(),
            tag_match_mode="or",
            include_no_tags=False,
        )
        assert not state.has_active_filters()

    def test_type_filter_active_when_not_all(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="csharp",
            tags=set(),
            tag_match_mode="or",
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_tag_filter_active_when_tags_selected(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags={"Favorites"},
            tag_match_mode="or",
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_tag_filter_active_when_no_tags_selected(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags=set(),
            tag_match_mode="or",
            include_no_tags=True,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_multiple_categories_active(self) -> None:
        state = FilterState(
            sources={"workshop"},
            mod_type="xml",
            tags={"Cosmetic"},
            tag_match_mode="or",
            include_no_tags=False,
        )
        assert state.active_category_count() == 3

    def test_default_factory(self) -> None:
        state = FilterState.default()
        assert state.sources == FilterState.ALL_SOURCES
        assert state.mod_type == "all"
        assert state.tags == set()
        assert state.tag_match_mode == "or"
        assert state.include_no_tags is False

    def test_tag_match_or_mode_matches_any_selected_tag(self) -> None:
        state = FilterState(tags={"milira", "expansion"}, tag_match_mode="or")
        assert state.matches_tags({"milira", "patch"}) is True
        assert state.matches_tags({"kiiro", "patch"}) is False

    def test_tag_match_and_mode_matches_all_selected_tags(self) -> None:
        state = FilterState(tags={"milira", "expansion"}, tag_match_mode="and")
        assert state.matches_tags({"milira", "expansion"}) is True
        assert state.matches_tags({"milira", "patch"}) is False

    def test_tag_match_no_tags_is_additive(self) -> None:
        state = FilterState(
            tags={"milira", "expansion"},
            tag_match_mode="and",
            include_no_tags=True,
        )
        assert state.matches_tags(set()) is True
        assert state.matches_tags({"milira", "expansion"}) is True
        assert state.matches_tags({"milira"}) is False
