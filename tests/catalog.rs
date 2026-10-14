//! Behavioral tests for the installed-copy catalog and active-token resolution
//! (Task 2D).
//!
//! Every record is built here from inline paths and metadata; no directory is
//! walked, no file is read and no real game installation is touched.

use rimsort_rust::domain::catalog::{ActiveEntry, Catalog, UnresolvedReason, resolve_active};
use rimsort_rust::domain::metadata::parse_about;
use rimsort_rust::domain::types::{
    DiagnosticKind, Error, GameVersion, MetadataDiagnostic, ModId, ModMetadata, PackageId,
    ParsedMetadata, Source,
};
use rimsort_rust::integrations::config::parse_config;

/// A canonical directory identity for a hand-authored path.
fn mod_id(path: &str) -> ModId {
    ModId::new(path)
}

/// A package id as the catalog indexes it.
fn package(raw: &str) -> PackageId {
    PackageId::normalize(raw).unwrap_or_else(|| panic!("{raw:?} must normalize to a package id"))
}

/// One installed copy with usable metadata.
fn record(path: &str, source: Source, package_id: &str) -> ModMetadata {
    let parsed = ParsedMetadata {
        package_id: Some(package(package_id)),
        name: Some(format!("{package_id} at {path}")),
        ..ParsedMetadata::default()
    };
    ModMetadata::new(mod_id(path), source, parsed)
}

/// One installed copy read from inline `About.xml` bytes.
fn scanned(path: &str, source: Source, about: &[u8]) -> ModMetadata {
    let version = GameVersion::parse("1.5").expect("the target version must parse");
    let parsed = parse_about(about, &version)
        .unwrap_or_else(|error| panic!("{path}: inline About.xml must parse: {error}"));
    ModMetadata::new(mod_id(path), source, parsed)
}

/// Builds the catalog, failing with the construction error.
fn catalog(mods: Vec<ModMetadata>) -> Catalog {
    Catalog::new(mods).unwrap_or_else(|error| panic!("catalog must build: {error}"))
}

fn copy_ids<'records>(copies: impl Iterator<Item = &'records ModMetadata>) -> Vec<ModId> {
    copies.map(|record| record.id.clone()).collect()
}

fn resolved_id(entry: &ActiveEntry) -> ModId {
    entry
        .mod_id()
        .unwrap_or_else(|| panic!("expected a resolved entry, found {entry:?}"))
        .clone()
}

fn unresolved(entry: &ActiveEntry) -> UnresolvedReason {
    match entry {
        ActiveEntry::Unresolved { reason, .. } => *reason,
        ActiveEntry::Resolved { mod_id, .. } => {
            panic!("expected an unresolved entry, found a copy at {mod_id}")
        }
    }
}

#[test]
fn keeps_every_physical_record_in_the_order_it_was_given() {
    let mods = vec![
        record(
            "/games/Data/Royalty",
            Source::Official,
            "ludeon.rimworld.royalty",
        ),
        record("/mods/harmony", Source::Local, "brrainz.harmony"),
        record("/workshop/1234", Source::Workshop, "unlimited.workshop"),
    ];
    let expected: Vec<ModId> = mods.iter().map(|record| record.id.clone()).collect();

    let catalog = catalog(mods);

    assert_eq!(
        catalog
            .mods()
            .iter()
            .map(|record| record.id.clone())
            .collect::<Vec<ModId>>(),
        expected
    );
    assert_eq!(catalog.mods().len(), 3);
}

#[test]
fn gets_a_record_by_its_canonical_directory_identity() {
    let catalog = catalog(vec![
        record("/mods/harmony", Source::Local, "brrainz.harmony"),
        record(
            "/steamcmd/workshop/harmony",
            Source::SteamCmd,
            "brrainz.harmony",
        ),
    ]);

    assert_eq!(
        catalog
            .get(&mod_id("/steamcmd/workshop/harmony"))
            .map(|record| record.source),
        Some(Source::SteamCmd)
    );
    assert_eq!(
        catalog
            .get(&mod_id("/mods/harmony"))
            .map(|record| record.source),
        Some(Source::Local)
    );
    // A path nobody installed is absent rather than guessed.
    assert!(catalog.get(&mod_id("/mods/never-scanned")).is_none());
}

#[test]
fn rejects_a_repeated_directory_identity_and_names_the_existing_row() {
    let error = match Catalog::new(vec![
        record("/mods/harmony", Source::Local, "brrainz.harmony"),
        record("/workshop/9999", Source::Workshop, "other.mod"),
        record("/mods/harmony", Source::SteamCmd, "brrainz.harmony.clone"),
    ]) {
        Ok(catalog) => panic!(
            "one directory cannot be two records, built {} records anyway",
            catalog.mods().len()
        ),
        Err(error) => error,
    };

    match &error {
        Error::InvalidInput { context, message } => {
            assert_eq!(context, "Catalog::new");
            assert!(
                message.contains("/mods/harmony"),
                "the message has to name the directory: {message}"
            );
            assert!(
                message.contains('0') && message.contains('2'),
                "the message has to name both positions: {message}"
            );
        }
        other => panic!("expected invalid input, found {other}"),
    }
}

#[test]
fn lists_every_copy_of_a_shared_package_id_in_default_preference_order() {
    let catalog = catalog(vec![
        record("/workshop/1000", Source::Workshop, "shared.mod"),
        record("/mods/git/shared", Source::Git, "shared.mod"),
        record("/game/Data/shared", Source::Official, "shared.mod"),
        record("/steamcmd/shared", Source::SteamCmd, "shared.mod"),
        record("/mods/local/shared", Source::Local, "shared.mod"),
    ]);

    assert_eq!(
        copy_ids(catalog.copies(&package("shared.mod"))),
        vec![
            mod_id("/game/Data/shared"),
            mod_id("/mods/local/shared"),
            mod_id("/steamcmd/shared"),
            mod_id("/mods/git/shared"),
            mod_id("/workshop/1000"),
        ]
    );
    assert_eq!(catalog.copies(&package("shared.mod")).len(), 5);
}

#[test]
fn offers_no_copies_for_a_package_id_nothing_declares() {
    let catalog = catalog(vec![record(
        "/mods/harmony",
        Source::Local,
        "brrainz.harmony",
    )]);

    let copies = catalog.copies(&package("nobody.declares.this"));
    assert_eq!(copies.len(), 0);
    assert_eq!(copies.count(), 0);
}

#[test]
fn resolves_a_bare_token_to_the_preferred_copy_by_normalised_package_id() {
    let catalog = catalog(vec![
        record("/workshop/7777", Source::Workshop, "brrainz.harmony"),
        record("/mods/harmony", Source::Local, "brrainz.harmony"),
    ]);

    // Case and surrounding spacing are the existing package-id normalisation's
    // business; the catalog does not invent a second spelling of it.
    assert_eq!(
        resolved_id(&catalog.resolve_token("  BrrAinz.Harmony ")),
        mod_id("/mods/harmony")
    );
}

#[test]
fn leaves_a_token_for_an_absent_package_id_unresolved_with_its_raw_text() {
    let catalog = catalog(vec![record(
        "/mods/harmony",
        Source::Local,
        "brrainz.harmony",
    )]);

    let entry = catalog.resolve_token("Crait.AlienRace ");
    assert_eq!(
        unresolved(&entry),
        UnresolvedReason::NotInstalled,
        "a package id nothing declares is not installed, not merely unusable"
    );
    assert_eq!(entry.original_token(), "Crait.AlienRace ");
    assert_eq!(entry.mod_id(), None);
}

/// The same package id installed from every source.
fn every_source(mods: &mut Vec<ModMetadata>, package_id: &str) {
    mods.push(record("/game/Data/multi", Source::Official, package_id));
    mods.push(record("/mods/local/multi", Source::Local, package_id));
    mods.push(record("/steamcmd/multi", Source::SteamCmd, package_id));
    mods.push(record("/mods/git/multi", Source::Git, package_id));
    mods.push(record("/workshop/multi", Source::Workshop, package_id));
}

#[test]
fn prefers_the_workshop_copy_for_a_trailing_steam_token_in_any_case() {
    let mut mods = Vec::new();
    every_source(&mut mods, "multi.mod");
    let catalog = catalog(mods);

    for spelling in [
        "multi.mod_steam",
        "multi.mod_Steam",
        "multi.mod_STEAM",
        "  Multi.Mod_Steam ",
    ] {
        assert_eq!(
            resolved_id(&catalog.resolve_token(spelling)),
            mod_id("/workshop/multi"),
            "{spelling:?} is the trailing marker in another case"
        );
    }
}

#[test]
fn walks_the_qualified_preference_list_down_from_workshop() {
    let official = record("/game/Data/multi", Source::Official, "multi.mod");
    let local = record("/mods/local/multi", Source::Local, "multi.mod");
    let git = record("/mods/git/multi", Source::Git, "multi.mod");
    let steamcmd = record("/steamcmd/multi", Source::SteamCmd, "multi.mod");

    for (installed, expected) in [
        (
            vec![
                official.clone(),
                local.clone(),
                git.clone(),
                steamcmd.clone(),
            ],
            mod_id("/steamcmd/multi"),
        ),
        (
            vec![official.clone(), local.clone(), git.clone()],
            mod_id("/mods/git/multi"),
        ),
        (
            vec![official.clone(), local.clone()],
            mod_id("/mods/local/multi"),
        ),
    ] {
        let catalog = catalog(installed);
        assert_eq!(
            resolved_id(&catalog.resolve_token("multi.mod_steam")),
            expected,
            "a qualified token takes the best copy a qualified lookup allows"
        );
        // The same token without the marker still prefers game data.
        assert_eq!(
            resolved_id(&catalog.resolve_token("multi.mod")),
            mod_id("/game/Data/multi"),
            "a bare token keeps the default preference"
        );
    }
}

#[test]
fn never_falls_back_to_game_data_for_a_qualified_token() {
    let catalog = catalog(vec![
        record("/game/Data/multi", Source::Official, "multi.mod"),
        record("/game/Data/other", Source::Official, "other.mod"),
    ]);

    let entry = catalog.resolve_token("multi.mod_steam");
    assert_eq!(
        unresolved(&entry),
        UnresolvedReason::NoEligibleCopy,
        "the copy is installed and usable, it is just not one a qualified token may pick"
    );
    assert_eq!(entry.original_token(), "multi.mod_steam");
    // The package id is known, so this is not "not installed".
    assert_eq!(
        unresolved(&catalog.resolve_token("other.mod_steam")),
        UnresolvedReason::NoEligibleCopy
    );
    assert_eq!(
        unresolved(&catalog.resolve_token("nothing.mod_steam")),
        UnresolvedReason::NotInstalled
    );
}

#[test]
fn keeps_an_infix_steam_spelling_as_part_of_the_identity() {
    let catalog = catalog(vec![
        record("/game/Data/caps", Source::Official, "caps_steam_mod"),
        record("/workshop/caps", Source::Workshop, "caps_steam_mod"),
        record("/workshop/unrelated", Source::Workshop, "unrelated.mod"),
    ]);

    // The marker is only ever trailing; interior text is never rewritten.
    assert_eq!(
        resolved_id(&catalog.resolve_token("caps_steam_mod")),
        mod_id("/game/Data/caps"),
        "a package id with _steam inside it stays a bare token"
    );
    assert_eq!(
        resolved_id(&catalog.resolve_token("caps_steam_mod_STEAM")),
        mod_id("/workshop/caps"),
        "the trailing marker is read off the end of that identity"
    );
    assert_eq!(
        unresolved(&catalog.resolve_token("caps_steam_unrelated")),
        UnresolvedReason::NotInstalled,
        "no infix marker means no cross-package fallback"
    );
}

#[test]
fn treats_a_marker_without_a_stem_as_an_opaque_unresolved_entry() {
    let catalog = catalog(vec![record(
        "/workshop/multi",
        Source::Workshop,
        "multi.mod",
    )]);

    for spelling in ["_steam", "_STEAM", "   _steam   ", "_Steam"] {
        let entry = catalog.resolve_token(spelling);
        assert_eq!(
            unresolved(&entry),
            UnresolvedReason::MarkerOnlyToken,
            "{spelling:?} marks nothing: it has no package id to look up"
        );
        assert_eq!(entry.original_token(), spelling);
        assert_eq!(entry.mod_id(), None);
    }
}

#[test]
fn leaves_blank_tokens_unresolved_with_their_original_text() {
    let catalog = catalog(vec![record(
        "/workshop/multi",
        Source::Workshop,
        "multi.mod",
    )]);

    for spelling in ["", " ", "\t\t", "\n"] {
        let entry = catalog.resolve_token(spelling);
        assert_eq!(unresolved(&entry), UnresolvedReason::EmptyToken);
        assert_eq!(entry.original_token(), spelling);
        assert_eq!(entry.mod_id(), None);
    }
}

#[test]
fn keeps_an_unusable_record_visible_by_identity_without_inventing_an_id() {
    let about = br#"<ModMetaData>
  <name>No package id</name>
  <supportedVersions><li>1.5</li></supportedVersions>
</ModMetaData>
"#;
    let catalog = catalog(vec![
        scanned("/broken/about", Source::Local, about),
        record("/workshop/multi", Source::Workshop, "multi.mod"),
    ]);

    let broken = catalog
        .get(&mod_id("/broken/about"))
        .expect("an invalid record stays retrievable by its directory");
    assert!(!broken.is_valid());
    assert_eq!(
        broken.parsed.package_id, None,
        "no synthetic package id is invented for a record that has none"
    );
    assert_eq!(catalog.mods().len(), 2, "the row is not dropped");
    assert_eq!(
        resolved_id(&catalog.resolve_token("multi.mod")),
        mod_id("/workshop/multi"),
        "the usable copy is unaffected by a neighbour with no identity"
    );
    assert_eq!(
        unresolved(&catalog.resolve_token("broken.about")),
        UnresolvedReason::NotInstalled,
        "a broken row is not filed under a package id nobody declared for it"
    );
}

#[test]
fn a_usable_copy_answers_the_token_before_an_unusable_copy_of_the_same_id() {
    let mut unusable = record("/workshop/broken", Source::Workshop, "multi.mod");
    unusable.parsed.diagnostics.push(MetadataDiagnostic::new(
        DiagnosticKind::EmptyPackageId,
        "ModMetaData/packageId",
    ));

    let catalog = catalog(vec![
        unusable,
        record("/game/Data/multi", Source::Official, "multi.mod"),
    ]);

    assert_eq!(
        copy_ids(catalog.copies(&package("multi.mod"))),
        vec![mod_id("/game/Data/multi"), mod_id("/workshop/broken")],
        "every copy stays inspectable, usable or not"
    );
    assert_eq!(
        resolved_id(&catalog.resolve_token("multi.mod")),
        mod_id("/game/Data/multi"),
        "an unusable copy is never silently chosen because it sorts first"
    );
}

#[test]
fn does_not_treat_a_known_package_id_with_only_unusable_copies_as_absent() {
    let mut unusable = record("/workshop/broken", Source::Workshop, "multi.mod");
    unusable.parsed.diagnostics.push(MetadataDiagnostic::new(
        DiagnosticKind::MissingPackageId,
        "ModMetaData",
    ));

    let catalog = catalog(vec![unusable]);

    assert_eq!(catalog.copies(&package("multi.mod")).len(), 1);
    assert_eq!(
        unresolved(&catalog.resolve_token("multi.mod")),
        UnresolvedReason::NoEligibleCopy,
        "the copy is installed; only its metadata is unusable"
    );
}

#[test]
fn orders_same_source_copies_naturally_so_mod2_precedes_mod10() {
    let catalog = catalog(vec![
        record("/workshop/mod10", Source::Workshop, "multi.mod"),
        record("/workshop/mod2", Source::Workshop, "multi.mod"),
        record("/workshop/mod1", Source::Workshop, "multi.mod"),
    ]);

    assert_eq!(
        copy_ids(catalog.copies(&package("multi.mod"))),
        vec![
            mod_id("/workshop/mod1"),
            mod_id("/workshop/mod2"),
            mod_id("/workshop/mod10"),
        ]
    );
    assert_eq!(
        resolved_id(&catalog.resolve_token("multi.mod_steam")),
        mod_id("/workshop/mod1"),
    );
}

#[test]
fn compares_long_digit_runs_without_a_numeric_limit() {
    let huge = format!("/workshop/mod{}", "9".repeat(40));
    let longer = format!("/workshop/mod{}0", "9".repeat(40));
    let catalog = catalog(vec![
        record(&longer, Source::Workshop, "multi.mod"),
        record(&huge, Source::Workshop, "multi.mod"),
        record(
            "/workshop/mod100000000000000000000",
            Source::Workshop,
            "multi.mod",
        ),
    ]);

    assert_eq!(
        copy_ids(catalog.copies(&package("multi.mod"))),
        vec![
            mod_id("/workshop/mod100000000000000000000"),
            mod_id(&huge),
            mod_id(&longer),
        ],
        "digit runs compare by length then text, so no segment has to fit an integer"
    );
}

#[test]
fn input_order_does_not_change_copies_or_resolution() {
    let mut mods = Vec::new();
    every_source(&mut mods, "multi.mod");
    mods.push(record("/game/Data/extra", Source::Official, "multi.mod"));
    let expected_copies = vec![
        mod_id("/game/Data/extra"),
        mod_id("/game/Data/multi"),
        mod_id("/mods/local/multi"),
        mod_id("/steamcmd/multi"),
        mod_id("/mods/git/multi"),
        mod_id("/workshop/multi"),
    ];

    let mut reversed = mods.clone();
    reversed.reverse();
    for arrangement in [
        mods.clone(),
        reversed,
        arranged(&mods, 3),
        arranged(&mods, 5),
    ] {
        let catalog = catalog(arrangement);
        assert_eq!(
            copy_ids(catalog.copies(&package("multi.mod"))),
            expected_copies,
            "copy order comes from the records, not from the order they arrived in"
        );
        for token in ["multi.mod", "MULTI.MOD", "  multi.mod\t"] {
            assert_eq!(
                resolved_id(&catalog.resolve_token(token)),
                mod_id("/game/Data/extra"),
                "{token:?} is a bare token in every arrangement"
            );
        }
        for token in ["multi.mod_steam", "Multi.Mod_STEAM"] {
            assert_eq!(
                resolved_id(&catalog.resolve_token(token)),
                mod_id("/workshop/multi"),
                "{token:?} is a qualified token in every arrangement"
            );
        }
    }
}

/// The same records rotated by `step`, which keeps every identity unique.
fn arranged(mods: &[ModMetadata], step: usize) -> Vec<ModMetadata> {
    let len = mods.len();
    (0..len)
        .map(|index| mods[(index + step) % len].clone())
        .collect()
}

#[test]
fn resolves_an_active_list_in_order_without_touching_the_snapshot() {
    let snapshot = parse_config(
        br#"<ModsConfigData>
  <version>1.5.4104 rev435</version>
  <activeMods>
    <li>ludeon.rimworld</li>
    <li>Multi.Mod_STEAM</li>
    <li>  multi.mod  </li>
    <li>ludeon.rimworld</li>
    <li></li>
    <li>_steam</li>
    <li>absent.mod</li>
    <li>only.official</li>
  </activeMods>
</ModsConfigData>
"#,
    )
    .expect("the inline config must load");
    let before = snapshot.clone();

    let mut mods = Vec::new();
    every_source(&mut mods, "multi.mod");
    mods.push(record("/game/Data/only", Source::Official, "only.official"));
    let catalog = catalog(mods);

    let entries = resolve_active(&snapshot, &catalog);

    assert_eq!(
        entries
            .iter()
            .map(ActiveEntry::original_token)
            .collect::<Vec<&str>>(),
        snapshot
            .active_tokens
            .iter()
            .map(String::as_str)
            .collect::<Vec<&str>>(),
        "one entry per configured entry, in order, with the text as written"
    );
    assert_eq!(
        entries
            .iter()
            .map(|entry| (entry.mod_id().cloned(), unresolved_of(entry)))
            .collect::<Vec<(Option<ModId>, Option<UnresolvedReason>)>>(),
        vec![
            (None, Some(UnresolvedReason::NotInstalled)),
            (Some(mod_id("/workshop/multi")), None),
            (Some(mod_id("/game/Data/multi")), None),
            (None, Some(UnresolvedReason::NotInstalled)),
            (None, Some(UnresolvedReason::EmptyToken)),
            (None, Some(UnresolvedReason::MarkerOnlyToken)),
            (None, Some(UnresolvedReason::NotInstalled)),
            // A bare token resolves against game data; the qualified variant
            // above is what stays unresolved when only game data exists.
            (Some(mod_id("/game/Data/only")), None),
        ]
    );
    assert_eq!(snapshot, before, "resolution must not edit the loaded file");
    assert_eq!(
        snapshot.active_tokens.len(),
        entries.len(),
        "repeated entries stay repeated rather than collapsing"
    );
}

/// The reason an entry is unresolved, for comparison tables.
fn unresolved_of(entry: &ActiveEntry) -> Option<UnresolvedReason> {
    match entry {
        ActiveEntry::Resolved { .. } => None,
        ActiveEntry::Unresolved { reason, .. } => Some(*reason),
    }
}
