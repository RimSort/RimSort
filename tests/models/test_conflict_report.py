from array import array
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QWidget

from app.models.conflict_report import (
    ConflictReportBrowser,
    ConflictTableModel,
    FindingFilters,
    safe_text,
)
from tests.conflict_detector_fixtures import (
    extract_context_sources,
    force_one_row_per_tick,
    make_notes_diagnostics,
    make_triage_report,
    make_triage_report_with_counts,
    make_triage_report_with_duplicate_participant_names,
)


class NonIterablePublishedRows(array[int]):
    def __iter__(self) -> Any:
        raise AssertionError("published compact row buffer should not be iterated")


def _row_values(source_rows: Sequence[int]) -> list[int]:
    return [int(source_rows[index]) for index in range(len(source_rows))]


def _report_with_conflicting_summary() -> dict[str, Any]:
    report = make_triage_report()
    report["summary"]["conflicts_by_severity"] = {
        "error": 0,
        "warning": 1,
        "info": 1,
    }
    return report


def _browser_with_views() -> tuple[ConflictReportBrowser, list[Any]]:
    browser = ConflictReportBrowser()
    views: list[Any] = []
    browser.applied.connect(views.append)
    return browser, views


def _forced_browser_with_views(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ConflictReportBrowser, list[Any]]:
    force_one_row_per_tick(monkeypatch)
    return _browser_with_views()


def _wait_for_applied_views(
    qtbot: Any,
    browser: ConflictReportBrowser,
    views: list[Any],
    count: int,
) -> None:
    qtbot.waitUntil(lambda: len(views) == count and not browser.busy)


def test_scan_notes_preserve_attention_and_all_native_records(qtbot: Any) -> None:
    from app.models.conflict_report import NoteRef, ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    records = make_notes_diagnostics()
    model = ScanNotesModel(lambda record: record["message"])
    model.set_notes(ScanSnapshot((), "1.7", "instance", ()), records)
    assert model.busy
    assert model.attention_count is None
    qtbot.waitUntil(lambda: not model.busy)
    assert model.attention_count == 3
    assert [model.note(model.index(row, 0)) for row in range(3)] == [
        NoteRef("native", 0),
        NoteRef("native", 1),
        NoteRef("native", 2),
    ]
    model.set_show_info(True)
    assert model.rowCount() == 4
    assert [model.note(model.index(row, 0)) for row in range(4)] == [
        NoteRef("native", 0),
        NoteRef("native", 1),
        NoteRef("native", 2),
        NoteRef("native", 3),
    ]
    model.dispose()


def test_notes_replacement_yields_and_keeps_old_dataset_until_publication(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    snapshot = ScanSnapshot((), "1.7", "instance", ())

    def record(message: str, severity: str = "warning") -> dict[str, Any]:
        return {
            "source": "xml_parsing",
            "severity": severity,
            "analysis_incomplete": False,
            "message": message,
            "affected_mod": None,
        }

    model = ScanNotesModel(lambda diagnostic: diagnostic["message"])
    old = [record("old-0"), record("old-1"), record("old-2")]
    model.set_notes(snapshot, old)
    qtbot.waitUntil(lambda: not model.busy)
    assert model.data(model.index(2, 1)) == "old-2"
    force_one_row_per_tick(monkeypatch)
    replacement = [record("new-info", "info"), record("new-warning")]
    publications: list[int | None] = []
    partial: list[tuple[bool, int | None, int, object]] = []
    model.prepared.connect(lambda: publications.append(model.attention_count))

    def observe_partial() -> None:
        if model._index == 1 and not partial:
            partial.append(
                (
                    model.busy,
                    model.attention_count,
                    model.rowCount(),
                    model.data(model.index(2, 1)),
                )
            )
            model.set_show_info(True)

    model._timer.timeout.connect(observe_partial)
    model.set_notes(snapshot, replacement)
    qtbot.waitUntil(lambda: not model.busy)
    assert partial == [(True, None, 3, "old-2")]
    assert publications == [1]
    assert model.rowCount() == 2
    assert model.data(model.index(0, 1)) == "new-info"
    model.dispose()


def test_notes_reset_and_prepared_reentrancy_publish_only_current_dataset(
    qtbot: Any,
) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    snapshot = ScanSnapshot((), "1.7", "instance", ())

    def record(message: str) -> dict[str, Any]:
        return {
            "source": "xml_parsing",
            "severity": "warning",
            "analysis_incomplete": False,
            "message": message,
            "affected_mod": None,
        }

    owner = QWidget()
    qtbot.addWidget(owner)
    model = ScanNotesModel(lambda diagnostic: diagnostic["message"], owner)
    publications: list[object] = []
    triggered: list[bool] = []

    def replace_on_reset() -> None:
        if not triggered:
            triggered.append(True)
            model.set_notes(snapshot, [record("reset-replacement")])

    def replace_on_prepared() -> None:
        publications.append(model.data(model.index(0, 1)))
        if len(publications) == 1:
            model.set_notes(snapshot, [record("prepared-replacement")])

    model.modelAboutToBeReset.connect(replace_on_reset)
    model.prepared.connect(replace_on_prepared)
    model.set_notes(snapshot, [record("obsolete")])
    qtbot.waitUntil(lambda: not model.busy)
    assert publications == ["reset-replacement", "prepared-replacement"]
    assert model.data(model.index(0, 1)) == "prepared-replacement"
    model.dispose()


def test_notes_replace_during_actual_progress_then_dispose_during_progress(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    owner = QWidget()
    qtbot.addWidget(owner)
    model = ScanNotesModel(lambda diagnostic: diagnostic["message"], owner)
    snapshot = ScanSnapshot((), "1.7", "instance", ())
    record = {
        "source": "xml_parsing",
        "severity": "warning",
        "analysis_incomplete": False,
        "message": "old",
        "affected_mod": None,
    }
    replacement = dict(record, message="new")
    force_one_row_per_tick(monkeypatch)
    events: list[str] = []
    model.prepared.connect(lambda: events.append("prepared"))

    def interrupt() -> None:
        if model._index == 1 and not events:
            events.append("replaced")
            model.set_notes(snapshot, [replacement] * 3)
        elif model._index == 1 and events == ["replaced"]:
            events.append("disposed")
            model.dispose()

    model._timer.timeout.connect(interrupt)
    model.set_notes(snapshot, [record] * 4)
    qtbot.waitUntil(lambda: "disposed" in events)
    qtbot.wait(10)
    assert events == ["replaced", "disposed"]
    assert not model.busy
    assert model.rowCount() == 0


def test_notes_dispose_from_about_to_reset_pairs_reset_without_publication(
    qtbot: Any,
) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    owner = QWidget()
    qtbot.addWidget(owner)
    model = ScanNotesModel(lambda diagnostic: diagnostic["message"], owner)
    resets: list[str] = []
    model.modelAboutToBeReset.connect(model.dispose)
    model.modelReset.connect(lambda: resets.append("reset"))
    model.prepared.connect(lambda: resets.append("prepared"))
    model.set_notes(ScanSnapshot((), "1.7", "instance", ()), [])
    qtbot.waitUntil(lambda: bool(resets))
    assert resets == ["reset"]
    assert not model.busy
    assert model.rowCount() == 0


def test_notes_model_reset_show_info_and_busy_callbacks_honor_latest_request(
    qtbot: Any,
) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    snapshot = ScanSnapshot((), "1.7", "instance", ())
    info = {
        "source": "xml_parsing",
        "severity": "info",
        "analysis_incomplete": False,
        "message": "info",
        "affected_mod": None,
    }
    warning = dict(info, severity="warning", message="new")
    model = ScanNotesModel(lambda diagnostic: diagnostic["message"])
    prepared: list[int] = []
    busy: list[bool] = []

    def reset_show_info() -> None:
        model.set_show_info(True)

    def track_busy(value: bool) -> None:
        busy.append(value)
        if not value and len(prepared) == 1:
            model.set_notes(snapshot, [warning])

    model.modelReset.connect(reset_show_info)
    model.prepared.connect(lambda: prepared.append(model.rowCount()))
    model.busy_changed.connect(track_busy)
    model.set_notes(snapshot, [info])
    qtbot.waitUntil(lambda: len(prepared) == 2 and not model.busy)
    assert prepared == [0, 1]
    assert busy == [True, False, True, False]
    assert model.data(model.index(0, 1)) == "new"
    model.dispose()


def test_notes_prepared_callback_can_reveal_info(qtbot: Any) -> None:
    from app.models.conflict_report import ScanNotesModel
    from app.services.conflict_snapshot import ScanSnapshot

    record = {
        "source": "xml_parsing",
        "severity": "info",
        "analysis_incomplete": False,
        "message": "revealed",
        "affected_mod": None,
    }
    model = ScanNotesModel(lambda diagnostic: diagnostic["message"])
    model.prepared.connect(lambda: model.set_show_info(True))
    model.set_notes(ScanSnapshot((), "1.7", "instance", ()), [record])
    qtbot.waitUntil(lambda: not model.busy)
    assert model.rowCount() == 1
    assert model.data(model.index(0, 1)) == "revealed"
    model.dispose()


def test_safe_text_preserves_unicode_and_escapes_invalid_bytes() -> None:
    assert safe_text("Mód 猫") == "Mód 猫"
    assert safe_text("bad-\udcff") == "bad-\\udcff"


def test_browser_prepares_error_findings_first_and_restores_selection(
    qtbot: Any,
) -> None:
    browser, views = _browser_with_views()
    report = make_triage_report()

    browser.set_report(report)

    _wait_for_applied_views(qtbot, browser, views, 1)
    first_view = views[-1]
    assert browser.conflicts is report["conflicts"]
    assert browser.initial_filters.severities == frozenset({"error"})
    assert browser.filters.severities == frozenset({"error"})
    assert list(first_view.source_rows) == [1, 3]
    assert first_view.selected_visible_row == 0

    browser.set_filters(
        FindingFilters(frozenset({"error", "warning", "info"})),
        selected_source_row=3,
    )

    qtbot.waitUntil(lambda: len(views) == 2 and not browser.busy)
    second_view = views[-1]
    assert list(second_view.source_rows) == [1, 3, 2, 0]
    assert second_view.selected_visible_row == 1

    browser.dispose()


def test_browser_uses_prepared_buckets_for_initial_default_not_summary_counts(
    qtbot: Any,
) -> None:
    browser, views = _browser_with_views()

    browser.set_report(_report_with_conflicting_summary())

    _wait_for_applied_views(qtbot, browser, views, 1)
    assert browser.initial_filters.severities == frozenset({"error"})
    assert browser.filters.severities == frozenset({"error"})
    assert list(views[0].source_rows) == [1, 3]


def test_browser_preserves_explicit_filter_request_made_during_preparation(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, views = _forced_browser_with_views(monkeypatch)
    report = _report_with_conflicting_summary()

    browser.set_report(report)
    browser.set_filters(
        FindingFilters(frozenset({"error", "warning", "info"})),
        selected_source_row=3,
    )

    _wait_for_applied_views(qtbot, browser, views, 1)
    assert browser.initial_filters.severities == frozenset({"error"})
    assert browser.filters.severities == frozenset({"error", "warning", "info"})
    assert list(views[0].source_rows) == [1, 3, 2, 0]
    assert views[0].selected_visible_row == 1


def test_browser_reset_filters_clears_non_severity_constraints_immediately(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, views = _forced_browser_with_views(monkeypatch)

    browser.set_report(make_triage_report())
    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            package_id="example.c",
            query="Shared",
            finding_type="def",
        )
    )

    browser.reset_filters()

    assert browser.filters == FindingFilters(frozenset({"error", "warning", "info"}))
    _wait_for_applied_views(qtbot, browser, views, 1)
    assert browser.initial_filters.severities == frozenset({"error"})
    assert browser.filters == FindingFilters(frozenset({"error"}))
    assert list(views[0].source_rows) == [1, 3]


def test_browser_reset_filters_uses_existing_default_after_preparation(
    qtbot: Any,
) -> None:
    browser, views = _browser_with_views()

    browser.set_report(_report_with_conflicting_summary())
    _wait_for_applied_views(qtbot, browser, views, 1)

    browser.set_filters(
        FindingFilters(
            frozenset({"warning"}),
            package_id="example.b",
            query="Other",
        )
    )
    _wait_for_applied_views(qtbot, browser, views, 2)

    browser.reset_filters()

    _wait_for_applied_views(qtbot, browser, views, 3)
    assert browser.filters == FindingFilters(frozenset({"error"}))
    assert list(views[-1].source_rows) == [1, 3]


def test_browser_reset_filters_yields_to_later_explicit_request_reusing_same_dto(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, views = _forced_browser_with_views(monkeypatch)
    explicit_filters = FindingFilters(frozenset({"warning"}), query="Other")

    browser.set_report(make_triage_report())
    browser.set_filters(explicit_filters)
    browser.reset_filters()
    browser.set_filters(explicit_filters)

    _wait_for_applied_views(qtbot, browser, views, 1)
    assert browser.filters is explicit_filters
    assert list(views[0].source_rows) == [2]


def test_browser_reset_filters_does_not_restart_preparation(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    force_one_row_per_tick(monkeypatch)
    browser = ConflictReportBrowser()

    browser.set_report(make_triage_report())
    qtbot.waitUntil(lambda: browser._prepare_index > 0)
    prepare_index_before_reset = browser._prepare_index

    browser.reset_filters()

    assert browser._prepare_index == prepare_index_before_reset
    qtbot.waitUntil(lambda: not browser.busy)


def test_browser_reset_filters_is_invalidated_by_report_replacement(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, views = _forced_browser_with_views(monkeypatch)

    browser.set_report(make_triage_report())
    browser.reset_filters()
    browser.set_report(make_triage_report_with_counts(0, 1, 1))

    _wait_for_applied_views(qtbot, browser, views, 1)
    assert browser.initial_filters.severities == frozenset({"warning"})
    assert browser.filters == FindingFilters(frozenset({"warning"}))
    assert list(views[0].source_rows) == [1]


def test_browser_reset_filters_dispose_prevents_publication(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, views = _forced_browser_with_views(monkeypatch)

    browser.set_report(make_triage_report())
    browser.reset_filters()
    browser.dispose()

    qtbot.waitUntil(lambda: not browser.busy)
    assert views == []


def test_browser_reentrant_filter_request_from_applied_stays_busy_until_latest_view(
    qtbot: Any,
) -> None:
    browser = ConflictReportBrowser()
    events: list[tuple[str, object]] = []

    def on_busy_changed(busy: bool) -> None:
        events.append(("busy", busy))

    def on_applied(view: Any) -> None:
        rows = list(view.source_rows)
        events.append(("applied", rows))
        if rows == [1, 3]:
            browser.set_filters(FindingFilters(frozenset({"warning"})))
            events.append(("requested", list(browser.filters.severities)))

    browser.busy_changed.connect(on_busy_changed)
    browser.applied.connect(on_applied)

    browser.set_report(make_triage_report())

    qtbot.waitUntil(
        lambda: (
            sum(1 for kind, _ in events if kind == "applied") == 2 and not browser.busy
        )
    )
    assert [value for kind, value in events if kind == "applied"] == [[1, 3], [2]]
    false_index = events.index(("busy", False))
    second_applied_index = next(
        index for index, event in enumerate(events) if event == ("applied", [2])
    )
    assert false_index > second_applied_index


def test_browser_prepared_callback_report_replacement_never_publishes_old_rows(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    force_one_row_per_tick(monkeypatch)
    browser = ConflictReportBrowser()
    first_report = make_triage_report()
    second_report = make_triage_report_with_counts(0, 1, 1)
    publications: list[list[int]] = []
    replaced: list[bool] = []

    def replace_report() -> None:
        if not replaced:
            replaced.append(True)
            browser.set_report(second_report)

    browser.prepared.connect(replace_report)
    browser.applied.connect(lambda view: publications.append(list(view.source_rows)))

    browser.set_report(first_report)

    qtbot.waitUntil(lambda: len(publications) == 1 and not browser.busy)
    assert publications == [[1]]
    assert browser.conflicts is second_report["conflicts"]


def test_browser_prepared_callback_dispose_prevents_publication(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    force_one_row_per_tick(monkeypatch)
    browser = ConflictReportBrowser()
    publications: list[list[int]] = []
    browser.prepared.connect(browser.dispose)
    browser.applied.connect(lambda view: publications.append(list(view.source_rows)))

    browser.set_report(make_triage_report())

    qtbot.waitUntil(lambda: not browser.busy)
    assert publications == []


def test_browser_publishes_compact_rows_without_iterating_buffer(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models import conflict_report

    monkeypatch.setattr(conflict_report, "array", NonIterablePublishedRows)
    browser = ConflictReportBrowser()
    views: list[Any] = []
    browser.applied.connect(views.append)

    browser.set_report(make_triage_report())

    qtbot.waitUntil(lambda: len(views) == 1 and not browser.busy)
    published_rows = views[0].source_rows
    assert isinstance(published_rows, NonIterablePublishedRows)
    assert published_rows.typecode == "Q"
    assert _row_values(published_rows) == [1, 3]


def test_browser_published_compact_rows_remain_unchanged_after_later_requests(
    qtbot: Any,
) -> None:
    browser = ConflictReportBrowser()
    views: list[Any] = []
    browser.applied.connect(views.append)
    second_report = make_triage_report_with_counts(0, 1, 1)

    browser.set_report(make_triage_report())

    qtbot.waitUntil(lambda: len(views) == 1 and not browser.busy)
    first_rows = views[0].source_rows
    assert isinstance(first_rows, array)
    assert getattr(first_rows, "typecode", None) == "Q"
    assert _row_values(first_rows) == [1, 3]

    browser.set_filters(
        FindingFilters(frozenset({"error", "warning", "info"})),
        selected_source_row=3,
    )

    qtbot.waitUntil(lambda: len(views) == 2 and not browser.busy)
    second_rows = views[1].source_rows
    assert second_rows is not first_rows
    assert _row_values(second_rows) == [1, 3, 2, 0]
    assert _row_values(first_rows) == [1, 3]

    browser.set_report(second_report)

    qtbot.waitUntil(lambda: len(views) == 3 and not browser.busy)
    assert _row_values(views[2].source_rows) == [1]
    browser.dispose()
    assert _row_values(first_rows) == [1, 3]


def test_browser_combined_filter_counts_distinct_participating_mods(
    qtbot: Any,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    browser = ConflictReportBrowser(parent)
    applied: list[Any] = []
    browser.applied.connect(applied.append)

    browser.set_report(make_triage_report())
    qtbot.waitUntil(lambda: len(applied) == 1 and not browser.busy)

    browser.set_filters(FindingFilters(frozenset({"error"}), package_id="example.b"))

    qtbot.waitUntil(lambda: len(applied) == 2 and not browser.busy)
    assert list(applied[-1].source_rows) == [1]

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            package_id="example.c",
            query="PAWN",
            finding_type="harmony",
        )
    )

    qtbot.waitUntil(lambda: len(applied) == 3 and not browser.busy)
    assert list(applied[-1].source_rows) == [3]
    assert [(m.package_id, m.error, m.warning, m.info) for m in browser.mods] == [
        ("example.a", 2, 0, 1),
        ("example.b", 1, 1, 1),
        ("example.c", 1, 1, 0),
    ]


def test_browser_query_uses_literal_unstripped_target_and_participant_search_only(
    qtbot: Any,
) -> None:
    browser = ConflictReportBrowser()
    views: list[Any] = []
    report = make_triage_report()
    report["conflicts"][0]["mods"][0]["name"] = "Mód <猫>"
    browser.applied.connect(views.append)

    browser.set_report(report)
    qtbot.waitUntil(lambda: len(views) == 1 and not browser.busy)

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            query="example.B",
            finding_type="def",
        )
    )
    qtbot.waitUntil(lambda: len(views) == 2 and not browser.busy)
    assert list(views[-1].source_rows) == [1, 2, 0]

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            query="Verse.Pawn.Tick",
            finding_type="harmony",
        )
    )
    qtbot.waitUntil(lambda: len(views) == 3 and not browser.busy)
    assert list(views[-1].source_rows) == [3]

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            query="Verse.Pawn.Tick ",
            finding_type="harmony",
        )
    )
    qtbot.waitUntil(lambda: len(views) == 4 and not browser.busy)
    assert list(views[-1].source_rows) == []

    browser.set_filters(
        FindingFilters(frozenset({"error", "warning", "info"}), query="label")
    )
    qtbot.waitUntil(lambda: len(views) == 5 and not browser.busy)
    assert list(views[-1].source_rows) == []

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            query="mÓd <猫>",
        )
    )
    qtbot.waitUntil(lambda: len(views) == 6 and not browser.busy)
    assert list(views[-1].source_rows) == [1, 3, 0]


def _assert_browser_searches_duplicate_participant_name(
    qtbot: Any,
    *,
    finding_type: str,
    source_row: int,
) -> None:
    from app.services.conflict_detector_worker import _conflict_valid

    browser = ConflictReportBrowser()
    views: list[Any] = []
    report = make_triage_report_with_duplicate_participant_names(finding_type)
    browser.applied.connect(views.append)

    if finding_type == "def":
        assert (
            report["conflicts"][0]["mods"][0] is not report["conflicts"][0]["mods"][1]
        )
    else:
        patches = report["conflicts"][3]["patches"]
        assert patches[0]["mod_summary"] is not patches[1]["mod_summary"]
    assert _conflict_valid(report["conflicts"][source_row])

    browser.set_report(report)
    qtbot.waitUntil(lambda: len(views) == 1 and not browser.busy)

    browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            query="Alias Bloom",
            finding_type=finding_type,
        )
    )

    qtbot.waitUntil(lambda: len(views) == 2 and not browser.busy)
    assert list(views[-1].source_rows) == [source_row]
    example_a = next(mod for mod in browser.mods if mod.package_id == "example.a")
    assert (example_a.error, example_a.warning, example_a.info) == (2, 0, 1)


def test_browser_searches_every_captured_def_participant_name(
    qtbot: Any,
) -> None:
    _assert_browser_searches_duplicate_participant_name(
        qtbot,
        finding_type="def",
        source_row=0,
    )


def test_browser_searches_every_captured_harmony_participant_name(
    qtbot: Any,
) -> None:
    _assert_browser_searches_duplicate_participant_name(
        qtbot,
        finding_type="harmony",
        source_row=3,
    )


def test_empty_string_package_id_filter_is_not_the_all_mods_sentinel(
    qtbot: Any,
) -> None:
    browser = ConflictReportBrowser()
    views: list[Any] = []
    report = make_triage_report()
    report["conflicts"][2]["mods"][1]["package_id"] = ""
    report["conflicts"][2]["mods"][1]["name"] = "Empty ID"
    report["conflicts"][3]["patches"][2]["mod_summary"]["package_id"] = ""
    report["conflicts"][3]["patches"][2]["mod_summary"]["name"] = "Empty ID"
    browser.applied.connect(views.append)

    browser.set_report(report)
    qtbot.waitUntil(lambda: len(views) == 1 and not browser.busy)

    expected_view_count = len(views) + 1
    browser.set_filters(
        FindingFilters(frozenset({"error", "warning", "info"}), package_id="")
    )

    qtbot.waitUntil(lambda: len(views) == expected_view_count and not browser.busy)
    latest_rows = views[-1].source_rows
    assert [int(latest_rows[index]) for index in range(len(latest_rows))] == [3, 2]
    assert browser.mods[-1].package_id == ""
    assert browser.mods[-1].name == "Empty ID"


def test_conflict_table_model_maps_visible_rows_to_source_findings() -> None:
    report = make_triage_report()
    model = ConflictTableModel()
    model.set_rows(report["conflicts"], (1, 3))

    assert model.columnCount() == 3
    assert model.source_row(model.index(0, 0)) == 1
    assert model.finding(model.index(1, 0)) is report["conflicts"][3]
    assert model.index(0, 0).data() == "Error"
    assert model.index(0, 1).data() == "ThingDef: Shared — Direct replacement"
    assert model.index(1, 1).data() == "Verse.Pawn.Tick — Harmony"
    assert model.index(1, 2).data() == "A, A, C"


def test_table_model_labels_are_extracted_for_translation(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "app/models/conflict_report.py"
    messages = extract_context_sources(
        tmp_path,
        source,
        "conflict-report-model.ts",
        "ConflictTableModel",
    )
    expected = {
        "Severity",
        "Target / mechanism",
        "Involved mods",
        "Error",
        "Warning",
        "Info",
        "Harmony",
        "Direct replacement",
        "XPath overlap",
        "XPath on replaced Def",
        "Non-overlapping XPath edits",
    }
    assert expected <= messages, expected - messages
