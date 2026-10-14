//! Behavioral tests for rewrite settings persistence (Task 2A).
//!
//! Every persistence case injects a path inside its own temporary directory, so
//! no test writes to a real application-data directory, touches the Python
//! settings or changes process environment. Locations are only read, never
//! written, by the `settings_path` test.

use std::fs;
use std::path::{Path, PathBuf};

use rimsort_rust::domain::types::{Error, GameVersion};
use rimsort_rust::integrations::settings::{Settings, load_settings, save_settings, settings_path};
use tempfile::TempDir;

/// The configured state the UI will hand to the scanner: every field set.
fn configured() -> Settings {
    Settings {
        schema_version: 1,
        game_root: Some(PathBuf::from("/games/RimWorld 数据")),
        content_root: Some(PathBuf::from("/games/RimWorld 数据/Data")),
        config_path: Some(PathBuf::from("/games/RimWorld 数据/Config")),
        local_mods_root: Some(PathBuf::from("/mods/Local Mods")),
        workshop_root: Some(PathBuf::from("/steam/steamapps/workshop/content/292730")),
        target_version: Some(version("1.5.4171 rev0")),
        executable_override: Some(PathBuf::from("/games/RimWorld 数据/RimWorldLinux")),
        confirm_warnings: true,
    }
}

fn version(text: &str) -> GameVersion {
    GameVersion::parse(text).unwrap_or_else(|error| panic!("version {text:?} must parse: {error}"))
}

fn temp_settings(temp: &TempDir) -> PathBuf {
    temp.path().join("settings.json")
}

/// Writes settings bytes exactly as given, for the cases where the file on disk
/// is not something this build produced.
fn write_json(temp: &TempDir, content: &str) -> PathBuf {
    let path = temp_settings(temp);
    fs::write(&path, content)
        .unwrap_or_else(|error| panic!("cannot write {}: {error}", path.display()));
    path
}

fn raw(path: &Path) -> String {
    fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()))
}

fn loaded(path: &Path) -> Settings {
    load_settings(path)
        .unwrap_or_else(|error| panic!("settings must load from {}: {error}", path.display()))
}

fn saved(path: &Path, settings: &Settings) {
    save_settings(path, settings)
        .unwrap_or_else(|error| panic!("settings must save to {}: {error}", path.display()));
}

fn load_error(path: &Path) -> Error {
    match load_settings(path) {
        Ok(settings) => panic!("{}: expected an error, loaded {settings:?}", path.display()),
        Err(error) => error,
    }
}

fn save_error(path: &Path, settings: &Settings) -> Error {
    match save_settings(path, settings) {
        Ok(()) => panic!("{}: expected an error, saved {settings:?}", path.display()),
        Err(error) => error,
    }
}

/// The path and full message of an [`Error::Io`], failing for any other variant.
fn io_error(error: Error) -> (PathBuf, String) {
    match &error {
        Error::Io { path, .. } => (path.clone(), error.to_string()),
        other => panic!("expected a filesystem error, got {other}"),
    }
}

/// The context and message of an [`Error::InvalidInput`], failing for any other
/// variant.
fn invalid_input(error: Error) -> (String, String) {
    match error {
        Error::InvalidInput { context, message } => (context, message),
        other => panic!("expected an invalid input error, got {other}"),
    }
}

fn invalid_game_version(error: Error) -> (String, String) {
    match error {
        Error::InvalidGameVersion { value, reason } => (value, reason),
        other => panic!("expected an invalid game version error, got {other}"),
    }
}

#[test]
fn defaults_describe_first_run_setup() {
    let settings = Settings::default();

    assert_eq!(settings.schema_version, 1);
    assert_eq!(settings.game_root, None);
    assert_eq!(settings.content_root, None);
    assert_eq!(settings.config_path, None);
    assert_eq!(settings.local_mods_root, None);
    assert_eq!(settings.workshop_root, None);
    assert_eq!(settings.target_version, None);
    assert_eq!(settings.executable_override, None);
    assert!(settings.confirm_warnings);
}

#[test]
fn a_missing_file_loads_defaults_and_stays_missing() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);

    let settings =
        load_settings(&path).unwrap_or_else(|error| panic!("missing settings must load: {error}"));

    assert_eq!(settings, Settings::default());
    assert!(!path.exists(), "loading must not create {}", path.display());
}

#[test]
fn deliberate_first_run_settings_roundtrip() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);

    saved(&path, &Settings::default());
    let settings = loaded(&path);

    assert_eq!(settings, Settings::default());
    assert!(raw(&path).contains("\"schema_version\": 1"));
}

#[test]
fn every_configured_field_roundtrips() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    let expected = configured();

    saved(&path, &expected);

    assert_eq!(loaded(&path), expected);
}

#[test]
fn a_version_is_stored_as_its_display_text() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);

    saved(&path, &configured());
    let stored = raw(&path);

    assert!(
        stored.contains("\"target_version\": \"1.5.4171 rev0\""),
        "the version must be stored as its display text, in {stored}"
    );
    assert!(
        !stored.contains("major"),
        "internal version structure must stay private: {stored}"
    );
    assert!(
        !stored.contains("minor"),
        "internal version structure must stay private: {stored}"
    );
}

#[test]
fn an_unset_workshop_root_stays_unset() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    let mut settings = configured();
    settings.workshop_root = None;

    saved(&path, &settings);
    let reloaded = loaded(&path);

    assert_eq!(reloaded.workshop_root, None);
    assert_eq!(reloaded, settings);
    assert!(raw(&path).contains("\"workshop_root\": null"));
}

#[test]
fn absent_optional_fields_load_as_unset_with_warnings_on() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, r#"{ "schema_version": 1 }"#);

    let settings = loaded(&path);

    assert_eq!(settings.game_root, None);
    assert_eq!(settings.content_root, None);
    assert_eq!(settings.config_path, None);
    assert_eq!(settings.local_mods_root, None);
    assert_eq!(settings.workshop_root, None);
    assert_eq!(settings.target_version, None);
    assert_eq!(settings.executable_override, None);
    assert!(settings.confirm_warnings);
}

#[test]
fn disabled_warning_confirmation_is_preserved() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    let mut settings = configured();
    settings.confirm_warnings = false;

    saved(&path, &settings);

    assert!(!loaded(&path).confirm_warnings);
}

#[test]
fn configured_paths_are_never_validated_against_the_filesystem() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    let mut settings = configured();
    settings.game_root = Some(PathBuf::from("/nowhere/RimWorld 数据"));
    settings.local_mods_root = Some(PathBuf::from("/nowhere/Local Mods"));

    saved(&path, &settings);

    assert_eq!(loaded(&path), settings);
    assert!(!Path::new("/nowhere/RimWorld 数据").exists());
}

#[test]
fn paths_with_spaces_and_non_ascii_text_roundtrip() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    let mut settings = configured();
    settings.game_root = Some(temp.path().join("Rim 游戏 数据/Local Mods"));
    settings.local_mods_root = Some(PathBuf::from("/mods/Каталог модов Ω"));

    saved(&path, &settings);
    let reloaded = loaded(&path);

    assert_eq!(reloaded.game_root, settings.game_root);
    assert_eq!(reloaded.local_mods_root, settings.local_mods_root);
    assert_eq!(reloaded, settings);
}

#[test]
fn malformed_json_is_an_explicit_error_and_stays_untouched() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, "{ \"game_root\": \"/games/RimWorld\",");

    let error = load_error(&path);

    let (error_path, message) = io_error(error);
    assert_eq!(error_path, path);
    assert!(
        message.contains(path.to_str().expect("utf-8 temp path")),
        "the message must name the file: {message}"
    );
    assert_eq!(raw(&path), "{ \"game_root\": \"/games/RimWorld\",");
}

#[test]
fn a_json_scalar_that_is_not_a_path_is_an_explicit_error() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, r#"{ "schema_version": 1, "game_root": 7 }"#);

    let (error_path, message) = io_error(load_error(&path));

    assert_eq!(error_path, path);
    assert!(message.contains(path.to_str().expect("utf-8 temp path")));
}

#[test]
fn a_missing_schema_version_is_an_explicit_error() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, r#"{ "confirm_warnings": false }"#);

    let (error_path, message) = io_error(load_error(&path));

    assert_eq!(error_path, path);
    assert!(message.contains("schema_version"), "{message}");
}

#[test]
fn a_non_numeric_schema_version_is_an_explicit_error() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, r#"{ "schema_version": "1" }"#);

    let (error_path, _) = io_error(load_error(&path));

    assert_eq!(error_path, path);
}

#[test]
fn an_unknown_field_is_rejected_rather_than_dropped() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(
        &temp,
        r#"{ "schema_version": 1, "gamePath": "/games/RimWorld" }"#,
    );

    let (error_path, message) = io_error(load_error(&path));

    assert_eq!(error_path, path);
    assert!(message.contains("gamePath"), "{message}");
    assert_eq!(
        raw(&path),
        r#"{ "schema_version": 1, "gamePath": "/games/RimWorld" }"#
    );
}

#[test]
fn a_future_schema_version_is_rejected_and_left_untouched() {
    let temp = TempDir::new().expect("temporary directory");
    let stored = r#"{ "schema_version": 2, "game_root": "/games/RimWorld" }"#;
    let path = write_json(&temp, stored);

    let (context, message) = invalid_input(load_error(&path));

    assert!(
        context.contains(path.to_str().expect("utf-8 temp path")),
        "{context}"
    );
    assert!(message.contains("2"), "{message}");
    assert_eq!(raw(&path), stored);
}

#[test]
fn a_zero_schema_version_is_rejected_and_left_untouched() {
    let temp = TempDir::new().expect("temporary directory");
    let stored = r#"{ "schema_version": 0 }"#;
    let path = write_json(&temp, stored);

    let (context, message) = invalid_input(load_error(&path));

    assert!(
        context.contains(path.to_str().expect("utf-8 temp path")),
        "{context}"
    );
    assert!(message.contains("0"), "{message}");
    assert_eq!(raw(&path), stored);
}

#[test]
fn an_unusable_target_version_is_reported_with_its_value() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(&temp, r#"{ "schema_version": 1, "target_version": "1" }"#);

    let (value, reason) = invalid_game_version(load_error(&path));

    assert_eq!(value, "1");
    assert!(!reason.is_empty());
}

#[test]
fn a_non_numeric_target_version_is_rejected() {
    let temp = TempDir::new().expect("temporary directory");
    let path = write_json(
        &temp,
        r#"{ "schema_version": 1, "target_version": "nightly" }"#,
    );

    let (value, _) = invalid_game_version(load_error(&path));

    assert_eq!(value, "nightly");
}

#[test]
fn a_directory_instead_of_a_settings_file_is_an_explicit_error() {
    let temp = TempDir::new().expect("temporary directory");
    let directory = temp.path().join("settings.json");
    fs::create_dir(&directory)
        .unwrap_or_else(|error| panic!("cannot create {}: {error}", directory.display()));

    let (error_path, message) = io_error(load_error(&directory));

    assert_eq!(error_path, directory);
    assert!(
        message.contains(directory.to_str().expect("utf-8 temp path")),
        "{message}"
    );
}

#[test]
fn saving_rejects_an_unsupported_schema_before_touching_the_file() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    saved(&path, &configured());
    let stored = raw(&path);

    for version_number in [0, 2, 99] {
        let mut settings = configured();
        settings.schema_version = version_number;

        let (context, message) = invalid_input(save_error(&path, &settings));

        assert!(
            context.contains(path.to_str().expect("utf-8 temp path")),
            "{context}"
        );
        assert!(message.contains(&version_number.to_string()), "{message}");
    }

    assert_eq!(raw(&path), stored);
    assert_eq!(loaded(&path), configured());
}

#[test]
fn saving_creates_missing_parent_directories() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp.path().join("RimSortRust").join("settings.json");
    let settings = configured();

    saved(&path, &settings);

    assert_eq!(loaded(&path), settings);
}

#[test]
fn saving_reports_an_explicit_error_when_the_parent_is_unusable() {
    let temp = TempDir::new().expect("temporary directory");
    let occupied = temp.path().join("occupied");
    fs::write(&occupied, "not a directory")
        .unwrap_or_else(|error| panic!("cannot write {}: {error}", occupied.display()));
    let path = occupied.join("settings.json");

    let (error_path, message) = io_error(save_error(&path, &configured()));

    assert_eq!(error_path, path);
    assert!(
        message.contains(path.to_str().expect("utf-8 temp path")),
        "{message}"
    );
    assert!(
        !path.exists(),
        "a failed save must not create {}",
        path.display()
    );
}

#[test]
fn saving_replaces_the_file_and_leaves_no_temporary_files() {
    let temp = TempDir::new().expect("temporary directory");
    let path = temp_settings(&temp);
    saved(&path, &configured());

    let mut updated = configured();
    updated.local_mods_root = Some(PathBuf::from("/mods/Renamed Local Mods"));
    updated.confirm_warnings = false;
    saved(&path, &updated);

    assert_eq!(loaded(&path), updated);
    let entries: Vec<String> = fs::read_dir(temp.path())
        .expect("directory listing")
        .map(|entry| {
            entry
                .expect("entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    assert_eq!(entries, vec![String::from("settings.json")]);
}

#[test]
fn settings_path_names_a_rimsortrust_data_directory() {
    let path =
        settings_path().unwrap_or_else(|error| panic!("settings location must resolve: {error}"));

    assert!(path.is_absolute(), "{} must be absolute", path.display());
    assert_eq!(
        path.file_name().and_then(|name| name.to_str()),
        Some("settings.json")
    );
    let projects_the_rewrite = path
        .parent()
        .into_iter()
        .flat_map(|parent| parent.components())
        .any(|component| {
            component
                .as_os_str()
                .to_string_lossy()
                .eq_ignore_ascii_case("rimsortrust")
        });
    assert!(
        projects_the_rewrite,
        "{} must live in a RimSortRust directory",
        path.display()
    );
}
