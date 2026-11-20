"""Structured inspector for a selected conflict finding."""

import json
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.conflict_report import (
    NoteRef,
    ScanNotesModel,
    _note_source_text,
    safe_text,
)
from app.services.conflict_snapshot import InputIssue, ScanSnapshot


class ScanNotesView(QWidget):
    def __init__(
        self,
        format_diagnostic: Callable[[dict[str, Any]], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._format_diagnostic = format_diagnostic
        self._disposed = False
        self._selected: NoteRef | None = None
        self.model = ScanNotesModel(format_diagnostic, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.selectionModel().currentRowChanged.connect(self._select_note)
        self.model.modelAboutToBeReset.connect(self._model_resetting)
        self.show_info = QCheckBox(self.tr("Show ordinary information"))
        self.show_info.toggled.connect(self.model.set_show_info)
        self.updating_label = QLabel(self.tr("Preparing scan notes…"))
        self.updating_label.setVisible(False)
        self.details_view = QPlainTextEdit()
        self.details_view.setReadOnly(True)
        self.raw_button = QToolButton()
        self.raw_button.setCheckable(True)
        self.raw_button.setText(self.tr("Show raw note data"))
        self.raw_button.setEnabled(False)
        self.raw_button.toggled.connect(self._toggle_raw)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setVisible(False)
        layout = QVBoxLayout(self)
        layout.addWidget(self.show_info)
        layout.addWidget(self.updating_label)
        layout.addWidget(self.table)
        layout.addWidget(self.details_view)
        layout.addWidget(self.raw_button)
        layout.addWidget(self.raw_view)
        self.model.busy_changed.connect(self._busy_changed)

    def set_notes(
        self, snapshot: ScanSnapshot, diagnostics: list[dict[str, Any]], error: str = ""
    ) -> None:
        if not self._disposed:
            self.model.set_notes(snapshot, diagnostics, error)

    def dispose(self) -> None:
        if not self._disposed:
            self._disposed = True
            self.model.dispose()

    def _busy_changed(self, busy: bool) -> None:
        if self._disposed:
            return
        self.table.setEnabled(not busy)
        self.updating_label.setVisible(busy)
        if busy:
            self._clear_selection()

    def _model_resetting(self) -> None:
        if not self._disposed:
            self._clear_selection()

    def _clear_selection(self) -> None:
        self._selected = None
        self.details_view.clear()
        self.raw_button.blockSignals(True)
        self.raw_button.setChecked(False)
        self.raw_button.blockSignals(False)
        self.raw_button.setEnabled(False)
        self.raw_view.clear()
        self.raw_view.setVisible(False)

    def _select_note(self, current: Any, _previous: Any) -> None:
        if self._disposed:
            return
        self._clear_selection()
        if self.model.busy:
            return
        ref = self.model.note(current)
        if ref is None:
            return
        record = self.model._record(ref)
        self._selected = ref
        self.raw_button.setEnabled(True)
        if isinstance(record, dict):
            translate = QCoreApplication.translate
            severity = {
                "error": translate("ConflictReportDialog", "Error"),
                "warning": translate("ConflictReportDialog", "Warning"),
                "info": translate("ConflictReportDialog", "Info"),
            }[record["severity"]]
            message = self._format_diagnostic(record)
            affected = record.get("affected_mod")
            text = f"{severity} / {_note_source_text(record['source'])}: {message}"
            if affected:
                text += f" ({affected})"
            params = record.get("params")
            if record.get("code") == "load_folders_parse_failure" and isinstance(
                params, dict
            ):
                path = params.get("path")
                if isinstance(path, str):
                    path_label = self.tr("Path")
                    text += f"\n{path_label}: {path}"
        elif isinstance(record, InputIssue):
            text = f"{record.message}: {record.path}" if record.path else record.message
        else:
            text = str(record)
        self.details_view.setPlainText(safe_text(text))

    def _toggle_raw(self, checked: bool) -> None:
        if self._disposed:
            return
        if not checked or self._selected is None or self.model.busy:
            self.raw_view.clear()
            self.raw_view.setVisible(False)
            return
        record = self.model._record(self._selected)
        if isinstance(record, InputIssue):
            record = {"message": record.message, "path": record.path}
        self.raw_view.setPlainText(
            safe_text(json.dumps(record, ensure_ascii=False, indent=2))
        )
        self.raw_view.setVisible(True)


class FindingInspector(QWidget):
    mod_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._finding: dict[str, Any] | None = None
        self._generation = 0
        self._raw_revision = 0
        self._mod_actions_enabled = True
        self._mod_buttons: list[QPushButton] = []

        self._severity_label = self._make_text_label()
        self._target_label = self._make_text_label()
        self._mechanism_label = self._make_text_label()
        self._explanation_label = self._make_text_label()
        self.outcome_label = self._make_text_label()
        self.raw_button = QToolButton()
        self.raw_button.setCheckable(True)
        self.raw_button.toggled.connect(self._toggle_raw)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setVisible(False)
        self.raw_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.raw_view.setMinimumHeight(self.fontMetrics().lineSpacing() * 8)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self._content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Severity")
            )
        )
        content_layout.addWidget(self._severity_label)
        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Target")
            )
        )
        content_layout.addWidget(self._target_label)
        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Mechanism")
            )
        )
        content_layout.addWidget(self._mechanism_label)
        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Explanation")
            )
        )
        content_layout.addWidget(self._explanation_label)

        self._participants_label = self._make_section_label(
            QCoreApplication.translate("ConflictReportDialog", "Participant mods")
        )
        self._participants_widget = QWidget()
        self._participants_layout = QVBoxLayout(self._participants_widget)
        self._participants_layout.setContentsMargins(0, 0, 0, 0)
        self._participants_layout.setSpacing(8)
        content_layout.addWidget(self._participants_label)
        content_layout.addWidget(self._participants_widget)

        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Reported outcome")
            )
        )
        content_layout.addWidget(self.outcome_label)

        self.technical_button = QToolButton()
        self.technical_button.setCheckable(True)
        self.technical_button.setText(
            QCoreApplication.translate("ConflictReportDialog", "Technical details")
        )
        self.technical_button.setArrowType(Qt.ArrowType.RightArrow)
        self.technical_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.technical_button.toggled.connect(self._toggle_technical)
        content_layout.addWidget(self.technical_button)
        self._details_widget = QWidget()
        self._details_widget.setVisible(False)
        self._details_layout = QVBoxLayout(self._details_widget)
        self._details_layout.setContentsMargins(0, 0, 0, 0)
        self._details_layout.setSpacing(8)
        content_layout.addWidget(self._details_widget)
        content_layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Raw finding data")
            )
        )
        content_layout.addWidget(self.raw_button)
        content_layout.addWidget(self.raw_view)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._clear_summary()
        self._clear_outcome()
        self._clear_raw()
        self._update_raw_button_text(False)
        self.raw_button.setEnabled(False)
        self.technical_button.setEnabled(False)

    def set_finding(self, finding: dict[str, Any] | None) -> None:
        self._generation += 1
        generation = self._generation
        self._finding = finding
        participants, buttons = self._replace_dynamic_sections()
        if generation != self._generation:
            return
        self._clear_summary()
        self._clear_outcome()
        self._reset_technical()
        if generation != self._generation:
            return
        self._clear_raw()
        if generation != self._generation:
            return
        self.technical_button.setEnabled(finding is not None)
        self.raw_button.setEnabled(finding is not None)
        if finding is None:
            return
        self._populate_summary(finding)
        if finding["type"] == "def":
            self._populate_def(finding, participants, buttons, generation)
        else:
            self._populate_harmony(finding, participants, buttons, generation)

    def set_mod_actions_enabled(self, enabled: bool) -> None:
        self._mod_actions_enabled = enabled
        for button in self._mod_buttons:
            button.setEnabled(enabled)

    def _make_text_label(self) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        return label

    def _make_section_label(self, text: str) -> QLabel:
        label = self._make_text_label()
        label.setText(text)
        return label

    def _clear_summary(self) -> None:
        for label in (
            self._severity_label,
            self._target_label,
            self._mechanism_label,
            self._explanation_label,
        ):
            label.clear()

    def _replace_dynamic_sections(self) -> tuple[QVBoxLayout, list[QPushButton]]:
        old_participants = self._participants_widget
        old_details = self._details_widget
        participants_index = self._content_layout.indexOf(old_participants)
        details_index = self._content_layout.indexOf(old_details)
        participants = QWidget()
        participants_layout = QVBoxLayout(participants)
        participants_layout.setContentsMargins(0, 0, 0, 0)
        participants_layout.setSpacing(8)
        details = QWidget()
        details.setVisible(False)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        buttons: list[QPushButton] = []
        self._participants_widget = participants
        self._participants_layout = participants_layout
        self._details_widget = details
        self._details_layout = details_layout
        self._mod_buttons = buttons
        self._content_layout.removeWidget(old_participants)
        self._content_layout.insertWidget(participants_index, participants)
        self._content_layout.removeWidget(old_details)
        self._content_layout.insertWidget(details_index, details)
        for widget in (old_participants, old_details):
            widget.setEnabled(False)
            widget.hide()
            widget.deleteLater()
        return participants_layout, buttons

    def _clear_outcome(self) -> None:
        self.outcome_label.clear()

    def _clear_raw(self) -> None:
        generation = self._generation
        self._raw_revision += 1
        revision = self._raw_revision
        self.raw_button.blockSignals(True)
        self.raw_button.setChecked(False)
        self.raw_button.blockSignals(False)
        self.raw_view.clear()
        if generation != self._generation or revision != self._raw_revision:
            return
        self.raw_view.setVisible(False)
        if generation != self._generation or revision != self._raw_revision:
            return
        self._update_raw_button_text(False)

    def _populate_summary(self, finding: dict[str, Any]) -> None:
        self._severity_label.setText(self._severity_text(finding["severity"]))
        self._target_label.setText(self._target_summary(finding))
        self._mechanism_label.setText(self._mechanism_title(finding))
        self._explanation_label.setText(self._explanation_text(finding))

    def _populate_def(
        self,
        finding: dict[str, Any],
        layout: QVBoxLayout,
        buttons: list[QPushButton],
        generation: int,
    ) -> None:
        layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Mods")
            )
        )
        for mod in finding["mods"]:
            layout.addWidget(self._mod_button(mod, buttons, generation))
        if generation != self._generation:
            return
        self.outcome_label.setText(
            "\n".join(
                (
                    self._field_text(
                        QCoreApplication.translate("ConflictReportDialog", "Winner"),
                        finding["winner"],
                    ),
                    self._field_text(
                        QCoreApplication.translate("ConflictReportDialog", "Condition"),
                        finding["condition"],
                    ),
                )
            )
        )

    def _populate_def_details(
        self, finding: dict[str, Any], layout: QVBoxLayout
    ) -> None:
        for mod in finding["mods"]:
            layout.addWidget(self._mod_widget(mod))
        target = finding["target"]
        layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Target")
            )
        )
        layout.addWidget(
            self._field_label(
                QCoreApplication.translate("ConflictReportDialog", "Def type"),
                target["def_type"],
            )
        )
        layout.addWidget(
            self._field_label(
                QCoreApplication.translate("ConflictReportDialog", "Def name"),
                target["def_name"],
            )
        )
        layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Mechanism")
            )
        )
        layout.addWidget(
            self._field_label(
                QCoreApplication.translate("ConflictReportDialog", "Mechanism"),
                self._mechanism_title(finding),
            )
        )
        kind, body = next(iter(finding["mechanism"].items()))
        if kind == "direct_replacement":
            layout.addWidget(
                self._field_label(
                    QCoreApplication.translate(
                        "ConflictReportDialog", "Divergent fields"
                    ),
                    body["divergent_fields"],
                )
            )
            return
        if kind == "x_path_overlap":
            for label, key in (
                (
                    QCoreApplication.translate("ConflictReportDialog", "First XPath"),
                    "xpath_a",
                ),
                (
                    QCoreApplication.translate("ConflictReportDialog", "Second XPath"),
                    "xpath_b",
                ),
                (
                    QCoreApplication.translate("ConflictReportDialog", "Wildcard"),
                    "wildcard",
                ),
            ):
                layout.addWidget(self._field_label(label, body[key]))
            return
        if kind == "x_path_on_replaced_def":
            for label, key in (
                (
                    QCoreApplication.translate("ConflictReportDialog", "XPath"),
                    "xpath",
                ),
                (
                    QCoreApplication.translate("ConflictReportDialog", "Replaced by"),
                    "replaced_by",
                ),
            ):
                layout.addWidget(self._field_label(label, body[key]))
            return
        layout.addWidget(
            self._field_label(
                QCoreApplication.translate("ConflictReportDialog", "XPath pairs"),
                body["xpath_pairs"],
            )
        )

    def _populate_harmony(
        self,
        finding: dict[str, Any],
        layout: QVBoxLayout,
        buttons: list[QPushButton],
        generation: int,
    ) -> None:
        layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Patches")
            )
        )
        for patch in finding["patches"]:
            layout.addWidget(
                self._mod_button(patch["mod_summary"], buttons, generation)
            )
        if generation != self._generation:
            return
        self.outcome_label.setText(
            QCoreApplication.translate(
                "ConflictReportDialog",
                "Harmony patches do not report a Def-style winner.",
            )
        )

    def _populate_harmony_details(
        self, finding: dict[str, Any], layout: QVBoxLayout
    ) -> None:
        for patch in finding["patches"]:
            layout.addWidget(self._patch_widget(patch))
        target = finding["target"]
        for label, value in (
            (
                QCoreApplication.translate("ConflictReportDialog", "Type"),
                target["type_name"],
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Method"),
                target["method_name"],
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Parameter types"),
                target["parameter_types"],
            ),
            (
                QCoreApplication.translate(
                    "ConflictReportDialog", "Short-circuit risk"
                ),
                finding["short_circuit_risk"],
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Execution order"),
                finding["execution_order"],
            ),
        ):
            layout.addWidget(self._field_label(label, value))

    def _mod_widget(self, mod: dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._add_mod_fields(layout, mod)
        return widget

    def _patch_widget(self, patch: dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(
            self._make_section_label(
                QCoreApplication.translate("ConflictReportDialog", "Mod")
            )
        )
        self._add_mod_fields(layout, patch["mod_summary"])
        for label, key in (
            (QCoreApplication.translate("ConflictReportDialog", "DLL"), "dll_name"),
            (
                QCoreApplication.translate("ConflictReportDialog", "Patch kind"),
                "patch_kind",
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Priority"),
                "priority",
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Before"),
                "before",
            ),
            (QCoreApplication.translate("ConflictReportDialog", "After"), "after"),
            (
                QCoreApplication.translate("ConflictReportDialog", "Returns bool"),
                "returns_bool",
            ),
        ):
            layout.addWidget(self._field_label(label, patch[key]))
        return widget

    def _add_mod_fields(self, layout: QVBoxLayout, mod: dict[str, Any]) -> None:
        for label, key in (
            (QCoreApplication.translate("ConflictReportDialog", "Name"), "name"),
            (
                QCoreApplication.translate("ConflictReportDialog", "Package ID"),
                "package_id",
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Author"),
                "author",
            ),
            (
                QCoreApplication.translate("ConflictReportDialog", "Base content"),
                "is_base_content",
            ),
        ):
            layout.addWidget(self._field_label(label, mod[key]))

    def _mod_button(
        self, mod: dict[str, Any], buttons: list[QPushButton], generation: int
    ) -> QPushButton:
        package_id = mod.get("package_id")
        button = QPushButton()
        button.setAutoDefault(False)
        button.setEnabled(self._mod_actions_enabled and isinstance(package_id, str))
        button.setText(self._mod_button_text(mod).replace("&", "&&"))
        if isinstance(package_id, str):
            button.clicked.connect(
                lambda _checked: (
                    self.mod_requested.emit(package_id)
                    if generation == self._generation
                    else None
                )
            )
        buttons.append(button)
        return button

    def _mod_button_text(self, mod: dict[str, Any]) -> str:
        name = safe_text(str(mod.get("name", "")))
        package_id = safe_text(str(mod.get("package_id", "")))
        if name and package_id and name != package_id:
            return f"{name} ({package_id})"
        return name or package_id

    def _field_label(self, label: str, value: Any) -> QLabel:
        widget = self._make_text_label()
        widget.setText(self._field_text(label, value))
        return widget

    def _field_text(self, label: str, value: Any) -> str:
        return f"{label}: {self._value_text(value)}"

    def _value_text(self, value: Any) -> str:
        if value is None:
            return QCoreApplication.translate("ConflictReportDialog", "Unknown")
        if isinstance(value, bool):
            if value:
                return QCoreApplication.translate("ConflictReportDialog", "Yes")
            return QCoreApplication.translate("ConflictReportDialog", "No")
        if isinstance(value, list):
            return safe_text(json.dumps(value, ensure_ascii=False))
        return safe_text(str(value))

    def _severity_text(self, severity: str) -> str:
        labels = {
            "error": QCoreApplication.translate("ConflictReportDialog", "Error"),
            "warning": QCoreApplication.translate("ConflictReportDialog", "Warning"),
            "info": QCoreApplication.translate("ConflictReportDialog", "Info"),
        }
        return labels.get(severity, safe_text(severity))

    def _target_summary(self, finding: dict[str, Any]) -> str:
        target = finding["target"]
        if finding["type"] == "def":
            return safe_text(f"{target['def_type']}: {target['def_name']}")
        method_name = target["method_name"]
        if target["parameter_types"]:
            method_name = f"{method_name}({safe_text(json.dumps(target['parameter_types'], ensure_ascii=False))})"
        return safe_text(f"{target['type_name']}.{method_name}")

    def _mechanism_title(self, finding: dict[str, Any]) -> str:
        if finding["type"] == "harmony":
            return QCoreApplication.translate("ConflictReportDialog", "Harmony")
        kind = next(iter(finding["mechanism"]))
        titles = {
            "direct_replacement": QCoreApplication.translate(
                "ConflictReportDialog", "Direct replacement"
            ),
            "x_path_overlap": QCoreApplication.translate(
                "ConflictReportDialog", "XPath overlap"
            ),
            "x_path_on_replaced_def": QCoreApplication.translate(
                "ConflictReportDialog", "XPath on replaced Def"
            ),
            "xpath_same_def_non_overlap": QCoreApplication.translate(
                "ConflictReportDialog", "Non-overlapping XPath edits"
            ),
        }
        return titles[kind]

    def _explanation_text(self, finding: dict[str, Any]) -> str:
        if finding["type"] == "harmony":
            return QCoreApplication.translate(
                "ConflictReportDialog",
                "These Harmony patches target the same method. Patch overlap may be intentional and is not proof of broken gameplay.",
            )
        kind = next(iter(finding["mechanism"]))
        explanations = {
            "direct_replacement": QCoreApplication.translate(
                "ConflictReportDialog",
                "This report says one mod directly replaced another definition. Replacements may be intentional and are not proof of broken gameplay.",
            ),
            "x_path_overlap": QCoreApplication.translate(
                "ConflictReportDialog",
                "These mods edit overlapping XPath targets on the same definition. Overlap may be intentional and is not proof of broken gameplay.",
            ),
            "x_path_on_replaced_def": QCoreApplication.translate(
                "ConflictReportDialog",
                "This mod edits a definition that another mod replaced. That relationship may be intentional and is not proof of broken gameplay.",
            ),
            "xpath_same_def_non_overlap": QCoreApplication.translate(
                "ConflictReportDialog",
                "These mods edit different XPath targets on the same definition. Shared targets may be intentional and are not proof of broken gameplay.",
            ),
        }
        return explanations[kind]

    def _reset_technical(self) -> None:
        self.technical_button.blockSignals(True)
        self.technical_button.setChecked(False)
        self.technical_button.blockSignals(False)
        self.technical_button.setArrowType(Qt.ArrowType.RightArrow)
        self._details_widget.setVisible(False)

    @Slot(bool)
    def _toggle_technical(self, checked: bool) -> None:
        generation = self._generation
        finding = self._finding
        layout = self._details_layout
        widget = self._details_widget
        if checked and finding is not None and not layout.count():
            if finding["type"] == "def":
                self._populate_def_details(finding, layout)
            else:
                self._populate_harmony_details(finding, layout)
        if generation != self._generation:
            return
        self.technical_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        widget.setVisible(checked and finding is not None)

    def _update_raw_button_text(self, checked: bool) -> None:
        if checked:
            self.raw_button.setText(
                QCoreApplication.translate(
                    "ConflictReportDialog", "Hide raw finding data"
                )
            )
            return
        self.raw_button.setText(
            QCoreApplication.translate("ConflictReportDialog", "Show raw finding data")
        )

    @Slot(bool)
    def _toggle_raw(self, checked: bool) -> None:
        generation = self._generation
        self._raw_revision += 1
        revision = self._raw_revision
        self._update_raw_button_text(checked)
        if not checked:
            self.raw_view.clear()
            if generation == self._generation and revision == self._raw_revision:
                self.raw_view.setVisible(False)
            return
        if self._finding is None:
            self._clear_raw()
            if generation == self._generation:
                self.raw_button.setEnabled(False)
            return
        self.raw_view.setPlainText(
            safe_text(json.dumps(self._finding, indent=2, ensure_ascii=False))
        )
        if generation == self._generation and revision == self._raw_revision:
            self.raw_view.setVisible(True)
