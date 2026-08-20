from pathlib import Path
from typing import cast

from app.controllers.metadata_controller import MetadataController
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    BaseRules,
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


def _make_alt_dependency_metadata(active_paths: set[str]) -> MetadataController:
    parent = _make_mod(
        "author.parent",
        "/mods/parent",
        dependencies={
            "author.required": DependencyMod(
                package_id=CaseInsensitiveStr("author.required"),
                alternative_package_ids={CaseInsensitiveStr("author.alt")},
            )
        },
    )
    alt = _make_mod("author.alt", "/mods/alt")
    return cast(
        MetadataController,
        MagicMockMetadata(
            mods_metadata={"/mods/parent": parent, "/mods/alt": alt},
            active_paths=active_paths,
            use_alternatives=True,
        ),
    )


class TestParseWorkshopIdFromUrl:
    def test_query_id(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=12345"
        assert parse_workshop_id_from_url(url) == "12345"

    def test_community_file_page_with_trailing_slash(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/CommunityFilePage/67890/"
        assert parse_workshop_id_from_url(url) == "67890"

    def test_query_id_with_extra_query_params(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=11111&searchtext=foo"
        assert parse_workshop_id_from_url(url) == "11111"

    def test_community_file_page_with_path_suffix(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/CommunityFilePage/22222/extra"
        assert parse_workshop_id_from_url(url) == "22222"

    def test_unrecognized_url_returns_none(self) -> None:
        assert parse_workshop_id_from_url("https://example.com/mod") is None

    def test_query_id_with_ampersand_suffix(self) -> None:
        url = "https://steamcommunity.com/sharedfiles/filedetails/?id=33333&foo=bar"
        assert parse_workshop_id_from_url(url) == "33333"


class TestResolveDependencyWorkshopId:
    def test_steam_db_match(self) -> None:
        metadata = MagicMockMetadata()
        result = resolve_dependency_workshop_id(
            cast(MetadataController, metadata), "author.missing", set()
        )
        assert isinstance(result, DepResolveResult)
        assert result.workshop_id == "999"
        assert result.source == "steam_db"

    def test_about_xml_match(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "parent"
        about_dir = parent_path / "About"
        about_dir.mkdir(parents=True)
        about_xml = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <modDependencies>
    <li>
      <packageId>author.fromabout</packageId>
      <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id=55555</steamWorkshopUrl>
    </li>
  </modDependencies>
</ModMetaData>
"""
        (about_dir / "About.xml").write_text(about_xml, encoding="utf-8")

        parent = _make_mod(
            "author.parent",
            str(parent_path),
            dependencies={
                "author.fromabout": DependencyMod(
                    package_id=CaseInsensitiveStr("author.fromabout")
                )
            },
        )
        metadata = MagicMockMetadata(
            mods_metadata={str(parent_path): parent},
            active_paths={str(parent_path)},
            steam_db_empty=True,
        )

        result = resolve_dependency_workshop_id(
            cast(MetadataController, metadata),
            "author.fromabout",
            {str(parent_path)},
        )

        assert result.workshop_id == "55555"
        assert result.source == "about_xml"

    def test_no_match_returns_none_source(self) -> None:
        metadata = MagicMockMetadata(steam_db_empty=True)
        result = resolve_dependency_workshop_id(
            cast(MetadataController, metadata), "author.unknown", set()
        )
        assert result.workshop_id is None
        assert result.workshop_url is None
        assert result.source == "none"

    def test_versioned_about_xml_match(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "parent"
        about_dir = parent_path / "About"
        about_dir.mkdir(parents=True)
        about_xml = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <modDependenciesByVersion>
    <v1.5>
      <li>
        <packageId>author.versioned</packageId>
        <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id=77777</steamWorkshopUrl>
      </li>
    </v1.5>
  </modDependenciesByVersion>
</ModMetaData>
"""
        (about_dir / "About.xml").write_text(about_xml, encoding="utf-8")

        parent = _make_mod(
            "author.parent",
            str(parent_path),
            dependencies={
                "author.versioned": DependencyMod(
                    package_id=CaseInsensitiveStr("author.versioned")
                )
            },
        )
        metadata = MagicMockMetadata(
            mods_metadata={str(parent_path): parent},
            active_paths={str(parent_path)},
            steam_db_empty=True,
            prefer_versioned=True,
        )

        result = resolve_dependency_workshop_id(
            cast(MetadataController, metadata),
            "author.versioned",
            {str(parent_path)},
        )

        assert result.workshop_id == "77777"
        assert result.source == "about_xml"

    def test_about_xml_package_id_case_insensitive(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "parent"
        about_dir = parent_path / "About"
        about_dir.mkdir(parents=True)
        about_xml = """<?xml version="1.0" encoding="utf-8"?>
<ModMetaData>
  <modDependencies>
    <li>
      <packageId>Author.MixedCase</packageId>
      <steamWorkshopUrl>https://steamcommunity.com/sharedfiles/filedetails/?id=88888</steamWorkshopUrl>
    </li>
  </modDependencies>
</ModMetaData>
"""
        (about_dir / "About.xml").write_text(about_xml, encoding="utf-8")

        parent = _make_mod("author.parent", str(parent_path))
        metadata = MagicMockMetadata(
            mods_metadata={str(parent_path): parent},
            active_paths={str(parent_path)},
            steam_db_empty=True,
        )

        result = resolve_dependency_workshop_id(
            cast(MetadataController, metadata),
            "author.mixedcase",
            {str(parent_path)},
        )

        assert result.workshop_id == "88888"
        assert result.source == "about_xml"


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
            cast(MetadataController, metadata), {"/mods/parent"}
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
            cast(MetadataController, metadata), {"/mods/parent"}
        )

        assert deps_summary["author.parent"]["local"] == {"author.localdep"}
        assert deps_summary["author.parent"]["download"] == set()
        assert missing_deps["author.parent"] == {"author.localdep"}
        assert "author.localdep" not in dep_resolve

    def test_satisfied_dependency_not_missing(self) -> None:
        parent = _make_mod(
            "author.parent",
            "/mods/parent",
            dependencies={
                "author.core": DependencyMod(
                    package_id=CaseInsensitiveStr("author.core")
                )
            },
        )
        core = _make_mod("author.core", "/mods/core")
        metadata = MagicMockMetadata(
            mods_metadata={
                "/mods/parent": parent,
                "/mods/core": core,
            },
            active_paths={"/mods/parent", "/mods/core"},
        )

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            cast(MetadataController, metadata), {"/mods/parent", "/mods/core"}
        )

        assert deps_summary["author.parent"]["satisfied"] == {"author.core"}
        assert deps_summary["author.parent"]["local"] == set()
        assert deps_summary["author.parent"]["download"] == set()
        assert "author.parent" not in missing_deps
        assert dep_resolve == {}

    def test_alternative_package_id_satisfies_dependency(self) -> None:
        paths = {"/mods/parent", "/mods/alt"}
        metadata = _make_alt_dependency_metadata(paths)

        deps_summary, missing_deps, _ = build_dependencies_dialog_context(
            metadata, paths
        )

        assert deps_summary["author.parent"]["satisfied"] == {"author.required"}
        assert "author.parent" not in missing_deps

    def test_alternative_local_dep_classified_as_local(self) -> None:
        paths = {"/mods/parent"}
        metadata = _make_alt_dependency_metadata(paths)

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            metadata, paths
        )

        assert deps_summary["author.parent"]["local"] == {"author.required"}
        assert deps_summary["author.parent"]["download"] == set()
        assert missing_deps["author.parent"] == {"author.required"}
        assert "author.required" not in dep_resolve

    def test_skips_mod_without_package_id(self) -> None:
        parent = _make_mod(
            "author.parent",
            "/mods/parent",
            dependencies={
                "author.missing": DependencyMod(
                    package_id=CaseInsensitiveStr("author.missing")
                )
            },
        )
        parent.package_id = CaseInsensitiveStr("")
        metadata = MagicMockMetadata(
            mods_metadata={"/mods/parent": parent},
            active_paths={"/mods/parent"},
        )

        deps_summary, missing_deps, dep_resolve = build_dependencies_dialog_context(
            cast(MetadataController, metadata), {"/mods/parent"}
        )

        assert deps_summary == {}
        assert missing_deps == {}
        assert dep_resolve == {}


class MagicMockMetadata:
    def __init__(
        self,
        mods_metadata: dict[str, AboutXmlMod] | None = None,
        active_paths: set[str] | None = None,
        steam_db_empty: bool = False,
        use_alternatives: bool = False,
        prefer_versioned: bool = False,
    ) -> None:
        self.mods_metadata = mods_metadata or {}
        self.active_paths = active_paths or set()
        self.steam_db = (
            None
            if steam_db_empty
            else type(
                "DB",
                (),
                {
                    "database": {
                        "999": type("Entry", (), {"packageId": "author.missing"})(),
                    }
                },
            )()
        )
        self.game_version = "1.5"
        self.settings = type(
            "S",
            (),
            {
                "prefer_versioned_about_tags": prefer_versioned,
                "use_alternative_package_ids_as_satisfying_dependencies": use_alternatives,
            },
        )()
