from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from app.controllers.file_search_controller import FileSearchController
from app.models.settings import Settings
from app.views.file_search_dialog import FileSearchDialog


@pytest.fixture(scope="session")
def qapp():
    """qt app instance for tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def setup_test_files(tmp_path):
    """setup test environment with mock mod files"""
    # create main directories
    mods_dir = tmp_path / "Mods"
    mods_dir.mkdir(exist_ok=True)
    print("\n=== Setting up test files ===")
    print(f"Mods directory: {mods_dir}")

    # create some test mod folders with files
    mod1_dir = mods_dir / "TestMod1"
    mod1_dir.mkdir(exist_ok=True)
    about_dir = mod1_dir / "About"
    about_dir.mkdir(exist_ok=True, parents=True)
    about_file = about_dir / "About.xml"
    about_file.write_text("<ModMetaData><name>Test Mod 1</name></ModMetaData>")
    print(f"Created About.xml in {about_file}")

    defs_dir = mod1_dir / "Defs"
    defs_dir.mkdir(exist_ok=True, parents=True)
    test_def_file = defs_dir / "TestDef.xml"
    test_def_file.write_text(
        "<Defs><ThingDef><defName>TestContent</defName></ThingDef></Defs>"
    )
    print(f"Created TestDef.xml in {test_def_file}")

    mod2_dir = mods_dir / "TestMod2"
    mod2_dir.mkdir(exist_ok=True)
    about_dir2 = mod2_dir / "About"
    about_dir2.mkdir(exist_ok=True, parents=True)
    about_file2 = about_dir2 / "About.xml"
    about_file2.write_text("<ModMetaData><name>Test Mod 2</name></ModMetaData>")
    print(f"Created About.xml in {about_file2}")

    lang_dir = mod2_dir / "Languages" / "English"
    lang_dir.mkdir(exist_ok=True, parents=True)
    strings_file = lang_dir / "Strings.xml"
    strings_file.write_text(
        "<LanguageData><TestString>Test</TestString></LanguageData>"
    )
    print(f"Created Strings.xml in {strings_file}")

    # create a binary file that should be skipped
    textures_dir = mod2_dir / "Textures"
    textures_dir.mkdir(exist_ok=True)
    with open(textures_dir / "test.png", "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    print(f"Created test.png in {textures_dir}")

    print(f"\nTest files setup complete. Root directory: {mods_dir}")
    return mods_dir  # return the Mods directory instead of tmp_path


@pytest.fixture
def file_search_controller(qapp, setup_test_files):
    """create controller instance with mock settings"""
    settings = Settings()
    settings.current_instance = "test"

    # create a more complete test instance with all required attributes
    class TestInstance:
        def __init__(self, local_folder):
            self.local_folder = str(local_folder)  # ensure string path
            self.workshop_folder = None  # no steam mods for testing
            self.config_folder = None  # no config folder for testing
            print("\n=== Test instance setup ===")
            print(f"Local folder: {self.local_folder}")

    settings.instances["test"] = TestInstance(setup_test_files)

    dialog = FileSearchDialog()
    active_mod_ids = {"TestMod1"}  # only first mod is active
    controller = FileSearchController(settings, dialog, active_mod_ids)
    print(f"Active mod IDs: {active_mod_ids}")

    yield controller

    # cleanup
    if controller.search_worker and controller.search_worker.isRunning():
        controller.searcher.stop_search()
        controller.search_worker.wait()
    dialog.close()


def test_simple_search(file_search_controller):
    """test simple text search functionality"""
    # setup search parameters
    file_search_controller.dialog.search_input.setText("TestContent")
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.case_sensitive.setChecked(False)
    file_search_controller.dialog.xml_only.setChecked(True)

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):  # mock dialog
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify results
    assert file_search_controller.dialog.results_table.rowCount() == 1
    assert file_search_controller.dialog.results_table.item(0, 0).text() == "TestMod1"
    assert (
        "TestDef.xml" in file_search_controller.dialog.results_table.item(0, 1).text()
    )


def test_search_with_scope(file_search_controller):
    """test search with different scope settings"""
    # setup search for active mods only
    file_search_controller.dialog.search_input.setText("Test")
    file_search_controller.dialog.search_scope.setCurrentText("active mods")
    file_search_controller.dialog.xml_only.setChecked(True)

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify only active mod results are shown
    results_count = file_search_controller.dialog.results_table.rowCount()
    assert results_count > 0  # make sure we have results
    for row in range(results_count):
        assert (
            file_search_controller.dialog.results_table.item(row, 0).text()
            == "TestMod1"
        )


def test_skip_translations(file_search_controller):
    """test skipping translation files"""
    # setup search with skip translations
    file_search_controller.dialog.search_input.setText("Test")
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.skip_translations.setChecked(True)
    file_search_controller.dialog.xml_only.setChecked(True)

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify no translation files in results
    results_count = file_search_controller.dialog.results_table.rowCount()
    assert results_count > 0  # make sure we have results
    for row in range(results_count):
        path = file_search_controller.dialog.results_table.item(row, 2).text()
        assert "Languages" not in path


def test_case_sensitive_search(file_search_controller):
    """test case sensitive search functionality"""
    # setup search parameters
    file_search_controller.dialog.search_input.setText("DEFNAME")
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.case_sensitive.setChecked(True)
    file_search_controller.dialog.xml_only.setChecked(True)
    file_search_controller.dialog.algorithm_selector.setCurrentText(
        "simple search (good for small mod collections)"
    )

    # perform search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify results
    assert file_search_controller.dialog.results_table.rowCount() == 0

    # try with correct case
    file_search_controller.dialog.search_input.setText("defName")
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify results
    assert file_search_controller.dialog.results_table.rowCount() > 0


def test_filter_results(file_search_controller):
    """test filtering search results"""
    # perform search first
    file_search_controller.dialog.search_input.setText("Test")
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.xml_only.setChecked(True)

    print("\n=== Starting search ===")
    print("Search text: Test")
    print("Search scope: all mods")
    print(f"XML only: {file_search_controller.dialog.xml_only.isChecked()}")

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # log initial results
    initial_results = file_search_controller.dialog.results_table.rowCount()
    print(f"\n=== Initial search results: {initial_results} rows ===")
    for row in range(initial_results):
        mod_name = file_search_controller.dialog.results_table.item(row, 0).text()
        file_name = file_search_controller.dialog.results_table.item(row, 1).text()
        print(f"Row {row}: mod={mod_name}, file={file_name}")

    print("\n=== Applying filter ===")
    print("Filter text: TestMod1")
    # apply filter
    file_search_controller.dialog.filter_input.setText("TestMod1")

    # verify filtered results
    visible_rows = 0
    for row in range(file_search_controller.dialog.results_table.rowCount()):
        if not file_search_controller.dialog.results_table.isRowHidden(row):
            visible_rows += 1
            mod_name = file_search_controller.dialog.results_table.item(row, 0).text()
            file_name = file_search_controller.dialog.results_table.item(row, 1).text()
            print(f"Visible after filter: mod={mod_name}, file={file_name}")

    print(f"\n=== Filter results: {visible_rows} visible rows ===")
    assert visible_rows > 0, "Expected at least one visible row after filtering"


def test_parallel_search(file_search_controller):
    """test parallel search functionality"""
    # setup search parameters
    file_search_controller.dialog.search_input.setText(
        "Test Mod"
    )  # search for mod names in About.xml files
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.case_sensitive.setChecked(False)
    file_search_controller.dialog.xml_only.setChecked(True)
    file_search_controller.dialog.algorithm_selector.setCurrentText(
        "parallel search (for large mod collections)"
    )

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # wait for search to complete
    while (
        file_search_controller.search_worker
        and file_search_controller.search_worker.isRunning()
    ):
        QApplication.processEvents()

    # verify results - should find matches in both mods
    results_count = file_search_controller.dialog.results_table.rowCount()
    assert results_count > 0  # should find at least one file containing "Test Mod"

    # collect all found mod names
    found_mods = set()
    found_files = set()
    for row in range(results_count):
        found_mods.add(file_search_controller.dialog.results_table.item(row, 0).text())
        found_files.add(file_search_controller.dialog.results_table.item(row, 1).text())

    # should find matches in both mods' About.xml files
    assert "TestMod1" in found_mods or "TestMod2" in found_mods
    assert "About.xml" in found_files  # should find in About.xml files


def test_search_algorithm_switch(file_search_controller):
    """test switching between different search algorithms"""
    search_algorithms = [
        "simple search (good for small mod collections)",
        "parallel search (for large mod collections)",
    ]

    for algorithm in search_algorithms:
        # setup search parameters
        file_search_controller.dialog.search_input.setText("Test")
        file_search_controller.dialog.search_scope.setCurrentText("all mods")
        file_search_controller.dialog.case_sensitive.setChecked(False)
        file_search_controller.dialog.xml_only.setChecked(True)
        file_search_controller.dialog.algorithm_selector.setCurrentText(algorithm)

        # trigger search
        with patch("app.utils.gui_info.show_dialogue_conditional"):
            file_search_controller._on_search_clicked()

        # wait for search to complete
        while (
            file_search_controller.search_worker
            and file_search_controller.search_worker.isRunning()
        ):
            QApplication.processEvents()

        # verify each algorithm finds results
        results_count = file_search_controller.dialog.results_table.rowCount()
        assert results_count > 0, f"No results found with algorithm: {algorithm}"

        # clear results for next iteration
        file_search_controller.dialog.clear_results()


def test_search_with_stop(file_search_controller):
    """test stopping search operation"""
    # setup search parameters
    file_search_controller.dialog.search_input.setText("Test")
    file_search_controller.dialog.search_scope.setCurrentText("all mods")
    file_search_controller.dialog.case_sensitive.setChecked(False)
    file_search_controller.dialog.xml_only.setChecked(True)

    # trigger search
    with patch("app.utils.gui_info.show_dialogue_conditional"):
        file_search_controller._on_search_clicked()

    # stop the search immediately
    file_search_controller._on_stop_clicked()

    # verify search was stopped
    assert (
        not file_search_controller.search_worker
        or not file_search_controller.search_worker.isRunning()
    )
    assert file_search_controller.dialog.search_button.isEnabled()
    assert not file_search_controller.dialog.stop_button.isEnabled()
