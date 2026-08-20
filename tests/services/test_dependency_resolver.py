from pathlib import Path

from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    BaseRules,
    CaseInsensitiveSet,
    CaseInsensitiveStr,
    DependencyMod,
    Rules,
)
from app.services.dependency_resolver import (
    DepResolveResult,
    build_dependencies_dialog_context,
    parse_workshop_id_from_url,
    resolve_dependency_workshop_id,
)


def _make_mod(
    package_id: str,
    path: str,
    dependencies: dict[str, DependencyMod] | None = None,
) -> AboutXmlMod:
    mod = AboutXmlMod()
    mod.package_id = CaseInsensitiveStr(package_id)
    mod.mod_path = Path(path)
    mod.about_rules = BaseRules()
    if dependencies:
        mod.about_rules.dependencies = {
            CaseInsensitiveStr(k): v for k, v in dependencies.items()
        }
    mod.community_rules = Rules()
    mod.user_rules = Rules()
    return mod


class TestParseWorkshopIdFromUrl:
    def test_query_id(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=12345"
        assert parse_workshop_id_from_url(url) == "12345"


class TestResolveDependencyWorkshopId:
    def test_steam_db_match(self) -> None:
        metadata = MagicMockMetadata()
        result = resolve_dependency_workshop_id(
            metadata, "author.missing", set()
        )
        assert isinstance(result, DepResolveResult)
        assert result.workshop_id == "999"
        assert result.source == "steam_db"


class TestBuildDependenciesDialogContext:
    def test_download_dep_gets_dep_resolve_with_workshop_id(self) -> None:
        parent = _make_mod(
            "author.parent",
            "/mods/parent",
            dependencies={
                "author.missing": DependencyMod(
                    package_id=CaseInsensitiveStr("author.missing")
                )
            },
        )
        metadata = MagicMockMetadata(
            mods_metadata={"/mods/parent": parent},
            active_paths={"/mods/parent"},
        )

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            metadata, {"/mods/parent"}
        )

        assert deps_summary["author.parent"]["download"] == {"author.missing"}
        assert deps_summary["author.parent"]["local"] == set()
        assert missing_deps["author.parent"] == {"author.missing"}
        assert "author.missing" in dep_resolve
        assert dep_resolve["author.missing"].workshop_id == "999"
        assert dep_resolve["author.missing"].source == "steam_db"

    def test_local_dep_not_in_dep_resolve(self) -> None:
        parent = _make_mod(
            "author.parent",
            "/mods/parent",
            dependencies={
                "author.localdep": DependencyMod(
                    package_id=CaseInsensitiveStr("author.localdep")
                )
            },
        )
        local_dep = _make_mod("author.localdep", "/mods/localdep")
        metadata = MagicMockMetadata(
            mods_metadata={
                "/mods/parent": parent,
                "/mods/localdep": local_dep,
            },
            active_paths={"/mods/parent"},
        )

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            metadata, {"/mods/parent"}
        )

        assert deps_summary["author.parent"]["local"] == {"author.localdep"}
        assert deps_summary["author.parent"]["download"] == set()
        assert missing_deps["author.parent"] == {"author.localdep"}
        assert "author.localdep" not in dep_resolve


class MagicMockMetadata:
    def __init__(
        self,
        mods_metadata: dict[str, AboutXmlMod] | None = None,
        active_paths: set[str] | None = None,
    ) -> None:
        self.mods_metadata = mods_metadata or {}
        self.active_paths = active_paths or set()
        self.steam_db = type(
            "DB",
            (),
            {
                "database": {
                    "999": type("Entry", (), {"packageId": "author.missing"})(),
                }
            },
        )()
        self.game_version = "1.5"
        self.settings = type(
            "S",
            (),
            {
                "prefer_versioned_about_tags": False,
                "use_alternative_package_ids_as_satisfying_dependencies": False,
            },
        )()
