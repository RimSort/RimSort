"""Test file search functionality"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from tests.utils import setup_test_controller


@pytest.fixture
def setup_test_files(request):
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
    about_file1.write_text("<modmetadata><n>test mod 1<n></modmetadata>")
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
    about_file2.write_text("<modmetadata><n>test mod 2<n></modmetadata>")
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


def test_filter_results(setup_test_files):
    """Test filtering search results"""
    # create controller with test files
    controller = setup_test_controller(setup_test_files, {"TestMod1"})

    # perform search
    search_text = "Test"  # This should match both TestMod1 and TestMod2 files
    controller.dialog.search_input.setText(search_text)
    controller.dialog.search_scope.setCurrentText("all mods")
    controller.dialog.xml_only.setChecked(True)

    print("\n=== Starting search ===")
    print(f"Search text: {search_text}")
    print("Search scope: all mods")
    print(f"XML only: {controller.dialog.xml_only.isChecked()}")

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        controller._on_search_clicked()

    # wait for search to complete
    while controller.search_worker and controller.search_worker.isRunning():
        QApplication.processEvents()

    # log initial results
    initial_results = controller.dialog.results_table.rowCount()
    print(f"\n=== Initial search results: {initial_results} rows ===")
    for row in range(initial_results):
        mod_name = controller.dialog.results_table.item(row, 0).text()
        file_name = controller.dialog.results_table.item(row, 1).text()
        file_path = controller.dialog.results_table.item(row, 2).text()
        print(f"Row {row}: mod={mod_name}, file={file_name}, path={file_path}")

    # apply filter for TestMod1
    print("\n=== Applying filter ===")
    filter_text = "TestMod1"
    print(f"Filter text: {filter_text}")
    controller.dialog.filter_input.setText(filter_text)

    # verify filtered results
    visible_rows = 0
    for row in range(controller.dialog.results_table.rowCount()):
        if not controller.dialog.results_table.isRowHidden(row):
            visible_rows += 1
            mod_name = controller.dialog.results_table.item(row, 0).text()
            file_name = controller.dialog.results_table.item(row, 1).text()
            file_path = controller.dialog.results_table.item(row, 2).text()
            print(
                f"Visible after filter: mod={mod_name}, file={file_name}, path={file_path}"
            )

    assert visible_rows > 0, "Expected at least one visible row after filtering"
