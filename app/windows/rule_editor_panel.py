from functools import partial
from typing import Any, Callable

from loguru import logger
from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    Qt,
    Signal,
)
from PySide6.QtGui import QDropEvent, QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QItemDelegate,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.app_info import AppInfo
from app.utils.metadata import MetadataManager
from app.views.dialogue import show_dialogue_input, show_warning


class EditableDelegate(QItemDelegate):
    comment_edited_signal = Signal(
        list
    )  # signal connects to _do_update_rules_database in main_content_panel.py

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        if index.column() == 4:  # Check if it's the 5th column
            model = index.model()
            column3_value = model.index(
                index.row(), 2
            ).data()  # Get the value of the 3rd column

            # Add detailed logging for debugging
            logger.debug(
                f"Attempting to create editor for row {index.row()}, column {index.column()}"
            )
            logger.debug(f"Column 3 value: {column3_value}")

            if column3_value in [
                "Community Rules",
                "User Rules",
            ]:  # Only create an editor if the condition is met
                editor = super().createEditor(parent, option, index)
                return editor

            # Provide more informative error message if editor creation fails
            if column3_value not in ["About.xml"]:
                error_msg = (
                    f"Editor creation failed! for Column 3 value '{column3_value}' "
                )
                logger.error(error_msg)

        # Handle case where wrong column is being edited
        return QLineEdit(parent, readOnly=True)  # Return a basic editor as fallback

    def setEditorData(
        self, editor: QWidget, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if index.column() == 4:  # Only set data for the 5th column
            super().setEditorData(editor, index)

    def setModelData(
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if index.column() == 4:  # Only set data for the 5th column
            super().setModelData(editor, model, index)
            # Send the column data back to the editor so we can update the metadata
            # edited_data = model.data(index, Qt.DisplayRole)  # Get the edited data
            column_values = [
                model.data(
                    model.index(index.row(), column), Qt.ItemDataRole.DisplayRole
                )
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

    # Type annotations for class variables
    mods_list: QListWidget
    local_metadata_button: QPushButton
    community_rules_button: QPushButton
    user_rules_button: QPushButton

    def __init__(
        self,
        initial_mode: str,
        compact: bool | None = None,
        edit_packageid: str | None = None,
    ) -> None:
        super().__init__()
        logger.debug("Initializing RuleEditor")

        # Cache MetadataManager instance
        self.metadata_manager = MetadataManager.instance()

        # STYLESHEET
        self.setObjectName("RuleEditor")

        # LAUNCH OPTIONS
        self.block_comment_prompt = (
            False  # Used to block comment prompt when metadata is being populated
        )
        self.compact = compact
        self.edit_packageid = edit_packageid
        self.initial_mode = initial_mode
        # THE METADATA
        self.local_rules_hidden: bool = False
        self.community_rules = (
            self.metadata_manager.external_community_rules.copy()
            if self.metadata_manager.external_community_rules
            else {}
        )
        self.community_rules_hidden: bool = False
        self.user_rules = (
            self.metadata_manager.external_user_rules.copy()
            if self.metadata_manager.external_user_rules
            else {}
        )
        self.user_rules_hidden: bool = False
        # Can be used to get proper names for mods found in list
        # items that are not locally available
        self.steam_workshop_metadata_packageids_to_name = {}
        external_steam_metadata = self.metadata_manager.external_steam_metadata
        if external_steam_metadata and len(external_steam_metadata.keys()) > 0:
            for metadata in external_steam_metadata.values():
                package_id = metadata.get("packageId") or metadata.get("packageid")
                if package_id:
                    self.steam_workshop_metadata_packageids_to_name[package_id] = (
                        metadata["name"]
                    )

        # MOD LABEL
        self.mod_label = QLabel(self.tr("No mod currently being edited"))
        self.mod_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # CONTAINER LAYOUTS
        self.upper_layout = QHBoxLayout()
        self.lower_layout = QVBoxLayout()
        layout = QVBoxLayout()

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
        self.local_metadata_loadAfter_label = QLabel(self.tr("About.xml (loadAfter)"))
        self.local_metadata_loadBefore_label = QLabel(self.tr("About.xml (loadBefore)"))
        self.local_metadata_incompatibilities_label = QLabel(
            self.tr("About.xml (incompatibilitiesWith)")
        )
        self.local_metadata_loadAfter_list = QListWidget()
        self.local_metadata_loadBefore_list = QListWidget()
        self.local_metadata_incompatibilities_list = QListWidget()

        # community rules
        self.external_community_rules_loadAfter_label = QLabel(
            self.tr("Community Rules (loadAfter)")
        )
        self.external_community_rules_loadBefore_label = QLabel(
            self.tr("Community Rules (loadBefore)")
        )
        self.external_community_rules_incompatibilities_label = QLabel(
            self.tr("Community Rules (incompatibilitiesWith)")
        )
        self.external_community_rules_loadAfter_list = QListWidget()
        self.external_community_rules_loadAfter_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_community_rules_loadAfter_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_community_rules_loadAfter_list,
            )
        )
        self.external_community_rules_loadAfter_list.setAcceptDrops(True)
        self.external_community_rules_loadAfter_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_community_rules_loadAfter_list.dropEvent = self.createDropEvent(  # type: ignore
            self.external_community_rules_loadAfter_list
        )
        self.external_community_rules_loadBefore_list = QListWidget()
        self.external_community_rules_loadBefore_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_community_rules_loadBefore_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_community_rules_loadBefore_list,
            )
        )
        self.external_community_rules_loadBefore_list.setAcceptDrops(True)
        self.external_community_rules_loadBefore_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_community_rules_loadBefore_list.dropEvent = self.createDropEvent(  # type: ignore
            self.external_community_rules_loadBefore_list
        )
        self.external_community_rules_loadTop_checkbox = QCheckBox(
            self.tr("Force load at top of list")
        )
        self.external_community_rules_loadTop_checkbox.setObjectName("summaryValue")
        self.external_community_rules_loadBottom_checkbox = QCheckBox(
            self.tr("Force load at bottom of list")
        )
        self.external_community_rules_loadBottom_checkbox.setObjectName("summaryValue")
        self.external_community_rules_incompatibilities_list = QListWidget()
        self.external_community_rules_incompatibilities_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_community_rules_incompatibilities_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_community_rules_incompatibilities_list,
            )
        )
        self.external_community_rules_incompatibilities_list.setAcceptDrops(True)
        self.external_community_rules_incompatibilities_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_community_rules_incompatibilities_list.dropEvent = (  # type: ignore
            self.createDropEvent(self.external_community_rules_incompatibilities_list)
        )
        # user rules
        self.external_user_rules_loadAfter_label = QLabel(
            self.tr("User Rules (loadAfter)")
        )
        self.external_user_rules_loadBefore_label = QLabel(
            self.tr("User Rules (loadBefore)")
        )
        self.external_user_rules_incompatibilities_label = QLabel(
            self.tr("User Rules (incompatibilitiesWith)")
        )
        self.external_user_rules_loadAfter_list = QListWidget()
        self.external_user_rules_loadAfter_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_user_rules_loadAfter_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_user_rules_loadAfter_list,
            )
        )
        self.external_user_rules_loadAfter_list.setAcceptDrops(True)
        self.external_user_rules_loadAfter_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_user_rules_loadAfter_list.dropEvent = self.createDropEvent(  # type: ignore
            self.external_user_rules_loadAfter_list
        )
        self.external_user_rules_loadBefore_list = QListWidget()
        self.external_user_rules_loadBefore_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_user_rules_loadBefore_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_user_rules_loadBefore_list,
            )
        )
        self.external_user_rules_loadBefore_list.setAcceptDrops(True)
        self.external_user_rules_loadBefore_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_user_rules_loadBefore_list.dropEvent = self.createDropEvent(  # type: ignore
            self.external_user_rules_loadBefore_list
        )
        self.external_user_rules_loadTop_checkbox = QCheckBox(
            self.tr("Force load at top of list")
        )
        self.external_user_rules_loadTop_checkbox.setObjectName("summaryValue")
        self.external_user_rules_loadBottom_checkbox = QCheckBox(
            self.tr("Force load at bottom of list")
        )
        self.external_user_rules_loadBottom_checkbox.setObjectName("summaryValue")
        self.external_user_rules_incompatibilities_list = QListWidget()
        self.external_user_rules_incompatibilities_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.external_user_rules_incompatibilities_list.customContextMenuRequested.connect(
            partial(
                self.ruleItemContextMenuEvent,
                _list=self.external_user_rules_incompatibilities_list,
            )
        )
        self.external_user_rules_incompatibilities_list.setAcceptDrops(True)
        self.external_user_rules_incompatibilities_list.setDragDropMode(
            QListWidget.DragDropMode.DropOnly
        )
        self.external_user_rules_incompatibilities_list.dropEvent = (  # type: ignore
            self.createDropEvent(self.external_user_rules_incompatibilities_list)
        )
        # EDITOR WIDGETS
        # Create the model and set column headers
        self.editor_model = QStandardItemModel(0, 5)
        self.editor_model.setHorizontalHeaderLabels(
            [
                self.tr("Name"),
                self.tr("PackageId"),
                self.tr("Rule source"),
                self.tr("Rule type"),
                self.tr("Comment"),
            ]
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
            QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.EditKeyPressed
        )  # Enable editing
        # Set default stretch for each column
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.editor_table_view.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
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
            self.tr("Save rules to communityRules.json")
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
        self.editor_save_user_rules_button.setToolTip(
            self.tr("Save rules to userRules.json")
        )
        self.editor_save_user_rules_button.setIcon(self.editor_save_user_rules_icon)
        self.editor_save_user_rules_button.clicked.connect(
            partial(self._save_editor_rules, rules_source="User Rules")
        )
        # MODS WIDGETS
        # Mods search
        self.mods_search = QLineEdit()
        self.mods_search.setClearButtonEnabled(True)
        self.mods_search.textChanged.connect(self.signal_mods_search)
        self.mods_search.setPlaceholderText(self.tr("Search mods by name"))
        self.mods_search_clear_button: object | QToolButton | None = (
            self.mods_search.findChild(QToolButton)
        )
        if type(self.mods_search_clear_button) is not QToolButton:
            raise Exception("Failed to find clear button in QLineEdit")
        if self.mods_search_clear_button is not None:
            self.mods_search_clear_button.setEnabled(True)
            self.mods_search_clear_button.clicked.connect(self.clear_mods_search)
        # Mods list
        self.mods_list = QListWidget()
        self.mods_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mods_list.customContextMenuRequested.connect(self.modItemContextMenuEvent)
        self.mods_list.setDragEnabled(True)

        # Actions
        self.local_metadata_button = QPushButton()
        self.local_metadata_button.clicked.connect(
            partial(
                self._toggle_details_layout_widgets,
                self.internal_local_metadata_layout,
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
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_incompatibilities_label
        )
        self.internal_local_metadata_layout.addWidget(
            self.local_metadata_incompatibilities_list
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
            self.external_community_rules_loadTop_checkbox
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_loadBottom_checkbox
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_incompatibilities_label
        )
        self.external_community_rules_layout.addWidget(
            self.external_community_rules_incompatibilities_list
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
            self.external_user_rules_loadTop_checkbox
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_loadBottom_checkbox
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_incompatibilities_label
        )
        self.external_user_rules_layout.addWidget(
            self.external_user_rules_incompatibilities_list
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
        layout.addWidget(self.mod_label)
        layout.addLayout(self.upper_layout, 66)
        layout.addLayout(self.lower_layout, 33)

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
            self.external_community_rules_loadTop_checkbox.setCheckable(False)
            self.external_user_rules_loadTop_checkbox.setCheckable(False)
            self.external_community_rules_loadBottom_checkbox.setCheckable(False)
            self.external_user_rules_loadBottom_checkbox.setCheckable(False)
        # Initial mode
        if self.initial_mode == "community_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=False
            )
            self._toggle_details_layout_widgets(
                layout=self.external_user_rules_layout, override=False
            )
        elif self.initial_mode == "user_rules":
            self._toggle_details_layout_widgets(
                layout=self.external_community_rules_layout, override=False
            )
            self._toggle_details_layout_widgets(
                layout=self.external_user_rules_layout, override=False
            )
        # Connect these after metadata population
        self.external_community_rules_loadTop_checkbox.stateChanged.connect(
            partial(self._toggle_loadTop_rule, "Community Rules")
        )
        self.external_community_rules_loadBottom_checkbox.stateChanged.connect(
            partial(self._toggle_loadBottom_rule, "Community Rules")
        )
        self.external_user_rules_loadTop_checkbox.stateChanged.connect(
            partial(self._toggle_loadTop_rule, "User Rules")
        )
        self.external_user_rules_loadBottom_checkbox.stateChanged.connect(
            partial(self._toggle_loadBottom_rule, "User Rules")
        )
        # Setup the window
        self.setWindowTitle("RimSort - Rule Editor")
        self.setLayout(layout)
        # Set the window size
        self.resize(900, 600)

    def createDropEvent(
        self, destination_list: QListWidget
    ) -> Callable[[QDropEvent], None]:
        def dropEvent(event: QDropEvent) -> None:
            # If the item was sourced from mods list
            if event.source() == self.mods_list and self.edit_packageid:
                logger.debug("DROP")
                # Accept event
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                # Create new item for destination list & copy source item
                source_item = self.mods_list.currentItem()
                item_label = source_item.listWidget().itemWidget(source_item)
                assert isinstance(item_label, QLabel)
                item_label_text = item_label.text()
                rule_data = source_item.data(Qt.ItemDataRole.UserRole)
                copied_item = QListWidgetItem()
                copied_item.setData(Qt.ItemDataRole.UserRole, rule_data)
                # Create editor row & append rule to metadata after item is populated into the destination list
                # Determine action mode
                if destination_list is self.external_community_rules_loadAfter_list:
                    mode = ["Community Rules", "loadAfter"]

                elif destination_list is self.external_community_rules_loadBefore_list:
                    mode = ["Community Rules", "loadBefore"]

                elif (
                    destination_list
                    is self.external_community_rules_incompatibilities_list
                ):
                    mode = ["Community Rules", "incompatibleWith"]

                elif destination_list is self.external_user_rules_loadAfter_list:
                    mode = ["User Rules", "loadAfter"]

                elif destination_list is self.external_user_rules_loadBefore_list:
                    mode = ["User Rules", "loadBefore"]

                elif (
                    destination_list is self.external_user_rules_incompatibilities_list
                ):
                    mode = ["User Rules", "incompatibleWith"]

                else:
                    logger.error(f"Invalid destination list!: {destination_list}")
                    event.ignore()
                    return
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
                        (packageid_value and rule_data == packageid_value.text())
                        and (rule_source_value and mode[0] == rule_source_value.text())
                        and (rule_type_value and mode[1] == rule_type_value.text())
                    ):
                        show_warning(
                            title=self.tr("Duplicate rule"),
                            text=self.tr("Tried to add duplicate rule."),
                            information=self.tr("Skipping creation of duplicate rule!"),
                        )
                        return
                # If we don't find anything existing that matches...
                # Add the item to the destination list
                destination_list.addItem(copied_item)
                destination_list.setItemWidget(copied_item, QLabel(item_label_text))
                # Add a new row in the editor - prompt user to enter a comment for their rule addition
                args, ok = show_dialogue_input(
                    title=self.tr("Enter comment"),
                    label=self.tr("""Enter a comment to annotate why this rule exists.
                      This is useful for your own records, as well as others."""),
                )
                if ok:
                    comment = args
                else:
                    comment = ""
                # Populate new row for our rule
                self._add_rule_to_table(
                    item_label_text,
                    rule_data,
                    mode[0],
                    mode[1],
                    comment=comment,
                )
                # Select database for editing
                if mode[0] == "Community Rules":
                    metadata = self.community_rules
                elif mode[0] == "User Rules":
                    metadata = self.user_rules
                else:
                    logger.error(f"Invalid mode!: {mode[0]}")
                    event.ignore()
                    return
                # Add rule to the database if it doesn't already exist
                if not metadata.get(self.edit_packageid):
                    metadata[self.edit_packageid] = {}
                if not metadata[self.edit_packageid].get(mode[1]):
                    metadata[self.edit_packageid][mode[1]] = {}
                if not metadata[self.edit_packageid][mode[1]].get(rule_data):
                    metadata[self.edit_packageid][mode[1]][rule_data] = {}
                metadata[self.edit_packageid][mode[1]][rule_data]["name"] = (
                    item_label_text
                )
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
        hidden: bool = False,
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
        # Show tooltip for the items
        items[0].setToolTip(name)
        if rule_source == "About.xml":
            tooltip_comment = self.tr(
                "Rules from mods's About.xml cannot be modified. Only 'Community Rules' and 'User Rules' are allowed."
            )
            items[1].setToolTip(tooltip_comment)
            items[2].setToolTip(tooltip_comment)
            items[3].setToolTip(tooltip_comment)
            items[4].setToolTip(tooltip_comment)
        else:
            tooltip_comment = self.tr("Rules can be Modified.")
            items[1].setToolTip(tooltip_comment)
            items[2].setToolTip(tooltip_comment)
            items[3].setToolTip(tooltip_comment)
            items[4].setToolTip(tooltip_comment)

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
        self.local_metadata_incompatibilities_list.clear()
        self.external_community_rules_loadAfter_list.clear()
        self.external_community_rules_loadBefore_list.clear()
        self.external_community_rules_incompatibilities_list.clear()
        self.external_user_rules_loadAfter_list.clear()
        self.external_user_rules_loadBefore_list.clear()
        self.external_user_rules_incompatibilities_list.clear()
        self.editor_model.removeRows(0, self.editor_model.rowCount())

    def _comment_edited(self, instruction: list[str]) -> None:
        if self.edit_packageid:
            # Select metadata
            if instruction[2] == "Community Rules":
                metadata = self.community_rules
            elif instruction[2] == "User Rules":
                metadata = self.user_rules
            else:
                logger.error(f"Invalid rule source!: {instruction[2]}")
                return
            # Edit based on type of rule
            if (
                instruction[3] == "loadAfter"
                or instruction[3] == "loadBefore"
                or instruction[3] == "incompatibleWith"
            ):
                metadata[self.edit_packageid][instruction[3]][instruction[1]][
                    "comment"
                ] = instruction[4]
            elif instruction[3] == "loadTop":
                metadata[self.edit_packageid][instruction[3]]["comment"] = instruction[
                    4
                ]
            elif instruction[3] == "loadBottom":
                metadata[self.edit_packageid][instruction[3]]["comment"] = instruction[
                    4
                ]

    def _create_list_item(
        self, _list: QListWidget, title: str, metadata: str | None = None
    ) -> None:
        # Create our list item
        item = QListWidgetItem()
        if metadata:
            # Always store the packageId as UserRole for rule lists
            item.setData(Qt.ItemDataRole.UserRole, metadata)
            if _list == self.mods_list:
                item.setToolTip(metadata)
            else:
                item.setToolTip(title)
        # Set list item label
        label = QLabel(title)
        label.setObjectName("ListItemLabel")
        # Set the size hint of the item to be the size of the label
        item.setSizeHint(label.sizeHint())
        # Add to our list
        _list.addItem(item)
        _list.setItemWidget(item, label)

    def _open_mod_in_editor(self, context_item: QListWidgetItem) -> None:
        logger.debug(f"Opening mod in editor: {self.edit_packageid}")
        self.edit_packageid = context_item.data(Qt.ItemDataRole.UserRole)
        if self.edit_packageid:
            self.external_community_rules_loadTop_checkbox.setCheckable(True)
            self.external_user_rules_loadTop_checkbox.setCheckable(True)
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
                # Local metadata rule
                # Additionally, populate anything that is not exit_packageid into the mods list
                if (
                    metadata.get("packageid")
                    and self.edit_packageid
                    and metadata["packageid"].lower() == self.edit_packageid.lower()
                ):
                    self.edit_name = metadata["name"]
                    self.mod_label.setText(
                        self.tr("Editing rules for: {name}").format(name=self.edit_name)
                    )
                    # All Lowercase!!!
                    # cSpell:enableCompoundWords
                    rule_types = {
                        "loadafter": self.local_metadata_loadAfter_list,
                        "loadbefore": self.local_metadata_loadBefore_list,
                        "incompatiblewith": self.local_metadata_incompatibilities_list,
                    }

                    for rule_type, _list in rule_types.items():
                        if metadata.get(rule_type) and metadata[rule_type].get("li"):
                            rules = metadata[rule_type]["li"]
                            if isinstance(rules, str):
                                rules = [rules]
                            if isinstance(rules, list):
                                for rule in rules:
                                    name = self.steam_workshop_metadata_packageids_to_name.get(
                                        rule.lower(), rule
                                    )
                                    # Ensure name is a string
                                    name_str = str(name) if name is not None else rule
                                    self._create_list_item(_list=_list, title=name_str)
                                    self._add_rule_to_table(
                                        name=name_str,
                                        packageid=rule,
                                        rule_source="About.xml",
                                        rule_type=rule_type,
                                        comment="Added from mod metadata",
                                        hidden=self.local_rules_hidden,
                                    )
                else:  # Otherwise, add everything else to the mod list
                    self._create_list_item(
                        _list=self.mods_list,
                        title=metadata.get("name"),
                        metadata=metadata.get("packageid"),
                    )

        def _parse_rules(
            rules: dict[str, Any],
            loadAfter_list: QListWidget,
            loadBefore_list: QListWidget,
            loadTop_checkbox: QCheckBox,
            loadBottom_checkbox: QCheckBox,
            incompatibilities_list: QListWidget,
            hidden: bool,
            rule_source: str,
        ) -> None:
            """Parses rules from a given dictionary and populates the editor with them

            :param rules: The dictionary containing the rules
            :type rules: dict
            :param loadAfter_list: The QListWidget to populate with loadAfter rules
            :type loadAfter_list: QListWidget
            :param loadBefore_list: The QListWidget to populate with loadBefore rules
            :type loadBefore_list: QListWidget
            :param loadBottom_checkbox: The checkbox to set for loadBottom rules
            :type loadBottom_checkbox: QCheckBox
            :param incompatibilities_list: The QListWidget to populate with incompatiblewith rules
            :type incompatibilities_list: QListWidget
            :param hidden: Indicates if the rules should be hidden
            :type hidden: bool
            :param rule_source: The source of the rules
            :type rule_source: str
            """
            if not rules or not self.edit_packageid:
                return

            # TODO: Leaving for now in case case-insensitivity matters
            for packageid, metadata in rules.items():
                if self.edit_packageid.lower() != packageid.lower():
                    continue

                def _get_first_item_or_value(data: list[Any] | Any) -> Any:
                    return data[0] if isinstance(data, list) else data

                # Snake Case!
                for rule_type in ["loadAfter", "loadBefore", "incompatibleWith"]:
                    if not metadata.get(rule_type):
                        continue
                    for rule_id, rule_data in metadata[rule_type].items():
                        rule_name = _get_first_item_or_value(rule_data.get("name", ""))
                        rule_comment = _get_first_item_or_value(
                            rule_data.get("comment", "")
                        )

                        if not rule_name:
                            # Set rule name to the packageid if it's empty
                            rule_name = rule_id
                            logger.warning(
                                f"Rule name is missing for {rule_type} rule in mod {self.edit_packageid}."
                                f" Using packageid {rule_id} as name."
                            )

                        self._create_list_item(
                            _list=(
                                self._get_list_type(
                                    rule_type,
                                    loadAfter_list,
                                    loadBefore_list,
                                    incompatibilities_list,
                                )
                            ),
                            title=rule_name,
                            metadata=rule_id,
                        )
                        self._add_rule_to_table(
                            name=rule_name,
                            packageid=rule_id,
                            rule_source=rule_source,
                            rule_type=rule_type,
                            comment=rule_comment,
                            hidden=hidden,
                        )
                rule_data = metadata.get("loadTop")
                if rule_data:
                    self.block_comment_prompt = True
                    loadTop_checkbox.setChecked(rule_data.get("value", False))
                    self.block_comment_prompt = False
                    if rule_data.get("value"):
                        self._add_rule_to_table(
                            name=self.edit_name,
                            packageid=self.edit_packageid,
                            rule_source=rule_source,
                            rule_type="loadTop",
                            comment=_get_first_item_or_value(
                                rule_data.get("comment", "")
                            ),
                            hidden=hidden,
                        )

                rule_data = metadata.get("loadBottom")
                if rule_data:
                    self.block_comment_prompt = True
                    loadBottom_checkbox.setChecked(rule_data.get("value", False))
                    self.block_comment_prompt = False
                    if rule_data.get("value"):
                        self._add_rule_to_table(
                            name=self.edit_name,
                            packageid=self.edit_packageid,
                            rule_source=rule_source,
                            rule_type="loadBottom",
                            comment=_get_first_item_or_value(
                                rule_data.get("comment", "")
                            ),
                            hidden=hidden,
                        )

        logger.debug("Parsing Community Rules")
        # Community Rules rules
        _parse_rules(
            rules=self.community_rules,
            loadAfter_list=self.external_community_rules_loadAfter_list,
            loadBefore_list=self.external_community_rules_loadBefore_list,
            loadTop_checkbox=self.external_community_rules_loadTop_checkbox,
            loadBottom_checkbox=self.external_community_rules_loadBottom_checkbox,
            incompatibilities_list=self.external_community_rules_incompatibilities_list,
            hidden=self.community_rules_hidden,
            rule_source="Community Rules",
        )

        logger.debug("Parsing User Rules")
        # User Rules rules
        _parse_rules(
            rules=self.user_rules,
            loadAfter_list=self.external_user_rules_loadAfter_list,
            loadBefore_list=self.external_user_rules_loadBefore_list,
            loadTop_checkbox=self.external_user_rules_loadTop_checkbox,
            loadBottom_checkbox=self.external_user_rules_loadBottom_checkbox,
            incompatibilities_list=self.external_user_rules_incompatibilities_list,
            hidden=self.user_rules_hidden,
            rule_source="User Rules",
        )

    def _remove_rule(self, context_item: QListWidgetItem, _list: QListWidget) -> None:
        logger.debug(f"Removing rule from mod: {self.edit_packageid}")
        _list.takeItem(_list.row(context_item))
        rule_data = context_item.data(Qt.ItemDataRole.UserRole)
        # Determine action mode
        if _list is self.external_community_rules_loadAfter_list:
            mode = ["Community Rules", "loadAfter"]

        elif _list is self.external_community_rules_loadBefore_list:
            mode = ["Community Rules", "loadBefore"]

        elif _list is self.external_community_rules_incompatibilities_list:
            mode = ["Community Rules", "incompatibleWith"]

        elif _list is self.external_user_rules_loadAfter_list:
            mode = ["User Rules", "loadAfter"]

        elif _list is self.external_user_rules_loadBefore_list:
            mode = ["User Rules", "loadBefore"]

        elif _list is self.external_user_rules_incompatibilities_list:
            mode = ["User Rules", "incompatibleWith"]

        else:
            logger.error(f"Invalid list!: {_list}")
            return
        # Select database for editing
        if mode[0] == "Community Rules":
            metadata = self.community_rules
        elif mode[0] == "User Rules":
            metadata = self.user_rules
        else:
            logger.error(f"Invalid mode!: {mode[0]}")
            return

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
        if self.edit_packageid is not None and metadata.get(
            self.edit_packageid, {}
        ).get(mode[1], {}).get(rule_data):
            metadata[self.edit_packageid][mode[1]].pop(rule_data)

    def _save_editor_rules(self, rules_source: str) -> None:
        logger.debug(f"Updating rules source: {rules_source}")
        # Only emit the update signal; let main_content_panel.py handle disk writes
        if rules_source == "Community Rules":
            metadata = self.community_rules
        elif rules_source == "User Rules":
            metadata = self.user_rules
        else:
            raise ValueError(f"Invalid rule source: {rules_source}")
        self.update_database_signal.emit([rules_source, metadata])
        # Ensure cache and UI are refreshed after saving
        self.metadata_manager.refresh_cache()
        self._clear_widget()
        self._populate_from_metadata()

    def _toggle_details_layout_widgets(
        self, layout: QVBoxLayout, override: bool = False
    ) -> None:
        visibility = None
        # Iterate through all widgets in layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if widget is not None:
                if visibility is None:  # We only need to set this once per pass
                    visibility = widget.isVisible()
                    # Override so we can toggle this upon initialization if we want to
                    if override:
                        visibility = override
                # Toggle visibility of the widgets
                if visibility is not None:
                    widget.setVisible(not visibility)
        # Change button text based on the layout we are toggling
        # If this is True, it means the widgets are hidden. Edit btn text + hide rules to reflect.
        if visibility is None:
            logger.error("Visibility was not set and is None!")
            return
        if visibility:
            if layout is self.internal_local_metadata_layout:
                self.local_rules_hidden = True
                self.local_metadata_button.setText(self.tr("Show About.xml rules"))
                self._toggle_editor_table_rows(
                    rule_type="About.xml", visibility=visibility
                )
            elif layout is self.external_community_rules_layout:
                self.community_rules_hidden = True
                self.community_rules_button.setText(self.tr("Edit Community Rules"))
                self._toggle_editor_table_rows(
                    rule_type="Community Rules", visibility=visibility
                )
            elif layout is self.external_user_rules_layout:
                self.user_rules_hidden = True
                self.user_rules_button.setText(self.tr("Edit User Rules"))
                self._toggle_editor_table_rows(
                    rule_type="User Rules", visibility=visibility
                )
        else:
            if layout is self.internal_local_metadata_layout:
                self.local_rules_hidden = False
                self.local_metadata_button.setText(self.tr("Hide About.xml rules"))
                self._toggle_editor_table_rows(
                    rule_type="About.xml", visibility=visibility
                )
            elif layout is self.external_community_rules_layout:
                self.community_rules_hidden = False
                self.community_rules_button.setText(self.tr("Lock Community Rules"))
                self._toggle_editor_table_rows(
                    rule_type="Community Rules", visibility=visibility
                )
            elif layout is self.external_user_rules_layout:
                self.user_rules_hidden = False
                self.user_rules_button.setText(self.tr("Lock User Rules"))
                self._toggle_editor_table_rows(
                    rule_type="User Rules", visibility=visibility
                )

    def _toggle_editor_table_rows(self, rule_type: str, visibility: bool) -> None:
        for row in range(self.editor_model.rowCount()):
            item = self.editor_model.item(row, 2)  # Get the item in column 3 (index 2)
            if (
                item and item.text() == rule_type
            ):  # Toggle row visibility based on the value
                self.editor_table_view.setRowHidden(row, visibility)

    def _toggle_loadTop_rule(self, rule_source: str, state: int) -> None:
        if self.edit_packageid:
            logger.debug(f"Toggle loadTop for {self.edit_packageid}: {state}")
            # Select database for editing
            if rule_source == "Community Rules":
                metadata = self.community_rules
            elif rule_source == "User Rules":
                metadata = self.user_rules
            else:
                raise ValueError(f"Invalid rule source: {rule_source}")

            if state == 2:
                comment = ""
                if not self.block_comment_prompt:
                    # Add a new row in the editor - prompt user to enter a comment for their rule addition
                    args, ok = show_dialogue_input(
                        title=self.tr("Enter comment"),
                        label=self.tr(
                            "Enter a comment to annotate why this rule exists."
                            "This is useful for your own records, as well as others."
                        ),
                        parent=self,
                    )
                    if ok:
                        comment = args
                    self._add_rule_to_table(
                        name=self.edit_name,
                        packageid=self.edit_packageid,
                        rule_source=rule_source,
                        rule_type="loadTop",
                        comment=comment,
                    )
                # Add rule to the database if it doesn't already exist
                if not metadata.get(self.edit_packageid):
                    metadata[self.edit_packageid] = {}
                if not metadata[self.edit_packageid].get("loadTop"):
                    metadata[self.edit_packageid]["loadTop"] = {}
                metadata[self.edit_packageid]["loadTop"]["value"] = True
                if comment:
                    metadata[self.edit_packageid]["loadTop"]["comment"] = comment
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
                        and (rule_type_value and "loadTop" in rule_type_value.text())
                    ):  # Remove row if criteria matches search
                        self.editor_model.removeRow(row)
                # Remove rule from the database
                if (
                    metadata.get(self.edit_packageid, {})
                    .get("loadTop", {})
                    .get("value")
                ):
                    metadata[self.edit_packageid].pop("loadTop")

    def _toggle_loadBottom_rule(self, rule_source: str, state: int) -> None:
        if self.edit_packageid:
            logger.debug(f"Toggle loadBottom for {self.edit_packageid}: {state}")
            # Select database for editing
            if rule_source == "Community Rules":
                metadata = self.community_rules
            elif rule_source == "User Rules":
                metadata = self.user_rules
            else:
                raise ValueError(f"Invalid rule source: {rule_source}")

            if state == 2:
                comment = ""
                if not self.block_comment_prompt:
                    # Add a new row in the editor - prompt user to enter a comment for their rule addition
                    args, ok = show_dialogue_input(
                        title=self.tr("Enter comment"),
                        label=self.tr(
                            "Enter a comment to annotate why this rule exists."
                            "This is useful for your own records, as well as others."
                        ),
                        parent=self,
                    )
                    if ok:
                        comment = args
                    self._add_rule_to_table(
                        name=self.edit_name,
                        packageid=self.edit_packageid,
                        rule_source=rule_source,
                        rule_type="loadBottom",
                        comment=comment,
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

    def _show_comment_input(self) -> str:
        """Creates comment input dialogue for the user to enter a comment for their rule addition.

        Returns:
            str: The comment entered by the user if dialogue is accepted, otherwise an empty string.
        """
        item, ok = show_dialogue_input(
            title=self.tr("Enter comment"),
            label=self.tr(
                "Enter a comment to annotate why this rule exists."
                " This is useful for your own records, as well as others."
            ),
            parent=self,
        )
        if ok:
            return item
        return ""

    def modItemContextMenuEvent(self, point: QPoint) -> None:
        context_menu = QMenu(self)  # Mod item context menu event
        context_item = self.mods_list.itemAt(point)
        open_mod = context_menu.addAction(
            self.tr("Open this mod in the editor")
        )  # open mod in editor
        open_mod.triggered.connect(
            partial(self._open_mod_in_editor, context_item=context_item)
        )
        _ = context_menu.exec_(self.mods_list.mapToGlobal(point))

    def ruleItemContextMenuEvent(self, point: QPoint, _list: QListWidget) -> None:
        context_item = _list.itemAt(point)
        if context_item is None:
            return
        context_menu = QMenu(self)  # Rule item context menu event
        remove_rule = context_menu.addAction(
            self.tr("Remove this rule")
        )  # remove this rule
        remove_rule.triggered.connect(
            partial(
                self._remove_rule,
                context_item=context_item,
                _list=_list,
            )
        )
        _ = context_menu.exec_(_list.mapToGlobal(point))

    def clear_mods_search(self) -> None:
        self.mods_search.setText("")
        self.mods_search.clearFocus()

    def signal_mods_search(self, pattern: str) -> None:
        # Convert the pattern to lowercase once
        pattern_lower = pattern.lower() if pattern else ""

        # Loop through the items
        for index in range(self.mods_list.count()):
            item = self.mods_list.item(index)
            widget = item.listWidget().itemWidget(item)
            name = None
            if type(widget) is QLabel:
                name = widget.text()
            name_lower = name.lower() if name else ""

            # Check if the pattern is not found in the name
            if pattern_lower and pattern_lower not in name_lower:
                item.setHidden(True)
            else:
                item.setHidden(False)

    def _get_list_type(
        self,
        rule_type: str,
        loadAfter_list: QListWidget,
        loadBefore_list: QListWidget,
        incompatibilities_list: QListWidget,
    ) -> QListWidget:
        """Returns the appropriate QListWidget object based on the given rule type."""
        if rule_type == "loadAfter":
            return loadAfter_list
        elif rule_type == "loadBefore":
            return loadBefore_list
        elif rule_type == "incompatibleWith":
            return incompatibilities_list
        else:
            raise ValueError(f"Invalid rule type: {rule_type}")
