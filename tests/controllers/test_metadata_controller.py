from pathlib import Path
from unittest.mock import patch

import pytest

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController


@pytest.fixture()
def metadata_db_controller(tmp_path: Path) -> AuxMetadataController:
    with patch("app.controllers.metadata_db_controller.AppInfo") as mock_app_info:
        mock_app_info.aux_metadata_db = tmp_path / "test_metadata.db"
        return AuxMetadataController()


@pytest.fixture()
def metadata_controller(
    settings_controller: SettingsController,
    metadata_db_controller: AuxMetadataController,
) -> MetadataController:
    return MetadataController(settings_controller, metadata_db_controller)
