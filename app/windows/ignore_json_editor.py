from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.event_bus import EventBus
from app.utils.ignore_manager import IgnoreManager

# Placeholder text shown when ignore list is empty
_EMPTY_LIST_PLACEHOLDER = "No mods in ignore list."


class IgnoreJsonEditor(QDialog):
    """
    Dialog for managing the ignore list of mods.

    Displays ignored mods as a list with checkboxes to remove items,
    allowing users to easily manage which mods are ignored.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the Ignore JSON Editor dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        logger.debug("Initializing IgnoreJsonEditor")

        self.setWindowTitle(self.tr("RimSort - Manage Ignore List"))
        self.setGeometry(100, 100, 500, 400)
        self._empty_list_placeholder = self.tr(_EMPTY_LIST_PLACEHOLDER)

        # Create main layout
        main_layout = QVBoxLayout(self)

        # Add description label
        description_label = QLabel(
            self.tr("Mods checked below will be removed from the ignore list.")
        )
        main_layout.addWidget(description_label)

        # Create list widget
        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        # Create button layout
        button_layout = QHBoxLayout()
        self._create_buttons(button_layout)
        main_layout.addLayout(button_layout)

        # Load initial content
        self._load_ignored_mods()

        logger.debug("Finished IgnoreJsonEditor initialization")

    def _create_buttons(self, button_layout: QHBoxLayout) -> None:
        """
        Create and connect dialog buttons.

        Args:
            button_layout: Layout to add buttons to
        """
        # Remove button
        remove_button = QPushButton(self.tr("Remove Selected"))
        remove_button.clicked.connect(self._remove_selected)
        button_layout.addWidget(remove_button)

        # Save button
        save_button = QPushButton(self.tr("Save"))
        save_button.clicked.connect(self._save_changes)
        button_layout.addWidget(save_button)

        # Cancel button
        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.clicked.connect(self.close)
        button_layout.addWidget(cancel_button)

    def _remove_selected(self) -> None:
        """Remove checked items from the list display."""
        # Collect indices to remove (in reverse order to maintain correct indices)
        indices_to_remove = [
            i
            for i in range(self.list_widget.count())
            if (item := self.list_widget.item(i))
            and item.checkState() == Qt.CheckState.Checked
        ]

        # Remove in reverse order to maintain correct indices
        for i in reversed(indices_to_remove):
            self.list_widget.takeItem(i)

        logger.debug(f"Removed {len(indices_to_remove)} item(s) from list")

    def _load_ignored_mods(self) -> None:
        """Load the ignore list and display as checkbox items."""
        try:
            ignored_mods = IgnoreManager.load_ignored_mods()

            if not ignored_mods:
                self._add_empty_placeholder()
                logger.info("No ignored mods found")
                return

            # Add each ignored mod as a checkbox item (sorted for consistency)
            for mod_packageid in sorted(ignored_mods):
                self._add_mod_item(mod_packageid)

            logger.info(f"Loaded {len(ignored_mods)} ignored mods")
        except Exception as e:
            logger.error(f"Failed to load ignored mods: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Failed to load ignored mods: {e}"),
            )

    def _add_empty_placeholder(self) -> None:
        """Add placeholder item when list is empty."""
        item = QListWidgetItem(self._empty_list_placeholder)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.list_widget.addItem(item)

    def _add_mod_item(self, mod_packageid: str) -> None:
        """
        Add a mod item to the list as a checkbox.

        Args:
            mod_packageid: Package ID of the mod to add
        """
        item = QListWidgetItem(mod_packageid)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.list_widget.addItem(item)

    def _save_changes(self) -> None:
        """Save changes by saving the current list to ignore.json."""
        try:
            # Collect remaining items (those not marked for removal)
            remaining_mods = self._collect_remaining_mods()

            # Save updated list
            if IgnoreManager.save_ignored_mods(remaining_mods):
                logger.info(f"Saved {len(remaining_mods)} mod(s) to ignore list")
                QMessageBox.information(
                    self,
                    self.tr("Success"),
                    self.tr("Ignore list has been saved successfully."),
                )
                self.close()
                # Emit event to check and warn about missing mod properties after closing the panel
                EventBus().do_check_missing_mod_properties.emit()
            else:
                logger.error("Failed to save changes to ignore list")
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr("Failed to save changes to ignore list."),
                )
        except Exception as e:
            logger.error(f"Error saving changes: {e}")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"Error saving changes: {e}"),
            )

    def _collect_remaining_mods(self) -> set[str]:
        """
        Collect mods that should be kept (not removed).

        Returns:
            Set of remaining mod package IDs
        """
        remaining_mods = set()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.text() and item.text() != self._empty_list_placeholder:
                remaining_mods.add(item.text())
        return remaining_mods
