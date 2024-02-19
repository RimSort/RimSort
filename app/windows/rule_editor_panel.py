from functools import partial

from PySide6.QtCore import Qt, QPoint, QSize, Signal
from PySide6.QtGui import (
    QIcon,
    QStandardItemModel,
    QStandardItem,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QItemDelegate,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTableView,
    QToolButton,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
)
from loguru import logger

from app.models.dialogue import show_dialogue_input, show_warning
from app.utils.app_info import AppInfo
from app.utils.metadata import MetadataManager


class EditableDelegate(QItemDelegate):
    comment_edited_signal = Signal(list)

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
            # Send the column data back to the editor so we can update the metadata
            # edited_data = model.data(index, Qt.DisplayRole)  # Get the edited data
            column_values = [
                model.data(model.index(index.row(), column), Qt.DisplayRole)
                for column in range(model.columnCount())
            ]  # Get the values of all columns in the edited row

            self.comment_edited_signal.emit(
                column_values
            )  # Emit the signal with column values and edited data


class RuleEditor(QWidget):
    """
    A generic panel used to edit Paladin communityRules.json style rules
    """

    update_database_signal = Signal(list)

    def __init__(self, initial_mode: str, compact=None, edit_packageid=None):
        super().__init__()
        logger.debug("Initializing RuleEditor")

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        # STYLESHEET
        self.setObjectName("RuleEditor")

        # LAUNCH OPTIONS
        self.block_comment_prompt = (
            None  # Used to block comment prompt when metadata is being populated
        )
        self.compact = compact
        self.edit_packageid = edit_packageid
        self.initial_mode = initial_mode
        # THE METADATA
        self.local_rules_hidden = None
        self.community_rules = (
            self.metadata_manager.external_community_rules.copy()
            if self.metadata_manager.external_community_rules
            else {}
        )
        self.community_rules_hidden = None
        self.user_rules = (
            self.metadata_manager.external_user_rules.copy()
            if self.metadata_manager.external_user_rules
            else {}
        )
        self.user_rules_hidden = None
        # Can be used to get proper names for mods found in list
        # items that are not locally available
        self.steam_workshop_metadata_packageids_to_name = {}
        if (
            self.metadata_manager.external_steam_metadata
            and len(self.metadata_manager.external_steam_metadata.keys()) > 0
        ):
            for metadata in self.metadata_manager.external_steam_metadata.values():
                if metadata.get("packageid"):
                    self.steam_workshop_metadata_packageids_to_name[
                        metadata["packageid"]
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
        self.external_user_rules_layout = QVBoxLayout()

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
        self.external_community_rules_loadAfter_list.setAcceptDrops(True)
        self.external_community_rules_loadAfter_list.setDragDropMode(
            QListWidget.DropOnly
        )
        self.external_community_rules_loadAfter_list.dropEvent = self.createDropEvent(
            self.external_community_rules_loadAfter_list
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
        self.external_community_rules_loadBefore_list.setAcceptDrops(True)
        self.external_community_rules_loadBefore_list.setDragDropMode(
            QListWidget.DropOnly
        )
        self.external_community_rules_loadBefore_list.dropEvent = self.createDropEvent(
            self.external_community_rules_loadBefore_list
        )
        self.external_community_rules_loadBottom_checkbox = QCheckBox(
            "Force load at bottom of list"
        )
        self.external_community_rules_loadBottom_checkbox.setObjectName("summaryValue")
        # user rules
        self.external_user_rules_loadAfter_label = QLabel("User Rules (loadAfter)")
        self.external_user_rules_loadBefore_label = QLabel("User Rules (loadBefore)")
        self.external_user_rules_loadAfter_list = QListWidget()
        self.external_user_rules_loadAfter_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.external_user_rules_loadAfter_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_user_rules_loadAfter_list,
            )
        )
        self.external_user_rules_loadAfter_list.setAcceptDrops(True)
        self.external_user_rules_loadAfter_list.setDragDropMode(QListWidget.DropOnly)
        self.external_user_rules_loadAfter_list.dropEvent = self.createDropEvent(
            self.external_user_rules_loadAfter_list
        )
        self.external_user_rules_loadBefore_list = QListWidget()
        self.external_user_rules_loadBefore_list.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.external_user_rules_loadBefore_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_user_rules_loadBefore_list,
            )
        )
        self.external_user_rules_loadBefore_list.setAcceptDrops(True)
        self.external_user_rules_loadBefore_list.setDragDropMode(QListWidget.DropOnly)
        self.external_user_rules_loadBefore_list.dropEvent = self.createDropEvent(
            self.external_user_rules_loadBefore_list
        )
        self.external_user_rules_loadBottom_checkbox = QCheckBox(
            "Force load at bottom of list"
        )
        self.external_user_rules_loadBottom_checkbox.setObjectName("summaryValue")
        # EDITOR WIDGETS
        # Create the model and set column headers
        self.editor_model = QStandardItemModel(0, 5)
        self.editor_model.setHorizontalHeaderLabels(
            ["Name", "PackageId", "Rule source", "Rule type", "Comment"]
        )
        # Create the table view and set the model
        self.editor_delegate = EditableDelegate()
        self.editor_delegate.comment_edited_signal.connect(
            self._comment_edited
        )  # Connect the signal to the slot
        self.editor_table_view = QTableView()
        self.editor_table_view.setCornerButtonEnabled(False)
        self.editor_table_view.setModel(self.editor_model)
        self.editor_table_view.setSortingEnabled(True)  # Enable sorting on the columns
        self.editor_table_view.setItemDelegate(
            self.editor_delegate
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
            str(
                AppInfo().theme_data_folder
                / "default-icons"
                / "save_community_rules.png"
            )
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
        self.editor_save_user_rules_icon = QIcon(
            str(AppInfo().theme_data_folder / "default-icons" / "save_user_rules.png")
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
        self.mods_search.setPlaceholderText("Search mods by name")
        self.mods_search_clear_button = self.mods_search.findChild(QToolButton)
        self.mods_search_clear_button.setEnabled(True)
        self.mods_search_clear_button.clicked.connect(self.clear_mods_search)
        # Mods list
        self.mods_list = QListWidget()
        self.mods_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mods_list.customContextMenuRequested.connect(self.modItemContextMenuEvent)
        self.mods_list.setDragEnabled(True)

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
                self.external_user_rules_layout,
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
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadBottom_checkbox
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadAfter_label
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadAfter_list
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadBefore_label
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadBefore_list
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadBottom_checkbox
        )
        self.details_layout.addLayout(self.internal_local_metadata_layout)
        self.details_layout.addLayout(self.external_community_rules_layout)
        self.details_layout.addLayout(self.external_user_rules_layout)

        # Build the editor layouts
        self.editor_actions_layout.addWidget(self.editor_save_community_rules_button)
        self.editor_actions_layout.addWidget(self.editor_save_user_rules_button)
        self.editor_layout.addWidget(self.editor_table_view)
        self.editor_layout.addLayout(self.editor_actions_layout)

        # Build the mods layouts
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

        # Add our layouts to the main layouts
        self.layout.addWidget(self.mod_label)
        self.layout.addLayout(self.upper_layout, 66)
        self.layout.addLayout(self.lower_layout, 33)

        # Allow toggle layouts based on context
        if self.compact:
            self._toggle_details_layout_widgets(
                layout=self.internal_local_metadata_layout, override=True
            )
        else:
            self._toggle_details_layout_widgets(
                layout=self.internal_local_metadata_layout, override=False
            )
        # If no initial packageid supplied, lock checkboxes
        if not self.edit_packageid:
            self.external_community_rules_loadBottom_checkbox.setCheckable(False)
            self.external_user_rules_loadBottom_checkbox.setCheckable(False)
        # Initial mode
        if self.initial_mode == "community_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=False
            )
            self._toggle_details_layout_widgets(
                layout=self.external_user_rules_layout, override=True
            )
        elif self.initial_mode == "user_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=True
            )
            self._toggle_details_layout_widgets(
                layout=self.external_user_rules_layout, override=False
            )
        # Connect these after metadata population
        self.external_community_rules_loadBottom_checkbox.stateChanged.connect(
            partial(self._toggle_loadBottom_rule, "Community Rules")
        )
        self.external_user_rules_loadBottom_checkbox.stateChanged.connect(
            partial(self._toggle_loadBottom_rule, "User Rules")
        )
        # Setup the window
        self.setWindowTitle("RimSort - Rule Editor")
        self.setLayout(self.layout)
        self.setMinimumSize(QSize(800, 600))

    def createDropEvent(self, destination_list: QListWidget):
        def dropEvent(event):
            # If the item was sourced from mods list
            if event.source() == self.mods_list and self.edit_packageid:
                logger.debug("DROP")
                # Accept event
                event.setDropAction(Qt.CopyAction)
                event.accept()
                # Create new item for destination list & copy source item
                source_item = self.mods_list.currentItem()
                item_label = source_item.listWidget().itemWidget(source_item)
                item_label_text = item_label.text()
                rule_data = source_item.data(Qt.UserRole)
                copied_item = QListWidgetItem()
                copied_item.setData(Qt.UserRole, rule_data)
                # Create editor row & append rule to metadata after item is populated into the destination list
                # Determine action mode
                if destination_list is self.external_community_rules_loadAfter_list:
                    mode = ["Community Rules", "loadAfter"]

                elif destination_list is self.external_community_rules_loadBefore_list:
                    mode = ["Community Rules", "loadBefore"]

                elif destination_list is self.external_user_rules_loadAfter_list:
                    mode = ["User Rules", "loadAfter"]

                elif destination_list is self.external_user_rules_loadBefore_list:
                    mode = ["User Rules", "loadBefore"]
                # Append row
                # Search for & remove the rule's row entry from the editor table
                for row in range(self.editor_model.rowCount()):
                    # Define criteria
                    packageid_value = self.editor_model.item(
                        row, 1
                    )  # Get the item in column 2 (index 1)
                    rule_source_value = self.editor_model.item(
                        row, 2
                    )  # Get the item in column 3 (index 2)
                    rule_type_value = self.editor_model.item(
                        row, 3
                    )  # Get the item in column 4 (index 3)
                    # Search table for rows that match.
                    if (
                        (packageid_value and rule_data in packageid_value.text())
                        and (rule_source_value and mode[0] in rule_source_value.text())
                        and (rule_type_value and mode[1] in rule_type_value.text())
                    ):
                        show_warning(
                            title="Duplicate rule",
                            text="Tried to add duplicate rule.",
                            information="Skipping creation of duplicate rule!",
                        )
                        return
                # If we don't find anything existing that matches...
                # Add the item to the destination list
                destination_list.addItem(copied_item)
                destination_list.setItemWidget(copied_item, QLabel(item_label_text))
                # Add a new row in the editor - prompt user to enter a comment for their rule addition
                args, ok = show_dialogue_input(
                    title="Enter comment",
                    text="Enter a comment to annotate why this rule exists. This is useful for your own records, as well as others.",
                )
                if ok:
                    comment = args
                else:
                    comment = ""
                # Populate new row for our rule
                self._add_rule_to_table(
                    item_label_text, rule_data, mode[0], mode[1], comment
                )
                # Select database for editing
                if mode[0] == "Community Rules":
                    metadata = self.community_rules
                elif mode[0] == "User Rules":
                    metadata = self.user_rules
                # Add rule to the database if it doesn't already exist
                if not metadata.get(self.edit_packageid):
                    metadata[self.edit_packageid] = {}
                if not metadata[self.edit_packageid].get(mode[1]):
                    metadata[self.edit_packageid][mode[1]] = {}
                if not metadata[self.edit_packageid][mode[1]].get(rule_data):
                    metadata[self.edit_packageid][mode[1]][rule_data] = {}
                metadata[self.edit_packageid][mode[1]][rule_data][
                    "name"
                ] = item_label_text
                metadata[self.edit_packageid][mode[1]][rule_data]["comment"] = comment
            else:
                event.ignore()

        return dropEvent

    # RULES

    def _add_rule_to_table(
        self,
        name: str,
        packageid: str,
        rule_source: str,
        rule_type: str,
        comment: str,
        hidden=None,
    ) -> None:
        if not self.edit_packageid:
            return
        logger.debug(
            f"Adding {rule_source} {rule_type} rule to mod {self.edit_packageid} with comment: {comment}"
        )
        # Create the standard items for each column
        items = [
            QStandardItem(name),
            QStandardItem(packageid),
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
        logger.debug("Clearing editor")
        self.clear_mods_search()
        self.mods_list.clear()
        self.local_metadata_loadAfter_list.clear()
        self.local_metadata_loadBefore_list.clear()
        self.external_community_rules_loadAfter_list.clear()
        self.external_community_rules_loadBefore_list.clear()
        self.external_user_rules_loadAfter_list.clear()
        self.external_user_rules_loadBefore_list.clear()
        self.editor_model.removeRows(0, self.editor_model.rowCount())

    def _comment_edited(self, instruction: list) -> None:
        if self.edit_packageid:
            # Select metadata
            if instruction[2] == "Community Rules":
                metadata = self.community_rules
            elif instruction[2] == "User Rules":
                metadata = self.user_rules
            # Edit based on type of rule
            if instruction[3] == "loadAfter" or instruction[3] == "loadBefore":
                metadata[self.edit_packageid][instruction[3]][instruction[1]][
                    "comment"
                ] = instruction[4]
            elif instruction[3] == "loadBottom":
                metadata[self.edit_packageid][instruction[3]]["comment"] = instruction[
                    4
                ]

    def _create_list_item(self, _list: QListWidget, title: str, metadata=None) -> None:
        # Create our list item
        item = QListWidgetItem()
        if metadata:
            item.setData(Qt.UserRole, metadata)
            if _list == self.mods_list:
                item.setToolTip(metadata)
            else:
                item.setToolTip(title)
        # Set list item label
        label = QLabel(title)
        label.setObjectName("ListItemLabel")
        # Set the size hint of the item to be the size of the label
        item.setSizeHint(label.sizeHint())
        # add to our list
        _list.addItem(item)
        _list.setItemWidget(item, label)

    def _open_mod_in_editor(self, context_item: QListWidgetItem) -> None:
        logger.debug(f"Opening mod in editor: {self.edit_packageid}")
        self.edit_packageid = context_item.data(Qt.UserRole)
        if self.edit_packageid:
            self.external_community_rules_loadBottom_checkbox.setCheckable(True)
            self.external_user_rules_loadBottom_checkbox.setCheckable(True)
        self._clear_widget()
        self._populate_from_metadata()

    def _populate_from_metadata(self) -> None:
        logger.debug(f"Populating editor from metadata with mod: {self.edit_packageid}")
        logger.debug("Parsing local metadata")
        if (
            self.metadata_manager.internal_local_metadata
            and len(self.metadata_manager.internal_local_metadata.keys()) > 0
        ):
            for metadata in self.metadata_manager.internal_local_metadata.values():
                # Local metadata rulez
                # Additionally, populate anything that is not exit_packageid into the mods list
                if (
                    metadata.get("packageid")
                    and self.edit_packageid
                    and metadata["packageid"].lower() == self.edit_packageid.lower()
                ):
                    self.edit_name = metadata["name"]
                    self.mod_label.setText(f"Editing rules for: {self.edit_name}")
                    if metadata.get("loadafter") and metadata["loadafter"].get("li"):
                        loadAfters = metadata["loadafter"]["li"]
                        if isinstance(loadAfters, str):
                            self._create_list_item(
                                _list=self.local_metadata_loadAfter_list,
                                title=(
                                    self.steam_workshop_metadata_packageids_to_name[
                                        loadAfters.lower()
                                    ]
                                    if loadAfters.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                    ]
                                    else loadAfters
                                ),
                                metadata=loadAfters,
                            )
                            self._add_rule_to_table(
                                name=(
                                    self.steam_workshop_metadata_packageids_to_name[
                                        loadAfters.lower()
                                    ]
                                    if loadAfters.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                    ]
                                    else loadAfters
                                ),
                                packageid=loadAfters,
                                rule_source="About.xml",
                                rule_type="loadAfter",
                                comment="Added from mod metadata",
                                hidden=self.local_rules_hidden,
                            )
                        elif isinstance(loadAfters, list):
                            for rule in loadAfters:
                                self._create_list_item(
                                    _list=self.local_metadata_loadAfter_list,
                                    title=(
                                        self.steam_workshop_metadata_packageids_to_name[
                                            rule.lower()
                                        ]
                                        if rule.lower()
                                        in [
                                            key.lower()
                                            for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                        ]
                                        else rule
                                    ),
                                    metadata=rule,
                                )
                                self._add_rule_to_table(
                                    name=(
                                        self.steam_workshop_metadata_packageids_to_name[
                                            rule.lower()
                                        ]
                                        if rule.lower()
                                        in [
                                            key.lower()
                                            for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                        ]
                                        else rule
                                    ),
                                    packageid=rule,
                                    rule_source="About.xml",
                                    rule_type="loadAfter",
                                    comment="Added from mod metadata",
                                    hidden=self.local_rules_hidden,
                                )
                    if metadata.get("loadbefore") and metadata["loadbefore"].get("li"):
                        loadBefores = metadata["loadbefore"]["li"]
                        if isinstance(loadBefores, str):
                            self._create_list_item(
                                _list=self.local_metadata_loadBefore_list,
                                title=(
                                    self.steam_workshop_metadata_packageids_to_name[
                                        loadBefores.lower()
                                    ]
                                    if loadBefores.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                    ]
                                    else loadBefores
                                ),
                                metadata=loadBefores,
                            )
                            self._add_rule_to_table(
                                name=(
                                    self.steam_workshop_metadata_packageids_to_name[
                                        loadBefores.lower()
                                    ]
                                    if loadBefores.lower()
                                    in [
                                        key.lower()
                                        for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                    ]
                                    else loadBefores
                                ),
                                packageid=loadBefores,
                                rule_source="About.xml",
                                rule_type="loadBefore",
                                comment="Added from mod metadata",
                                hidden=self.local_rules_hidden,
                            )
                        elif isinstance(loadBefores, list):
                            for rule in loadBefores:
                                self._create_list_item(
                                    _list=self.local_metadata_loadBefore_list,
                                    title=(
                                        self.steam_workshop_metadata_packageids_to_name[
                                            rule.lower()
                                        ]
                                        if rule.lower()
                                        in [
                                            key.lower()
                                            for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                        ]
                                        else rule
                                    ),
                                    metadata=rule,
                                )
                                self._add_rule_to_table(
                                    name=(
                                        self.steam_workshop_metadata_packageids_to_name[
                                            rule.lower()
                                        ]
                                        if rule.lower()
                                        in [
                                            key.lower()
                                            for key in self.steam_workshop_metadata_packageids_to_name.keys()
                                        ]
                                        else rule
                                    ),
                                    packageid=rule,
                                    rule_source="About.xml",
                                    rule_type="loadBefore",
                                    comment="Added from mod metadata",
                                    hidden=self.local_rules_hidden,
                                )
                else:  # Otherwise, add everything else to the mod list
                    self._create_list_item(
                        _list=self.mods_list,
                        title=metadata.get("name"),
                        metadata=metadata.get("packageid"),
                    )
        logger.debug("Parsing Community Rules")
        # Community Rules rulez
        if (
            self.community_rules
            and len(self.community_rules.keys()) > 0
            and self.edit_packageid
        ):
            for packageid, metadata in self.community_rules.items():
                if (
                    self.edit_packageid
                    and self.edit_packageid.lower() == packageid.lower()
                ):
                    if metadata.get("loadAfter"):
                        for rule_id, rule_data in metadata["loadAfter"].items():
                            self._create_list_item(
                                _list=self.external_community_rules_loadAfter_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule_to_table(
                                name=rule_data["name"][0],
                                packageid=rule_id,
                                rule_source="Community Rules",
                                rule_type="loadAfter",
                                comment=(
                                    rule_data["comment"][0]
                                    if rule_data.get("comment")
                                    else ""
                                ),
                                hidden=self.community_rules_hidden,
                            )
                    if metadata.get("loadBefore"):
                        for rule_id, rule_data in metadata["loadBefore"].items():
                            self._create_list_item(
                                _list=self.external_community_rules_loadBefore_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule_to_table(
                                name=rule_data["name"][0],
                                packageid=rule_id,
                                rule_source="Community Rules",
                                rule_type="loadBefore",
                                comment=(
                                    rule_data["comment"][0]
                                    if rule_data.get("comment")
                                    else ""
                                ),
                                hidden=self.community_rules_hidden,
                            )
                    if metadata.get("loadBottom") and metadata["loadBottom"].get(
                        "value"
                    ):
                        self.block_comment_prompt = True
                        self.external_community_rules_loadBottom_checkbox.setChecked(
                            True
                        )
                        self.block_comment_prompt = False
                        self._add_rule_to_table(
                            name=self.edit_name,
                            packageid=self.edit_packageid,
                            rule_source="Community Rules",
                            rule_type="loadBottom",
                            comment=(
                                rule_data["comment"][0]
                                if rule_data.get("comment")
                                else ""
                            ),
                            hidden=self.community_rules_hidden,
                        )
        logger.debug("Parsing User Rules")
        # User Rules rulez
        if self.user_rules and len(self.user_rules.keys()) > 0 and self.edit_packageid:
            for packageid, metadata in self.user_rules.items():
                if (
                    self.edit_packageid
                    and self.edit_packageid.lower() == packageid.lower()
                ):
                    if metadata.get("loadAfter"):
                        for rule_id, rule_data in metadata["loadAfter"].items():
                            self._create_list_item(
                                _list=self.external_user_rules_loadAfter_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule_to_table(
                                name=rule_data["name"][0],
                                packageid=rule_id,
                                rule_source="User Rules",
                                rule_type="loadAfter",
                                comment=(
                                    rule_data["comment"][0]
                                    if rule_data.get("comment")
                                    else ""
                                ),
                                hidden=self.user_rules_hidden,
                            )
                    if metadata.get("loadBefore"):
                        for rule_id, rule_data in metadata["loadBefore"].items():
                            self._create_list_item(
                                _list=self.external_user_rules_loadBefore_list,
                                title=rule_data["name"][0],
                                metadata=rule_id,
                            )
                            self._add_rule_to_table(
                                name=rule_data["name"][0],
                                packageid=rule_id,
                                rule_source="User Rules",
                                rule_type="loadBefore",
                                comment=(
                                    rule_data["comment"][0]
                                    if rule_data.get("comment")
                                    else ""
                                ),
                                hidden=self.user_rules_hidden,
                            )
                    if metadata.get("loadBottom") and metadata["loadBottom"].get(
                        "value"
                    ):
                        self.block_comment_prompt = True
                        self.external_user_rules_loadBottom_checkbox.setChecked(True)
                        self._add_rule_to_table(
                            name=self.edit_name,
                            packageid=self.edit_packageid,
                            rule_source="User Rules",
                            rule_type="loadBottom",
                            comment=(
                                rule_data["comment"][0]
                                if rule_data.get("comment")
                                else ""
                            ),
                            hidden=self.user_rules_hidden,
                        )
                        self.block_comment_prompt = False

    def _remove_rule(self, context_item: QListWidgetItem, _list: QListWidget) -> None:
        logger.debug(f"Removing rule from mod: {self.edit_packageid}")
        _list.takeItem(_list.row(context_item))
        rule_data = context_item.data(Qt.UserRole)
        # Determine action mode
        if _list is self.external_community_rules_loadAfter_list:
            mode = ["Community Rules", "loadAfter"]

        elif _list is self.external_community_rules_loadBefore_list:
            mode = ["Community Rules", "loadBefore"]

        elif _list is self.external_user_rules_loadAfter_list:
            mode = ["User Rules", "loadAfter"]

        elif _list is self.external_user_rules_loadBefore_list:
            mode = ["User Rules", "loadBefore"]
        # Select database for editing
        if mode[0] == "Community Rules":
            metadata = self.community_rules
        elif mode[0] == "User Rules":
            metadata = self.user_rules
        # Search for & remove the rule's row entry from the editor table
        for row in range(self.editor_model.rowCount()):
            # Define criteria
            packageid_value = self.editor_model.item(
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
                (packageid_value and rule_data in packageid_value.text())
                and (rule_source_value and mode[0] in rule_source_value.text())
                and (rule_type_value and mode[1] in rule_type_value.text())
            ):  # Remove row if criteria matches search
                self.editor_model.removeRow(row)
        # Remove rule from the database
        if metadata.get(self.edit_packageid, {}).get(mode[1], {}).get(rule_data):
            metadata[self.edit_packageid][mode[1]].pop(rule_data)

    def _save_editor_rules(self, rules_source: str) -> None:
        logger.debug(f"Updating rules source: {rules_source}")
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
            elif layout is self.external_user_rules_layout:
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
            elif layout is self.external_user_rules_layout:
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

    def _toggle_loadBottom_rule(self, rule_source: str, state) -> None:
        if self.edit_packageid:
            logger.debug(f"Toggle loadBottom for {self.edit_packageid}: {state}")
            # Select database for editing
            if rule_source == "Community Rules":
                metadata = self.community_rules
            elif rule_source == "User Rules":
                metadata = self.user_rules
            if state == 2:
                comment = None
                if not self.block_comment_prompt:
                    # Add a new row in the editor - prompt user to enter a comment for their rule addition
                    args, ok = show_dialogue_input(
                        title="Enter comment",
                        text="Enter a comment to annotate why this rule exists. This is useful for your own records, as well as others.",
                    )
                    if ok:
                        comment = args
                    self._add_rule_to_table(
                        name=self.edit_name,
                        packageid=self.edit_packageid,
                        rule_source=rule_source,
                        rule_type="loadBottom",
                        comment=comment if comment else "",
                    )
                # Add rule to the database if it doesn't already exist
                if not metadata.get(self.edit_packageid):
                    metadata[self.edit_packageid] = {}
                if not metadata[self.edit_packageid].get("loadBottom"):
                    metadata[self.edit_packageid]["loadBottom"] = {}
                metadata[self.edit_packageid]["loadBottom"]["value"] = True
                if comment:
                    metadata[self.edit_packageid]["loadBottom"]["comment"] = comment
            else:
                # Search for & remove the rule's row entry from the editor table
                for row in range(self.editor_model.rowCount()):
                    # Define criteria
                    packageid_value = self.editor_model.item(
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
                        (
                            packageid_value
                            and self.edit_packageid in packageid_value.text()
                        )
                        and (
                            rule_source_value
                            and rule_source in rule_source_value.text()
                        )
                        and (rule_type_value and "loadBottom" in rule_type_value.text())
                    ):  # Remove row if criteria matches search
                        self.editor_model.removeRow(row)
                # Remove rule from the database
                if (
                    metadata.get(self.edit_packageid, {})
                    .get("loadBottom", {})
                    .get("value")
                ):
                    metadata[self.edit_packageid].pop("loadBottom")

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
            name = item.listWidget().itemWidget(item).text()
            if pattern and name and not pattern.lower() in name.lower():
                item.setHidden(True)
            else:
                item.setHidden(False)
