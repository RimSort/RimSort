import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

from PySide6.QtWidgets import QApplication, QComboBox

from app.controllers.language_controller import LanguageController


class TestLanguageController(unittest.TestCase):
    def setUp(self) -> None:
        """Set up the test environment."""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])

    def test_populate_languages_combobox(self) -> None:
        """Test that the language combobox is populated correctly."""
        # Create a mock QComboBox
        mock_combo_box = QComboBox()

        # Create a LanguageController instance
        with patch(
            "app.controllers.language_controller.LanguageController._get_supported_languages"
        ) as mock_get_supported:
            mock_get_supported.return_value = {
                "en_US",
                "es_ES",
                "fr_FR",
                "de_DE",
                "zh_CN",
                "ja_JP",
                "ru_RU",
                "tr_TR",
                "pt_BR",
                "zh_TW",
            }
            controller = LanguageController()
            controller.populate_languages_combobox(mock_combo_box)

            # Check that the combobox has the correct number of items
            self.assertEqual(mock_combo_box.count(), 10)

            # Check that zh_CN is in the combobox
            korean_index = mock_combo_box.findData("zh_CN")
            self.assertNotEqual(korean_index, -1)
            self.assertEqual(mock_combo_box.itemText(korean_index), "简体中文")
            self.assertEqual(mock_combo_box.itemData(korean_index), "zh_CN")

    def test_get_supported_languages(self) -> None:
        """Test that supported languages are correctly identified."""
        with patch(
            "app.controllers.language_controller.AppInfo.language_data_folder",
            new_callable=PropertyMock,
        ) as mock_lang_folder:
            # Create a mock directory with some dummy language files
            mock_dir = Path("mock_locales")
            mock_dir.mkdir(exist_ok=True)
            (mock_dir / "en_US.qm").touch()
            (mock_dir / "pt_BR.qm").touch()
            (mock_dir / "fr_FR.qm").touch()
            (mock_dir / "test.txt").touch()  # Non-qm file, should be ignored

            mock_lang_folder.return_value = mock_dir

            controller = LanguageController()
            supported_languages = controller._get_supported_languages()

            # Check that the correct languages were found
            self.assertEqual(supported_languages, {"en_US", "pt_BR", "fr_FR"})

            # Clean up the mock directory
            for item in mock_dir.iterdir():
                item.unlink()
            mock_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
