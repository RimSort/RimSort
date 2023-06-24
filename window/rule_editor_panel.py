from functools import partial
from logger_tt import logger
import os
import platform
from typing import Any, Dict, List, Optional, Tuple


from PySide6.QtCore import Qt, QModelIndex, QObject, QPoint, QSize, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHeaderView,
    QItemDelegate,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableView,
    QToolButton,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)

from model.dialogue import show_warning


class EditableDelegate(QItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 4:  # Check if it's the 5th column
            model = index.model()
            column3_value = model.index(
                index.row(), 2
            ).data()  # Get the value of the 3rd column
            if column3_value in [
                "Community Rules",
                "User Rules",
            ]:  # Only create an editor if the condition is met
                editor = super().createEditor(parent, option, index)
                return editor
        return None

    def setEditorData(self, editor, index):
        if index.column() == 4:  # Only set data for the 5th column
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 4:  # Only set data for the 5th column
            super().setModelData(editor, model, index)


class RuleEditor(QWidget):
    """
    A generic panel used to edit Paladin communityRules.json style rules
    """

    update_database_signal = Signal(list)

    def __init__(
        self,
        initial_mode: str,
        local_metadata: Dict[str, Any],
        community_rules: Dict[str, Any],
        user_rules: Dict[str, Any],
        compact=None,
        edit_packageId=None,
        steam_workshop_metadata=None,
    ):
        super().__init__()
        logger.info("Initializing RuleEditor")

        # LAUNCH OPTIONS
        self.compact = compact
        self.edit_packageId = edit_packageId
        self.initial_mode = initial_mode
        # THE METADATA
        self.local_metadata = local_metadata
        self.local_rules_hidden = None
        self.community_rules = community_rules.copy()
        self.community_rules_hidden = None
        self.user_rules = user_rules.copy()
        self.user_rules_hidden = None
        # Can be used to get proper names for mods found in list
        # items that are not locally available
        self.steam_workshop_metadata_packageIds_to_name = None
        self.steam_workshop_metadata = steam_workshop_metadata
        if (
            self.steam_workshop_metadata
            and len(self.steam_workshop_metadata.keys()) > 0
        ):
            self.steam_workshop_metadata_packageIds_to_name = {}
            for metadata in self.steam_workshop_metadata.values():
                if metadata.get("packageId"):
                    self.steam_workshop_metadata_packageIds_to_name[
                        metadata["packageId"]
                    ] = metadata["name"]

        # MOD LABEL
        self.mod_label = QLabel("No mod currently being edited")
        self.mod_label.setAlignment(Qt.AlignCenter)

        # CONTAINER LAYOUTS
        self.upper_layout = QHBoxLayout()
        self.lower_layout = QVBoxLayout()
        self.layout = QVBoxLayout()

        # SUB LAYOUTS
        self.details_layout = QHBoxLayout()
        self.editor_layout = QHBoxLayout()
        self.editor_actions_layout = QVBoxLayout()
        self.mods_layout = QVBoxLayout()
        self.mods_actions_layout = QHBoxLayout()

        # SUB SUB LAYOUTS
        self.internal_local_metadata_layout = QVBoxLayout()
        self.external_community_rules_layout = QVBoxLayout()
        self.internal_user_rules_layout = QVBoxLayout()

        # DETAILS WIDGETS
        # local metadata
        self.local_metadata_loadAfter_label = QLabel("About.xml (loadAfter)")
        self.local_metadata_loadBefore_label = QLabel("About.xml (loadBefore)")
        self.local_metadata_loadAfter_list = QListWidget()
        self.local_metadata_loadBefore_list = QListWidget()
        # community rules
        self.external_community_rules_loadAfter_label = QLabel(
            "Community Rules (loadAfter)"
        )
        self.external_community_rules_loadBefore_label = QLabel(
            "Community Rules (loadBefore)"
        )
        self.external_community_rules_loadAfter_list = QListWidget()
        self.external_community_rules_loadAfter_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.external_community_rules_loadAfter_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_community_rules_loadAfter_list,
            )
        )
        self.external_community_rules_loadAfter_list.setDefaultDropAction(Qt.MoveAction)
        self.external_community_rules_loadAfter_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )
        self.external_community_rules_loadBefore_list = QListWidget()
        self.external_community_rules_loadBefore_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.external_community_rules_loadBefore_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_community_rules_loadBefore_list,
            )
        )
        self.external_community_rules_loadBefore_list.setDefaultDropAction(
            Qt.MoveAction
        )
        self.external_community_rules_loadBefore_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )
        # user rules
        self.internal_user_rules_loadAfter_label = QLabel("User Rules (loadAfter)")
        self.internal_user_rules_loadBefore_label = QLabel("User Rules (loadBefore)")
        self.internal_user_rules_loadAfter_list = QListWidget()
        self.internal_user_rules_loadAfter_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.internal_user_rules_loadAfter_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.internal_user_rules_loadAfter_list,
            )
        )
        self.internal_user_rules_loadAfter_list.setDefaultDropAction(Qt.MoveAction)
        self.internal_user_rules_loadAfter_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )
        self.internal_user_rules_loadBefore_list = QListWidget()
        self.internal_user_rules_loadBefore_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.internal_user_rules_loadBefore_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.internal_user_rules_loadBefore_list,
            )
        )
        self.internal_user_rules_loadBefore_list.setDefaultDropAction(Qt.MoveAction)
        self.internal_user_rules_loadBefore_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )

        # EDITOR WIDGETS
        # Create the model and set column headers
        self.editor_model = QStandardItemModel(0, 5)
        self.editor_model.setHorizontalHeaderLabels(
            ["Name", "PackageId", "Rule source", "Rule type", "Comment"]
        )
        # Create the table view and set the model
        self.editor_table_view = QTableView()
        self.editor_table_view.setModel(self.editor_model)
        self.editor_table_view.setSortingEnabled(True)  # Enable sorting on the columns
        self.editor_table_view.setItemDelegate(
            EditableDelegate()
        )  # Set the delegate for editing
        self.editor_table_view.setEditTriggers(
            QTableView.DoubleClicked | QTableView.EditKeyPressed
        )  # Enable editing
        # Set default stretch for each column
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch
        )
        # Editor actions
        # community rules
        self.editor_save_community_rules_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/save_community_rules.png")
        )
        self.editor_save_community_rules_button = QToolButton()
        self.editor_save_community_rules_button.setToolTip(
            "Save rules to communityRules.json"
        )
        self.editor_save_community_rules_button.setIcon(
            self.editor_save_community_rules_icon
        )
        self.editor_save_community_rules_button.clicked.connect(
            partial(self._save_editor_rules, rules_source="Community Rules")
        )
        # user rules
        # Editor actions
        self.editor_save_user_rules_icon = QIcon(
            os.path.join(os.path.dirname(__file__), "../data/save_user_rules.png")
        )
        self.editor_save_user_rules_button = QToolButton()
        self.editor_save_user_rules_button.setToolTip("Save rules to userRules.json")
        self.editor_save_user_rules_button.setIcon(self.editor_save_user_rules_icon)
        self.editor_save_user_rules_button.clicked.connect(
            partial(self._save_editor_rules, rules_source="User Rules")
        )

        # MODS WIDGETS
        # Mods search
        self.mods_search = QLineEdit()
        self.mods_search.setClearButtonEnabled(True)
        self.mods_search.textChanged.connect(self.signal_mods_search)
        self.mods_search.setPlaceholderText("Search mods by name or packageId")
        self.mods_search_clear_button = self.mods_search.findChild(QToolButton)
        self.mods_search_clear_button.setEnabled(True)
        self.mods_search_clear_button.clicked.connect(self.clear_mods_search)
        # Mods list
        self.mods_list = QListWidget()
        self.mods_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mods_list.customContextMenuRequested.connect(self.modItemContextMenuEvent)

        # Actions
        self.local_metadata_button = QPushButton()
        self.local_metadata_button.clicked.connect(
            partial(
                self._toggle_details_layout_widgets, self.internal_local_metadata_layout
            )
        )
        self.community_rules_button = QPushButton()
        self.community_rules_button.clicked.connect(
            partial(
                self._toggle_details_layout_widgets,
                self.external_community_rules_layout,
            )
        )
        self.user_rules_button = QPushButton()
        self.user_rules_button.clicked.connect(
            partial(
                self._toggle_details_layout_widgets,
                self.internal_user_rules_layout,
            )
        )
        # Build the details layout
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_loadAfter_label
        )
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_loadAfter_list
        )
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_loadBefore_label
        )
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_loadBefore_list
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadAfter_label
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadAfter_list
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadBefore_label
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadBefore_list
        )
        self.internal_user_rules_layout.addWidget(
            self.internal_user_rules_loadAfter_label
        )
        self.internal_user_rules_layout.addWidget(
            self.internal_user_rules_loadAfter_list
        )
        self.internal_user_rules_layout.addWidget(
            self.internal_user_rules_loadBefore_label
        )
        self.internal_user_rules_layout.addWidget(
            self.internal_user_rules_loadBefore_list
        )
        self.details_layout.addLayout(self.internal_local_metadata_layout)
        self.details_layout.addLayout(self.external_community_rules_layout)
        self.details_layout.addLayout(self.internal_user_rules_layout)

        # Build the editor layouts
        self.editor_actions_layout.addWidget(self.editor_save_community_rules_button)
        self.editor_actions_layout.addWidget(self.editor_save_user_rules_button)
        self.editor_layout.addWidget(self.editor_table_view)
        self.editor_layout.addLayout(self.editor_actions_layout)

        # Build the mods layout layout
        self.mods_layout.addWidget(self.mods_search)
        self.mods_actions_layout.addWidget(self.local_metadata_button)
        self.mods_actions_layout.addWidget(self.community_rules_button)
        self.mods_actions_layout.addWidget(self.user_rules_button)
        self.mods_layout.addWidget(self.mods_list)
        self.mods_layout.addLayout(self.mods_actions_layout)

        # Add our widget layouts to the containers
        self.upper_layout.addLayout(self.details_layout, 50)
        self.upper_layout.addLayout(self.mods_layout, 50)
        self.lower_layout.addLayout(self.editor_layout)

        # Add our layouts to the main layout
        self.layout.addWidget(self.mod_label)
        self.layout.addLayout(self.upper_layout, 66)
        self.layout.addLayout(self.lower_layout, 33)

        # Allow for dragging and dropping between lists
        # self.mods_list.setDefaultDropAction(Qt.MoveAction)
        # self.mods_list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        # self.external_community_rules_loadAfter_list.setDefaultDropAction(Qt.MoveAction)
        # self.external_community_rules_loadAfter_list.setDragDropMode(
        #     QAbstractItemView.DragDropMode.DragDrop
        # )
        # self.external_community_rules_loadBefore_list.setDefaultDropAction(
        #     Qt.MoveAction
        # )
        # self.external_community_rules_loadBefore_list.setDragDropMode(
        #     QAbstractItemView.DragDropMode.DragDrop
        # )
        # self.internal_user_rules_loadAfter_list.setDefaultDropAction(Qt.MoveAction)
        # self.internal_user_rules_loadAfter_list.setDragDropMode(
        #     QAbstractItemView.DragDropMode.DragDrop
        # )
        # self.internal_user_rules_loadBefore_list.setDefaultDropAction(Qt.MoveAction)
        # self.internal_user_rules_loadBefore_list.setDragDropMode(
        #     QAbstractItemView.DragDropMode.DragDrop
        # )

        # Allow toggle layouts based on context
        if self.compact:
            self._toggle_details_layout_widgets(
                layout=self.internal_local_metadata_layout, override=True
            )
        else:
            self._toggle_details_layout_widgets(
                layout=self.internal_local_metadata_layout, override=False
            )
        if self.initial_mode == "community_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=False
            )
            self._toggle_details_layout_widgets(
                layout=self.internal_user_rules_layout, override=True
            )
        elif self.initial_mode == "user_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=True
            )
            self._toggle_details_layout_widgets(
                layout=self.internal_user_rules_layout, override=False
            )
        # Put it all together
        self._populate_from_metadata()
        self.setWindowTitle("RimSort - Rule Editor")
        self.setLayout(self.layout)
        self.setMinimumSize(QSize(800, 600))

    def current_list_widget(self, position):
        widgets = [
            self.mods_list,
            self.external_community_rules_loadAfter_list,
            self.external_community_rules_loadBefore_list,
            self.internal_user_rules_loadAfter_list,
            self.internal_user_rules_loadBefore_list,
        ]
        for widget in widgets:
            if widget.geometry().contains(position):
                return widget
        return None

    # def dragEnterEvent(self, event):
    #     if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
    #         event.accept()
    #     else:
    #         event.ignore()

    # def dropEvent(self, event):
    #     if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
    #         data = event.mimeData()
    #         items = data.data("application/x-qabstractitemmodeldatalist").split(b"\x00")
    #         list_widget = self.current_list_widget(event.pos())
    #         if list_widget:
    #             for item_data in items:
    #                 item = QListWidgetItem(item_data.decode())
    #                 list_widget.addItem(item)

    #             event.accept()
    #     else:
    #         event.ignore()

    # RULES

    def _add_rule(
        self,
        name: str,
        packageId: str,
        rule_source: str,
        rule_type: str,
        comment: str,
        hidden=None,
    ):
        # Create the standard items for each column
        items = [
            QStandardItem(name),
            QStandardItem(packageId),
            QStandardItem(rule_source),
            QStandardItem(rule_type),
            QStandardItem(comment),
        ]
        items[0].setToolTip(name)
        # Set the items as a new row in the model
        self.editor_model.appendRow(items)

        # Set row visibility based on the 'hidden' parameter
        if hidden:
            row = self.editor_model.rowCount() - 1
            self.editor_table_view.setRowHidden(row, hidden)

    def _clear_widget(self) -> None:
        self.clear_mods_search()
        self.mods_list.clear()
        self.local_metadata_loadAfter_list.clear()
        self.local_metadata_loadBefore_list.clear()
        self.external_community_rules_loadAfter_list.clear()
        self.external_community_rules_loadBefore_list.clear()
        self.internal_user_rules_loadAfter_list.clear()
        self.internal_user_rules_loadBefore_list.clear()
        self.editor_model.removeRows(0, self.editor_model.rowCount())

    def _create_list_item(self, _list: QListWidget, title: str, metadata=None) -> None:
        # Create our list item
        item = QListWidgetItem()
        if metadata:
            item.setData(Qt.UserRole, metadata)
        # Set list item label
        label = QLabel(title)
        label.setObjectName("ListItemLabel")
        # Set the size hint of the item to be the size of the label
        item.setSizeHint(label.sizeHint())
        # add to our list
        _list.addItem(item)
        _list.setItemWidget(item, label)

    def _open_mod_in_editor(self, context_item: QListWidgetItem) -> None:
        json_data = context_item.data(Qt.UserRole)
        self.edit_packageId = json_data["packageId"]
        self._clear_widget()
        self._populate_from_metadata()

    def _populate_from_metadata(self) -> None:
        if self.local_metadata and len(self.local_metadata.keys()) > 0:
            for metadata in self.local_metadata.values():
                # Local metadata rulez
                # Additionally, populate anything that is not exit_packageId into the mods list
                if (
                    metadata.get("packageId")
                    and self.edit_packageId
                    and metadata["packageId"].lower() == self.edit_packageId.lower()
                ):
                    self.mod_label.setText(f'Editing rules for: {metadata["name"]}')
                    if metadata.get("loadAfter") and metadata["loadAfter"].get("li"):
                        loadAfters = metadata["loadAfter"]["li"]
                        if isinstance(loadAfters, str):
                            self._create_list_item(
                                _list=self.local_metadata_loadAfter_list,
                                title=self.steam_workshop_metadata_packageIds_to_name[
                                    loadAfters.lower()
                                ]
                                if loadAfters.lower()
                                in [
                                    key.lower()
                                    for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                ]
                                else loadAfters,
                                metadata=loadAfters,
                            )
                            self._add_rule(
                                name=self.steam_workshop_metadata_packageIds_to_name[
                                    loadAfters.lower()
                                ]
                                if loadAfters.lower()
                                in [
                                    key.lower()
                                    for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                ]
                                else loadAfters,
                                packageId=loadAfters,
                                rule_source="About.xml",
                                rule_type="loadAfter",
                                comment="Added from mod metadata",
                                hidden=self.local_rules_hidden,
                            )
                        elif isinstance(loadAfters, list):
                            for rule in loadAfters:
                                self._create_list_item(
                                    _list=self.local_metadata_loadAfter_list,
                                    title=self.steam_workshop_metadata_packageIds_to_name[
                                        rule.lower()
                                    ]
                                    if rule.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                    ]
                                    else rule,
                                    metadata=rule,
                                )
                                self._add_rule(
                                    name=self.steam_workshop_metadata_packageIds_to_name[
                                        rule.lower()
                                    ]
                                    if rule.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                    ]
                                    else rule,
                                    packageId=rule,
                                    rule_source="About.xml",
                                    rule_type="loadAfter",
                                    comment="Added from mod metadata",
                                    hidden=self.local_rules_hidden,
                                )
                    elif metadata.get("loadBefore") and metadata["loadBefore"].get(
                        "li"
                    ):
                        loadBefores = metadata["loadBefore"]["li"]
                        if isinstance(loadBefores, str):
                            self._create_list_item(
                                _list=self.local_metadata_loadBefore_list,
                                title=self.steam_workshop_metadata_packageIds_to_name[
                                    loadBefores.lower()
                                ]
                                if loadBefores.lower()
                                in [
                                    key.lower()
                                    for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                ]
                                else loadBefores,
                                metadata=loadBefores,
                            )
                            self._add_rule(
                                name=self.steam_workshop_metadata_packageIds_to_name[
                                    loadAfters.lower()
                                ]
                                if loadAfters.lower()
                                in [
                                    key.lower()
                                    for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                ]
                                else loadAfters,
                                packageId=loadAfters,
                                rule_source="About.xml",
                                rule_type="loadBefore",
                                comment="Added from mod metadata",
                                hidden=self.local_rules_hidden,
                            )
                        elif isinstance(loadBefores, list):
                            for rule in loadBefores:
                                self._create_list_item(
                                    _list=self.local_metadata_loadBefore_list,
                                    title=self.steam_workshop_metadata_packageIds_to_name[
                                        rule.lower()
                                    ]
                                    if rule.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                    ]
                                    else rule,
                                    metadata=rule,
                                )
                                self._add_rule(
                                    name=self.steam_workshop_metadata_packageIds_to_name[
                                        rule.lower()
                                    ]
                                    if rule.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageIds_to_name.keys()
                                    ]
                                    else rule,
                                    packageId=rule,
                                    rule_source="About.xml",
                                    rule_type="loadBefore",
                                    comment="Added from mod metadata",
                                    hidden=self.local_rules_hidden,
                                )
                else:  # Otherwise, add everything else to the mod list
                    self._create_list_item(
                        _list=self.mods_list,
                        title=metadata["name"],
                        metadata={
                            "packageId": metadata["packageId"]
                            if metadata.get("packageId")
                            else None,
                        },
                    )
        # Community Rules rulez
        if self.community_rules and len(self.community_rules.keys()) > 0:
            for packageId, metadata in self.community_rules.items():
                if (
                    self.edit_packageId
                    and self.edit_packageId.lower() == packageId.lower()
                ):
                    if metadata.get("loadAfter"):
                        for rule_id, rule_data in metadata["loadAfter"].items():
                            self._create_list_item(
                                _list=self.external_community_rules_loadAfter_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule(
                                name=rule_data["name"][0],
                                packageId=rule_id,
                                rule_source="Community Rules",
                                rule_type="loadAfter",
                                comment=rule_data["comment"][0]
                                if rule_data.get("comment")
                                else "",
                                hidden=self.community_rules_hidden,
                            )
                    if metadata.get("loadBefore"):
                        for rule_id, rule_data in metadata["loadBefore"].items():
                            self._create_list_item(
                                _list=self.external_community_rules_loadBefore_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule(
                                name=rule_data["name"][0],
                                packageId=rule_id,
                                rule_source="Community Rules",
                                rule_type="loadBefore",
                                comment=rule_data["comment"][0]
                                if rule_data.get("comment")
                                else "",
                                hidden=self.community_rules_hidden,
                            )
        # User Rules rulez
        if self.user_rules and len(self.user_rules.keys()) > 0:
            for packageId, metadata in self.user_rules.items():
                if (
                    self.edit_packageId
                    and self.edit_packageId.lower() == packageId.lower()
                ):
                    if metadata.get("loadAfter"):
                        for rule_id, rule_data in metadata["loadAfter"].items():
                            self._create_list_item(
                                _list=self.internal_user_rules_loadAfter_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule(
                                name=rule_data["name"][0],
                                packageId=rule_id,
                                rule_source="User Rules",
                                rule_type="loadAfter",
                                comment=rule_data["comment"][0]
                                if rule_data.get("comment")
                                else "",
                                hidden=self.user_rules_hidden,
                            )
                    if metadata.get("loadBefore"):
                        for rule_id, rule_data in metadata["loadBefore"].items():
                            self._create_list_item(
                                _list=self.internal_user_rules_loadBefore_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule(
                                name=rule_data["name"][0],
                                packageId=rule_id,
                                rule_source="User Rules",
                                rule_type="loadBefore",
                                comment=rule_data["comment"][0]
                                if rule_data.get("comment")
                                else "",
                                hidden=self.user_rules_hidden,
                            )

    def _remove_rule(self, context_item: QListWidgetItem, _list: QListWidget) -> None:
        _list.takeItem(_list.row(context_item))
        rule_data = context_item.data(Qt.UserRole)
        # Determine action mode
        if _list is self.external_community_rules_loadAfter_list:
            mode = ["community", "loadAfter"]

        elif _list is self.external_community_rules_loadBefore_list:
            mode = ["community", "loadBefore"]

        elif _list is self.internal_user_rules_loadAfter_list:
            mode = ["user", "loadAfter"]

        elif _list is self.internal_user_rules_loadBefore_list:
            mode = ["user", "loadBefore"]
        # Select database for editing
        if mode[0] == "community":
            metadata = self.community_rules
        elif mode[0] == "user":
            metadata = self.user_rules
        # Remove rule from the database
        if metadata.get(self.edit_packageId, "").get(mode[1], "").get(rule_data):
            metadata[self.edit_packageId][mode[1]].pop(rule_data)
        # Search for & remove the rule's row entry from the editor table
        for row in range(self.editor_model.rowCount()):
            # Define criteria
            packageId_value = self.editor_model.item(
                row, 1
            )  # Get the item in column 2 (index 1)
            rule_source_value = self.editor_model.item(
                row, 2
            )  # Get the item in column 3 (index 2)
            rule_type_value = self.editor_model.item(
                row, 3
            )  # Get the item in column 4 (index 3)
            # Search table for rows that match
            if (
                (packageId_value and rule_data in packageId_value.text())
                and (rule_source_value and mode[0] in rule_source_value.text().lower())
                and (rule_type_value and mode[1] in rule_type_value.text())
            ):  # Remove row if criteria matches search
                self.editor_model.removeRow(row)

    def _save_editor_rules(self, rules_source: str) -> None:
        # Overwrite rules source with any changes to our metadata
        if rules_source == "Community Rules":
            metadata = self.community_rules
        elif rules_source == "User Rules":
            metadata = self.user_rules
        self.update_database_signal.emit([rules_source, metadata])

    def _toggle_details_layout_widgets(
        self, layout: QVBoxLayout, override=None
    ) -> None:
        # Iterate through all widgets in layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not "visibility" in locals():  # We only need to set this once per pass
                visibility = item.widget().isVisible()
                # Override so we can toggle this upon initialization if we want to
                if override:
                    visibility = override
            # Toggle visibility of the widgets
            item.widget().setVisible(not visibility)
        # Change button text based on the layout we are toggling
        # If this is True, it means the widgets are hidden. Edit btn text + hide rules to reflect.
        if visibility:
            if layout is self.internal_local_metadata_layout:
                self.local_rules_hidden = True
                self.local_metadata_button.setText("Show About.xml rules")
                self._toggle_editor_table_rows(
                    rule_type="About.xml", visibility=visibility
                )
            elif layout is self.external_community_rules_layout:
                self.community_rules_hidden = True
                self.community_rules_button.setText("Edit Community Rules")
                self._toggle_editor_table_rows(
                    rule_type="Community Rules", visibility=visibility
                )
            elif layout is self.internal_user_rules_layout:
                self.user_rules_hidden = False
                self.user_rules_button.setText("Edit User Rules")
                self._toggle_editor_table_rows(
                    rule_type="User Rules", visibility=visibility
                )
        else:
            if layout is self.internal_local_metadata_layout:
                self.local_rules_hidden = False
                self.local_metadata_button.setText("Hide About.xml rules")
                self._toggle_editor_table_rows(
                    rule_type="About.xml", visibility=visibility
                )
            elif layout is self.external_community_rules_layout:
                self.community_rules_hidden = False
                self.community_rules_button.setText("Lock Community Rules")
                self._toggle_editor_table_rows(
                    rule_type="Community Rules", visibility=visibility
                )
            elif layout is self.internal_user_rules_layout:
                self.user_rules_hidden = False
                self.user_rules_button.setText("Lock User Rules")
                self._toggle_editor_table_rows(
                    rule_type="User Rules", visibility=visibility
                )

    def _toggle_editor_table_rows(self, rule_type: str, visibility: bool):
        for row in range(self.editor_model.rowCount()):
            item = self.editor_model.item(row, 2)  # Get the item in column 3 (index 2)
            if (
                item and item.text() == rule_type
            ):  # Toggle row visibility based on the value
                self.editor_table_view.setRowHidden(row, visibility)

    def modItemContextMenuEvent(self, point: QPoint) -> None:
        context_menu = QMenu(self)  # Mod item context menu event
        context_item = self.mods_list.itemAt(point)
        open_mod = context_menu.addAction(
            "Open this mod in the editor"
        )  # open mod in editor
        open_mod.triggered.connect(
            partial(self._open_mod_in_editor, context_item=context_item)
        )
        action = context_menu.exec_(self.mods_list.mapToGlobal(point))

    def ruleItemContextMenuEvent(self, point: QPoint, _list: QListWidget) -> None:
        context_menu = QMenu(self)  # Rule item context menu event
        context_item = _list.itemAt(point)
        remove_rule = context_menu.addAction("Remove this rule")  # remove this rule
        remove_rule.triggered.connect(
            partial(
                self._remove_rule,
                context_item=context_item,
                _list=_list,
            )
        )
        action = context_menu.exec_(_list.mapToGlobal(point))

    def clear_mods_search(self) -> None:
        self.mods_search.setText("")
        self.mods_search.clearFocus()

    def signal_mods_search(self, pattern: str) -> None:
        # Loop through the items
        for index in range(self.mods_list.count()):
            item = self.mods_list.item(index)
            json_data = item.data(Qt.UserRole)
            if (
                pattern
                and json_data.get("name")
                and not pattern.lower() in json_data["name"].lower()
            ):
                item.setHidden(True)
            else:
                item.setHidden(False)
            if (
                pattern
                and json_data.get("packageId")
                and not pattern.lower() in json_data["packageId"].lower()
            ):
                item.setHidden(True)
            else:
                item.setHidden(False)
