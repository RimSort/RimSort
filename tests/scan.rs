//! Behavioral tests for read-only mod-directory discovery (Task 2C).
//!
//! Every case builds its own temporary install tree, so no test reads a real
//! game install, a real Workshop folder or the Python application's settings.
//! The scanner is read-only, so the tree snapshot test is the contract that
//! nothing was created, changed or deleted anywhere in the temporary tree.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use rimsort_rust::domain::types::{
    DiagnosticKind, DiagnosticSeverity, Error, GameVersion, ModMetadata, Source,
};
use rimsort_rust::integrations::scan::{ScanDiagnostic, ScanResult, scan_install};
use rimsort_rust::integrations::settings::Settings;
use tempfile::TempDir;

const TARGET: &str = "1.5.4171";

fn version(text: &str) -> GameVersion {
    GameVersion::parse(text).unwrap_or_else(|error| panic!("version {text:?} must parse: {error}"))
}

/// A temporary install: `game/` with a separate `game/Mods/Data` content root,
/// `Local Mods/` and `Workshop/` beside it. The three roots are distinct
/// directories because the settings fields are distinct, and the official
/// `Data` folder is created up front because it is a required part of the
/// installation: a scan of a valid layout must not depend on the scanner
/// tolerating a missing official root.
struct Install {
    temp: TempDir,
    game_root: PathBuf,
    content_root: PathBuf,
    data_root: PathBuf,
    local_root: PathBuf,
    workshop_root: PathBuf,
}

impl Install {
    fn new() -> Self {
        let temp = TempDir::new().expect("temporary install");
        let game_root = temp.path().join("game");
        let content_root = game_root.join("Mods");
        let data_root = content_root.join("Data");
        let local_root = temp.path().join("Local Mods");
        let workshop_root = temp.path().join("Workshop");
        for directory in [&game_root, &data_root, &local_root, &workshop_root] {
            fs::create_dir_all(directory)
                .unwrap_or_else(|error| panic!("cannot create {}: {error}", directory.display()));
        }
        Self {
            temp,
            game_root,
            content_root,
            data_root,
            local_root,
            workshop_root,
        }
    }

    fn root(&self) -> &Path {
        self.temp.path()
    }

    /// The settings a UI would hand over: the configured roots, a target
    /// release and no config path, because the scan must not need one.
    fn settings(&self) -> Settings {
        Settings {
            schema_version: 1,
            game_root: Some(self.game_root.clone()),
            content_root: Some(self.content_root.clone()),
            config_path: None,
            local_mods_root: Some(self.local_root.clone()),
            workshop_root: Some(self.workshop_root.clone()),
            target_version: Some(version(TARGET)),
            executable_override: None,
            confirm_warnings: true,
        }
    }

    fn scanned(&self) -> ScanResult {
        scan(&self.settings())
    }
}

/// Creates a mod directory holding a valid `About/About.xml` and returns it.
fn add_mod(root: &Path, name: &str, package_id: &str) -> PathBuf {
    let path = root.join(name);
    let about = path.join("About");
    fs::create_dir_all(&about)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", about.display()));
    fs::write(about.join("About.xml"), about_xml(package_id, name))
        .unwrap_or_else(|error| panic!("cannot write {name}/About/About.xml: {error}"));
    path
}

fn about_xml(package_id: &str, name: &str) -> String {
    format!(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModMetaData>\n  <packageId>{package_id}</packageId>\n  <name>{name}</name>\n</ModMetaData>\n"
    )
}

/// Creates a mod directory with no `About` folder at all.
fn add_hollow_mod(root: &Path, name: &str) -> PathBuf {
    let path = root.join(name);
    fs::create_dir_all(&path)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", path.display()));
    path
}

/// Writes raw `About/About.xml` bytes for an existing mod directory.
fn write_about(mod_path: &Path, bytes: &str) {
    let about = mod_path.join("About");
    fs::create_dir_all(&about)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", about.display()));
    fs::write(about.join("About.xml"), bytes).unwrap_or_else(|error| {
        panic!(
            "cannot write {}/About/About.xml: {error}",
            mod_path.display()
        )
    });
}

/// Writes `About/PublishedFileId.txt`, creating the `About` folder when needed.
fn write_published_file_id(mod_path: &Path, id: &str) {
    write_published_file_id_bytes(mod_path, id.as_bytes());
}

fn write_published_file_id_bytes(mod_path: &Path, bytes: &[u8]) {
    let about = mod_path.join("About");
    fs::create_dir_all(&about)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", about.display()));
    let marker = about.join("PublishedFileId.txt");
    fs::write(&marker, bytes)
        .unwrap_or_else(|error| panic!("cannot write {}: {error}", marker.display()));
}

fn add_git_directory(mod_path: &Path) {
    let marker = mod_path.join(".git");
    fs::create_dir_all(&marker)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", marker.display()));
}

fn add_git_file(mod_path: &Path) {
    let marker = mod_path.join(".git");
    fs::write(&marker, "gitdir: /elsewhere/.git/worktrees/one\n")
        .unwrap_or_else(|error| panic!("cannot write {}: {error}", marker.display()));
}

fn touch(path: &Path, bytes: &str) {
    fs::write(path, bytes)
        .unwrap_or_else(|error| panic!("cannot write {}: {error}", path.display()));
}

fn scan(settings: &Settings) -> ScanResult {
    scan_install(settings).unwrap_or_else(|error| panic!("scan must succeed, got {error}"))
}

fn scan_error(settings: &Settings) -> Error {
    match scan_install(settings) {
        Ok(result) => panic!(
            "expected an error, scanned {} mod rows and {} diagnostics",
            result.mods.len(),
            result.diagnostics.len()
        ),
        Err(error) => error,
    }
}

/// The path an install entry resolves to; the scanner reports canonical ids.
fn canon(path: &Path) -> PathBuf {
    path.canonicalize()
        .unwrap_or_else(|error| panic!("cannot canonicalise {}: {error}", path.display()))
}

/// Rows keyed by canonical id, valued by source and validity.
fn found(result: &ScanResult) -> BTreeMap<PathBuf, (Source, bool)> {
    result
        .mods
        .iter()
        .map(|row| (row.id.as_path().to_path_buf(), (row.source, row.is_valid())))
        .collect()
}

fn ids(result: &ScanResult) -> Vec<PathBuf> {
    result
        .mods
        .iter()
        .map(|row| row.id.as_path().to_path_buf())
        .collect()
}

fn row<'a>(result: &'a ScanResult, path: &Path) -> &'a ModMetadata {
    result
        .mods
        .iter()
        .find(|row| row.id.as_path() == path)
        .unwrap_or_else(|| panic!("{} is not one of {:?}", path.display(), ids(result)))
}

/// Asserts the rows are ordered by canonical id, which is what makes the
/// result independent of filesystem enumeration order.
fn assert_ordered(result: &ScanResult) {
    let mut sorted = ids(result);
    sorted.sort();
    assert_eq!(ids(result), sorted, "rows must be ordered by canonical id");
}

/// The reason of a row's error-severity unreadable-About diagnostic.
fn unreadable_reason(row: &ModMetadata) -> String {
    assert!(
        !row.is_valid(),
        "{} must stay an invalid record",
        row.id.as_path().display()
    );
    for diagnostic in &row.parsed.diagnostics {
        if let DiagnosticKind::UnreadableAbout { reason } = &diagnostic.kind {
            assert_eq!(
                diagnostic.severity(),
                DiagnosticSeverity::Error,
                "an unreadable About must be an error"
            );
            return reason.clone();
        }
    }
    panic!(
        "{} has no unreadable-About diagnostic: {:?}",
        row.id.as_path().display(),
        row.parsed.diagnostics
    );
}

/// Exactly one scan diagnostic for `path`.
fn diagnostic_for<'a>(result: &'a ScanResult, path: &Path) -> &'a ScanDiagnostic {
    let matching: Vec<&ScanDiagnostic> = result
        .diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.path == path)
        .collect();
    assert_eq!(
        matching.len(),
        1,
        "expected one diagnostic for {}, got {:?}",
        path.display(),
        result.diagnostics
    );
    matching[0]
}

/// The path, [`std::io::ErrorKind`] and message of an [`Error::Io`], failing for
/// any other variant. Tests assert the error kind rather than the English
/// sentence an operating system happens to print for it, which is not part of
/// the scanner contract and is not portable.
fn io_failure(error: &Error) -> (PathBuf, io::ErrorKind, String) {
    match error {
        Error::Io { path, source } => (path.clone(), source.kind(), source.to_string()),
        other => panic!("expected a filesystem error, got {other}"),
    }
}

/// The context and message of an [`Error::InvalidInput`], failing for any other
/// variant. A configured root that is not usable must be reported as a clear
/// input failure, not as a mysterious filesystem error.
fn input_failure(error: &Error) -> (String, String) {
    match error {
        Error::InvalidInput { context, message } => (context.clone(), message.clone()),
        other => panic!("expected an invalid-input error, got {other}"),
    }
}

/// Diagnostics as `(fixture-relative path, operation, severity, message)`, so
/// two installs created in different orders can be compared even though each
/// one lives under its own temporary folder.
#[cfg(unix)]
fn diagnostic_sequence(
    result: &ScanResult,
    root: &Path,
) -> Vec<(String, String, DiagnosticSeverity, String)> {
    result
        .diagnostics
        .iter()
        .map(|diagnostic| {
            let path = diagnostic
                .path
                .strip_prefix(root)
                .unwrap_or_else(|error| {
                    panic!(
                        "{} is not under {}: {error}",
                        diagnostic.path.display(),
                        root.display()
                    )
                })
                .display()
                .to_string();
            (
                path,
                diagnostic.operation.clone(),
                diagnostic.severity,
                diagnostic.message.clone(),
            )
        })
        .collect()
}

/// Every path in the tree with its kind and bytes, for read-only assertions.
fn snapshot(root: &Path) -> BTreeMap<String, (String, Vec<u8>)> {
    let mut entries = BTreeMap::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory)
            .unwrap_or_else(|error| panic!("cannot read {}: {error}", directory.display()))
        {
            let entry = entry.expect("readable directory entry");
            let path = entry.path();
            let relative = path
                .strip_prefix(root)
                .unwrap_or(path.as_path())
                .display()
                .to_string();
            let file_type = entry
                .file_type()
                .unwrap_or_else(|error| panic!("cannot type {}: {error}", path.display()));
            if file_type.is_dir() {
                entries.insert(relative, ("directory".to_string(), Vec::new()));
                stack.push(path);
            } else {
                let bytes = fs::read(&path)
                    .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()));
                entries.insert(relative, ("file".to_string(), bytes));
            }
        }
    }
    entries
}

#[test]
fn discovers_official_local_and_workshop_mods() {
    let install = Install::new();
    let core = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let royalty = add_mod(&install.data_root, "Royalty", "ludeon.rimworld.royalty");
    let local = add_mod(&install.local_root, "my-mod", "author.my-mod");
    let workshop = add_mod(&install.workshop_root, "1234567890", "workshop.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&core), (Source::Official, true)),
            (canon(&royalty), (Source::Official, true)),
            (canon(&local), (Source::Local, true)),
            (canon(&workshop), (Source::Workshop, true)),
        ])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
    assert_ordered(&result);
}

#[test]
fn data_mods_root_is_the_content_roots_data_folder() {
    let install = Install::new();
    // Content in the game root's own `Data` folder is not the mod list root.
    let game_data = install.game_root.join("Data");
    fs::create_dir_all(&game_data).expect("game Data folder");
    add_mod(&game_data, "NotScanned", "not.scanned");
    let official = add_mod(&install.data_root, "Core", "ludeon.rimworld");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&official), (Source::Official, true))])
    );
}

#[test]
fn parsed_metadata_is_read_from_the_mods_about_folder() {
    let install = Install::new();
    let path = add_hollow_mod(&install.local_root, "detailed");
    fs::create_dir_all(path.join("About")).expect("About folder");
    fs::write(
        path.join("About/About.xml"),
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModMetaData>\n  <packageId>detailed.mod</packageId>\n  <name>Detailed Mod</name>\n  <author>Someone</author>\n  <supportedVersions><li>1.5</li></supportedVersions>\n</ModMetaData>\n",
    )
    .expect("About.xml");

    let result = install.scanned();

    let row = row(&result, &canon(&path));
    assert_eq!(row.source, Source::Local);
    assert!(row.is_valid(), "{:?}", row.parsed.diagnostics);
    assert_eq!(
        row.parsed.package_id.as_ref().unwrap().as_str(),
        "detailed.mod"
    );
    assert_eq!(row.parsed.name.as_deref(), Some("Detailed Mod"));
    assert_eq!(row.parsed.authors, vec!["Someone".to_string()]);
    assert!(row.parsed.supports_version(&version("1.5")));
}

#[test]
fn the_configured_target_version_selects_versioned_about_fields() {
    let install = Install::new();
    let path = add_hollow_mod(&install.local_root, "versioned");
    write_about(
        &path,
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModMetaData>\n  <packageId>versioned.mod</packageId>\n  <name>Versioned</name>\n  <loadAfter><li>base.after</li></loadAfter>\n  <loadAfterByVersion>\n    <v1.6><li>new.after</li></v1.6>\n  </loadAfterByVersion>\n</ModMetaData>\n",
    );

    let mut settings = install.settings();
    settings.target_version = Some(version("1.6.5555"));
    let selected = scan(&settings);
    assert_eq!(
        row(&selected, &canon(&path))
            .parsed
            .load_after
            .iter()
            .map(|id| id.as_str().to_string())
            .collect::<Vec<_>>(),
        vec!["new.after".to_string()]
    );

    let unselected = install.scanned();
    assert_eq!(
        row(&unselected, &canon(&path))
            .parsed
            .load_after
            .iter()
            .map(|id| id.as_str().to_string())
            .collect::<Vec<_>>(),
        vec!["base.after".to_string()]
    );
}

#[test]
fn an_unset_workshop_root_is_not_reported_as_a_problem() {
    let install = Install::new();
    let official = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let local = add_mod(&install.local_root, "my-mod", "author.my-mod");
    add_mod(&install.workshop_root, "1234567890", "workshop.mod");

    let mut settings = install.settings();
    settings.workshop_root = None;

    let result = scan(&settings);

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&official), (Source::Official, true)),
            (canon(&local), (Source::Local, true)),
        ])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[test]
fn a_missing_workshop_root_stays_a_usable_scan_with_a_path_diagnostic() {
    let install = Install::new();
    let official = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let local = add_mod(&install.local_root, "my-mod", "author.my-mod");
    let absent = install.root().join("Workshop-Absent");

    let mut settings = install.settings();
    settings.workshop_root = Some(absent.clone());

    let result = scan(&settings);

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&official), (Source::Official, true)),
            (canon(&local), (Source::Local, true)),
        ])
    );
    let diagnostic = diagnostic_for(&result, &absent);
    assert_eq!(diagnostic.severity, DiagnosticSeverity::Warning);
    assert!(
        !diagnostic.message.is_empty(),
        "the optional root must explain itself"
    );
}

#[test]
fn an_explicitly_configured_non_directory_workshop_root_is_a_clear_error() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let file = install.root().join("workshop.txt");
    touch(&file, "not a folder\n");

    let mut settings = install.settings();
    settings.workshop_root = Some(file.clone());

    let (context, message) = input_failure(&scan_error(&settings));
    let text = format!("{context}: {message}");
    assert!(
        text.contains("workshop_root"),
        "the error must name the Workshop root setting: {text}"
    );
    assert!(text.contains("not a directory"), "unexpected error: {text}");
}

#[test]
fn each_unset_required_root_aborts_the_scan() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");

    for field in ["game_root", "content_root", "local_mods_root"] {
        let mut settings = install.settings();
        match field {
            "game_root" => settings.game_root = None,
            "content_root" => settings.content_root = None,
            "local_mods_root" => settings.local_mods_root = None,
            other => unreachable!("unhandled field {other}"),
        }

        let (context, message) = input_failure(&scan_error(&settings));
        let text = format!("{context}: {message}");
        assert!(
            text.contains(field),
            "{field} must be named in the error, got: {text}"
        );
    }
}

#[test]
fn an_unset_target_version_aborts_the_scan() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");

    let mut settings = install.settings();
    settings.target_version = None;

    let (context, message) = input_failure(&scan_error(&settings));
    let text = format!("{context}: {message}");
    assert!(
        text.contains("target_version"),
        "the error must name the target version: {text}"
    );
}

#[test]
fn a_nonexistent_required_root_keeps_the_filesystem_failure() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let absent = install.root().join("Local-Gone");

    let mut settings = install.settings();
    settings.local_mods_root = Some(absent.clone());

    let (path, kind, message) = io_failure(&scan_error(&settings));
    assert_eq!(path, absent);
    assert_eq!(
        kind,
        io::ErrorKind::NotFound,
        "the actual filesystem cause must be kept: {message}"
    );
    assert!(
        !message.is_empty(),
        "the cause must stay readable to a caller"
    );
}

#[test]
fn a_required_root_that_is_a_file_is_a_clear_error() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let file = install.root().join("local-mods.txt");
    touch(&file, "not a folder\n");

    let mut settings = install.settings();
    settings.local_mods_root = Some(file.clone());

    let (context, message) = input_failure(&scan_error(&settings));
    let text = format!("{context}: {message}");
    assert!(text.contains("not a directory"), "unexpected error: {text}");
}

#[test]
fn a_missing_data_folder_aborts_the_scan_and_creates_nothing() {
    let install = Install::new();
    fs::remove_dir_all(&install.data_root).expect("remove the Data folder");
    add_mod(&install.local_root, "my-mod", "author.my-mod");
    let expected_data = canon(&install.content_root).join("Data");
    let before = snapshot(install.root());

    let (path, kind, message) = io_failure(&scan_error(&install.settings()));

    assert_eq!(
        path, expected_data,
        "the failure must name the official Data root"
    );
    assert_eq!(
        kind,
        io::ErrorKind::NotFound,
        "the actual cause must be kept: {message}"
    );
    assert!(
        !install.data_root.exists(),
        "a scan never creates the folder it is missing"
    );
    assert_eq!(
        snapshot(install.root()),
        before,
        "the aborted scan must still have written nothing"
    );
}

#[test]
fn a_data_folder_that_is_a_file_is_a_clear_error() {
    let install = Install::new();
    fs::remove_dir_all(&install.data_root).expect("remove the Data folder");
    let data_file = install.content_root.join("Data");
    touch(&data_file, "not a folder\n");
    add_mod(&install.local_root, "my-mod", "author.my-mod");

    let (context, message) = input_failure(&scan_error(&install.settings()));
    let text = format!("{context}: {message}");
    assert!(
        text.contains("Data"),
        "the error must name the official Data root: {text}"
    );
    assert!(text.contains("not a directory"), "unexpected error: {text}");
}

#[cfg(unix)]
#[test]
fn a_data_folder_that_cannot_be_resolved_keeps_the_filesystem_failure() {
    let install = Install::new();
    fs::remove_dir_all(&install.data_root).expect("remove the Data folder");
    let link = install.content_root.join("Data");
    std::os::unix::fs::symlink(&link, &link).expect("self-referential Data link");
    add_mod(&install.local_root, "my-mod", "author.my-mod");

    let (path, kind, message) = io_failure(&scan_error(&install.settings()));

    assert_eq!(path, link, "the failure must name the Data path");
    assert_ne!(
        kind,
        io::ErrorKind::NotFound,
        "a resolution failure is not a missing folder: {message}"
    );
    assert!(!message.is_empty(), "the cause must be kept");
}

#[test]
fn config_paths_are_neither_required_nor_read() {
    let install = Install::new();
    let config = install.game_root.join("Config");
    fs::create_dir_all(&config).expect("Config folder");
    let mods_config = config.join("ModsConfig.xml");
    touch(
        &mods_config,
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModsConfigData><activeModList><li>whatever</li></activeModList></ModsConfigData>\n",
    );
    add_mod(&install.data_root, "Core", "ludeon.rimworld");

    let mut settings = install.settings();
    settings.config_path = None;

    let result = scan(&settings);
    assert_eq!(result.mods.len(), 1);

    // No settings file for the scan to read, and nothing written either.
    assert!(
        fs::read_to_string(&mods_config)
            .unwrap()
            .contains("whatever")
    );
    assert!(!install.root().join("settings.json").exists());
}

#[test]
fn a_malformed_about_stays_visible_beside_a_valid_sibling() {
    let install = Install::new();
    let broken = add_hollow_mod(&install.local_root, "broken");
    write_about(
        &broken,
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModMetaData>\n  <packageId>broken.mod</packageId>\n  <name>Broken\n</ModMetaData>\n",
    );
    let good = add_mod(&install.local_root, "good", "good.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&broken), (Source::Local, false)),
            (canon(&good), (Source::Local, true)),
        ])
    );
    let row = row(&result, &canon(&broken));
    assert_eq!(row.source, Source::Local);
    assert!(row.parsed.package_id.is_none(), "no identity is invented");
    let reason = unreadable_reason(row);
    assert!(
        reason.contains("malformed XML"),
        "unexpected reason: {reason}"
    );
}

#[test]
fn a_missing_about_is_a_visible_error_row() {
    let install = Install::new();
    let hollow = add_hollow_mod(&install.local_root, "hollow");
    let good = add_mod(&install.local_root, "good", "good.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&hollow), (Source::Local, false)),
            (canon(&good), (Source::Local, true)),
        ])
    );
    let reason = unreadable_reason(row(&result, &canon(&hollow)));
    assert!(reason.contains("missing"), "unexpected reason: {reason}");
}

#[test]
fn an_about_path_that_is_a_directory_is_a_visible_error_row() {
    let install = Install::new();
    let weird = add_hollow_mod(&install.local_root, "weird");
    fs::create_dir_all(weird.join("About/About.xml")).expect("About.xml as a folder");

    let result = install.scanned();

    let row = row(&result, &canon(&weird));
    assert_eq!(row.source, Source::Local);
    let reason = unreadable_reason(row);
    assert!(reason.contains("read"), "unexpected reason: {reason}");
}

#[test]
fn an_empty_about_file_is_a_visible_error_row() {
    let install = Install::new();
    let empty = add_hollow_mod(&install.local_root, "empty");
    write_about(&empty, "");

    let result = install.scanned();

    let reason = unreadable_reason(row(&result, &canon(&empty)));
    assert!(!reason.is_empty());
}

#[test]
fn a_document_that_is_not_mod_metadata_is_a_visible_error_row() {
    let install = Install::new();
    let wrong = add_hollow_mod(&install.local_root, "wrong");
    write_about(
        &wrong,
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<ModsConfigData><li>x</li></ModsConfigData>\n",
    );

    let result = install.scanned();

    let reason = unreadable_reason(row(&result, &canon(&wrong)));
    assert!(
        reason.contains("ModMetaData"),
        "unexpected reason: {reason}"
    );
}

#[test]
fn two_copies_of_one_package_id_keep_two_canonical_rows() {
    let install = Install::new();
    let first = add_mod(&install.local_root, "copy-one", "shared.package");
    let second = add_mod(&install.workshop_root, "copy-two", "shared.package");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&first), (Source::Local, true)),
            (canon(&second), (Source::Workshop, true)),
        ])
    );
}

#[test]
fn the_canonical_directory_is_the_identity_even_when_the_package_id_differs() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "Renamed-Folder", "some.other.package");

    let result = install.scanned();

    let row = row(&result, &canon(&folder));
    assert_eq!(row.id.as_path(), canon(&folder).as_path());
    assert_eq!(
        row.parsed.package_id.as_ref().unwrap().as_str(),
        "some.other.package"
    );
}

#[test]
fn non_directory_children_are_ignored() {
    let install = Install::new();
    touch(&install.local_root.join("README.md"), "# mods\n");
    touch(&install.local_root.join("some-mod.zip"), "zipbytes");
    let good = add_mod(&install.local_root, "good", "good.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&good), (Source::Local, true))])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[test]
fn a_git_folder_in_a_root_is_not_a_mod() {
    let install = Install::new();
    add_git_directory(&install.local_root);
    let good = add_mod(&install.local_root, "good", "good.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&good), (Source::Local, true))])
    );
}

#[test]
fn only_direct_children_of_a_root_are_mod_candidates() {
    let install = Install::new();
    let container = add_hollow_mod(&install.local_root, "Container");
    add_mod(&container.join("Inner"), "nested", "nested.mod");
    add_mod(
        &install.local_root.join("Data").join("Core"),
        "deep",
        "deep.mod",
    );

    let result = install.scanned();

    assert_eq!(
        ids(&result),
        vec![canon(&container), canon(&install.local_root.join("Data"))]
    );
    assert!(result.mods.iter().all(|row| !row.is_valid()));
}

#[test]
fn a_local_git_checkout_is_classified_from_its_own_marker() {
    let install = Install::new();
    let directory = add_mod(&install.local_root, "checkout", "checkout.mod");
    add_git_directory(&directory);
    let pointer = add_mod(&install.local_root, "worktree", "worktree.mod");
    add_git_file(&pointer);
    let plain = add_mod(&install.local_root, "plain", "plain.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&directory), (Source::Git, true)),
            (canon(&pointer), (Source::Git, true)),
            (canon(&plain), (Source::Local, true)),
        ])
    );
}

#[test]
fn a_published_file_id_matching_the_folder_is_steamcmd_even_with_a_git_marker() {
    let install = Install::new();
    let steamcmd = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    write_published_file_id(&steamcmd, "1234567890");
    add_git_directory(&steamcmd);

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&steamcmd), (Source::SteamCmd, true))])
    );
}

#[test]
fn a_published_file_id_marker_ignores_surrounding_whitespace() {
    let install = Install::new();
    let steamcmd = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    write_published_file_id(&steamcmd, "  1234567890\n");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&steamcmd), (Source::SteamCmd, true))])
    );
}

#[test]
fn a_mismatched_published_file_id_marker_is_checked_after_the_git_marker() {
    let install = Install::new();
    let git_with_marker = add_mod(&install.local_root, "checkout", "checkout.mod");
    write_published_file_id(&git_with_marker, "9999999999");
    add_git_directory(&git_with_marker);
    let marked = add_mod(&install.local_root, "loose", "loose.mod");
    write_published_file_id(&marked, "9999999999");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&git_with_marker), (Source::Git, true)),
            (canon(&marked), (Source::SteamCmd, true)),
        ])
    );
}

#[test]
fn a_directory_shaped_published_file_id_marker_is_reported_and_stays_steamcmd() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    // A deterministic unreadable marker: the path is a folder, not a file.
    fs::create_dir_all(folder.join("About/PublishedFileId.txt"))
        .expect("PublishedFileId.txt as a folder");

    let result = install.scanned();

    // The id could not be read, but the marker's presence was confirmed, so the
    // folder is not reclassified as a hand-managed local mod.
    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&folder), (Source::SteamCmd, true))])
    );
    let marker = canon(&folder).join("About").join("PublishedFileId.txt");
    let diagnostic = diagnostic_for(&result, &marker);
    assert_eq!(diagnostic.severity, DiagnosticSeverity::Error);
    assert!(!diagnostic.operation.is_empty());
    assert!(
        !diagnostic.message.is_empty(),
        "the actual cause must be kept"
    );
}

#[test]
fn an_unreadable_published_file_id_marker_beside_a_git_marker_is_classified_git() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    fs::create_dir_all(folder.join("About/PublishedFileId.txt"))
        .expect("PublishedFileId.txt as a folder");
    add_git_directory(&folder);

    let result = install.scanned();

    // No matching published id could be established, so the folder's own `.git`
    // marker wins over the marker's confirmed presence.
    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&folder), (Source::Git, true))])
    );
    let marker = canon(&folder).join("About").join("PublishedFileId.txt");
    let diagnostic = diagnostic_for(&result, &marker);
    assert_eq!(diagnostic.severity, DiagnosticSeverity::Error);
    assert!(
        !diagnostic.message.is_empty(),
        "the actual cause must be kept"
    );
}

#[test]
fn a_published_file_id_marker_under_a_non_directory_about_invents_no_source() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    fs::remove_dir_all(folder.join("About")).expect("remove the About folder");
    touch(&folder.join("About"), "not a folder\n");
    let marker = canon(&folder).join("About").join("PublishedFileId.txt");
    // Probe what this operating system actually reports for a path whose parent
    // is a file, instead of assuming the answer: a `NotFound` reads as absence,
    // any other failure is a marker whose presence has to be confirmed.
    let probed = fs::read(&marker)
        .err()
        .unwrap_or_else(|| panic!("{} must not be readable", marker.display()));

    let result = install.scanned();

    // Either way the folder stays Local rather than becoming a download: an
    // unconfirmed marker cannot claim a SteamCMD id, and neither can absence.
    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&folder), (Source::Local, false))])
    );
    let reported: Vec<&ScanDiagnostic> = result
        .diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.path == marker)
        .collect();
    if probed.kind() == io::ErrorKind::NotFound {
        assert!(
            reported.is_empty(),
            "absence must not be reported as an unreadable marker: {:?}",
            result.diagnostics
        );
    } else {
        assert_eq!(
            reported.len(),
            1,
            "an unreadable marker must be reported where it is: {:?}",
            result.diagnostics
        );
        assert_eq!(reported[0].severity, DiagnosticSeverity::Error);
        assert!(
            !reported[0].message.is_empty(),
            "the actual cause must be kept: {:?}",
            result.diagnostics
        );
    }
    let reason = unreadable_reason(row(&result, &canon(&folder)));
    assert!(!reason.is_empty(), "the unreadable About stays inspectable");
}

#[test]
fn a_published_file_id_marker_that_is_not_text_is_reported_and_stays_steamcmd() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    write_published_file_id_bytes(&folder, b"\xff\xfe1");

    let result = install.scanned();

    // The file is demonstrably there, only undecodable, so presence still
    // counts even though the id could not be read.
    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&folder), (Source::SteamCmd, true))])
    );
    assert_eq!(result.diagnostics.len(), 1, "{:?}", result.diagnostics);
    assert!(result.diagnostics[0].path.ends_with("PublishedFileId.txt"));
}

#[cfg(unix)]
#[test]
fn a_dangling_dot_git_link_is_not_a_checkout_marker() {
    let install = Install::new();
    let folder = add_mod(&install.local_root, "loose", "loose.mod");
    std::os::unix::fs::symlink(folder.join("elsewhere"), folder.join(".git")).expect("symlink");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&folder), (Source::Local, true))])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[test]
fn a_parent_repository_marker_is_never_inherited() {
    let install = Install::new();
    add_git_directory(install.root());
    let nested = install.root().join("repo");
    fs::create_dir_all(&nested).expect("repo folder");
    add_git_directory(&nested);
    let inside = add_mod(&install.local_root, "plain", "plain.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&inside), (Source::Local, true))])
    );
}

#[test]
fn official_and_workshop_roots_override_local_markers() {
    let install = Install::new();
    let core = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    add_git_directory(&core);
    write_published_file_id(&core, "Core");
    let workshop = add_mod(&install.workshop_root, "1234567890", "workshop.mod");
    write_published_file_id(&workshop, "1234567890");
    add_git_directory(&workshop);

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([
            (canon(&core), (Source::Official, true)),
            (canon(&workshop), (Source::Workshop, true)),
        ])
    );
}

#[test]
fn record_order_does_not_depend_on_creation_order() {
    let names = ["alpha", "mike", "zulu"];

    let mut relative_ids: Vec<Vec<String>> = Vec::new();
    for order in [&names, &["zulu", "mike", "alpha"]] {
        let install = Install::new();
        for name in order.iter() {
            add_mod(&install.local_root, name, &format!("{name}.mod"));
        }
        let result = install.scanned();
        assert_ordered(&result);
        let root = canon(&install.local_root);
        relative_ids.push(
            ids(&result)
                .iter()
                .map(|id| id.strip_prefix(&root).unwrap().display().to_string())
                .collect(),
        );
    }

    assert_eq!(
        relative_ids[0],
        vec!["alpha".to_string(), "mike".to_string(), "zulu".to_string()]
    );
    assert_eq!(relative_ids[0], relative_ids[1]);
}

#[test]
fn the_scan_writes_nothing_anywhere_in_the_tree() {
    let install = Install::new();
    add_mod(&install.data_root, "Core", "ludeon.rimworld");
    add_mod(&install.local_root, "checkout", "checkout.mod");
    add_git_directory(&install.local_root.join("checkout"));
    let config = install.game_root.join("Config");
    fs::create_dir_all(&config).expect("Config folder");
    touch(
        &config.join("ModsConfig.xml"),
        "<ModsConfigData><li>untouched</li></ModsConfigData>\n",
    );
    let settings_file = install.root().join("settings.json");
    touch(&settings_file, "{\"schema_version\":1}\n");

    let before = snapshot(install.root());
    let result = install.scanned();
    let after = snapshot(install.root());

    assert_eq!(result.mods.len(), 2);
    assert_eq!(before, after, "the scan must not touch the install");
}

#[cfg(unix)]
#[test]
fn a_symlink_to_a_mod_directory_yields_one_canonical_row() {
    let install = Install::new();
    let real = add_mod(&install.local_root, "real", "real.mod");
    std::os::unix::fs::symlink(&real, install.local_root.join("alias")).expect("symlink");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&real), (Source::Local, true))])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[cfg(unix)]
#[test]
fn two_aliases_for_one_directory_stay_one_row() {
    let install = Install::new();
    let real = add_mod(&install.local_root, "real", "real.mod");
    std::os::unix::fs::symlink(&real, install.local_root.join("first")).expect("first symlink");
    std::os::unix::fs::symlink(&real, install.local_root.join("second")).expect("second symlink");

    let result = install.scanned();

    assert_eq!(ids(&result), vec![canon(&real)]);
}

#[cfg(unix)]
#[test]
fn two_aliases_of_one_folder_with_an_unreadable_marker_are_reported_once() {
    let install = Install::new();
    let real = add_mod(&install.local_root, "1234567890", "steamcmd.mod");
    fs::create_dir_all(real.join("About/PublishedFileId.txt"))
        .expect("PublishedFileId.txt as a folder");
    std::os::unix::fs::symlink(&real, install.local_root.join("first")).expect("first symlink");
    std::os::unix::fs::symlink(&real, install.local_root.join("second")).expect("second symlink");

    let result = install.scanned();

    // Aliases collapse onto one canonical folder before it is classified, so one
    // marker is read once and reported once.
    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&real), (Source::SteamCmd, true))])
    );
    assert_eq!(result.diagnostics.len(), 1, "{:?}", result.diagnostics);
    assert!(result.diagnostics[0].path.ends_with("PublishedFileId.txt"));
}

#[cfg(unix)]
#[test]
fn a_local_alias_of_official_content_never_reads_local_markers() {
    let install = Install::new();
    let core = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    // Markers that would classify the folder locally, and report themselves, if
    // an already-claimed official folder were inspected a second time.
    fs::create_dir_all(core.join("About/PublishedFileId.txt"))
        .expect("PublishedFileId.txt as a folder");
    add_git_directory(&core);
    std::os::unix::fs::symlink(&core, install.local_root.join("Core-alias")).expect("symlink");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&core), (Source::Official, true))])
    );
    assert!(
        result.diagnostics.is_empty(),
        "the official claim is authoritative, so its local markers are irrelevant: {:?}",
        result.diagnostics
    );
}

#[cfg(unix)]
#[test]
fn a_local_root_that_is_the_data_folder_keeps_one_official_row() {
    let install = Install::new();
    let core = add_mod(&install.data_root, "Core", "ludeon.rimworld");
    let alias = install.root().join("LocalViaData");
    std::os::unix::fs::symlink(&install.data_root, &alias).expect("symlink");

    let mut settings = install.settings();
    settings.local_mods_root = Some(alias);

    let result = scan(&settings);

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&core), (Source::Official, true))])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[cfg(unix)]
#[test]
fn a_workshop_root_that_is_the_local_root_keeps_the_local_source() {
    let install = Install::new();
    let local = add_mod(&install.local_root, "my-mod", "author.my-mod");
    let alias = install.root().join("WorkshopViaLocal");
    std::os::unix::fs::symlink(&install.local_root, &alias).expect("symlink");

    let mut settings = install.settings();
    settings.workshop_root = Some(alias);

    let result = scan(&settings);

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&local), (Source::Local, true))])
    );
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
}

#[cfg(unix)]
#[test]
fn a_broken_child_link_reports_its_own_path() {
    let install = Install::new();
    let good = add_mod(&install.local_root, "good", "good.mod");
    // Reported paths are canonical, like the mod ids beside them.
    let local = canon(&install.local_root);
    let dangling = local.join("dangling");
    std::os::unix::fs::symlink(local.join("nowhere"), &dangling).expect("symlink");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&good), (Source::Local, true))])
    );
    let diagnostic = diagnostic_for(&result, &dangling);
    assert_eq!(diagnostic.severity, DiagnosticSeverity::Error);
    assert!(!diagnostic.operation.is_empty());
    assert!(!diagnostic.message.is_empty());
}

#[cfg(unix)]
#[test]
fn a_symlink_to_a_file_is_not_a_mod_candidate() {
    let install = Install::new();
    let outside = install.root().join("notes.txt");
    touch(&outside, "not a mod\n");
    std::os::unix::fs::symlink(&outside, install.local_root.join("notes-link")).expect("symlink");
    let good = add_mod(&install.local_root, "good", "good.mod");

    let result = install.scanned();

    assert_eq!(
        found(&result),
        BTreeMap::from([(canon(&good), (Source::Local, true))])
    );
}

#[cfg(unix)]
#[test]
fn diagnostics_are_ordered_independently_of_creation_order() {
    let mut sequences: Vec<Vec<(String, String, DiagnosticSeverity, String)>> = Vec::new();
    for names in [
        ["alpha-dangling", "zed-dangling"],
        ["zed-dangling", "alpha-dangling"],
    ] {
        let install = Install::new();
        let good = add_mod(&install.local_root, "good", "good.mod");
        let local = canon(&install.local_root);
        for name in names.iter() {
            std::os::unix::fs::symlink(local.join("nowhere"), local.join(name))
                .unwrap_or_else(|error| panic!("cannot link {name}: {error}"));
        }

        let result = install.scanned();

        assert_eq!(
            found(&result),
            BTreeMap::from([(canon(&good), (Source::Local, true))])
        );
        sequences.push(diagnostic_sequence(&result, &local));
    }

    let mut paths: Vec<&String> = sequences[0].iter().map(|entry| &entry.0).collect();
    let sorted = {
        paths.sort();
        paths.clone()
    };
    assert_eq!(
        sequences[0], sequences[1],
        "the whole diagnostic list must not depend on enumeration order"
    );
    assert_eq!(
        paths, sorted,
        "diagnostics must be returned in a deterministic order"
    );
    assert_eq!(
        sequences[0]
            .iter()
            .map(|entry| (entry.1.as_str(), entry.2))
            .collect::<Vec<_>>(),
        vec![("resolve mod directory", DiagnosticSeverity::Error); 2]
    );
}
