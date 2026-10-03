from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.controllers.settings_tabs.database_builder_tab_controller import (
    DatabaseBuilderTabController,
)


def _controller(expiry_text: str) -> tuple[DatabaseBuilderTabController, Any]:
    settings = SimpleNamespace(
        db_builder_include="all_mods",
        build_steam_database_dlc_data=False,
        build_steam_database_update_toggle=False,
        steam_apikey="",
        database_expiry=604800,
    )
    dialog = SimpleNamespace(
        db_builder_include_all_radio=SimpleNamespace(isChecked=lambda: True),
        db_builder_include_no_local_radio=SimpleNamespace(isChecked=lambda: False),
        db_builder_query_dlc_checkbox=SimpleNamespace(isChecked=lambda: False),
        db_builder_update_instead_of_overwriting_checkbox=SimpleNamespace(
            isChecked=lambda: False
        ),
        db_builder_steam_api_key=SimpleNamespace(text=lambda: ""),
        database_expiry=SimpleNamespace(text=lambda: expiry_text),
    )
    controller = DatabaseBuilderTabController.__new__(DatabaseBuilderTabController)
    untyped = cast(Any, controller)
    untyped.settings = settings
    untyped.dialog = dialog
    return controller, settings


@pytest.mark.parametrize(
    ("text", "expected"),
    [("604800", 604800), ("0", 0), ("", 0), ("abc", 0)],
)
def test_update_model_from_view_parses_database_expiry(
    text: str, expected: int
) -> None:
    controller, settings = _controller(text)

    controller.update_model_from_view()

    assert settings.database_expiry == expected
