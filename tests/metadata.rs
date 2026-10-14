//! Behavioral tests for `About.xml` metadata parsing (Task 1).
//!
//! Every case is a hand-authored fixture under `tests/fixtures/metadata`; no
//! real user files or game directories are read.

mod support;

use rimsort_rust::domain::metadata::parse_about;
use rimsort_rust::domain::types::{
    DiagnosticKind, Error, GameVersion, ModId, ModMetadata, PackageId, ParsedMetadata, Source,
};
use support::about_fixture;

/// Parses the target version, failing the test with the parse error when the
/// version under test is itself unusable.
fn target(text: &str) -> GameVersion {
    GameVersion::parse(text).unwrap_or_else(|error| panic!("version {text:?} must parse: {error}"))
}

fn parse(case: &str, version: &GameVersion) -> ParsedMetadata {
    parse_about(&about_fixture(case), version)
        .unwrap_or_else(|error| panic!("{case}: fixture must parse: {error}"))
}

fn parse_error(case: &str, version: &GameVersion) -> Error {
    match parse_about(&about_fixture(case), version) {
        Ok(parsed) => panic!("{case}: expected an error, parsed {parsed:?}"),
        Err(error) => error,
    }
}

fn normalized(ids: &[PackageId]) -> Vec<&str> {
    ids.iter().map(PackageId::as_str).collect()
}

fn package_id(parsed: &ParsedMetadata) -> Option<&str> {
    parsed.package_id.as_ref().map(PackageId::as_str)
}

fn kinds(parsed: &ParsedMetadata) -> Vec<String> {
    parsed
        .diagnostics
        .iter()
        .map(|diagnostic| diagnostic.kind.to_string())
        .collect()
}

fn has_diagnostic(parsed: &ParsedMetadata, kind: &DiagnosticKind) -> bool {
    parsed
        .diagnostics
        .iter()
        .any(|diagnostic| &diagnostic.kind == kind)
}

fn has_diagnostic_at(parsed: &ParsedMetadata, kind: &DiagnosticKind, element: &str) -> bool {
    parsed
        .diagnostics
        .iter()
        .any(|diagnostic| &diagnostic.kind == kind && diagnostic.element == element)
}

/// Diagnostics as `message @ element path`, for failure output.
fn diagnostic_report(parsed: &ParsedMetadata) -> Vec<String> {
    parsed
        .diagnostics
        .iter()
        .map(|diagnostic| format!("{} @ {}", diagnostic.kind, diagnostic.element))
        .collect()
}

/// Parses inline XML for the document-envelope and attribute cases, where a
/// fixture directory would hide what the document actually contains.
fn parse_inline(label: &str, xml: &str) -> ParsedMetadata {
    parse_about(xml.as_bytes(), &target("1.5.1234"))
        .unwrap_or_else(|error| panic!("{label}: document must parse: {error}"))
}

fn inline_error(label: &str, xml: &str) -> Error {
    match parse_about(xml.as_bytes(), &target("1.5.1234")) {
        Ok(parsed) => panic!("{label}: expected an error, parsed {parsed:?}"),
        Err(error) => error,
    }
}

/// Minimal valid document the envelope tests surround with extra content.
const ENVELOPE_ROOT: &str =
    "<ModMetaData><packageId>envelope.mod</packageId><name>Envelope</name></ModMetaData>";

#[test]
fn normalizes_package_ids() {
    let parsed = parse("package_id_normalization", &target("1.5.1234"));

    assert_eq!(
        package_id(&parsed),
        Some("author.mod"),
        "packageId is trimmed and case-normalized"
    );
    assert_eq!(
        normalized(&parsed.load_after),
        ["other.mod", "third.mod"],
        "loadAfter entries are normalized and case-insensitive duplicates removed in declaration order"
    );
    assert_eq!(
        normalized(&parsed.incompatible_with),
        ["incompat.mod"],
        "incompatibleWith entries are normalized"
    );
    assert_eq!(
        PackageId::normalize("  Author.Mod  ").map(|id| id.as_str().to_string()),
        Some("author.mod".to_string()),
        "PackageId::normalize trims and lowercases"
    );
    assert!(
        PackageId::normalize("   ").is_none(),
        "a blank package id is not an identity"
    );
}

#[test]
fn parses_single_and_multiple_list_items() {
    let parsed = parse("list_items", &target("1.5.1234"));

    assert_eq!(
        parsed.authors,
        ["Solo Author", "First Author", "Second Author"],
        "a singular author element and single or multiple li elements are all collected"
    );
    assert_eq!(
        normalized(&parsed.load_before),
        ["before.only"],
        "one li is a single entry"
    );
    assert_eq!(
        normalized(&parsed.load_after),
        ["after.one", "after.two"],
        "repeated identical entries are deduplicated, keeping declaration order"
    );
    assert_eq!(
        normalized(&parsed.incompatible_with),
        ["incompat.one", "incompat.two"],
        "multiple li entries are preserved"
    );
    assert_eq!(
        parsed.supported_versions,
        vec![target("1.4"), target("1.5")],
        "supportedVersions li entries are parsed as releases"
    );
    assert!(
        parsed.supports_version(&target("1.5.1234")),
        "a supported release matches the build-suffixed target"
    );
    assert!(
        !parsed.supports_version(&target("1.6")),
        "an unsupported release does not match"
    );
    assert_eq!(parsed.description.as_deref(), Some("A plain description."));
    assert_eq!(
        parsed.url.as_deref(),
        Some("https://example.invalid/list-items")
    );
    assert_eq!(parsed.mod_version.as_deref(), Some("1.2.3"));
    assert_eq!(
        parsed.mod_icon_path.as_deref(),
        Some("Mods/list.items/Icon.png")
    );
    assert_eq!(parsed.steam_app_id, Some(1_149_640));
    assert!(
        parsed.diagnostics.is_empty(),
        "an unknown element is ignored without diagnostics, got {:?}",
        kinds(&parsed)
    );
}

#[test]
fn empty_version_override_replaces_base() {
    let parsed = parse("empty_version_override", &target("1.5.1234"));

    assert_eq!(
        package_id(&parsed),
        Some("empty.override"),
        "the record itself still parses"
    );
    assert!(
        parsed.load_after.is_empty(),
        "a matching empty loadAfterByVersion erases base entries, got {:?}",
        normalized(&parsed.load_after)
    );
    assert!(
        parsed.load_before.is_empty(),
        "a matching empty loadBeforeByVersion erases base entries, got {:?}",
        normalized(&parsed.load_before)
    );
    assert!(
        parsed.incompatible_with.is_empty(),
        "a matching empty incompatibleWithByVersion erases base entries, got {:?}",
        normalized(&parsed.incompatible_with)
    );
    assert!(
        parsed.dependencies.is_empty(),
        "a matching empty modDependenciesByVersion erases base dependencies, got {:?}",
        parsed.dependencies
    );
}

#[test]
fn nonmatching_version_uses_base() {
    let parsed = parse("nonmatching_version", &target("1.5.1234"));

    assert_eq!(
        normalized(&parsed.load_after),
        ["base.after"],
        "a non-matching version key keeps the base entries"
    );
    assert_eq!(
        normalized(&parsed.incompatible_with),
        ["base.incompat"],
        "a non-matching version key keeps the base incompatibilities"
    );
    assert_eq!(
        parsed
            .dependencies
            .iter()
            .map(|dependency| dependency.package_id.as_str())
            .collect::<Vec<_>>(),
        ["base.dep"],
        "a non-matching version key keeps the base dependencies"
    );

    let parsed_1_4 = parse("nonmatching_version", &target("1.4"));
    assert_eq!(
        normalized(&parsed_1_4.load_after),
        ["old.after"],
        "the version that does match replaces the base entries"
    );
    assert_eq!(
        normalized(&parsed_1_4.incompatible_with),
        ["old.incompat"],
        "the version that does match replaces the base incompatibilities"
    );
    assert_eq!(
        parsed_1_4
            .dependencies
            .iter()
            .map(|dependency| dependency.package_id.as_str())
            .collect::<Vec<_>>(),
        ["old.dep"],
        "the version that does match replaces the base dependencies"
    );
}

#[test]
fn force_load_survives_override() {
    let parsed = parse("force_load_override", &target("1.5.1234"));

    assert_eq!(
        normalized(&parsed.load_after),
        ["versioned.after", "force.after"],
        "forceLoadAfter is added after a versioned override, which itself replaces the base entries"
    );
    assert_eq!(
        normalized(&parsed.load_before),
        ["versioned.before", "force.before"],
        "forceLoadBefore is added after a versioned override, which itself replaces the base entries"
    );
    assert!(
        !normalized(&parsed.load_after).contains(&"base.after"),
        "the overridden base entry is gone"
    );
    assert!(
        !normalized(&parsed.load_before).contains(&"base.before"),
        "the overridden base entry is gone"
    );
}

#[test]
fn alternative_dependency_ids_are_preserved() {
    let parsed = parse("alternative_dependencies", &target("1.5.1234"));

    assert_eq!(
        parsed.dependencies.len(),
        2,
        "both dependency entries are kept"
    );
    let primary = &parsed.dependencies[0];
    assert_eq!(primary.package_id.as_str(), "primary.dep");
    assert_eq!(primary.display_name.as_deref(), Some("Primary Dep"));
    assert_eq!(
        primary.workshop_url.as_deref(),
        Some("https://example.invalid/workshop/12345")
    );
    assert_eq!(
        normalized(&primary.alternatives),
        ["alt.one", "alt.two"],
        "alternativePackageIds keep declaration order, are normalized, and stay alternatives rather than extra requirements"
    );

    let second = &parsed.dependencies[1];
    assert_eq!(second.package_id.as_str(), "no.alts");
    assert_eq!(second.display_name, None);
    assert!(
        second.alternatives.is_empty(),
        "a dependency without alternatives has none recorded"
    );
    assert!(
        parsed.diagnostics.is_empty(),
        "alternative ids are valid metadata, got {:?}",
        kinds(&parsed)
    );
}

#[test]
fn official_metadata_without_name_is_visible() {
    let parsed = parse("official_without_name", &target("1.5.1234"));

    assert_eq!(package_id(&parsed), Some("ludeon.rimworld.royalty"));
    assert_eq!(
        parsed.name, None,
        "an omitted name stays omitted instead of being invented from a hardcoded table"
    );
    assert_eq!(parsed.description, None);
    assert!(
        parsed.is_valid(),
        "official content without a name is still a usable record, got {:?}",
        kinds(&parsed)
    );
    assert!(
        has_diagnostic(&parsed, &DiagnosticKind::MissingName),
        "the omission is visible as a diagnostic, got {:?}",
        kinds(&parsed)
    );
    assert_eq!(
        parsed.diagnostics[0].element, "ModMetaData",
        "the diagnostic names the element it came from"
    );
}

#[test]
fn malformed_xml_is_an_error() {
    let error = parse_error("malformed_xml", &target("1.5.1234"));

    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "a mismatched closing tag is a syntax error, got {error}"
    );
}

#[test]
fn unclosed_element_is_an_error() {
    let error = parse_error("unclosed_element", &target("1.5.1234"));

    assert!(
        matches!(error, Error::XmlSyntax { ref message, .. } if !message.is_empty()),
        "a document that ends inside an element is a syntax error, got {error}"
    );
}

#[test]
fn second_root_element_is_an_error() {
    let error = inline_error(
        "two root elements",
        "<ModMetaData><packageId>a.mod</packageId></ModMetaData><ModMetaData><packageId>b.mod</packageId></ModMetaData>",
    );

    assert!(
        matches!(error, Error::XmlSyntax { ref message, .. } if message.contains("more than one root element")),
        "a document with two root elements is refused, got {error}"
    );
}

#[test]
fn dtd_declarations_are_rejected() {
    let error = parse_error("dtd_entity", &target("1.5.1234"));

    assert!(
        matches!(error, Error::DocTypeNotAllowed { .. }),
        "a DTD is refused rather than resolved, got {error}"
    );
}

#[test]
fn undefined_entity_references_are_rejected() {
    let error = parse_error("undefined_entity", &target("1.5.1234"));

    assert!(
        matches!(error, Error::UnsupportedEntity { ref name, .. } if name == "mystery"),
        "a general entity that would need a DTD is refused, got {error}"
    );
}

#[test]
fn predefined_entities_are_decoded() {
    let parsed = parse("predefined_entities", &target("1.5.1234"));

    assert_eq!(
        parsed.name.as_deref(),
        Some("Tom & Jerry"),
        "predefined entities are expanded without losing inner spacing"
    );
    assert_eq!(
        parsed.description.as_deref(),
        Some("A <tag> \"quote\" \u{2014} dash with & again"),
        "predefined entities and character references are expanded"
    );
    assert_eq!(
        normalized(&parsed.load_after),
        ["a&b"],
        "entities are expanded inside list entries too"
    );
}

#[test]
fn numeric_version_keys_distinguish_1_5_from_1_50() {
    let parsed_1_5 = parse("version_key_precision", &target("1.5.1234"));

    assert_eq!(
        normalized(&parsed_1_5.load_after),
        ["base.after"],
        "a v1.50 key is not a match for target 1.5"
    );
    assert_eq!(
        normalized(&parsed_1_5.load_before),
        ["build.scoped.before"],
        "a v1.5.4171 key names release 1.5 and does match"
    );

    let parsed_1_50 = parse("version_key_precision", &target("1.50"));

    assert_eq!(
        normalized(&parsed_1_50.load_after),
        ["release.150"],
        "the 1.50 release selects its own versioned entries"
    );
    assert_eq!(
        normalized(&parsed_1_50.load_before),
        ["base.before"],
        "1.50 does not match a v1.5.4171 key"
    );
}

#[test]
fn missing_package_id_is_invalid_without_synthetic_identity() {
    let parsed = parse("missing_package_id", &target("1.5.1234"));

    assert_eq!(
        package_id(&parsed),
        None,
        "no identity is manufactured, so two such mods cannot collide on one shared id"
    );
    assert!(
        !parsed.is_valid(),
        "a record without a package id is invalid but still returned"
    );
    assert!(
        has_diagnostic(&parsed, &DiagnosticKind::MissingPackageId),
        "the reason is reported as a diagnostic, got {:?}",
        kinds(&parsed)
    );
    assert_eq!(
        parsed.name.as_deref(),
        Some("No Package Id"),
        "the rest of the record stays inspectable"
    );
    assert_eq!(normalized(&parsed.load_after), ["some.dep"]);
}

#[test]
fn blank_package_id_is_invalid() {
    let parsed = parse("blank_package_id", &target("1.5.1234"));

    assert_eq!(package_id(&parsed), None);
    assert!(!parsed.is_valid());
    assert!(
        has_diagnostic(&parsed, &DiagnosticKind::EmptyPackageId),
        "a whitespace-only packageId is reported, got {:?}",
        kinds(&parsed)
    );
}

#[test]
fn optional_fields_absent_are_not_fatal() {
    let parsed = parse("minimal", &target("1.5.1234"));

    assert_eq!(package_id(&parsed), Some("minimal.mod"));
    assert!(
        parsed.is_valid(),
        "absent optional fields do not invalidate the record, got {:?}",
        kinds(&parsed)
    );
    assert!(parsed.authors.is_empty());
    assert_eq!(parsed.description, None);
    assert!(parsed.supported_versions.is_empty());
    assert!(parsed.dependencies.is_empty());
    assert!(parsed.load_after.is_empty());
    assert!(parsed.load_before.is_empty());
    assert!(parsed.incompatible_with.is_empty());
    assert_eq!(parsed.url, None);
    assert_eq!(parsed.steam_app_id, None);
}

#[test]
fn element_names_are_matched_regardless_of_case() {
    let parsed = parse("case_normalized_root", &target("1.5.1234"));

    assert_eq!(
        package_id(&parsed),
        Some("case.normalized"),
        "a lowercase root and mixed-case child names are still recognized"
    );
    assert_eq!(parsed.name.as_deref(), Some("Case Normalized"));
    assert_eq!(
        parsed.description.as_deref(),
        Some("Root and child names are matched regardless of case.")
    );
    assert_eq!(parsed.supported_versions, vec![target("1.5")]);
    assert_eq!(normalized(&parsed.load_after), ["some.mod"]);
    assert_eq!(
        parsed
            .dependencies
            .iter()
            .map(|dependency| dependency.package_id.as_str())
            .collect::<Vec<_>>(),
        ["wants.dep"]
    );
    assert_eq!(
        normalized(&parsed.dependencies[0].alternatives),
        ["wants.alt"],
        "versioned and nested element names are matched case-insensitively"
    );
}

#[test]
fn dependency_duplicates_and_headless_entries_are_reported() {
    let parsed = parse("dependency_diagnostics", &target("1.5.1234"));

    assert_eq!(
        parsed.dependencies.len(),
        1,
        "only the first spelling of a duplicated dependency is kept, got {:?}",
        parsed.dependencies
    );
    assert_eq!(parsed.dependencies[0].package_id.as_str(), "dup.dep");
    assert_eq!(
        parsed.dependencies[0].display_name, None,
        "the first entry wins, so its fields are the ones kept"
    );
    assert!(
        has_diagnostic(
            &parsed,
            &DiagnosticKind::DuplicateDependency {
                package_id: PackageId::normalize("dup.dep").expect("test id"),
            }
        ),
        "the skipped duplicate is reported, got {:?}",
        kinds(&parsed)
    );
    assert!(
        has_diagnostic(&parsed, &DiagnosticKind::DependencyWithoutPackageId),
        "a dependency entry without a packageId is reported, got {:?}",
        kinds(&parsed)
    );
    assert!(parsed.is_valid(), "the mod record itself stays valid");
}

#[test]
fn dependency_and_list_entries_without_items_are_read() {
    let parsed = parse("plain_entries", &target("1.5.1234"));

    assert_eq!(
        parsed
            .dependencies
            .iter()
            .map(|dependency| dependency.package_id.as_str())
            .collect::<Vec<_>>(),
        ["wrapped.dep"],
        "a single dependency written without an li wrapper is still read"
    );
    assert_eq!(
        parsed.dependencies[0].display_name.as_deref(),
        Some("Wrapped Dep")
    );
    assert_eq!(
        normalized(&parsed.incompatible_with),
        ["plain.incompat"],
        "a list field written as plain text instead of li items is still read"
    );
    assert_eq!(normalized(&parsed.load_after), ["normal.entry"]);
}

#[test]
fn invalid_field_values_are_reported_without_failing_the_record() {
    let parsed = parse("invalid_field_values", &target("1.5.1234"));

    assert_eq!(
        parsed.supported_versions,
        vec![target("1.5")],
        "only the numeric supported version is kept"
    );
    assert!(has_diagnostic(
        &parsed,
        &DiagnosticKind::InvalidSupportedVersion {
            raw: "nightly".to_string(),
        }
    ));
    assert_eq!(
        parsed.steam_app_id, None,
        "a non-numeric steamAppId is not guessed at"
    );
    assert!(has_diagnostic(
        &parsed,
        &DiagnosticKind::InvalidSteamAppId {
            raw: "not-a-number".to_string(),
        }
    ));
    assert!(
        parsed.load_after.is_empty(),
        "a list entry carrying markup instead of text is dropped, got {:?}",
        normalized(&parsed.load_after)
    );
    assert!(has_diagnostic(
        &parsed,
        &DiagnosticKind::UnreadableEntry {
            field: "loadAfter".to_string(),
        }
    ));
    assert!(
        parsed.is_valid(),
        "unusable field values are warnings, not a fatal record"
    );
}

#[test]
fn unexpected_root_is_an_error() {
    let error = parse_error("wrong_root", &target("1.5.1234"));

    assert!(
        matches!(error, Error::UnexpectedRoot { ref found } if found == "SaveGame"),
        "a document that is not mod metadata is refused, got {error}"
    );
}

#[test]
fn description_by_version_replaces_base() {
    assert_eq!(
        parse("description_by_version", &target("1.5.1234"))
            .description
            .as_deref(),
        Some("Versioned description"),
        "a matching descriptionsByVersion entry replaces the base description"
    );
    assert_eq!(
        parse("description_by_version", &target("1.4"))
            .description
            .as_deref(),
        Some("Old description"),
        "the key that matches the target is the one used"
    );
    assert_eq!(
        parse("description_by_version", &target("1.6"))
            .description
            .as_deref(),
        Some("Base description"),
        "without a matching key the base description stays"
    );
}

#[test]
fn game_version_parses_releases_and_rejects_invalid_text() {
    let plain = GameVersion::parse("1.5").expect("1.5 parses");
    assert_eq!((plain.major(), plain.minor()), (1, 5));
    assert_eq!(plain.display(), "1.5");

    let with_build = GameVersion::parse("1.5.4171 rev0").expect("build suffix parses");
    assert_eq!((with_build.major(), with_build.minor()), (1, 5));
    assert_eq!(with_build.display(), "1.5.4171 rev0");
    assert_eq!(
        with_build, plain,
        "a release identity is major.minor, the build label is display only"
    );
    assert_eq!(
        GameVersion::parse(" 1.5 ")
            .expect("surrounding whitespace is trimmed")
            .display(),
        "1.5"
    );
    assert!(
        GameVersion::parse("1.10").expect("1.10 parses")
            > GameVersion::parse("1.9").expect("1.9 parses"),
        "versions compare numerically, not lexically"
    );

    for invalid in ["", "   ", "unknown", "1", "1.5x", "v1.5"] {
        assert!(
            matches!(
                GameVersion::parse(invalid),
                Err(Error::InvalidGameVersion { .. })
            ),
            "{invalid:?} is not a numeric release"
        );
    }

    let version = GameVersion::parse("1.5").expect("1.5 parses");
    assert!(version.matches_version_key("v1.5"));
    assert!(version.matches_version_key("v1.5.4171"));
    assert!(
        !version.matches_version_key("v1.50"),
        "1.50 is a different release than 1.5"
    );
    assert!(!version.matches_version_key("v15"));
    assert!(!version.matches_version_key("v1.5x"));
    assert!(!version.matches_version_key("v1"));
}

#[test]
fn mod_metadata_attaches_identity_and_source() {
    let parsed = parse("minimal", &target("1.5.1234"));
    let metadata = ModMetadata::new(
        ModId::new("/game/RimWorld/Data/Core"),
        Source::Official,
        parsed.clone(),
    );

    assert_eq!(
        metadata.id.as_path().to_string_lossy(),
        "/game/RimWorld/Data/Core"
    );
    assert_eq!(metadata.source, Source::Official);
    assert_eq!(metadata.parsed, parsed);
    assert!(metadata.is_valid());
    assert!(
        Source::Official < Source::Local && Source::Local < Source::Workshop,
        "source ordering follows the resolver priority"
    );
    assert_eq!(Source::SteamCmd.to_string(), "steamcmd");
    assert_eq!(
        ModId::new("/game/RimWorld/Data/Core").to_string(),
        "/game/RimWorld/Data/Core"
    );
}

#[test]
fn text_outside_the_root_element_is_an_error() {
    let leading = inline_error(
        "character data before the root",
        &format!("garbage{ENVELOPE_ROOT}"),
    );
    assert!(
        matches!(leading, Error::XmlSyntax { .. }),
        "text before the root element is refused, got {leading}"
    );

    let trailing = inline_error(
        "character data after the root",
        &format!("{ENVELOPE_ROOT}garbage"),
    );
    assert!(
        matches!(trailing, Error::XmlSyntax { .. }),
        "text after the root element is refused, got {trailing}"
    );
}

#[test]
fn cdata_and_references_outside_the_root_element_are_errors() {
    let cdata = inline_error(
        "CDATA after the root",
        &format!("{ENVELOPE_ROOT}<![CDATA[tail]]>"),
    );
    assert!(
        matches!(cdata, Error::XmlSyntax { .. }),
        "CDATA outside the root element is refused, got {cdata}"
    );

    let reference = inline_error(
        "entity reference before the root",
        &format!("&amp;{ENVELOPE_ROOT}"),
    );
    assert!(
        matches!(reference, Error::XmlSyntax { .. }),
        "an entity reference outside the root element is refused, got {reference}"
    );
}

#[test]
fn malformed_comment_is_an_error() {
    let error = inline_error(
        "double hyphen inside a comment",
        "<ModMetaData><!-- bad--comment --><packageId>envelope.mod</packageId></ModMetaData>",
    );
    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "an illegal comment is refused, got {error}"
    );
}

#[test]
fn misplaced_or_repeated_declaration_is_an_error() {
    let after_root = inline_error(
        "declaration after the root",
        &format!("{ENVELOPE_ROOT}<?xml version=\"1.0\"?>"),
    );
    assert!(
        matches!(after_root, Error::XmlSyntax { .. }),
        "a declaration cannot follow the root element, got {after_root}"
    );

    let repeated = inline_error(
        "two declarations",
        r#"<?xml version="1.0"?>
<?xml version="1.0"?>
<ModMetaData><packageId>envelope.mod</packageId></ModMetaData>"#,
    );
    assert!(
        matches!(repeated, Error::XmlSyntax { .. }),
        "a document has at most one declaration, got {repeated}"
    );

    let after_comment = inline_error(
        "declaration after a comment",
        r#"<!-- comment -->
<?xml version="1.0"?>
<ModMetaData><packageId>envelope.mod</packageId></ModMetaData>"#,
    );
    assert!(
        matches!(after_comment, Error::XmlSyntax { .. }),
        "only whitespace may precede the declaration, got {after_comment}"
    );
}

#[test]
fn legal_whitespace_and_comments_around_the_root_are_accepted() {
    let declared = parse_inline(
        "declaration, comments and whitespace around the root",
        r#"
<?xml version="1.0" encoding="utf-8"?>
<!-- leading comment -->
<ModMetaData>
  <packageId>envelope.mod</packageId>
  <name>Envelope</name>
</ModMetaData>
<!-- trailing comment -->
"#,
    );
    assert_eq!(package_id(&declared), Some("envelope.mod"));
    assert_eq!(declared.name.as_deref(), Some("Envelope"));

    let undeclared = parse_inline(
        "no declaration at all",
        r#"<!-- leading comment -->
<ModMetaData><packageId>envelope.mod</packageId></ModMetaData>
"#,
    );
    assert_eq!(package_id(&undeclared), Some("envelope.mod"));
    assert!(
        has_diagnostic_at(&undeclared, &DiagnosticKind::MissingName, "ModMetaData"),
        "a document without a declaration and with comments is accepted, got {:?}",
        diagnostic_report(&undeclared)
    );
    assert_eq!(
        undeclared.diagnostics.len(),
        1,
        "only the omitted name is reported, got {:?}",
        diagnostic_report(&undeclared)
    );
}

#[test]
fn duplicate_attributes_are_an_error() {
    let root = inline_error(
        "duplicate attribute on the root",
        r#"<ModMetaData a="1" a="2"><packageId>attrs.mod</packageId></ModMetaData>"#,
    );
    assert!(
        matches!(root, Error::XmlSyntax { .. }),
        "a repeated attribute name is refused, got {root}"
    );

    let nested = inline_error(
        "duplicate attribute on an ignored child",
        r#"<ModMetaData><packageId>attrs.mod</packageId><unknown b="1" b="2"/></ModMetaData>"#,
    );
    assert!(
        matches!(nested, Error::XmlSyntax { .. }),
        "attributes of ignored elements are validated too, got {nested}"
    );
}

#[test]
fn attribute_entity_reference_is_an_error() {
    let error = inline_error(
        "undeclared entity in an attribute",
        r#"<ModMetaData note="&mystery;"><packageId>attrs.mod</packageId></ModMetaData>"#,
    );
    assert!(
        matches!(error, Error::UnsupportedEntity { ref name, .. } if name == "mystery"),
        "an attribute cannot smuggle in a DTD entity, got {error}"
    );
}

#[test]
fn malformed_attribute_is_an_error() {
    let error = inline_error(
        "attribute without a value",
        r#"<ModMetaData note=><packageId>attrs.mod</packageId></ModMetaData>"#,
    );
    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "a malformed attribute is refused, got {error}"
    );
}

#[test]
fn valid_attribute_values_are_accepted() {
    let parsed = parse_inline(
        "escaped attribute values",
        r#"<ModMetaData xmlns:x="http://example.invalid" note="a &amp; b &#8212;" flag='true'>
  <packageId>attrs.mod</packageId>
  <name x:nil="false">Attributes</name>
</ModMetaData>"#,
    );
    assert_eq!(package_id(&parsed), Some("attrs.mod"));
    assert_eq!(
        parsed.name.as_deref(),
        Some("Attributes"),
        "attributes are validated but not read as values"
    );
}

#[test]
fn version_key_prefix_is_at_most_one_and_case_insensitive() {
    let version = target("1.5");
    assert!(
        version.matches_version_key("v1.5"),
        "the documented lowercase prefix matches"
    );
    assert!(
        version.matches_version_key("V1.5"),
        "an uppercase prefix matches, as element names do"
    );
    assert!(
        !version.matches_version_key("vv1.5"),
        "only one prefix is removed, a doubled prefix is not a version"
    );

    let parsed = parse("version_key_case", &target("1.5.1234"));
    assert_eq!(
        normalized(&parsed.load_after),
        ["upper.prefix.entry"],
        "a V1.5 override replaces the base entries while a vv1.5 key never matches"
    );
}

#[test]
fn wrapperless_dependency_container_without_id_is_reported() {
    let parsed = parse("wrapperless_dependency_without_id", &target("1.5.1234"));

    assert!(
        parsed.dependencies.is_empty(),
        "a dependency container without a packageId yields no dependency, got {:?}",
        parsed.dependencies
    );
    assert!(
        has_diagnostic_at(
            &parsed,
            &DiagnosticKind::DependencyWithoutPackageId,
            "ModMetaData/modDependencies",
        ),
        "the unusable container is reported rather than dropped, got {:?}",
        diagnostic_report(&parsed)
    );
    assert!(
        parsed.is_valid(),
        "the record itself stays usable, got {:?}",
        diagnostic_report(&parsed)
    );
}

#[test]
fn wrapperless_list_container_with_markup_is_reported() {
    let parsed = parse("wrapperless_list_markup", &target("1.5.1234"));

    assert!(
        parsed.load_after.is_empty(),
        "markup is not a load order entry, got {:?}",
        normalized(&parsed.load_after)
    );
    assert!(
        has_diagnostic_at(
            &parsed,
            &DiagnosticKind::UnreadableEntry {
                field: "loadAfter".to_string(),
            },
            "ModMetaData/loadAfter",
        ),
        "the unreadable field is reported, got {:?}",
        diagnostic_report(&parsed)
    );
    assert_eq!(
        normalized(&parsed.load_before),
        ["listed.before"],
        "a normal list field is unaffected"
    );
}

#[test]
fn versioned_dependency_diagnostics_name_the_versioned_source() {
    let parsed = parse("versioned_dependency_diagnostics", &target("1.5.1234"));

    assert_eq!(
        parsed
            .dependencies
            .iter()
            .map(|dependency| dependency.package_id.as_str())
            .collect::<Vec<_>>(),
        ["versioned.dup", "versioned.alts"],
        "the matching versioned container replaces the base dependencies"
    );

    let versioned_item = "ModMetaData/modDependenciesByVersion/v1.5/li";
    assert!(
        has_diagnostic_at(
            &parsed,
            &DiagnosticKind::DependencyWithoutPackageId,
            versioned_item,
        ),
        "a versioned headless dependency names the versioned path, got {:?}",
        diagnostic_report(&parsed)
    );
    assert!(
        has_diagnostic_at(
            &parsed,
            &DiagnosticKind::DuplicateDependency {
                package_id: PackageId::normalize("versioned.dup").expect("test id"),
            },
            versioned_item,
        ),
        "a versioned duplicate names the versioned path, got {:?}",
        diagnostic_report(&parsed)
    );
    assert!(
        has_diagnostic_at(
            &parsed,
            &DiagnosticKind::UnreadableEntry {
                field: "alternativePackageIds".to_string(),
            },
            "ModMetaData/modDependenciesByVersion/v1.5/li/alternativePackageIds/li",
        ),
        "unreadable alternatives name the versioned path, got {:?}",
        diagnostic_report(&parsed)
    );
    assert!(
        !parsed
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.element == "ModMetaData/modDependencies/li"),
        "the overridden base container is not blamed, got {:?}",
        diagnostic_report(&parsed)
    );
}

#[test]
fn empty_version_override_still_keeps_force_load_entries() {
    let parsed = parse("force_load_empty_override", &target("1.5.1234"));

    assert_eq!(
        normalized(&parsed.load_after),
        ["force.after"],
        "an empty versioned override erases the base entries, and forceLoadAfter is still added"
    );
    assert_eq!(
        normalized(&parsed.load_before),
        ["force.before"],
        "an empty versioned override erases the base entries, and forceLoadBefore is still added"
    );
    assert!(
        parsed.diagnostics.is_empty(),
        "an intentional empty override is not a defect, got {:?}",
        diagnostic_report(&parsed)
    );
}
