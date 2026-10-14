//! Shared domain types: mod identity, game versions, parsed metadata and
//! structured diagnostics.
//!
//! These types are the vocabulary later tasks build on, so they carry no UI
//! dependency and no filesystem traversal.

use std::fmt::{self};
use std::path::{Path, PathBuf};

/// Canonical identity of one discovered mod directory.
///
/// A `ModId` is always a directory path, never a list index or a package id,
/// because two installed copies can share a package id. Discovery (Task 2)
/// produces canonicalised paths; equality here is exact path equality.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ModId(PathBuf);

impl ModId {
    /// Wraps the directory path a mod was discovered at.
    #[must_use]
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self(path.into())
    }

    #[must_use]
    pub fn as_path(&self) -> &Path {
        &self.0
    }
}

impl fmt::Display for ModId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0.display().to_string())
    }
}

/// Trimmed, case-normalised mod package identifier.
///
/// RimWorld package ids are compared case-insensitively, so the normalised
/// lowercase form is the only stored spelling. The original token from a
/// `ModsConfig.xml` stays with the active-list entry that reads it (Task 2),
/// not here.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct PackageId(String);

impl PackageId {
    /// Normalises a raw package id: trims surrounding whitespace and
    /// lowercases it. Returns `None` when nothing is left, which keeps a blank
    /// `packageId` from becoming a usable identity.
    #[must_use]
    pub fn normalize(raw: &str) -> Option<Self> {
        let normalized = raw.trim().to_lowercase();
        if normalized.is_empty() {
            return None;
        }
        Some(Self(normalized))
    }

    /// The stored normalised text.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for PackageId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

/// Where a mod copy was installed from, ordered by the source priority the
/// resolver uses for bare package ids: Official, Local, SteamCMD, Git,
/// Workshop.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Source {
    /// Game `Data` folder content.
    Official,
    /// User-managed mod folder.
    Local,
    /// Workshop content downloaded by SteamCMD.
    SteamCmd,
    /// Git checkout.
    Git,
    /// Steam Workshop download folder.
    Workshop,
}

impl Source {
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Official => "official",
            Self::Local => "local",
            Self::SteamCmd => "steamcmd",
            Self::Git => "git",
            Self::Workshop => "workshop",
        }
    }
}

impl fmt::Display for Source {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Reads the leading `major.minor` pair of a version string. Later components
/// are an opaque build label, but no component may be empty, and a non-numeric
/// major or minor is not a version at all.
fn release_pair(text: &str) -> Option<(u32, u32)> {
    fn numeric(component: &str) -> Option<u32> {
        if component.is_empty() || !component.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        component.parse().ok()
    }

    let mut components = text.split('.');
    let major = numeric(components.next()?)?;
    let minor = numeric(components.next()?)?;
    if components.any(str::is_empty) {
        return None;
    }
    Some((major, minor))
}

/// Numeric RimWorld release used to pick versioned `About.xml` fields.
///
/// Only `major.minor` identifies a release; anything after it is a build label
/// kept in [`GameVersion::display`] and never used for matching. Two versions
/// with the same `major.minor` are equal even if their build labels differ, and
/// matching is numeric, so `1.5` and `1.50` are different releases.
#[derive(Clone, Debug)]
pub struct GameVersion {
    major: u32,
    minor: u32,
    display: String,
}

impl GameVersion {
    /// Parses `1.5`, `1.5.4171` or `1.5.4171 rev0`. `major` and `minor` must be
    /// numeric; the remainder is preserved as the display value.
    pub fn parse(text: &str) -> Result<Self, Error> {
        let display = text.trim();
        if let Some((major, minor)) = release_pair(display) {
            return Ok(Self {
                major,
                minor,
                display: display.to_string(),
            });
        }
        Err(Error::InvalidGameVersion {
            value: display.to_string(),
            reason: "expected a numeric major.minor release such as 1.5 or 1.5.4171".to_string(),
        })
    }

    #[must_use]
    pub fn major(&self) -> u32 {
        self.major
    }

    #[must_use]
    pub fn minor(&self) -> u32 {
        self.minor
    }

    /// The original version text, trimmed.
    #[must_use]
    pub fn display(&self) -> &str {
        &self.display
    }

    /// True when `key` is a versioned `About.xml` element name that names this
    /// exact release, such as `v1.5`, `V1.5` or `v1.5.4171`. At most one `v` or
    /// `V` prefix is removed, so `vv1.5` is not a version key.
    #[must_use]
    pub fn matches_version_key(&self, key: &str) -> bool {
        let key = key.trim();
        let without_prefix = key
            .strip_prefix('v')
            .or_else(|| key.strip_prefix('V'))
            .unwrap_or(key);
        release_pair(without_prefix) == Some((self.major, self.minor))
    }
}

impl PartialEq for GameVersion {
    fn eq(&self, other: &Self) -> bool {
        (self.major, self.minor) == (other.major, other.minor)
    }
}

impl Eq for GameVersion {}

impl PartialOrd for GameVersion {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for GameVersion {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        (self.major, self.minor).cmp(&(other.major, other.minor))
    }
}

impl std::hash::Hash for GameVersion {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        (self.major, self.minor).hash(state);
    }
}

impl fmt::Display for GameVersion {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.display)
    }
}

/// One `<li>` entry of `modDependencies` (or `modDependenciesByVersion`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Dependency {
    /// The preferred package id that satisfies this dependency.
    pub package_id: PackageId,
    /// `<displayName>` as declared, when present.
    pub display_name: Option<String>,
    /// `<workshopUrl>` as declared, when present.
    pub workshop_url: Option<String>,
    /// `<alternativePackageIds>` entries in declaration order, each normalised.
    /// Any one of them satisfies the dependency; they are not additional
    /// requirements.
    pub alternatives: Vec<PackageId>,
}

/// Severity of a [`MetadataDiagnostic`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticSeverity {
    /// The record is still usable and stays visible.
    Warning,
    /// The record cannot be used as it stands, but is still inspectable.
    Error,
}

/// Machine-readable classification of a metadata diagnostic.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DiagnosticKind {
    /// No `packageId` element at all: the mod has no identity.
    MissingPackageId,
    /// A `packageId` element that is blank after trimming.
    EmptyPackageId,
    /// No `name` element: official content legitimately omits it, so the
    /// omission stays visible instead of being filled in.
    MissingName,
    /// A `supportedVersions` entry that is not a numeric game version.
    InvalidSupportedVersion { raw: String },
    /// A `steamAppId` that is not a number.
    InvalidSteamAppId { raw: String },
    /// A list element that carries markup instead of text, so its value was
    /// dropped.
    UnreadableEntry { field: String },
    /// The same package id listed twice in `modDependencies`.
    DuplicateDependency { package_id: PackageId },
    /// A `modDependencies` entry without a usable `packageId`.
    DependencyWithoutPackageId,
}

impl DiagnosticKind {
    #[must_use]
    pub fn severity(&self) -> DiagnosticSeverity {
        match self {
            Self::MissingPackageId | Self::EmptyPackageId => DiagnosticSeverity::Error,
            Self::MissingName
            | Self::InvalidSupportedVersion { .. }
            | Self::InvalidSteamAppId { .. }
            | Self::UnreadableEntry { .. }
            | Self::DuplicateDependency { .. }
            | Self::DependencyWithoutPackageId => DiagnosticSeverity::Warning,
        }
    }
}

impl fmt::Display for DiagnosticKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingPackageId => {
                formatter.write_str("About.xml has no packageId, so the mod has no identity")
            }
            Self::EmptyPackageId => {
                formatter.write_str("packageId is present but empty after trimming")
            }
            Self::MissingName => formatter.write_str("About.xml has no name"),
            Self::InvalidSupportedVersion { raw } => {
                write!(
                    formatter,
                    "supportedVersions entry {raw:?} is not a numeric game version"
                )
            }
            Self::InvalidSteamAppId { raw } => {
                write!(formatter, "steamAppId {raw:?} is not a number")
            }
            Self::UnreadableEntry { field } => {
                write!(formatter, "{field} contains an entry without text")
            }
            Self::DuplicateDependency { package_id } => {
                write!(formatter, "duplicate dependency {package_id}")
            }
            Self::DependencyWithoutPackageId => {
                formatter.write_str("a modDependencies entry has no packageId")
            }
        }
    }
}

/// One diagnostics entry attached to a parsed record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MetadataDiagnostic {
    pub kind: DiagnosticKind,
    /// Slash-separated `About.xml` element path the diagnostic came from, for
    /// example `ModMetaData/modDependencies/li`.
    pub element: String,
}

impl MetadataDiagnostic {
    #[must_use]
    pub fn new(kind: DiagnosticKind, element: impl Into<String>) -> Self {
        Self {
            kind,
            element: element.into(),
        }
    }

    #[must_use]
    pub fn severity(&self) -> DiagnosticSeverity {
        self.kind.severity()
    }
}

impl fmt::Display for MetadataDiagnostic {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} (in {})", self.kind, self.element)
    }
}

/// Everything one `About.xml` says about a mod, before it is attached to an
/// installed copy.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ParsedMetadata {
    pub package_id: Option<PackageId>,
    pub name: Option<String>,
    /// `author` plus `authors/li` in declaration order.
    pub authors: Vec<String>,
    pub description: Option<String>,
    /// `supportedVersions/li` parsed as releases, in declaration order.
    pub supported_versions: Vec<GameVersion>,
    pub dependencies: Vec<Dependency>,
    /// `loadBefore/li` plus `forceLoadBefore/li` in declaration order.
    pub load_before: Vec<PackageId>,
    /// `loadAfter/li` plus `forceLoadAfter/li` in declaration order.
    pub load_after: Vec<PackageId>,
    pub incompatible_with: Vec<PackageId>,
    pub mod_version: Option<String>,
    /// Raw `modIconPath` text; resolution against the mod folder happens in
    /// the UI layer.
    pub mod_icon_path: Option<String>,
    pub url: Option<String>,
    pub steam_app_id: Option<u64>,
    pub diagnostics: Vec<MetadataDiagnostic>,
}

impl ParsedMetadata {
    /// A record is valid when no error-severity diagnostic was recorded. A
    /// missing `packageId` therefore stays an invalid but visible record
    /// instead of being given a shared synthetic identity.
    #[must_use]
    pub fn is_valid(&self) -> bool {
        !self
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.severity() == DiagnosticSeverity::Error)
    }

    /// True when `version` is listed in `supportedVersions`.
    #[must_use]
    pub fn supports_version(&self, version: &GameVersion) -> bool {
        self.supported_versions.contains(version)
    }
}

/// A parsed metadata record attached to one installed copy.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModMetadata {
    pub id: ModId,
    pub source: Source,
    pub parsed: ParsedMetadata,
}

impl ModMetadata {
    /// The scanner (Task 2) supplies identity and source; parsing itself never
    /// invents them.
    #[must_use]
    pub fn new(id: ModId, source: Source, parsed: ParsedMetadata) -> Self {
        Self { id, source, parsed }
    }

    #[must_use]
    pub fn is_valid(&self) -> bool {
        self.parsed.is_valid()
    }
}

/// Errors that make a record or operation unusable.
///
/// Later tasks extend this enum with the remaining shared-interface variants
/// (conflict/stale results and process launch) once code produces them; the
/// variants here cover the metadata and settings seams plus the filesystem
/// operations their callers perform.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// The XML document is not well-formed.
    #[error("malformed XML in {element}: {message}")]
    XmlSyntax { element: String, message: String },
    /// The document is well-formed but uses a construct we refuse to read.
    #[error("DTD declaration is not supported in {element}")]
    DocTypeNotAllowed { element: String },
    /// A general entity reference that is not one of the predefined XML
    /// entities, which would require the refused DTD to resolve.
    #[error(
        "entity reference {name:?} in {element} is not supported; only predefined XML entities are read"
    )]
    UnsupportedEntity { name: String, element: String },
    /// The document does not describe mod metadata.
    #[error("expected a ModMetaData root element, found {found:?}")]
    UnexpectedRoot { found: String },
    /// A version string is not a numeric major/minor release.
    #[error("invalid game version {value:?}: {reason}")]
    InvalidGameVersion { value: String, reason: String },
    /// A value is unusable for the operation that received it, keeping which
    /// operation or file rejected it and why.
    #[error("invalid input in {context}: {message}")]
    InvalidInput { context: String, message: String },
    /// A filesystem operation on a path did not complete.
    #[error("filesystem error for {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
}
