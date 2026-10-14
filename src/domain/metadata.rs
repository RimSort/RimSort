//! Interpretation of `About.xml` content as [`ParsedMetadata`].
//!
//! Versioned fields replace, rather than extend, the base field they name: a
//! matching `loadAfterByVersion` entry erases the base `loadAfter` entries even
//! when it is empty. `forceLoadBefore` and `forceLoadAfter` are additive and are
//! always applied on top of whichever set won.

use crate::domain::types::{
    Dependency, DiagnosticKind, Error, GameVersion, MetadataDiagnostic, PackageId, ParsedMetadata,
};
use crate::integrations::xml::{self, XmlElement};

/// Parses `About.xml` bytes against the target game version.
///
/// Mod identity and source are attached later by the scanner, which builds a
/// [`crate::domain::types::ModMetadata`] from this record. A document that is
/// not well-formed, is not mod metadata, or uses a refused XML construct is an
/// [`Error`]; a document that parses but has unusable fields is returned with
/// diagnostics.
pub fn parse_about(bytes: &[u8], version: &GameVersion) -> Result<ParsedMetadata, Error> {
    let root = xml::parse_document(bytes)?;
    if !root.has_name("modmetadata") {
        return Err(Error::UnexpectedRoot {
            found: root.name().to_string(),
        });
    }
    Ok(Interpreter::interpret(root, version).finish())
}

struct Interpreter<'version> {
    version: &'version GameVersion,
    root_name: String,
    parsed: ParsedMetadata,
}

impl<'version> Interpreter<'version> {
    fn interpret(root: XmlElement, version: &'version GameVersion) -> Self {
        let mut interpreter = Self {
            version,
            root_name: root.name().to_string(),
            parsed: ParsedMetadata::default(),
        };
        interpreter.read_identity(&root);
        interpreter.read_display(&root);
        interpreter.read_supported_versions(&root);
        interpreter.read_dependencies(&root);
        interpreter.read_load_order(&root);
        interpreter
    }

    fn finish(self) -> ParsedMetadata {
        self.parsed
    }

    fn record(&mut self, kind: DiagnosticKind, element: String) {
        self.parsed
            .diagnostics
            .push(MetadataDiagnostic::new(kind, element));
    }

    /// Element path of a field declared directly under the root element.
    fn field(&self, name: &str) -> String {
        format!("{}/{}", self.root_name, name)
    }

    /// Element path of the versioned container for `field` and the version key
    /// that was selected from it, so diagnostics name the source that actually
    /// produced the values.
    fn versioned_field(&self, field: &str, key: &str) -> String {
        format!("{}/{}", self.field(&format!("{field}ByVersion")), key)
    }

    fn read_identity(&mut self, root: &XmlElement) {
        self.parsed.package_id = match root.child("packageId") {
            Some(element) => {
                let normalized = PackageId::normalize(element.text());
                if normalized.is_none() {
                    self.record(DiagnosticKind::EmptyPackageId, self.field("packageId"));
                }
                normalized
            }
            None => {
                self.record(DiagnosticKind::MissingPackageId, self.root_name.clone());
                None
            }
        };

        let mut steam_app_id = None;
        if let Some(raw) = Self::scalar(root, "steamAppId") {
            steam_app_id = raw.parse().ok();
            if steam_app_id.is_none() {
                self.record(
                    DiagnosticKind::InvalidSteamAppId { raw },
                    self.field("steamAppId"),
                );
            }
        }
        self.parsed.steam_app_id = steam_app_id;
    }

    fn read_display(&mut self, root: &XmlElement) {
        self.parsed.name = Self::scalar(root, "name");
        if self.parsed.name.is_none() {
            self.record(DiagnosticKind::MissingName, self.root_name.clone());
        }

        let mut description = Self::scalar(root, "description");
        if let Some(versioned) = self.versioned_element(root, "descriptions")
            && let Some(text) = Self::own_text(versioned)
        {
            description = Some(text);
        }
        self.parsed.description = description;

        let mut authors = Vec::new();
        if let Some(single) = Self::scalar(root, "author") {
            authors.push(single);
        }
        if let Some(container) = root.child("authors") {
            let element = self.field("authors");
            authors.extend(self.list_values(container, "authors", &element));
        }
        self.parsed.authors = authors;

        self.parsed.mod_version = Self::scalar(root, "modVersion");
        self.parsed.mod_icon_path = Self::scalar(root, "modIconPath");
        self.parsed.url = Self::scalar(root, "url");
    }

    fn read_supported_versions(&mut self, root: &XmlElement) {
        let mut versions = Vec::new();
        if let Some(container) = root.child("supportedVersions") {
            let element = self.field("supportedVersions");
            let values = self.list_values(container, "supportedVersions", &element);
            for raw in values {
                match GameVersion::parse(&raw) {
                    Ok(version) => versions.push(version),
                    Err(_) => {
                        self.record(
                            DiagnosticKind::InvalidSupportedVersion { raw },
                            self.field("supportedVersions"),
                        );
                    }
                }
            }
        }
        self.parsed.supported_versions = versions;
    }

    fn read_dependencies(&mut self, root: &XmlElement) {
        let selected: Option<(&XmlElement, String)> =
            match self.versioned_element(root, "modDependencies") {
                Some(versioned) => Some((
                    versioned,
                    self.versioned_field("modDependencies", versioned.name()),
                )),
                None => root
                    .child("modDependencies")
                    .map(|container| (container, self.field("modDependencies"))),
            };

        let mut dependencies: Vec<Dependency> = Vec::new();
        if let Some((container, container_element)) = selected {
            for (entry, entry_element) in self.dependency_entries(container, &container_element) {
                let package_id = entry
                    .child("packageId")
                    .and_then(|id| PackageId::normalize(id.text()));
                let Some(package_id) = package_id else {
                    // An empty entry is not a dependency at all; anything else
                    // that cannot be identified is reported.
                    if !entry.children().is_empty() || !entry.text().is_empty() {
                        self.record(DiagnosticKind::DependencyWithoutPackageId, entry_element);
                    }
                    continue;
                };
                if dependencies
                    .iter()
                    .any(|existing| existing.package_id == package_id)
                {
                    self.record(
                        DiagnosticKind::DuplicateDependency { package_id },
                        entry_element,
                    );
                    continue;
                }

                let alternatives = match entry.child("alternativePackageIds") {
                    Some(container) => {
                        let element = format!("{entry_element}/alternativePackageIds");
                        unique_ids(self.list_values(container, "alternativePackageIds", &element))
                    }
                    None => Vec::new(),
                };
                dependencies.push(Dependency {
                    package_id,
                    display_name: Self::scalar(entry, "displayName"),
                    workshop_url: Self::scalar(entry, "workshopUrl"),
                    alternatives,
                });
            }
        }
        self.parsed.dependencies = dependencies;
    }

    fn read_load_order(&mut self, root: &XmlElement) {
        self.parsed.load_before = self.ordered_ids(root, "loadBefore", Some("forceLoadBefore"));
        self.parsed.load_after = self.ordered_ids(root, "loadAfter", Some("forceLoadAfter"));
        self.parsed.incompatible_with = self.ordered_ids(root, "incompatibleWith", None);
    }

    /// Base values, replaced by the matching versioned values when one exists,
    /// then extended by the additive `forceLoad*` values and normalised.
    fn ordered_ids(
        &mut self,
        root: &XmlElement,
        field: &str,
        force_field: Option<&str>,
    ) -> Vec<PackageId> {
        let mut values = match self.versioned_element(root, field) {
            Some(versioned) => {
                let element = self.versioned_field(field, versioned.name());
                self.list_values(versioned, field, &element)
            }
            None => match root.child(field) {
                Some(container) => {
                    let element = self.field(field);
                    self.list_values(container, field, &element)
                }
                None => Vec::new(),
            },
        };

        if let Some(force) = force_field
            && let Some(container) = root.child(force)
        {
            let element = self.field(force);
            values.extend(self.list_values(container, force, &element));
        }

        unique_ids(values)
    }

    /// The child of `<field>ByVersion` that names this release, if any.
    fn versioned_element<'root>(
        &self,
        root: &'root XmlElement,
        field: &str,
    ) -> Option<&'root XmlElement> {
        root.child(&format!("{field}ByVersion"))
            .and_then(|by_version| {
                by_version
                    .children()
                    .iter()
                    .find(|key| self.version.matches_version_key(key.name()))
            })
    }

    /// `li` children of a dependency container, or the container itself when a
    /// single dependency is written without an item wrapper. A container that
    /// offers neither but still carries content is reported, because dropping it
    /// silently would lose a requirement; an empty container is a legitimate
    /// statement of "no dependencies".
    fn dependency_entries<'container>(
        &mut self,
        container: &'container XmlElement,
        container_element: &str,
    ) -> Vec<(&'container XmlElement, String)> {
        let items: Vec<&XmlElement> = container.children_named("li").collect();
        if !items.is_empty() {
            return items
                .into_iter()
                .map(|item| (item, format!("{container_element}/li")))
                .collect();
        }
        if container.child("packageId").is_some() {
            return vec![(container, container_element.to_string())];
        }
        if !container.children().is_empty() || !container.text().is_empty() {
            self.record(
                DiagnosticKind::DependencyWithoutPackageId,
                container_element.to_string(),
            );
        }
        Vec::new()
    }

    /// Values of a list field: each `li` entry, or the field's own text when it
    /// has no items. Entries without text are skipped, and ones carrying markup
    /// instead of text are reported.
    fn list_values(&mut self, container: &XmlElement, field: &str, element: &str) -> Vec<String> {
        let items: Vec<&XmlElement> = container.children_named("li").collect();
        if items.is_empty() {
            if let Some(text) = Self::own_text(container) {
                return vec![text];
            }
            if !container.children().is_empty() {
                self.record(
                    DiagnosticKind::UnreadableEntry {
                        field: field.to_string(),
                    },
                    element.to_string(),
                );
            }
            return Vec::new();
        }

        let mut values = Vec::with_capacity(items.len());
        for item in items {
            if item.text().is_empty() {
                if !item.children().is_empty() {
                    self.record(
                        DiagnosticKind::UnreadableEntry {
                            field: field.to_string(),
                        },
                        format!("{element}/li"),
                    );
                }
                continue;
            }
            values.push(item.text().to_string());
        }
        values
    }

    /// Trimmed text of a named child, absent when the child or its text is
    /// missing.
    fn scalar(element: &XmlElement, name: &str) -> Option<String> {
        element.child(name).and_then(Self::own_text)
    }

    fn own_text(element: &XmlElement) -> Option<String> {
        let text = element.text();
        (!text.is_empty()).then(|| text.to_string())
    }
}

/// Normalises values to package ids, dropping blanks and later duplicates while
/// keeping declaration order.
fn unique_ids(values: Vec<String>) -> Vec<PackageId> {
    let mut ids: Vec<PackageId> = Vec::new();
    for value in values {
        if let Some(id) = PackageId::normalize(&value)
            && !ids.contains(&id)
        {
            ids.push(id);
        }
    }
    ids
}
