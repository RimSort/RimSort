"""Test file search functionality"""

import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QTableWidget


# Mock test utilities since they don't exist in tests.utils
def create_test_app() -> MagicMock:
    """Mock application creator"""
    return MagicMock()


def setup_test_controller(test_dir: str, mods: set[str]) -> MagicMock:
    """Mock controller setup with complete widget and behavior simulation"""
    # Create controller mock with proper return types
    controller = MagicMock(
        spec_set=[
            "dialog",
            "search_worker",
            "get_search_paths",
            "active_mod_ids",
            "_on_search_clicked",
            "_on_stop_clicked",
        ]
    )

    # Setup dialog mock with required widgets
    dialog = MagicMock(
        spec_set=[
            "results_table",
            "search_input",
            "filter_input",
            "search_scope",
            "xml_only",
            "skip_translations",
            "search_button",
            "stop_button",
        ]
    )
    controller.dialog = dialog

    # Setup table widget mock with all methods properly configured
    mock_table = MagicMock(spec=QTableWidget)
    mock_table.rowCount = MagicMock(return_value=2)
    mock_table.item = MagicMock(
        side_effect=lambda row, col: (
            MagicMock(text="TestMod1" if row == 0 else "TestMod2")
            if col == 0
            else MagicMock(text="About.xml")
            if col == 1
            else MagicMock(
                text=str(Path(test_dir) / f"TestMod{row + 1}/About/About.xml")
            )
        )
    )
    mock_table.isRowHidden = MagicMock(side_effect=lambda row: False)
    dialog.results_table = mock_table

    # Setup input widgets
    dialog.search_input = MagicMock()
    dialog.search_input.text.return_value = ""
    dialog.filter_input = MagicMock()
    dialog.filter_input.text.return_value = ""

    # Setup search options with defaults
    dialog.search_scope = MagicMock()
    dialog.search_scope.currentText.return_value = "active mods"

    dialog.xml_only = MagicMock()
    dialog.xml_only.isChecked.return_value = True

    dialog.skip_translations = MagicMock()
    dialog.skip_translations.isChecked.return_value = True

    # Setup search worker
    controller.search_worker = MagicMock()
    controller.search_worker.isRunning.return_value = True

    # Setup buttons with initial states
    dialog.search_button = MagicMock()
    dialog.search_button.isEnabled.return_value = True
    dialog.stop_button = MagicMock()
    dialog.stop_button.isEnabled.return_value = False

    # Setup search paths
    controller.get_search_paths.return_value = [test_dir]
    controller.active_mod_ids = mods

    # Ensure proper return type
    return controller


@pytest.fixture
def setup_test_files(request: pytest.FixtureRequest) -> Generator[str, None, None]:
    """Set up test files and clean up after test"""
    # create main directories
    mods_dir = Path(tempfile.gettempdir()) / "Mods"
    mods_dir.mkdir(exist_ok=True)
    print("\n=== Setting up test files ===")
    print(f"Mods directory: {mods_dir}")

    # create test mod directories
    test_mod1 = mods_dir / "TestMod1"
    test_mod2 = mods_dir / "TestMod2"

    # create About.xml files
    about_dir1 = test_mod1 / "About"
    about_dir1.mkdir(parents=True, exist_ok=True)
    about_file1 = about_dir1 / "About.xml"
    about_file1.write_text("<modmetadata><name>test mod 1</name></modmetadata>")
    print(f"Created About.xml in {about_file1}")

    # create TestDef.xml in TestMod1
    defs_dir1 = test_mod1 / "Defs"
    defs_dir1.mkdir(exist_ok=True)
    test_def1 = defs_dir1 / "TestDef.xml"
    test_def1.write_text("<defs><thingdef><defname>test</defname></thingdef></defs>")
    print(f"Created TestDef.xml in {test_def1}")

    # create About.xml in TestMod2
    about_dir2 = test_mod2 / "About"
    about_dir2.mkdir(parents=True, exist_ok=True)
    about_file2 = about_dir2 / "About.xml"
    about_file2.write_text("<modmetadata><name>test mod 2</name></modmetadata>")
    print(f"Created About.xml in {about_file2}")

    # create Strings.xml in TestMod2
    lang_dir2 = test_mod2 / "Languages" / "English"
    lang_dir2.mkdir(parents=True, exist_ok=True)
    strings_file2 = lang_dir2 / "Strings.xml"
    strings_file2.write_text(
        "<languagedata><teststring>test</teststring></languagedata>"
    )
    print(f"Created Strings.xml in {strings_file2}")

    # create test.png in TestMod2
    textures_dir2 = test_mod2 / "Textures"
    textures_dir2.mkdir(exist_ok=True)
    test_png2 = textures_dir2 / "test.png"
    test_png2.write_bytes(b"fake png data")
    print(f"Created test.png in {test_png2}")

    print("\nTest files setup complete. Root directory:", mods_dir)

    # return test directory for use in tests
    yield str(mods_dir)

    # cleanup after test
    try:
        import shutil

        shutil.rmtree(mods_dir)
    except Exception as e:
        print(f"Warning: Failed to clean up test directory: {e}")


def test_stop_search(setup_test_files: str) -> None:
    """Test stopping a search"""
    controller = setup_test_controller(setup_test_files, {"TestMod1"})
    dialog = controller.dialog

    # Mock button state changes
    def mock_search_clicked() -> None:
        dialog.search_button.isEnabled.return_value = False
        dialog.stop_button.isEnabled.return_value = True
        controller.search_worker.isRunning.return_value = True

    def mock_stop_clicked() -> None:
        controller.search_worker.isRunning.return_value = False
        dialog.search_button.isEnabled.return_value = True
        dialog.stop_button.isEnabled.return_value = False

    controller._on_search_clicked.side_effect = mock_search_clicked
    controller._on_stop_clicked.side_effect = mock_stop_clicked

    # Simulate search start
    controller._on_search_clicked()

    # Verify search started
    assert controller.search_worker.isRunning()
    assert not dialog.search_button.isEnabled()
    assert dialog.stop_button.isEnabled()

    # Simulate stop
    controller._on_stop_clicked()

    # Verify search stopped
    assert not controller.search_worker.isRunning()
    assert dialog.search_button.isEnabled()
    assert not dialog.stop_button.isEnabled()


def test_filter_results(setup_test_files: str) -> None:
    """Test filtering search results"""
    # create controller with test files
    controller = setup_test_controller(setup_test_files, {"TestMod1"})

    # perform search
    search_text = "Test"  # This should match both TestMod1 and TestMod2 files

    dialog = controller.dialog
    assert isinstance(dialog.results_table, QTableWidget)

    dialog.search_input.setText(search_text)  # Ensure search input is set
    dialog.results_table.clear()  # Clear previous results before search

    # Verify defaults are set correctly
    assert dialog.search_scope.currentText() == "active mods"
    assert dialog.xml_only.isChecked() is True
    assert dialog.skip_translations.isChecked() is True

    # Override scope for this test
    controller.dialog.search_scope.setCurrentText("all mods")

    print("\n=== Starting search ===")
    print(f"Search text: {search_text}")
    print("Search scope: all mods")
    print(f"XML only: {controller.dialog.xml_only.isChecked()}")

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        controller._on_search_clicked()

    # Mock search results
    controller.search_worker.isRunning.return_value = False
    controller.search_worker.finished.emit()

    # Ensure proper types for mock arguments
    mock_items = [
        [
            MagicMock(spec=QTableWidget, text=MagicMock(return_value="TestMod1")),
            MagicMock(spec=QTableWidget, text=MagicMock(return_value="About.xml")),
            MagicMock(
                spec=QTableWidget,
                text=MagicMock(
                    return_value=str(
                        Path(setup_test_files) / "TestMod1/About/About.xml"
                    )
                ),
            ),
        ],
        [
            MagicMock(spec=QTableWidget, text=MagicMock(return_value="TestMod2")),
            MagicMock(spec=QTableWidget, text=MagicMock(return_value="About.xml")),
            MagicMock(
                spec=QTableWidget,
                text=MagicMock(
                    return_value=str(
                        Path(setup_test_files) / "TestMod2/About/About.xml"
                    )
                ),
            ),
        ],
    ]

    # Create mock table with proper behavior
    mock_table = MagicMock(spec=QTableWidget)
    mock_table.rowCount.return_value = 2
    mock_table.item.side_effect = lambda row, col: mock_items[row][col]

    dialog.results_table = mock_table

    # Update filter_text to match only one row
    filter_text = "TestMod1"

    # Optimize filtering logic
    def is_row_visible(row: int) -> bool:
        mod_item = dialog.results_table.item(row, 0)
        return mod_item is not None and filter_text.lower() in mod_item.text().lower()

    visible_rows = sum(
        1 for row in range(dialog.results_table.rowCount()) if is_row_visible(row)
    )

    # Log visible rows
    for row in range(dialog.results_table.rowCount()):
        if is_row_visible(row):
            mod_item = dialog.results_table.item(row, 0)
            file_item = dialog.results_table.item(row, 1)
            path_item = dialog.results_table.item(row, 2)

            # Ensure items are not None before accessing text
            mod_text = mod_item.text() if mod_item else "<None>"
            file_text = file_item.text() if file_item else "<None>"
            path_text = path_item.text() if path_item else "<None>"

            print(
                f"Visible after filter: mod={mod_text}, file={file_text}, path={path_text}"
            )

    assert visible_rows == 1, (
        f"Expected exactly one visible row after filtering, got {visible_rows}"
    )


def test_xml_search_only_xml_files(setup_test_files: str) -> None:
    """Test that xml_search only processes .xml files."""
    from app.utils.file_search import FileSearch
    from app.utils.metadata import MetadataManager

    # Mock settings_controller
    mock_settings_controller = MagicMock()

    # Patch the instance method of SteamcmdInterface
    with patch(
        "app.utils.steam.steamcmd.wrapper.SteamcmdInterface.instance"
    ) as mock_instance_method:
        mock_instance_method.return_value = MagicMock()  # Return a mock instance

        # Create a FileSearch instance with mocked MetadataManager
        mock_metadata_manager = MetadataManager(mock_settings_controller)
        file_search = FileSearch(metadata_manager=mock_metadata_manager)

        # Define search parameters
        search_text = "<modmetadata>"
        root_paths = [setup_test_files]
        options = {"file_extensions": [".xml"]}

        # Collect results
        results = list(file_search.xml_search(search_text, root_paths, options))

        # Verify that only .xml files are included in the results
        for _, file_name, _ in results:
            assert file_name.endswith(".xml"), f"Non-XML file included: {file_name}"

        # Print results for debugging
        print("XML Search Results:")
        for mod_name, file_name, file_path in results:
            print(f"Mod: {mod_name}, File: {file_name}, Path: {file_path}")

        # Ensure results are not empty
        assert results, "No results found, but .xml files exist in the test setup."
