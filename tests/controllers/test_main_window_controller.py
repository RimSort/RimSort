from unittest.mock import MagicMock, patch

from app.controllers.main_window_controller import MainWindowController
from app.services.dependency_resolver import DepResolveResult


def _make_controller(
    active_paths: list[str],
) -> tuple[MainWindowController, MagicMock, MagicMock]:
    main_window = MagicMock()
    main_window.main_content_panel.mods_panel.active_mods_list.paths = active_paths
    main_window.main_content_panel.steamcmd_wrapper.setup = True
    mock_metadata = MagicMock()

    with patch(
        "app.controllers.main_window_controller.MetadataController"
    ) as mock_metadata_cls:
        mock_metadata_cls.instance.return_value = mock_metadata
        controller = MainWindowController(main_window)

    return controller, main_window, mock_metadata


@patch("app.controllers.main_window_controller.MissingDependenciesDialog")
@patch("app.controllers.main_window_controller.build_dependencies_dialog_context")
def test_check_dependencies_downloads_selected_workshop_mods(
    mock_build_context: MagicMock,
    mock_dialog_cls: MagicMock,
) -> None:
    dep_resolve = {
        "author.missing": DepResolveResult(
            package_id="author.missing",
            workshop_id="999",
            workshop_url="https://steamcommunity.com/sharedfiles/filedetails/?id=999",
            source="steam_db",
        )
    }
    mock_build_context.return_value = (
        {
            "author.parent": {
                "satisfied": set(),
                "local": set(),
                "download": {"author.missing"},
            }
        },
        {"author.parent": {"author.missing"}},
        dep_resolve,
    )

    mock_dialog = MagicMock()
    mock_dialog.show_dialog.return_value = {"author.missing"}
    mock_dialog_cls.return_value = mock_dialog

    controller, main_window, mock_metadata = _make_controller(["/mods/parent"])
    mock_metadata.packageid_to_paths.get.return_value = None

    controller.check_dependencies()

    mock_dialog.download_requested.connect.assert_called_once_with(
        main_window.main_content_panel._download_single_workshop_mod
    )
    main_window.main_content_panel._do_download_mods_with_steamcmd.assert_called_once_with(
        ["999"]
    )


@patch("app.controllers.main_window_controller.MissingDependenciesDialog")
@patch("app.controllers.main_window_controller.build_dependencies_dialog_context")
def test_check_dependencies_adds_local_mods_and_sorts(
    mock_build_context: MagicMock,
    mock_dialog_cls: MagicMock,
) -> None:
    mock_build_context.return_value = (
        {
            "author.parent": {
                "satisfied": set(),
                "local": {"author.localdep"},
                "download": set(),
            }
        },
        {"author.parent": {"author.localdep"}},
        {},
    )

    mock_dialog = MagicMock()
    mock_dialog.show_dialog.return_value = {"author.localdep"}
    mock_dialog_cls.return_value = mock_dialog

    controller, main_window, mock_metadata = _make_controller(["/mods/parent"])
    mock_metadata.packageid_to_paths.get.side_effect = (
        lambda pkg_id: {"/mods/localdep"} if pkg_id == "author.localdep" else None
    )

    controller.check_dependencies()

    active_paths = (
        main_window.main_content_panel.mods_panel.active_mods_list.paths
    )
    assert "/mods/localdep" in active_paths
    main_window.main_content_panel._do_sort.assert_called_once_with(check_deps=False)


@patch("app.controllers.main_window_controller.MissingDependenciesDialog")
@patch("app.controllers.main_window_controller.build_dependencies_dialog_context")
def test_check_dependencies_no_missing_returns_early(
    mock_build_context: MagicMock,
    mock_dialog_cls: MagicMock,
) -> None:
    mock_build_context.return_value = (
        {
            "author.parent": {
                "satisfied": {"author.core"},
                "local": set(),
                "download": set(),
            }
        },
        {},
        {},
    )

    mock_dialog = MagicMock()
    mock_dialog.show_dialog.return_value = set()
    mock_dialog_cls.return_value = mock_dialog

    controller, main_window, _mock_metadata = _make_controller(["/mods/parent"])

    controller.check_dependencies()

    main_window.main_content_panel._do_sort.assert_not_called()
    main_window.main_content_panel._do_download_mods_with_steamcmd.assert_not_called()
