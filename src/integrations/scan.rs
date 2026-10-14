//! Read-only discovery of the mod folders a settings record points at.
//!
//! The scanner turns configured roots into owned [`ModMetadata`] rows plus
//! path-aware [`ScanDiagnostic`]s. It reads and never writes, so unplugged
//! drives, a missing optional Workshop folder and a half-installed mod stay
//! visible as records instead of being repaired behind the user's back. The
//! game's `Config` folder and the rewrite's settings file are never consulted:
//! a scan needs roots, a target release and nothing else.
//!
//! Nothing here builds a catalog: identity, source and per-folder metadata are
//! returned as data, and package-id duplication, source preference between
//! copies and natural-resolution policy stay with the catalog builder.

use std::collections::BTreeMap;
use std::ffi::OsStr;
use std::fmt::{self};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::domain::metadata::parse_about;
use crate::domain::types::{
    DiagnosticKind, DiagnosticSeverity, Error, GameVersion, MetadataDiagnostic, ModId, ModMetadata,
    ParsedMetadata, Source,
};
use crate::integrations::settings::Settings;

/// Folder holding a mod's `About.xml` and `PublishedFileId.txt`.
const ABOUT_FOLDER: &str = "About";

/// Metadata document inside [`ABOUT_FOLDER`]; a non-standard spelling of this
/// path is reported as a missing document rather than guessed at.
const ABOUT_FILE: &str = "About.xml";

/// Marker a SteamCMD download carries, naming the folder it was unpacked into.
const PUBLISHED_FILE_ID_FILE: &str = "PublishedFileId.txt";

/// Git checkout marker, either a folder or a worktree pointer file. A root's
/// own `.git` is repository metadata, never a mod candidate.
const GIT_MARKER: &str = ".git";

/// Subfolder of the content root holding official content.
const DATA_FOLDER: &str = "Data";

/// One problem outside a mod record: a root or a directory entry that cannot be
/// turned into a mod at all.
///
/// `path` and `operation` say which filesystem step produced the problem and
/// `message` carries the actual cause, so a UI can show the failure without
/// re-reading the filesystem.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScanDiagnostic {
    pub severity: DiagnosticSeverity,
    pub path: PathBuf,
    pub operation: String,
    pub message: String,
}

impl ScanDiagnostic {
    #[must_use]
    pub fn new(
        severity: DiagnosticSeverity,
        path: impl Into<PathBuf>,
        operation: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            severity,
            path: path.into(),
            operation: operation.into(),
            message: message.into(),
        }
    }

    /// A problem the scan worked around; the result is still usable.
    #[must_use]
    pub fn warning(
        path: impl Into<PathBuf>,
        operation: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self::new(DiagnosticSeverity::Warning, path, operation, message)
    }

    /// A path that could not be turned into a mod record at all.
    #[must_use]
    pub fn error(
        path: impl Into<PathBuf>,
        operation: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self::new(DiagnosticSeverity::Error, path, operation, message)
    }
}

impl fmt::Display for ScanDiagnostic {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{} while {} on {}",
            self.message,
            self.operation,
            self.path.display()
        )
    }
}

/// What one scan found: owned mod rows and the path-aware problems that are not
/// representable as a mod.
#[derive(Clone, Debug)]
pub struct ScanResult {
    /// One row per canonical mod directory, ordered by [`ModId`].
    pub mods: Vec<ModMetadata>,
    pub diagnostics: Vec<ScanDiagnostic>,
}

/// Discovers the installed mod folders addressed by `settings`.
///
/// `game_root`, `content_root` and `local_mods_root` are required, as is
/// `target_version`; anything missing or not a directory is an error rather
/// than an empty scan, because a scan of nothing looks identical to an install
/// with no mods. `workshop_root` is optional: an absent folder leaves the rest
/// of the scan usable with a path-aware diagnostic.
///
/// Official content comes from `content_root/Data`. Each root contributes only
/// its direct subdirectories, canonicalised so that a symlinked alias of a
/// folder or of a whole root collapses onto the one row it names. A folder whose
/// `About.xml` cannot be read stays visible as an invalid row; a path that
/// cannot be resolved at all is reported as a diagnostic, since there is no
/// canonical identity to attach it to.
pub fn scan_install(settings: &Settings) -> Result<ScanResult, Error> {
    // The game root is validated up front even though the mod list is read from
    // the content root: a wrong install path is a settings mistake the user has
    // to see before a scan result is worth anything.
    required_root("game_root", settings.game_root.as_deref())?;
    let content_root = required_root("content_root", settings.content_root.as_deref())?;
    let local_root = required_root("local_mods_root", settings.local_mods_root.as_deref())?;
    let target_version = settings
        .target_version
        .as_ref()
        .ok_or_else(|| not_configured("target_version"))?;

    let mut discovery = Discovery::default();
    let workshop_root = optional_workshop_root(settings.workshop_root.as_deref(), &mut discovery)?;
    discovery.scan_official_root(&content_root)?;
    discovery.scan_root(&local_root, RootKind::Local)?;
    if let Some(workshop_root) = workshop_root {
        discovery.scan_root(&workshop_root, RootKind::Workshop)?;
    }

    let mods = discovery
        .candidates
        .iter()
        .map(|(directory, source)| {
            ModMetadata::new(
                ModId::new(directory.clone()),
                *source,
                read_metadata(directory, target_version),
            )
        })
        .collect();

    Ok(ScanResult {
        mods,
        diagnostics: discovery.diagnostics,
    })
}

/// Which root a mod directory was enumerated from: the root decides the source
/// unless a local folder's own markers say otherwise.
#[derive(Clone, Copy, Debug)]
enum RootKind {
    Official,
    Local,
    Workshop,
}

/// One scan's found-so-far state: canonical mod directories with the source
/// chosen for them, plus the path-aware problems met on the way.
#[derive(Default)]
struct Discovery {
    /// Keyed by canonical directory, so iteration yields rows in id order no
    /// matter how the filesystem enumerated them.
    candidates: BTreeMap<PathBuf, Source>,
    diagnostics: Vec<ScanDiagnostic>,
}

impl Discovery {
    /// Adds the mod folders directly inside a root. Official and Workshop
    /// content takes its source from the root, so their markers are never read.
    fn scan_root(&mut self, root: &Path, kind: RootKind) -> Result<(), Error> {
        for directory in self.mod_directories(root)? {
            let source = match kind {
                RootKind::Official => Source::Official,
                RootKind::Workshop => Source::Workshop,
                RootKind::Local => self.classify_local(&directory),
            };
            self.add(directory, source);
        }
        Ok(())
    }

    /// Official content lives in `content_root/Data`. A content root without
    /// that folder is reported and skipped rather than failing the scan: the
    /// local and Workshop folders are still worth reading.
    fn scan_official_root(&mut self, content_root: &Path) -> Result<(), Error> {
        let data_root = content_root.join(DATA_FOLDER);
        if !data_root.is_dir() {
            self.diagnostics.push(ScanDiagnostic::warning(
                data_root,
                "read official mod root",
                "the content root has no Data folder, so official content was not scanned",
            ));
            return Ok(());
        }
        self.scan_root(&canonical_directory(&data_root)?, RootKind::Official)
    }

    /// Direct subdirectories of `root`, canonicalised and sorted. Plain files
    /// and the `.git` metadata folder are not mod candidates; a symlink is
    /// resolved only far enough to name the directory it points at, never
    /// descended into.
    fn mod_directories(&mut self, root: &Path) -> Result<Vec<PathBuf>, Error> {
        let entries = fs::read_dir(root).map_err(|error| io_error(root, error))?;
        let mut directories = Vec::new();
        for entry in entries {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    self.report(root, "enumerate root entries", &error);
                    continue;
                }
            };
            if entry.file_name() == OsStr::new(GIT_MARKER) {
                continue;
            }
            let path = entry.path();
            let file_type = match entry.file_type() {
                Ok(file_type) => file_type,
                Err(error) => {
                    self.report(&path, "inspect mod candidate", &error);
                    continue;
                }
            };
            if file_type.is_file() {
                continue;
            }
            match path.canonicalize() {
                // A link to a file is not a mod either, and an alias of a mod
                // folder has already collapsed onto that folder here.
                Ok(canonical) => {
                    if canonical.is_dir() {
                        directories.push(canonical);
                    }
                }
                Err(error) => self.report(&path, "resolve mod directory", &error),
            }
        }
        directories.sort();
        Ok(directories)
    }

    /// Records a mod directory once, keeping the highest-preference source when
    /// two roots or two links name the same folder.
    fn add(&mut self, directory: PathBuf, source: Source) {
        use std::collections::btree_map::Entry;
        match self.candidates.entry(directory) {
            Entry::Occupied(mut entry) => {
                if source_rank(source) < source_rank(*entry.get()) {
                    entry.insert(source);
                }
            }
            Entry::Vacant(entry) => {
                entry.insert(source);
            }
        }
    }

    /// Classifies one folder of a local mods root. A `PublishedFileId.txt`
    /// naming the folder is a SteamCMD download even when the folder also
    /// carries a `.git` marker, because SteamCMD has been observed to leave one
    /// behind; otherwise the folder's own `.git` marker wins, then a bare
    /// marker, then a hand-managed local mod. Parent folders are never
    /// consulted, so an outer repository does not reclassify everything under it.
    fn classify_local(&mut self, directory: &Path) -> Source {
        let marker = directory.join(ABOUT_FOLDER).join(PUBLISHED_FILE_ID_FILE);
        let marker_id = match read_published_file_id(&marker) {
            Ok(id) => id,
            Err(error) => {
                // An unreadable marker is reported and then treated as absent:
                // no folder is promoted to a SteamCMD download on the strength
                // of a file that could not be read.
                self.report(&marker, "read PublishedFileId marker", &error);
                None
            }
        };
        let folder_name = directory.file_name().unwrap_or(OsStr::new(""));
        if marker_id.as_deref().is_some_and(|id| id == folder_name) {
            return Source::SteamCmd;
        }
        if self.has_git_marker(directory) {
            return Source::Git;
        }
        if marker_id.is_some() {
            return Source::SteamCmd;
        }
        Source::Local
    }

    fn has_git_marker(&mut self, directory: &Path) -> bool {
        let marker = directory.join(GIT_MARKER);
        // Following the marker keeps a dangling `.git` link from being mistaken
        // for a checkout, while a folder and a worktree pointer file both count.
        match fs::metadata(&marker) {
            Ok(_) => true,
            Err(error) if error.kind() == io::ErrorKind::NotFound => false,
            Err(error) => {
                self.report(&marker, "read .git marker", &error);
                false
            }
        }
    }

    /// Reports an entry-level failure with the path that produced it, so one
    /// unreadable child never removes its siblings from the result.
    fn report(&mut self, path: &Path, operation: &str, error: &io::Error) {
        self.diagnostics
            .push(ScanDiagnostic::error(path, operation, error.to_string()));
    }
}

/// Preference order for one canonical folder found under several roots:
/// official content, then anything derived from a local root, then Workshop.
fn source_rank(source: Source) -> u8 {
    match source {
        Source::Official => 0,
        Source::Local | Source::SteamCmd | Source::Git => 1,
        Source::Workshop => 2,
    }
}

/// A required root, canonicalised so aliases and overlapping roots collapse onto
/// the same mod directories.
fn required_root(field: &str, configured: Option<&Path>) -> Result<PathBuf, Error> {
    let path = configured.ok_or_else(|| not_configured(field))?;
    match path.canonicalize() {
        Ok(canonical) if canonical.is_dir() => Ok(canonical),
        Ok(canonical) => Err(not_a_directory(field, path, &canonical)),
        Err(error) => Err(io_error(path, error)),
    }
}

/// The Workshop root is optional: unset means nothing to scan and says so with
/// no diagnostic, an absent folder keeps the scan usable with one, and a
/// configured path that is not a directory is a mistake rather than an empty
/// Workshop.
fn optional_workshop_root(
    configured: Option<&Path>,
    discovery: &mut Discovery,
) -> Result<Option<PathBuf>, Error> {
    let Some(path) = configured else {
        return Ok(None);
    };
    match path.canonicalize() {
        Ok(canonical) if canonical.is_dir() => Ok(Some(canonical)),
        Ok(canonical) => Err(not_a_directory("workshop_root", path, &canonical)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            discovery.diagnostics.push(ScanDiagnostic::warning(
                path.to_path_buf(),
                "read workshop mod root",
                format!("the configured Workshop folder is not there: {error}"),
            ));
            Ok(None)
        }
        Err(error) => Err(io_error(path, error)),
    }
}

fn canonical_directory(path: &Path) -> Result<PathBuf, Error> {
    path.canonicalize().map_err(|error| io_error(path, error))
}

fn not_configured(field: &str) -> Error {
    Error::InvalidInput {
        context: format!("mod scan: {field}"),
        message: "the setting has no value, so there is nothing to scan".to_string(),
    }
}

fn not_a_directory(field: &str, path: &Path, canonical: &Path) -> Error {
    Error::InvalidInput {
        context: format!("mod scan: {field}"),
        message: format!(
            "{} is not a directory (it resolves to {})",
            path.display(),
            canonical.display()
        ),
    }
}

fn io_error(path: &Path, source: io::Error) -> Error {
    Error::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// Trimmed content of `About/PublishedFileId.txt`, or `None` when the marker is
/// not there. A marker that is present but unreadable is an error: guessing a
/// source from it would hide the failure.
fn read_published_file_id(path: &Path) -> Result<Option<String>, io::Error> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    let text = String::from_utf8(bytes).map_err(|error| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("PublishedFileId.txt is not text: {error}"),
        )
    })?;
    Ok(Some(text.trim().to_string()))
}

/// Reads a mod folder's `About/About.xml`. A folder whose document is missing,
/// unreadable or unusable still becomes a record, carrying the reason as an
/// error-severity diagnostic.
fn read_metadata(directory: &Path, target_version: &GameVersion) -> ParsedMetadata {
    let path = directory.join(ABOUT_FOLDER).join(ABOUT_FILE);
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return unreadable(format!("{} is missing", path.display()));
        }
        Err(error) => {
            return unreadable(format!("{} could not be read: {error}", path.display()));
        }
    };
    parse_about(&bytes, target_version).unwrap_or_else(|error| unreadable(error.to_string()))
}

fn unreadable(reason: String) -> ParsedMetadata {
    ParsedMetadata {
        diagnostics: vec![MetadataDiagnostic::new(
            DiagnosticKind::UnreadableAbout { reason },
            format!("{ABOUT_FOLDER}/{ABOUT_FILE}"),
        )],
        ..ParsedMetadata::default()
    }
}
