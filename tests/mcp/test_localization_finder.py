from __future__ import annotations

from unittest.mock import patch

from app.ai.tools.localization_finder import (
    _has_rus_marker,
    _is_already_localized,
    _score_candidate,
    find_russian_localizations_for_active_mods,
)


def test_has_rus_marker() -> None:
    assert _has_rus_marker("Allow Tool Russian")
    assert _has_rus_marker("mod [RU]")
    assert _has_rus_marker("[sbz] Fridge RU")
    assert _has_rus_marker("Fortifications - Industrial RU")
    assert not _has_rus_marker("Harmony")
    assert not _has_rus_marker("Syrus.CaravanMoodBuff")


def test_is_already_localized_by_name() -> None:
    active = {"author.mod"}
    installed = {
        "author.mod": {
            "package_id": "author.mod",
            "name": "My Mod Russian",
            "load_after": [],
            "mod_dependencies": [],
        }
    }
    assert _is_already_localized("author.mod", "My Mod Russian", active, installed)


def test_is_already_localized_by_companion() -> None:
    active = {"base.mod", "base.mod.rus"}
    installed = {
        "base.mod": {
            "package_id": "base.mod",
            "name": "Base Mod",
            "load_after": [],
            "mod_dependencies": [],
        },
        "base.mod.rus": {
            "package_id": "base.mod.rus",
            "name": "Base Mod Russian",
            "load_after": ["base.mod"],
            "mod_dependencies": [],
        },
    }
    assert _is_already_localized("base.mod", "Base Mod", active, installed)


def test_is_already_localized_by_name_overlap() -> None:
    active = {"duz.almosttherefork", "someone.almostthereru"}
    installed = {
        "duz.almosttherefork": {
            "package_id": "duz.almosttherefork",
            "name": "Almost There! Fork",
            "load_after": [],
            "mod_dependencies": [],
        },
        "someone.almostthereru": {
            "package_id": "someone.almostthereru",
            "name": "Almost There [RU]",
            "load_after": [],
            "mod_dependencies": [],
        },
    }
    assert _is_already_localized(
        "duz.almosttherefork", "Almost There! Fork", active, installed
    )


def test_is_already_localized_fridge_ru_companion() -> None:
    active = {"sbz.NeatStorageFridge", "astratangens.sbz.NeatStorageFridge"}
    installed = {
        "sbz.neatstoragefridge": {
            "package_id": "sbz.NeatStorageFridge",
            "name": "[sbz] Fridge",
            "load_after": [],
            "mod_dependencies": [],
        },
        "astratangens.sbz.neatstoragefridge": {
            "package_id": "astratangens.sbz.NeatStorageFridge",
            "name": "[sbz] Fridge RU",
            "load_after": [],
            "mod_dependencies": [],
        },
    }
    assert _is_already_localized(
        "sbz.NeatStorageFridge", "[sbz] Fridge", active, installed
    )


def test_score_candidate_prefers_russian_title() -> None:
    high = _score_candidate(
        {"title": "Allow Tool Russian"},
        "Allow Tool",
        "unlimitedhugs.allowtool",
    )
    low = _score_candidate(
        {"title": "Some Other Mod"},
        "Allow Tool",
        "unlimitedhugs.allowtool",
    )
    assert high > low


def test_find_russian_localizations_no_api_key() -> None:
    result = find_russian_localizations_for_active_mods(
        [{"package_id": "a.b", "name": "Mod A"}],
        {},
        "",
    )
    assert result["suggestions"] == []
    assert result["errors"]


def test_find_russian_localizations_with_mock_search() -> None:
    active = [{"package_id": "author.mod", "name": "Cool Mod"}]
    installed = {
        "author.mod": {
            "package_id": "author.mod",
            "name": "Cool Mod",
            "load_after": [],
            "mod_dependencies": [],
        }
    }
    fake_match = {
        "publishedfileid": "999",
        "title": "Cool Mod Russian",
        "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=999",
    }
    progress_log: list[tuple[int, int, str]] = []

    def on_progress(current: int, total: int, message: str) -> None:
        progress_log.append((current, total, message))

    with patch(
        "app.ai.tools.localization_finder.search_workshop_by_text",
        return_value=[fake_match],
    ):
        result = find_russian_localizations_for_active_mods(
            active,
            installed,
            "steam-key",
            limit_per_mod=3,
            on_progress=on_progress,
        )
    assert len(result["mods_needing_localization"]) == 1
    suggestion = result["suggestions"][0]
    assert suggestion["recommended"]["publishedfileid"] == "999"
    assert progress_log
    assert any("Workshop search" in msg for _, _, msg in progress_log)


def test_find_russian_localizations_skips_official_dlc() -> None:
    active = [{"package_id": "ludeon.rimworld.odyssey", "name": "RimWorld - Odyssey"}]
    installed = {
        "ludeon.rimworld.odyssey": {
            "package_id": "ludeon.rimworld.odyssey",
            "name": "RimWorld - Odyssey",
            "load_after": [],
            "mod_dependencies": [],
        }
    }
    with patch(
        "app.ai.tools.localization_finder.search_workshop_by_text"
    ) as mock_search:
        result = find_russian_localizations_for_active_mods(
            active,
            installed,
            "steam-key",
            limit_per_mod=3,
        )
    assert result["mods_needing_localization"] == []
    assert result["suggestions"] == []
    mock_search.assert_not_called()
