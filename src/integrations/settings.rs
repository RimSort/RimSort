//! Persistence for the rewrite's own settings.
//!
//! These settings belong to the Rust rewrite alone: they are read and written
//! in a `RimSortRust` application-data directory, never migrated from or
//! compared against the Python application's settings, and no path or game
//! release is ever autodetected or invented here. An unset field means "the user
//! has not chosen this yet", which is a state worth saving, so a first-run file
//! with every optional value absent is a legitimate record.
//!
//! Loading never checks that a configured path exists: drives are unplugged and
//! network shares go away while the settings still have to stay editable.
//! Validation is limited to what makes the record itself unusable, namely its
//! schema version, its JSON shape and its target game version.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use tempfile::NamedTempFile;

use crate::domain::types::{Error, GameVersion};

/// The only settings schema this build reads and writes.
const SUPPORTED_SCHEMA_VERSION: u32 = 1;

/// Project identity of the rewrite's application data. `directories` uses this
/// as the whole project path on Linux and macOS and as the organisation-free
/// application folder on Windows, so it cannot collide with the Python
/// application's own settings directory.
const PROJECT_NAME: &str = "RimSortRust";

/// File name the settings live under inside the project's data directory.
const SETTINGS_FILE_NAME: &str = "settings.json";

/// One user setup: the configured locations, the target release and how much
/// confirmation the app asks for.
///
/// Every path is optional and nothing here is resolved against the filesystem,
/// so the scanner decides what a configured root means when it reads it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Settings {
    /// Schema these values follow; [`Settings::default`] uses the one version
    /// this build supports.
    pub schema_version: u32,
    /// Game install root, which also holds `Data` and `Config`.
    pub game_root: Option<PathBuf>,
    /// Root the mod list is assembled from.
    pub content_root: Option<PathBuf>,
    /// Directory of `ModsConfig.xml`.
    pub config_path: Option<PathBuf>,
    /// User-managed mod folder.
    pub local_mods_root: Option<PathBuf>,
    /// Workshop content folder, which the user may deliberately leave unset.
    pub workshop_root: Option<PathBuf>,
    /// Release used to pick versioned `About.xml` fields.
    pub target_version: Option<GameVersion>,
    /// Game executable the user chose instead of the platform default.
    pub executable_override: Option<PathBuf>,
    /// Whether closing or activating warns before it takes effect. Disabling
    /// confirmation still leaves warnings visible.
    pub confirm_warnings: bool,
}

impl Default for Settings {
    /// The first-run state: nothing configured, warnings still confirmed.
    fn default() -> Self {
        Self {
            schema_version: SUPPORTED_SCHEMA_VERSION,
            game_root: None,
            content_root: None,
            config_path: None,
            local_mods_root: None,
            workshop_root: None,
            target_version: None,
            executable_override: None,
            confirm_warnings: true,
        }
    }
}

/// JSON face of [`Settings`].
///
/// The domain types stay serde-free: a target version is stored as the display
/// text a person would type, not as its parsed `major`/`minor` pair, and paths
/// are stored as the strings the user entered. Unknown keys are rejected rather
/// than dropped, so a hand-edited typo is reported instead of silently lost the
/// next time the app saves.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct SettingsWire {
    schema_version: u32,
    game_root: Option<PathBuf>,
    content_root: Option<PathBuf>,
    config_path: Option<PathBuf>,
    local_mods_root: Option<PathBuf>,
    workshop_root: Option<PathBuf>,
    target_version: Option<String>,
    executable_override: Option<PathBuf>,
    #[serde(default = "confirmed_warnings_by_default")]
    confirm_warnings: bool,
}

fn confirmed_warnings_by_default() -> bool {
    true
}

impl From<&Settings> for SettingsWire {
    fn from(settings: &Settings) -> Self {
        Self {
            schema_version: settings.schema_version,
            game_root: settings.game_root.clone(),
            content_root: settings.content_root.clone(),
            config_path: settings.config_path.clone(),
            local_mods_root: settings.local_mods_root.clone(),
            workshop_root: settings.workshop_root.clone(),
            target_version: settings
                .target_version
                .as_ref()
                .map(|version| version.display().to_string()),
            executable_override: settings.executable_override.clone(),
            confirm_warnings: settings.confirm_warnings,
        }
    }
}

impl SettingsWire {
    /// Rebuilds the domain record, refusing a schema this build does not know
    /// and a target version that is not a release, naming the file for both.
    fn into_settings(self, path: &Path) -> Result<Settings, Error> {
        let Self {
            schema_version,
            game_root,
            content_root,
            config_path,
            local_mods_root,
            workshop_root,
            target_version,
            executable_override,
            confirm_warnings,
        } = self;

        if schema_version != SUPPORTED_SCHEMA_VERSION {
            return Err(unsupported_schema(path, schema_version));
        }

        let target_version = target_version
            .as_deref()
            .map(|text| {
                GameVersion::parse(text).map_err(|error| invalid_target_version(path, error))
            })
            .transpose()?;

        Ok(Settings {
            schema_version,
            game_root,
            content_root,
            config_path,
            local_mods_root,
            workshop_root,
            target_version,
            executable_override,
            confirm_warnings,
        })
    }
}

/// Where the rewrite keeps its own settings.
///
/// Asking costs nothing: the directory is created by [`save_settings`], and this
/// never reads or writes the Python application's settings.
pub fn settings_path() -> Result<PathBuf, Error> {
    let project = ProjectDirs::from("", "", PROJECT_NAME).ok_or_else(|| Error::InvalidInput {
        context: "settings location".to_string(),
        message: "the platform application-data directory is unavailable".to_string(),
    })?;
    Ok(project.data_local_dir().join(SETTINGS_FILE_NAME))
}

/// Reads the settings stored at `path`.
///
/// A missing file is the first-run default rather than an error, and it is not
/// created. Any other filesystem failure, unreadable JSON, an unsupported schema
/// version and an unusable target version are reported with the path they came
/// from; nothing is written while loading.
pub fn load_settings(path: &Path) -> Result<Settings, Error> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Settings::default()),
        Err(error) => return Err(io_error(path, error)),
    };

    let wire: SettingsWire =
        serde_json::from_slice(&bytes).map_err(|error| json_error(path, error))?;

    wire.into_settings(path)
}

/// Writes `settings` to `path`, replacing the file atomically.
///
/// The record is validated and serialized completely before anything is
/// created, and the bytes go into a temporary file in the destination directory
/// that is then moved into place, so a rejected or failed save leaves the
/// previous settings exactly as they were. A missing parent directory of `path`
/// is created, which is how the application's own data folder comes to exist;
/// game configuration is never written.
pub fn save_settings(path: &Path, settings: &Settings) -> Result<(), Error> {
    if settings.schema_version != SUPPORTED_SCHEMA_VERSION {
        return Err(unsupported_schema(path, settings.schema_version));
    }

    let mut text = serde_json::to_string_pretty(&SettingsWire::from(settings))
        .map_err(|error| json_error(path, error))?;
    text.push('\n');

    let directory = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(directory).map_err(|error| io_error(path, error))?;

    let mut temporary = NamedTempFile::new_in(directory).map_err(|error| io_error(path, error))?;
    temporary
        .write_all(text.as_bytes())
        .map_err(|error| io_error(path, error))?;
    temporary.flush().map_err(|error| io_error(path, error))?;
    temporary
        .persist(path)
        .map_err(|error| io_error(path, error.error))?;

    Ok(())
}

/// Reports a schema this build must neither read nor write, naming the file, so
/// a newer or malformed settings file is shown to the user instead of being
/// reset behind their back.
fn unsupported_schema(path: &Path, found: u32) -> Error {
    let message = if found > SUPPORTED_SCHEMA_VERSION {
        format!(
            "schema version {found} is newer than this build reads, which supports version {SUPPORTED_SCHEMA_VERSION}"
        )
    } else {
        format!(
            "schema version {found} is not a settings schema this build reads or writes, supported version is {SUPPORTED_SCHEMA_VERSION}"
        )
    };
    Error::InvalidInput {
        context: format!("settings file {}", path.display()),
        message,
    }
}

fn io_error(path: &Path, source: io::Error) -> Error {
    Error::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// Reports an unusable `target_version` with the settings file it came from,
/// keeping the rejected text and the parser's own reason in the message. The
/// version rules stay the domain's; only the reporting boundary adds context.
fn invalid_target_version(path: &Path, error: Error) -> Error {
    match error {
        Error::InvalidGameVersion { value, reason } => Error::InvalidInput {
            context: format!("settings file {}", path.display()),
            message: format!("target version {value:?} is not usable: {reason}"),
        },
        other => other,
    }
}

/// Turns a JSON failure into a filesystem failure on that file, keeping the
/// serde reason as the cause so the message still says what is wrong with it.
fn json_error(path: &Path, source: serde_json::Error) -> Error {
    io_error(path, io::Error::new(io::ErrorKind::InvalidData, source))
}
