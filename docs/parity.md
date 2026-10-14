# Parity ledger

Capability ledger for the Rust rewrite, recorded per milestone task against the
pinned reference baseline `1e0085d58b2687a04ed86a2b0af06769c42c4708`.

Task 1 covers fixture-driven `About.xml` metadata parsing only. It is not whole
parity, and no capability below is claimed as verified on a real install or in a
native window.

## Status legend

- **verified (Task 1)**: implemented and pinned by a named headless test in
  `tests/metadata.rs` against a hand-authored fixture in
  `tests/fixtures/metadata/**`.
- **unimplemented**: not built yet; belongs to a later task of the offline
  milestone or a later milestone.

## Capabilities

| Capability | Status | Evidence |
| --- | --- | --- |
| Read `About.xml` into a metadata record | verified (Task 1) | `parses_single_and_multiple_list_items`, `optional_fields_absent_are_not_fatal`, `predefined_entities_are_decoded` |
| Package-id trimming and case normalization | verified (Task 1) | `normalizes_package_ids` |
| Element and version-key name case normalization | verified (Task 1) | `element_names_are_matched_regardless_of_case` |
| `supportedVersions` as numeric releases | verified (Task 1) | `parses_single_and_multiple_list_items`, `invalid_field_values_are_reported_without_failing_the_record` |
| Versioned field replacement (`modDependenciesByVersion`, `loadBeforeByVersion`, `loadAfterByVersion`, `incompatibleWithByVersion`, `descriptionsByVersion`) | verified (Task 1) | `empty_version_override_replaces_base`, `nonmatching_version_uses_base`, `description_by_version_replaces_base`, `empty_version_override_still_keeps_force_load_entries` |
| `forceLoadBefore` / `forceLoadAfter` additive after replacement | verified (Task 1) | `force_load_survives_override`, `empty_version_override_still_keeps_force_load_entries` |
| Dependency alternatives preserved as alternatives | verified (Task 1) | `alternative_dependency_ids_are_preserved` |
| Missing identity stays visible and invalid | verified (Task 1) | `missing_package_id_is_invalid_without_synthetic_identity`, `blank_package_id_is_invalid` |
| Official metadata without a name | verified (Task 1) | `official_metadata_without_name_is_visible` |
| Malformed XML and refused XML constructs | verified (Task 1) | `malformed_xml_is_an_error`, `unclosed_element_is_an_error`, `unexpected_root_is_an_error`, `dtd_declarations_are_rejected`, `undefined_entity_references_are_rejected` |
| Shared domain types for later tasks | verified (Task 1) | `mod_metadata_attaches_identity_and_source`, `game_version_parses_releases_and_rejects_invalid_text`, `version_key_prefix_is_at_most_one_and_case_insensitive` |
| Discovery of installed mods, `ModId`/`Source` assignment | unimplemented | Task 2 |
| `ModsConfig.xml` load and active-list resolution | unimplemented | Task 2 |
| Rewrite settings persistence | unimplemented | Task 2 |
| Editing state and session | unimplemented | Task 3 |
| Validation issues and topological sorting | unimplemented | Task 3 |
| Failure-safe configuration save | unimplemented | Task 4 |
| Save/launch/close workflow and launch adapter | unimplemented | Task 5 |
| Background jobs and Slint workspace | unimplemented | Task 6 |
| End-to-end offline acceptance and CI | unimplemented | Task 7 |
| Scenario (`.rsc`) metadata | unimplemented | Later milestone; reference `create_scenario_mod` has no rewrite equivalent yet |
| Community/user rule files, `loadTop`/`loadBottom` | unimplemented | Later milestone |
| Steam, Workshop, Git/SteamCMD acquisition and metadata databases | unimplemented | Later milestone |
| Standalone alphabetical sorting | excluded | Explicit parity exception in `docs/design/rust-rewrite.md` |

## Intentional differences from the pinned reference

Each row is a deliberate choice, not an oversight. The reference is
`app/models/metadata/metadata_factory.py` (plus `metadata_structure.py`).

1. **No synthetic package id.** A missing or blank `packageId` yields
   `package_id == None` with an error-severity diagnostic, so the record is
   invalid but still inspectable. The reference assigns the shared sentinel
   `missing.packageid` (`DEFAULT_MISSING_PACKAGEID`), which silently merges every
   such mod onto one identity and keeps it "valid".
   Tests: `missing_package_id_is_invalid_without_synthetic_identity`,
   `blank_package_id_is_invalid`.
2. **Official name omission stays visible.** Official DLC `About.xml` files omit
   `<name>` and `<description>`; the reference substitutes hard-coded
   `RIMWORLD_DLC_METADATA` text (or the package id) as the name. The rewrite
   records `name == None` plus a warning and leaves any name substitution to a
   later, explicit metadata source.
   Test: `official_metadata_without_name_is_visible`.
3. **Numeric version matching instead of a prefix regex.** The reference matches
   version keys with `re.match(f"v{major}.{minor}", key)`, where `.` is a regex
   wildcard and the pattern is an unanchored prefix. Target `1.5` therefore
   matched `v1.50`, and any key starting with `v1` plus any character plus `5`
   (for example `v1X5`) also matched. The rewrite parses the key numerically:
   one optional `v`/`V` prefix, then `major.minor` as numbers, with any further
   components treated as a build label. So `1.5` and `1.50` are different
   releases, `v1.5.4171` still names release `1.5`, and `vv1.5` matches nothing.
   Tests: `numeric_version_keys_distinguish_1_5_from_1_50`,
   `version_key_prefix_is_at_most_one_and_case_insensitive`.
4. **Version replacement only.** The reference exposes `prefer_versioned=False`
   for its "use this instead" metadata source. That source is out of this
   milestone, so `parse_about` always applies versioned replacement — the
   reference's default — and no toggle is invented.
   Tests: `empty_version_override_replaces_base`, `nonmatching_version_uses_base`.
5. **Strict XML without a lossy fallback.** The reference parses with
   `xml.etree.ElementTree` and re-parses failures through BeautifulSoup/`lxml-xml`
   after stripping empty tags, and it accepts DTDs. The rewrite refuses: DTD
   declarations, undeclared entity references, character data or CDATA outside
   the root element, entity references outside the root, illegal comments,
   misplaced or repeated XML declarations, a second root element, unclosed
   elements, and duplicate, malformed, entity-bearing or literal-`<` attributes —
   including on elements whose fields are ignored. Nothing is resolved externally,
   so a mod file cannot make the application read another file.
   Two envelope rules are stricter than a permissive Unicode read: outside the
   root only the four XML whitespace characters (space, tab, CR, LF) may appear,
   so U+00A0 and similar spacing is character data and an error rather than
   silently dropped text; and any exterior text at all, even legal whitespace,
   consumes the single position an XML declaration may occupy, so a declaration
   must start at the first byte. A declaration-free document may still begin with
   whitespace and comments.
   Tests: `dtd_declarations_are_rejected`, `undefined_entity_references_are_rejected`,
   `text_outside_the_root_element_is_an_error`,
   `cdata_and_references_outside_the_root_element_are_errors`,
   `non_xml_whitespace_outside_the_root_element_is_an_error`,
   `malformed_comment_is_an_error`, `misplaced_or_repeated_declaration_is_an_error`,
   `whitespace_before_the_declaration_is_an_error`,
   `duplicate_attributes_are_an_error`, `attribute_entity_reference_is_an_error`,
   `malformed_attribute_is_an_error`, `literal_angle_bracket_in_an_attribute_value_is_an_error`,
   `unexpected_root_is_an_error`, `second_root_element_is_an_error`.
   Legal controls: `legal_whitespace_and_comments_around_the_root_are_accepted`,
   `valid_attribute_values_are_accepted`.
   Whitespace trimming inside an element (`XmlElement::text`, `PackageId::normalize`)
   stays Unicode-based because it normalizes a value, not the document envelope.
6. **Case-insensitive element names at every level.** The reference lowercases
   only the top-level key before reading `modmetadata`, so child spellings such
   as `PackageID` or `LI` are silently ignored. The rewrite matches every field
   and item name ignoring ASCII case, which is the behavior the reference's own
   case-insensitive package-id handling implies for `About.xml` spelling.
   Test: `element_names_are_matched_regardless_of_case`.
7. **Deterministic ordered lists instead of sets.** The reference collects
   `loadBefore`, `loadAfter`, `incompatibleWith` and alternatives in
   `CaseInsensitiveSet`, whose iteration order is arbitrary. The rewrite keeps
   normalized, de-duplicated values in declaration order so later sorting and
   saving can depend on it. Duplicate spellings collapse to the first one.
   Tests: `normalizes_package_ids`, `parses_single_and_multiple_list_items`.
8. **Unusable values are reported, not dropped in silence.** The reference logs
   warnings and continues: a dependency without a `packageId` becomes an entry
   keyed by the empty string, and markup-only list entries are filtered out
   quietly. The rewrite skips the value, records a structured
   `MetadataDiagnostic` naming the element path that produced it (including the
   matched `*ByVersion` key), and leaves the rest of the record usable. Empty
   containers and intentional empty overrides stay diagnostic-free.
   Tests: `dependency_duplicates_and_headless_entries_are_reported`,
   `invalid_field_values_are_reported_without_failing_the_record`,
   `wrapperless_dependency_container_without_id_is_reported`,
   `wrapperless_list_container_with_markup_is_reported`,
   `versioned_dependency_diagnostics_name_the_versioned_source`.
9. **Blank list entries are dropped, a non-numeric `steamAppId` is reported.** The
   reference inserts `""` into its case-insensitive sets, and reads `steamAppId`
   only when every character is a digit while logging nothing about the failure.
   The rewrite drops blank list entries instead of inventing an empty id, reports
   a non-numeric `steamAppId` as a warning, and treats a blank `steamAppId` as
   absent.
   Tests: `parses_single_and_multiple_list_items`,
   `wrapperless_list_container_with_markup_is_reported` (blank `li` control),
   `invalid_field_values_are_reported_without_failing_the_record`.
10. **Game version identity is `major.minor`.** `GameVersion::parse` requires a
    numeric major and minor, preserves the original text as `display`, and
    compares on `major.minor` only, so `1.5.4171 rev0` and `1.5` identify the
    same release while `1.5x`, `unknown`, `1` or an empty string are errors
    rather than regex wildcards. The reference carries the version only as a
    string.
    Test: `game_version_parses_releases_and_rejects_invalid_text`.
11. **No XML-to-dictionary object model.** The reference converts XML into a
    dictionary and then interprets truthiness (`@isNull`, `#text`, single-vs-list
    key collapsing). The rewrite keeps a small element tree and interprets it
    directly, so an absent optional field, an intentionally empty override and a
    malformed value remain three distinguishable cases.
    Tests: `empty_version_override_replaces_base`,
    `optional_fields_absent_are_not_fatal`,
    `invalid_field_values_are_reported_without_failing_the_record`.

## Verification boundary

Task 1 evidence is headless `cargo test --locked --test metadata` on the host
platform plus the `just check` gates (fmt, clippy with denied warnings, tests,
build). No game install, real user configuration, Workshop content or native
Slint window was exercised, and the minimal Slint binary is unchanged.
