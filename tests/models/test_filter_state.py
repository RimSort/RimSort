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
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_source_filter_inactive_when_all(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags=set(),
            include_no_tags=False,
        )
        assert not state.has_active_filters()

    def test_type_filter_active_when_not_all(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="csharp",
            tags=set(),
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_tag_filter_active_when_tags_selected(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags={"Favorites"},
            include_no_tags=False,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_tag_filter_active_when_no_tags_selected(self) -> None:
        state = FilterState(
            sources=set(FilterState.ALL_SOURCES),
            mod_type="all",
            tags=set(),
            include_no_tags=True,
        )
        assert state.has_active_filters()
        assert state.active_category_count() == 1

    def test_multiple_categories_active(self) -> None:
        state = FilterState(
            sources={"workshop"},
            mod_type="xml",
            tags={"Cosmetic"},
            include_no_tags=False,
        )
        assert state.active_category_count() == 3

    def test_default_factory(self) -> None:
        state = FilterState.default()
        assert state.sources == FilterState.ALL_SOURCES
        assert state.mod_type == "all"
        assert state.tags == set()
        assert state.include_no_tags is False
