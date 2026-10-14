//! Behavioral tests for read-only `ModsConfig.xml` loading (Task 2B).
//!
//! Every document is inline XML or a hand-authored fixture under
//! `tests/fixtures/config`; no real user configuration is read and nothing is
//! ever written.

// The config suite shares `fixture` with the other suites and uses none of
// their loaders, so the rest of the module is unused here by design.
#[allow(dead_code)]
mod support;

use rimsort_rust::domain::types::Error;
use rimsort_rust::integrations::config::{ConfigDiagnostic, ConfigSnapshot, parse_config};
use support::fixture;

/// Bytes of the hand-authored `ModsConfig.xml` for one config case.
fn config_fixture(case: &str) -> Vec<u8> {
    let path = fixture(&format!("config/{case}/ModsConfig.xml"));
    std::fs::read(&path).unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()))
}

/// Loads inline XML, failing with the parse error when the document is legal.
fn parse_inline(label: &str, xml: &str) -> ConfigSnapshot {
    parse_config(xml.as_bytes())
        .unwrap_or_else(|error| panic!("{label}: document must load: {error}"))
}

fn inline_error(label: &str, xml: &str) -> Error {
    match parse_config(xml.as_bytes()) {
        Ok(snapshot) => panic!("{label}: expected an error, loaded {snapshot:?}"),
        Err(error) => error,
    }
}

/// The bytes the active-list span selects out of the snapshot's own copy.
fn spanned(snapshot: &ConfigSnapshot) -> Vec<u8> {
    snapshot.raw[snapshot.active_mods_span.clone()].to_vec()
}

#[test]
fn reads_ordered_active_tokens_verbatim() {
    let snapshot = parse_inline(
        "ordered tokens",
        r#"<ModsConfigData>
  <version>1.5.4104 rev435</version>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>Ludeon.RimWorld.Royalty</li>
    <li>brrainz.harmony_steam</li>
    <li>CapsMod_Steam_Internal</li>
  </activeMods>
</ModsConfigData>
"#,
    );

    assert_eq!(
        snapshot.active_tokens,
        [
            "ludeon.rimworld".to_string(),
            "Ludeon.RimWorld.Royalty".to_string(),
            "brrainz.harmony_steam".to_string(),
            "CapsMod_Steam_Internal".to_string(),
        ],
        "tokens keep file order, case and every _steam spelling exactly as written"
    );
    assert_eq!(
        snapshot.version.as_deref(),
        Some("1.5.4104 rev435"),
        "version is the file's own display text"
    );
    assert!(
        snapshot.diagnostics.is_empty(),
        "a plain list carries no diagnostics, got {:?}",
        snapshot.diagnostics
    );
}

#[test]
fn span_covers_the_whole_active_mods_element() {
    let document = "<ModsConfigData>  <activeMods class=\"list\">\n  <li>a.mod</li>\n</activeMods></ModsConfigData>";
    let snapshot = parse_inline("full span", document);

    assert_eq!(
        spanned(&snapshot),
        b"<activeMods class=\"list\">\n  <li>a.mod</li>\n</activeMods>",
        "the span starts at the element's own '<' and ends after its '</activeMods>'"
    );
    assert_eq!(
        &snapshot.raw[..snapshot.active_mods_span.start],
        b"<ModsConfigData>  ",
        "bytes before the span are untouched"
    );
    assert_eq!(
        &snapshot.raw[snapshot.active_mods_span.end..],
        b"</ModsConfigData>",
        "bytes after the span are untouched"
    );
}

#[test]
fn span_positions_are_bytes_with_bom_and_non_ascii() {
    let document = concat!(
        "\u{feff}<?xml version=\"1.0\" encoding=\"utf-8\"?>\n",
        "<!-- Älä älä -->\n",
        "<ModsConfigData><version>1.5</version>",
        "<activeMods><li>Ähtäri</li></activeMods></ModsConfigData>",
    );
    let snapshot = parse_config(document.as_bytes())
        .unwrap_or_else(|error| panic!("bom document must load: {error}"));

    assert_eq!(
        snapshot.active_mods_span.start,
        document.find("<activeMods").expect("start marker"),
        "a BOM and non-ASCII text before the element shift it by bytes, not characters"
    );
    assert_eq!(
        snapshot.active_mods_span.end,
        document.find("</activeMods").expect("end marker") + "</activeMods>".len(),
        "the span end is the byte just after the closing tag"
    );
    assert_eq!(
        snapshot.raw,
        document.as_bytes(),
        "the snapshot owns the original bytes, BOM included"
    );
    assert_eq!(
        snapshot.active_tokens,
        ["Ähtäri".to_string()],
        "non-ASCII token text is preserved"
    );
}

#[test]
fn accepts_empty_active_mods_in_both_writings() {
    let paired = parse_inline(
        "paired empty",
        "<ModsConfigData><version>1.5</version><activeMods>\n  </activeMods></ModsConfigData>",
    );
    assert!(
        paired.active_tokens.is_empty(),
        "an empty list is a legal empty list, got {:?}",
        paired.active_tokens
    );
    assert!(paired.diagnostics.is_empty());
    assert_eq!(
        spanned(&paired),
        b"<activeMods>\n  </activeMods>",
        "the paired element's bytes are the span even when it holds no entry"
    );

    let self_closing = parse_inline(
        "self-closing",
        "<ModsConfigData><version>1.5</version><activeMods/></ModsConfigData>",
    );
    assert!(
        self_closing.active_tokens.is_empty(),
        "a self-closing list holds no entry"
    );
    assert!(self_closing.diagnostics.is_empty());
    assert_eq!(
        spanned(&self_closing),
        b"<activeMods/>",
        "a self-closing element is spanned as written"
    );
}

#[test]
fn retains_empty_entries_with_a_diagnostic() {
    let snapshot = parse_inline(
        "empty entries",
        "<ModsConfigData><activeMods><li/>\n<li>   </li><li>real.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        [String::new(), "   ".to_string(), "real.mod".to_string()],
        "no entry disappears and no spacing is invented"
    );
    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::EmptyToken { index: 0 },
            ConfigDiagnostic::EmptyToken { index: 1 },
        ],
        "every entry without non-whitespace text is reported where it sits"
    );
}

#[test]
fn reports_repeated_exact_tokens_with_positions() {
    let snapshot = parse_inline(
        "repeated tokens",
        "<ModsConfigData><activeMods><li>a.mod</li><li>b.mod</li><li>a.mod</li><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        [
            "a.mod".to_string(),
            "b.mod".to_string(),
            "a.mod".to_string(),
            "a.mod".to_string(),
        ],
        "a repeated entry stays in the list"
    );
    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::RepeatedToken {
                token: "a.mod".to_string(),
                first_index: 0,
                index: 2,
            },
            ConfigDiagnostic::RepeatedToken {
                token: "a.mod".to_string(),
                first_index: 0,
                index: 3,
            },
        ],
        "each later copy names its own position and the first one"
    );
}

#[test]
fn does_not_report_case_or_spacing_variants_as_repeats() {
    let snapshot = parse_inline(
        "distinct tokens",
        "<ModsConfigData><activeMods><li>A.Mod</li><li>a.mod</li><li>a.mod </li></activeMods></ModsConfigData>",
    );

    assert!(
        snapshot.diagnostics.is_empty(),
        "identity-equivalent copies are the catalog's decision, not the loader's: {:?}",
        snapshot.diagnostics
    );
}

#[test]
fn decodes_entities_and_keeps_literal_token_text() {
    let snapshot = parse_inline(
        "entity tokens",
        "<ModsConfigData><activeMods><li>Tom &amp; Jerry</li><li>&lt;tagged&gt;</li><li>Ähtäri &#233; Co</li><li>space   run</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        [
            "Tom & Jerry".to_string(),
            "<tagged>".to_string(),
            "Ähtäri é Co".to_string(),
            "space   run".to_string(),
        ],
        "references are decoded once and nothing else changes"
    );
}

#[test]
fn preserves_unknown_fields_and_comments_in_the_loaded_bytes() {
    let document = r#"<?xml version="1.0" encoding="utf-8"?>
<!-- generated by RimWorld -->
<ModsConfigData approved="true">
  <version>1.9.9999 rev9999</version>
  <activeMods><li>ludeon.rimworld</li></activeMods>
  <knownExpansions>
    <li>ludeon.rimworld.royalty</li>
  </knownExpansions>
  <someFutureField><nested>keep</nested></someFutureField>
</ModsConfigData>
"#;
    let snapshot = parse_inline("unknown fields", document);

    assert_eq!(
        snapshot.raw,
        document.as_bytes(),
        "everything outside the active list survives in the snapshot"
    );
    assert_eq!(
        snapshot.version.as_deref(),
        Some("1.9.9999 rev9999"),
        "an unknown version is reported verbatim, never coerced"
    );
    assert_eq!(
        snapshot.active_tokens,
        ["ludeon.rimworld".to_string()],
        "knownExpansions entries are not active entries"
    );
}

#[test]
fn reads_the_workshop_fixture_without_writing() {
    let case = "workshop_list";
    let path = fixture(&format!("config/{case}/ModsConfig.xml"));
    let parent = path.parent().expect("fixture case directory");
    let before = config_fixture(case);
    let listing_before = directory_listing(parent);

    let snapshot =
        parse_config(&before).unwrap_or_else(|error| panic!("{case}: fixture must load: {error}"));

    assert_eq!(
        snapshot.raw, before,
        "the snapshot owns the bytes it was given"
    );
    assert_eq!(
        snapshot.active_tokens,
        [
            "ludeon.rimworld".to_string(),
            "Ludeon.RimWorld.Royalty".to_string(),
            "brrainz.harmony".to_string(),
            "unresolved.mod_steam".to_string(),
        ],
        "a comment between entries does not disturb the order"
    );
    assert_eq!(
        config_fixture(case),
        before,
        "loading a config never rewrites the file"
    );
    assert_eq!(
        directory_listing(parent),
        listing_before,
        "loading a config creates no file next to it"
    );
}

fn directory_listing(directory: &std::path::Path) -> Vec<String> {
    let mut names = std::fs::read_dir(directory)
        .unwrap_or_else(|error| panic!("cannot list {}: {error}", directory.display()))
        .map(|entry| {
            entry
                .expect("entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect::<Vec<_>>();
    names.sort();
    names
}

#[test]
fn rejects_a_document_without_an_active_mods_element() {
    let error = inline_error(
        "missing list",
        "<ModsConfigData><version>1.5</version><knownExpansions><li>a</li></knownExpansions></ModsConfigData>",
    );
    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "a config without <activeMods> is unusable, got {error}"
    );
    assert!(
        error.to_string().contains("activeMods"),
        "the message must name the missing element, got {error}"
    );
}

#[test]
fn rejects_repeated_active_mods_elements() {
    let same_case = inline_error(
        "two lists",
        "<ModsConfigData><activeMods><li>a</li></activeMods><activeMods><li>b</li></activeMods></ModsConfigData>",
    );
    let other_case = inline_error(
        "case-variant lists",
        "<ModsConfigData><activeMods><li>a</li></activeMods><Activemods><li>b</li></Activemods></ModsConfigData>",
    );

    for error in [same_case, other_case] {
        assert!(
            matches!(error, Error::XmlSyntax { .. }),
            "a second activeMods container is refused, got {error}"
        );
    }
}

#[test]
fn rejects_the_wrong_root_and_keeps_the_element_name_visible() {
    let error = inline_error(
        "wrong root",
        "<ModList><version>1.5</version><activeMods><li>a</li></activeMods></ModList>",
    );

    assert!(
        matches!(&error, Error::XmlSyntax { element, .. } if element == "ModList"),
        "the error reports the root it found, got {error:?}"
    );
    assert!(
        error.to_string().contains("ModsConfigData"),
        "the error names the root that was expected, got {error}"
    );
}

#[test]
fn rejects_markup_nested_inside_an_active_entry() {
    for (label, document) in [
        (
            "entry in entry",
            "<ModsConfigData><activeMods><li><li>a</li></li></activeMods></ModsConfigData>",
        ),
        (
            "wrapped entry",
            "<ModsConfigData><activeMods><li>a<name>b</name></li></activeMods></ModsConfigData>",
        ),
        (
            "empty nested",
            "<ModsConfigData><activeMods><li><pack/></li></activeMods></ModsConfigData>",
        ),
    ] {
        let error = inline_error(label, document);
        assert!(
            matches!(error, Error::XmlSyntax { .. }),
            "{label}: nested markup inside <activeMods> is refused, got {error}"
        );
    }
}

#[test]
fn rejects_unsupported_children_and_stray_text_in_active_mods() {
    for (label, document) in [
        (
            "wrong entry name",
            "<ModsConfigData><activeMods><item>a.mod</item></activeMods></ModsConfigData>",
        ),
        (
            "bare text",
            "<ModsConfigData><activeMods>a.mod</activeMods></ModsConfigData>",
        ),
    ] {
        let error = inline_error(label, document);
        assert!(
            matches!(error, Error::XmlSyntax { .. }),
            "{label}: refused, got {error}"
        );
    }
}

#[test]
fn accepts_comments_inside_active_mods() {
    let snapshot = parse_inline(
        "comment inside list",
        "<ModsConfigData><activeMods><!-- pinned --><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["a.mod".to_string()],
        "a comment is not an entry, and the entries around it survive"
    );
}

#[test]
fn refuses_a_document_type_declaration() {
    let error = inline_error(
        "dtd",
        "<!DOCTYPE ModsConfigData [<!ELEMENT ModsConfigData ANY>]><ModsConfigData><activeMods><li>a</li></activeMods></ModsConfigData>",
    );

    assert!(
        matches!(error, Error::DocTypeNotAllowed { .. }),
        "the shared strict reader owns DTD refusal, got {error}"
    );
}

#[test]
fn refuses_an_undefined_entity() {
    let error = inline_error(
        "undefined entity",
        "<ModsConfigData><activeMods><li>&unknown;</li></activeMods></ModsConfigData>",
    );

    assert!(
        matches!(&error, Error::UnsupportedEntity { name, .. } if name == "unknown"),
        "entity references that need a DTD are refused, got {error}"
    );
}

#[test]
fn refuses_malformed_documents() {
    for (label, document) in [
        (
            "unclosed element",
            "<ModsConfigData><activeMods><li>a.mod</li></activeMods>",
        ),
        (
            "crossed tags",
            "<ModsConfigData><activeMods><li>a.mod</activeMods></li></ModsConfigData>",
        ),
        (
            "end tag of another element",
            "<ModsConfigData><activeMods><li>a.mod</li></wrong></ModsConfigData>",
        ),
        (
            "second root",
            "<ModsConfigData><activeMods><li>a</li></activeMods></ModsConfigData><ModsConfigData/>",
        ),
        (
            "literal angle in entry",
            "<ModsConfigData><activeMods><li>a<b></li></activeMods></ModsConfigData>",
        ),
        ("no document at all", ""),
    ] {
        let error = inline_error(label, document);
        assert!(
            matches!(error, Error::XmlSyntax { .. }),
            "{label}: refused as malformed, got {error}"
        );
    }
}

#[test]
fn version_is_optional_and_blank_text_is_absent() {
    let absent = parse_inline(
        "no version",
        "<ModsConfigData><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );
    assert_eq!(absent.version, None, "no <version> is no version");

    let blank = parse_inline(
        "blank version",
        "<ModsConfigData><version>   </version><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );
    assert_eq!(
        blank.version, None,
        "a version with nothing in it is not a release name"
    );
}

#[test]
fn keeps_surrounding_whitespace_of_an_entry() {
    let snapshot = parse_inline(
        "spaced entry",
        "<ModsConfigData><activeMods><li>  spaced.mod  </li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["  spaced.mod  ".to_string()],
        "entry text is taken as written; trimming would rewrite the file's data"
    );
    assert!(
        snapshot.diagnostics.is_empty(),
        "a spaced entry is not an empty one: {:?}",
        snapshot.diagnostics
    );
}

#[test]
fn a_nested_look_alike_after_the_list_is_not_the_active_list() {
    let snapshot = parse_inline(
        "nested activeMods",
        "<ModsConfigData><version>1.5</version><activeMods><li>a.mod</li></activeMods><modLists><activeMods><li>saved.list</li></activeMods></modLists></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["a.mod".to_string()],
        "only the root's own activeMods is the active list"
    );
    assert_eq!(
        spanned(&snapshot),
        b"<activeMods><li>a.mod</li></activeMods>",
        "and the span locates that element, not the nested one"
    );
}

#[test]
fn loads_a_bom_fixture_with_byte_accurate_span() {
    let case = "bom_non_ascii";
    let bytes = config_fixture(case);
    assert_eq!(
        &bytes[..3],
        &[0xEF, 0xBB, 0xBF],
        "the fixture really carries a UTF-8 byte order mark"
    );

    let snapshot =
        parse_config(&bytes).unwrap_or_else(|error| panic!("{case}: must load: {error}"));

    let start = bytes
        .windows(b"<activeMods".len())
        .position(|window| window == b"<activeMods")
        .expect("list start");
    let end = bytes
        .windows(b"</activeMods>".len())
        .position(|window| window == b"</activeMods>")
        .expect("list end")
        + b"</activeMods>".len();
    assert_eq!(
        snapshot.active_mods_span,
        start..end,
        "the span counts the BOM and every non-ASCII byte before the element"
    );
    assert_eq!(
        snapshot.active_tokens,
        [
            "ludeon.rimworld".to_string(),
            "Åsa.Übermod_steam".to_string(),
            "Älytön.模式".to_string(),
        ],
        "non-ASCII entries come through exactly as written"
    );
    assert_eq!(snapshot.raw, bytes, "the file bytes are kept whole");
}

#[test]
fn loads_an_empty_list_fixture_and_preserves_the_rest() {
    let case = "empty_list";
    let bytes = config_fixture(case);
    let snapshot =
        parse_config(&bytes).unwrap_or_else(|error| panic!("{case}: must load: {error}"));

    assert!(
        snapshot.active_tokens.is_empty(),
        "the fixture's list is empty: {:?}",
        snapshot.active_tokens
    );
    assert!(snapshot.diagnostics.is_empty());
    assert_eq!(
        spanned(&snapshot),
        b"<activeMods>\n  </activeMods>",
        "an empty list still has exact bytes"
    );
    assert_eq!(
        snapshot.version.as_deref(),
        Some("1.6.4200 rev1"),
        "a version this rewrite does not know is still reported verbatim"
    );
    assert_eq!(snapshot.raw, bytes, "nothing about the file is lost");
}

#[test]
fn reports_repeated_blank_entries_as_empty_and_repeated() {
    let snapshot = parse_inline(
        "blank duplicates",
        "<ModsConfigData><activeMods><li/><li></li><li>x</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        [String::new(), String::new(), "x".to_string()],
        "both blanks stay in place"
    );
    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::EmptyToken { index: 0 },
            ConfigDiagnostic::EmptyToken { index: 1 },
            ConfigDiagnostic::RepeatedToken {
                token: String::new(),
                first_index: 0,
                index: 1,
            },
        ],
        "an exact repeat of a blank entry is reported as empty and as a repeat, in that order"
    );
}

#[test]
fn reports_repeated_whitespace_entries_as_exact_repeats() {
    let snapshot = parse_inline(
        "same whitespace repeats",
        "<ModsConfigData><activeMods><li> </li><li> </li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::EmptyToken { index: 0 },
            ConfigDiagnostic::EmptyToken { index: 1 },
            ConfigDiagnostic::RepeatedToken {
                token: " ".to_string(),
                first_index: 0,
                index: 1,
            },
        ],
        "the identical spacing string repeats, and the token keeps its own spaces"
    );
}

#[test]
fn does_not_report_different_blank_strings_as_repeats() {
    let snapshot = parse_inline(
        "different blanks",
        "<ModsConfigData><activeMods><li> </li><li>\t</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::EmptyToken { index: 0 },
            ConfigDiagnostic::EmptyToken { index: 1 },
        ],
        "distinct spacing strings are distinct decoded tokens"
    );
}

#[test]
fn repeated_entries_point_at_the_original_first_index() {
    let snapshot = parse_inline(
        "triple repeat",
        "<ModsConfigData><activeMods><li>x.mod</li><li>y.mod</li><li>x.mod</li><li>x.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.diagnostics,
        [
            ConfigDiagnostic::RepeatedToken {
                token: "x.mod".to_string(),
                first_index: 0,
                index: 2,
            },
            ConfigDiagnostic::RepeatedToken {
                token: "x.mod".to_string(),
                first_index: 0,
                index: 3,
            },
        ],
        "every later copy names the original first occurrence, not the copy before it"
    );
}

#[test]
fn keeps_cdata_entries_literal() {
    let snapshot = parse_inline(
        "cdata entry",
        "<ModsConfigData><activeMods><li><![CDATA[Literal &amp; Co]]></li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["Literal &amp; Co".to_string()],
        "CDATA content is literal text, so its entities are not references here"
    );
}

#[test]
fn loads_a_self_closing_entry_and_keeps_its_position() {
    let snapshot = parse_inline(
        "self-closing entry",
        "<ModsConfigData><activeMods><li>only.mod</li><li/></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["only.mod".to_string(), String::new()],
        "a self-closing entry is still an entry"
    );
    assert_eq!(
        snapshot.diagnostics,
        [ConfigDiagnostic::EmptyToken { index: 1 }],
        "and it is reported at its own index"
    );
}

#[test]
fn counts_only_the_root_own_active_mods_element() {
    let snapshot = parse_inline(
        "nested look-alike list",
        "<ModsConfigData><modLists><activeMods><li>saved.list</li></activeMods></modLists>\
         <activeMods><li>real.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["real.mod".to_string()],
        "an activeMods nested inside another field is not the active list"
    );
    assert_eq!(
        spanned(&snapshot),
        b"<activeMods><li>real.mod</li></activeMods>",
        "and the span locates the root's own element, which comes later in the file"
    );
}

#[test]
fn accepts_case_variants_of_the_config_element_names() {
    let snapshot = parse_inline(
        "case variants",
        "<ModsConfigData><ActiveMods><LI>x.mod</LI></ActiveMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["x.mod".to_string()],
        "element names are matched the way the shared reader matches them, ignoring ASCII case"
    );
    assert_eq!(
        spanned(&snapshot),
        b"<ActiveMods><LI>x.mod</LI></ActiveMods>",
        "the span still covers the whole element as written"
    );
}

#[test]
fn rejects_a_list_closed_with_a_case_variant_name() {
    let error = inline_error(
        "mismatched case",
        "<ModsConfigData><activeMods><li>x.mod</li></Activemods></ModsConfigData>",
    );

    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "XML requires the closing tag to repeat the opening name, got {error}"
    );
}

#[test]
fn keeps_the_surrounding_whitespace_of_the_first_and_last_entries() {
    let snapshot = parse_inline(
        "edge entries",
        "<ModsConfigData><activeMods><li>\n  core.mod\n  </li><li>tail.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["\n  core.mod\n  ".to_string(), "tail.mod".to_string()],
        "entry text is the element's own character data, nothing more"
    );
    assert!(
        snapshot.diagnostics.is_empty(),
        "a padded entry is not an empty one: {:?}",
        snapshot.diagnostics
    );
}

#[test]
fn keeps_carriage_returns_of_a_windows_written_file() {
    let document = "<ModsConfigData>\r\n  <activeMods>\r\n    <li>a.mod</li>\r\n  </activeMods>\r\n</ModsConfigData>";
    let snapshot = parse_inline("windows line ends", document);

    assert_eq!(
        snapshot.active_tokens,
        ["a.mod".to_string()],
        "line ends between entries are not entry text"
    );
    assert_eq!(
        spanned(&snapshot),
        b"<activeMods>\r\n    <li>a.mod</li>\r\n  </activeMods>",
        "the span keeps the file's own line ends instead of normalizing them"
    );
}

#[test]
fn decodes_entities_in_the_version_text() {
    let snapshot = parse_inline(
        "version entities",
        "<ModsConfigData><version>1.5 &amp; beta &#233;</version><activeMods><li>a</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.version.as_deref(),
        Some("1.5 & beta é"),
        "version text is decoded once and kept as written otherwise"
    );
}

#[test]
fn rejects_malformed_attributes_in_a_config() {
    for (label, document) in [
        (
            "duplicate attribute",
            "<ModsConfigData v=\"1\" v=\"2\"><activeMods><li>a</li></activeMods></ModsConfigData>",
        ),
        (
            "literal angle in an entry attribute",
            "<ModsConfigData><activeMods><li path=\"a<b\">x</li></activeMods></ModsConfigData>",
        ),
        (
            "entity needing a dtd in an attribute",
            "<ModsConfigData><activeMods><li path=\"&undeclared;\">x</li></activeMods></ModsConfigData>",
        ),
    ] {
        let error = inline_error(label, document);
        assert!(
            matches!(
                error,
                Error::XmlSyntax { .. } | Error::UnsupportedEntity { .. }
            ),
            "{label}: refused, got {error}"
        );
    }
}

#[test]
fn rejects_content_after_the_root_element() {
    let error = inline_error(
        "trailing content",
        "<ModsConfigData><activeMods><li>a</li></activeMods></ModsConfigData>trailing",
    );

    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "a config with stray bytes after the root is refused, got {error}"
    );
}

#[test]
fn loading_the_same_bytes_twice_gives_the_same_snapshot() {
    let document = "<ModsConfigData><version>1.5</version><activeMods><li>a</li><li>a</li></activeMods></ModsConfigData>";
    let first = parse_inline("first load", document);
    let second = parse_inline("second load", document);

    assert_eq!(
        first, second,
        "loading is a pure read of the bytes it was given"
    );
}

#[test]
fn ignores_entry_attributes_but_still_validates_them() {
    let snapshot = parse_inline(
        "entry attributes",
        "<ModsConfigData><activeMods><li approved=\"true\">marked.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["marked.mod".to_string()],
        "an attribute is not part of the entry's text"
    );
    assert!(
        spanned(&snapshot).starts_with(b"<activeMods>"),
        "the span still carries the original bytes: {:?}",
        String::from_utf8_lossy(&spanned(&snapshot))
    );
}

#[test]
fn span_includes_the_whitespace_inside_the_closing_tag() {
    let snapshot = parse_inline(
        "trailing padding",
        "<ModsConfigData><activeMods><li>a.mod</li>   </activeMods></ModsConfigData>",
    );

    assert_eq!(
        spanned(&snapshot),
        b"<activeMods><li>a.mod</li>   </activeMods>",
        "everything between the element's own tags is inside the span a save replaces"
    );
    assert_eq!(
        snapshot.active_tokens,
        ["a.mod".to_string()],
        "and padding is not an entry"
    );
}

#[test]
fn reports_an_entity_only_entry_as_empty() {
    let snapshot = parse_inline(
        "entity whitespace entry",
        "<ModsConfigData><activeMods><li>&#32;</li><li>&amp;</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        [" ".to_string(), "&".to_string()],
        "references decode once, and a decoded space is still spacing"
    );
    assert_eq!(
        snapshot.diagnostics,
        [ConfigDiagnostic::EmptyToken { index: 0 }],
        "only the entry that decodes to spacing counts as empty"
    );
}

#[test]
fn rejects_a_self_closing_root_and_an_empty_document() {
    for (label, document) in [
        ("self-closing root", "<ModsConfigData/>"),
        ("empty bytes", ""),
        ("only a declaration", "<?xml version=\"1.0\"?>"),
    ] {
        let error = inline_error(label, document);
        assert!(
            matches!(error, Error::XmlSyntax { .. }),
            "{label}: a document with no active list is refused, got {error}"
        );
    }
}

#[test]
fn rejects_undecodable_bytes() {
    let mut document = b"<ModsConfigData><activeMods><li>broken".to_vec();
    document.push(0xFF);
    document.extend_from_slice(b"</li></activeMods></ModsConfigData>");

    let error = match parse_config(&document) {
        Ok(snapshot) => panic!("undecodable bytes must be refused, loaded {snapshot:?}"),
        Err(error) => error,
    };
    assert!(
        matches!(error, Error::XmlSyntax { .. }),
        "invalid UTF-8 is a read failure, not a token, got {error}"
    );
}

#[test]
fn a_comment_inside_an_entry_never_becomes_text() {
    let snapshot = parse_inline(
        "comment in entry",
        "<ModsConfigData><activeMods><li>Core<!-- pinned --> Mod &amp; Co</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.active_tokens,
        ["Core Mod & Co".to_string()],
        "a comment contributes no characters, while the text and references around it do"
    );
}

#[test]
fn reads_only_the_roots_own_version() {
    let snapshot = parse_inline(
        "nested version",
        "<ModsConfigData><someField><version>9.9</version></someField><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.version, None,
        "a version inside another field is not this config's version"
    );
}

#[test]
fn reads_the_root_version_without_trimming_its_own_text() {
    let snapshot = parse_inline(
        "padded version before the list",
        "<ModsConfigData><version>  future &amp; beta  </version><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.version.as_deref(),
        Some("  future & beta  "),
        "version display text is the element's own decoded characters, padding included"
    );
}

#[test]
fn reads_a_version_written_after_the_active_list() {
    let snapshot = parse_inline(
        "padded version after the list",
        "<ModsConfigData><activeMods><li>a.mod</li></activeMods><version>  1.6 &amp; beyond  </version></ModsConfigData>",
    );

    assert_eq!(
        snapshot.version.as_deref(),
        Some("  1.6 & beyond  "),
        "locating the active list does not stop the config from reading a later version field"
    );
    assert_eq!(
        spanned(&snapshot),
        b"<activeMods><li>a.mod</li></activeMods>",
        "and the span still covers exactly the list element"
    );
}

#[test]
fn the_first_root_version_wins_even_when_it_is_blank() {
    let spaced = parse_inline(
        "blank then written",
        "<ModsConfigData><version>   </version><version>1.5</version><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );
    let self_closing = parse_inline(
        "self-closing then written",
        "<ModsConfigData><version/><version>1.5</version><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        spaced.version, None,
        "the first root-level version is the config's version, so a blank one is not skipped"
    );
    assert_eq!(
        self_closing.version, None,
        "and a self-closing first version is blank too"
    );
}

#[test]
fn keeps_the_first_version_when_a_file_declares_two() {
    let snapshot = parse_inline(
        "two versions",
        "<ModsConfigData><version>1.4</version><version>1.5</version><activeMods><li>a.mod</li></activeMods></ModsConfigData>",
    );

    assert_eq!(
        snapshot.version.as_deref(),
        Some("1.4"),
        "a repeated optional field is read from its first declaration, not merged"
    );
    assert_eq!(
        snapshot.active_tokens,
        ["a.mod".to_string()],
        "and the list is unaffected"
    );
}
