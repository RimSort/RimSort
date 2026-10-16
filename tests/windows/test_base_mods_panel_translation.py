"""Verify shared table headers use the compiled Brazilian Portuguese catalog."""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator
from pytestqt.qtbot import QtBot

from app.windows.base_mods_panel import BaseModsPanel


def test_shared_headers_are_translated(qtbot: QtBot) -> None:
    translator = QTranslator()
    catalog = Path(__file__).resolve().parents[2] / "locales" / "pt_BR.qm"
    assert translator.load(str(catalog))

    application = QCoreApplication.instance()
    assert application is not None
    application.installTranslator(translator)
    try:
        assert BaseModsPanel._get_standard_mod_columns() == [
            "Nome",
            "Autor",
            "ID do pacote",
            "ID do arquivo publicado",
            "Versões compatíveis",
            "Mod baixado",
            "Atualizado no Workshop",
            "Origem",
            "Caminho",
            "Página do Workshop",
        ]
        assert QCoreApplication.translate("MissingModsPrompt", "# Variants") == (
            "# Variantes"
        )
    finally:
        application.removeTranslator(translator)
