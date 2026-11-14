from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QModelIndex, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QDropEvent
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveSet,
    CaseInsensitiveStr,
)
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.custom_list_widget_item import CustomListWidgetItem
from app.utils.custom_list_widget_item_metadata import CustomListWidgetItemMetadata
from app.views.mods_panel import (
    ModListIcons,
    ModListItemInner,
    ModListWidget,
    TagEditDialog,
)


def _make_mod(name: str, path: str, package_id: str) -> AboutXmlMod:
    return AboutXmlMod(
        name=name,
        _mod_path=Path(path),
        package_id=CaseInsensitiveStr(package_id),
    )


def _make_active_mod_list(
    qtbot: Any,
    mods: dict[str, AboutXmlMod],
    paths: list[str],
) -> ModListWidget:
    settings = MagicMock(spec=Settings)
    settings.external_use_this_instead_metadata_source = "None"
    settings.show_save_comparison_indicators = False
    settings.mod_list_updated_indicator = False
    settings.mod_list_startup_impact = False
    settings.use_alternative_package_ids_as_satisfying_dependencies = False

    metadata_controller = MagicMock()
    metadata_controller.mods_metadata = mods
    metadata_controller.settings = settings
    metadata_controller.is_version_mismatch.return_value = False
    metadata_controller.is_soft_version_mismatch.return_value = False
    metadata_controller.steamdb_packageid_to_name = {}

    widget = ModListWidget.__new__(ModListWidget)
    QListWidget.__init__(widget)
    qtbot.addWidget(widget)
    widget.list_type = "Active"
    widget.settings = settings
    widget.metadata_controller = metadata_controller
    widget.paths = paths
    widget.ignore_warning_list = []

    for path in paths:
        item_data = object.__new__(CustomListWidgetItemMetadata)
        item_data.path = path
        item_data.warning_toggled = False
        item_data.alternative = None
        item_data.errors = ""
        item_data.warnings = ""
        item_data.errors_warnings = ""

        item = CustomListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, item_data, avoid_emit=True)
        widget.addItem(item)

    return widget


class TestTagEditDialog:
    """Test suite for the TagEditDialog dialog."""

    @pytest.fixture
    def dialog(self, qtbot: Any) -> TagEditDialog:
        """
        Create a TagEditDialog instance for testing.

        :param qtbot: Pytest-Qt bot for widget testing.
        :return: A mock TagEditDialog instance for testing.
        """
        with patch(
            "app.views.mods_panel.auxdb_get_all_tags",
            return_value={"a", "aa", "b", "bb", "c", "cc"},
        ):
            dialog = TagEditDialog(
                title="Test Dialog",
                settings=MagicMock(spec=Settings),
                existing_selected_tags={"a", "aa", "b", "bb"},
            )
            qtbot.addWidget(dialog)
            assert dialog.tags_list.count() == 6
            assert len(dialog.tags_list.selectedItems()) == 4
            return dialog

    @staticmethod
    def _get_tags(widget: QListWidget) -> list[QListWidgetItem]:
        """
        Get tags from the widget as a list to iterate over.

        :return: A list of tag items.
        """
        return [widget.item(i) for i in range(widget.count())]

    def test_insert_new_tag(self, dialog: TagEditDialog) -> None:
        """
        Test inserting a new tag.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("dd,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("dd", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "dd"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("c", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "c"
        assert item.isSelected() is False
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_update_existing_tag_already_selected(self, dialog: TagEditDialog) -> None:
        """
        Test updating an existing tag that is already selected.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("a,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is False
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("aa", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "aa"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("c", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "c"
        assert item.isSelected() is False
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_update_existing_tag_not_already_selected(
        self, dialog: TagEditDialog
    ) -> None:
        """
        Test updating an existing tag that is not already selected.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("cc,")

        # jscpd:ignore-start
        found_items = dialog.tags_list.findItems("cc", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "cc"
        assert item.isSelected() is True
        assert item.isHidden() is False

        found_items = dialog.tags_list.findItems("a", Qt.MatchFlag.MatchExactly)
        assert len(found_items) == 1
        item = found_items[0]
        assert item.text() == "a"
        assert item.isSelected() is True
        assert item.isHidden() is False
        # jscpd:ignore-end

    def test_select_all_and_none(self, dialog: TagEditDialog) -> None:
        """
        Test selecting all tags and selecting none of the tags.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.select_all()
        assert all(tag.isSelected() is True for tag in self._get_tags(dialog.tags_list))

        dialog.select_none()
        assert all(
            tag.isSelected() is False for tag in self._get_tags(dialog.tags_list)
        )

    def test_filter_tags(self, dialog: TagEditDialog) -> None:
        """
        Test filtering tags based on user input.

        :param dialog: The TagEditDialog instance to test.
        """
        dialog.tags_text_input.setText("a")
        assert all(
            tag.isHidden() is ("a" not in tag.text())
            for tag in self._get_tags(dialog.tags_list)
        )

        dialog.tags_text_input.setText("aa")
        assert all(
            tag.isHidden() is ("aa" not in tag.text())
            for tag in self._get_tags(dialog.tags_list)
        )

        dialog.tags_text_input.clear()
        assert all(tag.isHidden() is False for tag in self._get_tags(dialog.tags_list))

        dialog.tags_text_input.setText("d")
        assert all(tag.isHidden() is True for tag in self._get_tags(dialog.tags_list))


@pytest.mark.parametrize(
    ("rule_name", "paths", "expected_header", "unexpected_header"),
    [
        (
            "load_before",
            ["/mods/b", "/mods/a"],
            "Should be Loaded Before:",
            "Should be Loaded After:",
        ),
        (
            "load_after",
            ["/mods/a", "/mods/b"],
            "Should be Loaded After:",
            "Should be Loaded Before:",
        ),
    ],
)
def test_load_order_warning_header_matches_rule_direction(
    qtbot: Any,
    rule_name: str,
    paths: list[str],
    expected_header: str,
    unexpected_header: str,
) -> None:
    mod_a = _make_mod("Alpha", "/mods/a", "mod.a")
    mod_b = _make_mod("Beta", "/mods/b", "mod.b")
    setattr(mod_a.about_rules, rule_name, CaseInsensitiveSet(["mod.b"]))
    widget = _make_active_mod_list(
        qtbot,
        {"/mods/a": mod_a, "/mods/b": mod_b},
        paths,
    )

    widget.recalculate_internal_errors_warnings()

    item = widget.item(paths.index("/mods/a"))
    assert item is not None
    warning = item.data(Qt.ItemDataRole.UserRole).warnings
    assert expected_header in warning
    assert "* Beta" in warning
    assert unexpected_header not in warning


def test_rows_inserted_converts_plain_dropped_item(qtbot: Any) -> None:
    """A plain QListWidgetItem inserted into the list must be replaced by a
    CustomListWidgetItem carrying the same data and flags."""
    widget = _make_active_mod_list(qtbot, {}, [])
    data = object.__new__(CustomListWidgetItemMetadata)
    data.path = "/mods/dropped"
    data.list_type = "Inactive"
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled
    plain = QListWidgetItem("Dropped")
    plain.setData(Qt.ItemDataRole.UserRole, data)
    plain.setFlags(flags)
    widget.addItem(plain)

    widget.handle_rows_inserted(QModelIndex(), 0, 0)

    item = widget.item(0)
    assert isinstance(item, CustomListWidgetItem)
    assert item.data(Qt.ItemDataRole.UserRole) is data
    assert item.text() == "Dropped"
    assert item.flags() == flags
    assert data.list_type == "Active"
    assert widget.paths == ["/mods/dropped"]


@pytest.mark.parametrize("action", [Qt.DropAction.MoveAction, Qt.DropAction.CopyAction])
def test_cross_list_drop_keeps_item_data(qtbot: Any, action: Qt.DropAction) -> None:
    """Mods dropped onto the other list must keep their metadata and order
    and be tracked there; a copy must not share metadata with the source."""
    paths = ["/mods/a", "/mods/b"]
    source = _make_active_mod_list(qtbot, {}, list(paths))
    source.list_type = "Inactive"
    source_data = [source.item(row).data(Qt.ItemDataRole.UserRole) for row in range(2)]
    for data in source_data:
        data.list_type = "Inactive"
    target = _make_active_mod_list(qtbot, {}, [])
    target.model().rowsInserted.connect(
        target.handle_rows_inserted, Qt.ConnectionType.QueuedConnection
    )
    target.resize(200, 200)
    target.show()

    mime = source.model().mimeData([source.model().index(row, 0) for row in range(2)])
    event = QDropEvent(
        QPointF(10, 10),
        action,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    target.dropEvent(event)
    qtbot.waitUntil(lambda: target.paths == paths)

    for row, data in enumerate(source_data):
        item = target.item(row)
        assert isinstance(item, CustomListWidgetItem)
        dropped = item.data(Qt.ItemDataRole.UserRole)
        assert dropped.path == paths[row]
        assert dropped.list_type == "Active"
        if action == Qt.DropAction.MoveAction:
            assert dropped is data
        else:
            assert dropped is not data
            assert data.list_type == "Inactive"


class TestStartupImpactLabel:
    """The startup impact label on mod list items, driven via repolish."""

    @pytest.fixture
    def widget(self, qtbot: Any) -> ModListItemInner:
        settings = MagicMock(spec=Settings)
        settings.mod_type_filter = False
        settings.show_save_comparison_indicators = False
        settings.mod_list_updated_indicator = False
        settings.mod_list_startup_impact = True
        metadata_controller = MagicMock()
        metadata_controller.get_mod.return_value = None
        with patch("app.views.mods_panel.auxdb_get_mod_tags", return_value=[]):
            widget = ModListItemInner(
                errors_warnings="",
                errors="",
                warnings="",
                filtered=False,
                invalid=False,
                mismatch=False,
                alternative=False,
                settings=settings,
                path="/mods/test",
                mod_color=None,  # type: ignore[arg-type]
                metadata_controller=metadata_controller,
            )
        qtbot.addWidget(widget)
        return widget

    @staticmethod
    def _item(
        startup_impact_s: float | None, tooltip: str = ""
    ) -> CustomListWidgetItem:
        """Build an item whose metadata carries only what repolish reads."""
        data = object.__new__(CustomListWidgetItemMetadata)
        data.errors = ""
        data.warnings = ""
        data.mod_tags = []
        data.mod_color = None
        data.filtered = False
        data.list_type = "Active"
        data.startup_impact_s = startup_impact_s
        data.startup_impact_tooltip = tooltip
        item = CustomListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, data)
        return item

    def test_label_shown_with_impact(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(0.42, "Startup impact: 420ms"))

        assert not widget.startup_impact_label.isHidden()
        assert widget.startup_impact_label.text() == "420ms"
        assert widget.startup_impact_label.toolTip() == "Startup impact: 420ms"
        # below the warn threshold: green
        assert "#5cb85c" in widget.startup_impact_label.styleSheet()

    def test_label_placed_after_warning_and_error_icons(
        self, widget: ModListItemInner
    ) -> None:
        layout = widget.main_item_layout
        indices = {
            item.widget(): i
            for i in range(layout.count())
            if (item := layout.itemAt(i)) is not None and item.widget() is not None
        }
        # the updated icon (when enabled) is added before these two, so being
        # after warning/error also puts the label after the updated icon
        impact_index = indices[widget.startup_impact_label]
        assert impact_index > indices[widget.warning_icon_label]
        assert impact_index > indices[widget.error_icon_label]

    def test_label_color_thresholds(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(1.5))
        assert "#f0ad4e" in widget.startup_impact_label.styleSheet()

        widget.repolish(self._item(7.2))
        assert "#d9534f" in widget.startup_impact_label.styleSheet()

    def test_label_hidden_without_impact(self, widget: ModListItemInner) -> None:
        widget.repolish(self._item(2.34))
        widget.repolish(self._item(None))

        assert widget.startup_impact_label.isHidden()
        assert widget.startup_impact_label.text() == ""

    def test_label_hidden_when_setting_disabled(self, widget: ModListItemInner) -> None:
        widget.settings.mod_list_startup_impact = False
        widget.repolish(self._item(2.34))

        assert widget.startup_impact_label.isHidden()


@pytest.mark.parametrize("soft", [True, False])
def test_version_mismatch_soft_flag_and_stub_line(qtbot: Any, soft: bool) -> None:
    mod_a = _make_mod("Alpha", "/mods/a", "mod.a")
    widget = _make_active_mod_list(qtbot, {"/mods/a": mod_a}, ["/mods/a"])
    controller: Any = widget.metadata_controller
    controller.is_version_mismatch.return_value = True
    controller.is_soft_version_mismatch.return_value = soft

    widget.recalculate_internal_errors_warnings()

    item = widget.item(0)
    assert item is not None
    data = item.data(Qt.ItemDataRole.UserRole)
    assert data.__dict__["soft_warning"] is soft
    assert "Mod and Game Version Mismatch" in data.warnings
    stub_line = "Waylith provides compatibility stubs for 1.6"
    assert (stub_line in data.warnings) is soft


def test_warning_icon_selects_grayscale_variant_for_soft_warning(qtbot: Any) -> None:
    assert ModListItemInner._warning_icon_for(True) is ModListIcons.soft_warning_icon()
    assert ModListItemInner._warning_icon_for(False) is ModListIcons.warning_icon()


@pytest.fixture
def real_warning_icons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ModListIcons at the real warning.png and reset its cache.

    The icon path is computed from AppInfo at import time, which the test
    fixtures redirect elsewhere, so pixmaps would otherwise load as null.
    """
    theme_icon = Path(__file__).resolve().parents[2] / "themes" / "default-icons"
    monkeypatch.setattr(
        ModListIcons, "_warning_icon_path", str(theme_icon / "warning.png")
    )
    monkeypatch.setattr(ModListIcons, "_warning_icon", None)
    monkeypatch.setattr(ModListIcons, "_soft_warning_icon", None)


@pytest.mark.usefixtures("real_warning_icons")
def test_soft_warning_icon_is_grayscale_and_keeps_transparency(qtbot: Any) -> None:
    source = ModListIcons.warning_icon().pixmap(QSize(20, 20)).toImage()
    soft = ModListIcons.soft_warning_icon().pixmap(QSize(20, 20)).toImage()
    assert not source.isNull()
    assert soft.size() == source.size()
    brightest = 0
    for y in range(soft.height()):
        for x in range(soft.width()):
            soft_color = QColor.fromRgba(soft.pixel(x, y))
            source_color = QColor.fromRgba(source.pixel(x, y))
            assert soft_color.red() == soft_color.green() == soft_color.blue()
            assert soft_color.alpha() == source_color.alpha()
            brightest = max(brightest, soft_color.red())
    # The yellow fill (luma ~227) must be dimmed, not left at full brightness
    assert brightest > 0
    assert brightest <= 140


@pytest.mark.usefixtures("real_warning_icons")
def test_repolish_soft_warning_uses_dimmed_icon_and_soft_label(qtbot: Any) -> None:
    widget = _make_item_inner(qtbot, soft_warning=False)
    item = _make_item_for_repolish(
        {"errors": "", "warnings": "Mod and Game Version Mismatch", "soft": True}
    )

    widget.repolish(item)

    assert widget.main_label.objectName() == "ListItemLabelSoftWarning"
    assert (
        widget.warning_icon_label.pixmap().toImage()
        == ModListIcons.soft_warning_icon().pixmap(QSize(20, 20)).toImage()
    )
    assert (
        widget.warning_icon_label.pixmap().toImage()
        != ModListIcons.warning_icon().pixmap(QSize(20, 20)).toImage()
    )


@pytest.mark.usefixtures("real_warning_icons")
def test_repolish_soft_warning_with_errors_stays_invalid(qtbot: Any) -> None:
    widget = _make_item_inner(qtbot, soft_warning=False)
    item = _make_item_for_repolish(
        {"errors": "Missing Dependencies", "warnings": "x", "soft": True}
    )

    widget.repolish(item)

    # The name stays red because of the hard error; the warning icon is still
    # the soft one since the mismatch is the only warning on this mod.
    assert widget.main_label.objectName() == "ListItemLabelInvalid"
    assert (
        widget.warning_icon_label.pixmap().toImage()
        == ModListIcons.soft_warning_icon().pixmap(QSize(20, 20)).toImage()
    )


def _make_item_for_repolish(spec: dict[str, Any]) -> CustomListWidgetItem:
    data = object.__new__(CustomListWidgetItemMetadata)
    data.errors = spec["errors"]
    data.warnings = spec["warnings"]
    data.errors_warnings = spec["errors"] or spec["warnings"]
    data.mod_tags = []
    data.mod_color = None
    data.filtered = False
    data.path = "/mods/a"
    data.__dict__["soft_warning"] = spec["soft"]
    item = CustomListWidgetItem()
    item.setData(Qt.ItemDataRole.UserRole, data, avoid_emit=True)
    return item


def _make_item_inner(
    qtbot: Any, soft_warning: bool, errors: str = "", show_tags: bool = False
) -> ModListItemInner:
    controller: Any = MagicMock()
    controller.get_mod.return_value = None
    controller.steamdb_packageid_to_name = {}
    settings = MagicMock(spec=Settings)
    settings.mod_type_filter = False
    settings.mod_list_startup_impact = False
    settings.show_save_comparison_indicators = False
    settings.mod_list_updated_indicator = False
    settings.mod_list_updated_threshold_days = 0
    settings.external_use_this_instead_metadata_source = "None"
    settings.aux_db_path = str(AppInfo().databases_folder / "aux_metadata.db")
    # Item data carries mod_color=None when no custom color is set
    kwargs: dict[str, Any] = {
        "errors_warnings": "x",
        "errors": errors,
        "warnings": "x",
        "filtered": False,
        "invalid": False,
        "mismatch": True,
        "alternative": False,
        "settings": settings,
        "path": "/mods/a",
        "mod_color": None,
        "metadata_controller": controller,
        "soft_warning": soft_warning,
        "show_tags": show_tags,
    }
    widget = ModListItemInner(**kwargs)
    qtbot.addWidget(widget)
    return widget


def test_soft_warning_not_applied_when_load_order_warning_present(qtbot: Any) -> None:
    mod_a = _make_mod("Alpha", "/mods/a", "mod.a")
    mod_b = _make_mod("Beta", "/mods/b", "mod.b")
    mod_a.about_rules.load_before = CaseInsensitiveSet(["mod.b"])
    widget = _make_active_mod_list(
        qtbot, {"/mods/a": mod_a, "/mods/b": mod_b}, ["/mods/b", "/mods/a"]
    )
    controller: Any = widget.metadata_controller
    controller.is_version_mismatch.return_value = True
    controller.is_soft_version_mismatch.return_value = True

    widget.recalculate_internal_errors_warnings()

    item = widget.item(1)
    assert item is not None
    data = item.data(Qt.ItemDataRole.UserRole)
    assert "Should be Loaded Before:" in data.warnings
    assert data.__dict__["soft_warning"] is False


def test_soft_warning_label_uses_soft_object_name(qtbot: Any) -> None:
    soft = _make_item_inner(qtbot, soft_warning=True)
    assert soft.main_label.objectName() == "ListItemLabelSoftWarning"

    hard = _make_item_inner(qtbot, soft_warning=False)
    assert hard.main_label.objectName() == "ListItemLabelInvalid"

    with_errors = _make_item_inner(qtbot, soft_warning=True, errors="missing dep")
    assert with_errors.main_label.objectName() == "ListItemLabelInvalid"


def test_tags_label_not_separate_window(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for #2651: the tags label should not be visible as its own window."""
    monkeypatch.setattr(
        "app.views.mods_panel.auxdb_get_mod_tags", lambda *_args, **_kwargs: ["qol"]
    )
    floated_after_update: list[bool] = []
    real_update_tags_label = ModListItemInner.update_tags_label

    def update_then_check_label(
        self: ModListItemInner, tags: list[str] | None = None
    ) -> None:
        real_update_tags_label(self, tags)
        label = self.mod_tags_label
        floated_after_update.append(label.isWindow() and not label.isHidden())

    monkeypatch.setattr(ModListItemInner, "update_tags_label", update_then_check_label)

    widget = _make_item_inner(qtbot, soft_warning=False, show_tags=True)

    assert floated_after_update, "update_tags_label() never ran during construction"
    assert not any(floated_after_update)
    assert not widget.mod_tags_label.isHidden()
