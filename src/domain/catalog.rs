//! The installed-copy catalog and active-list token resolution.
//!
//! The catalog owns the physical records the scanner produced: one
//! [`ModMetadata`] per installed directory, with the directory path as identity
//! because two installed copies can share a package id. Nothing here opens a
//! file, walks a directory or reads a configuration; the scanner supplies
//! canonical [`ModId`]s and the config loader supplies decoded tokens.
//!
//! Resolution maps one active-list token to one physical copy. A token that
//! cannot be resolved stays an opaque entry holding the original text, so the
//! active list a user reads always has one entry per configured entry and no
//! token is quietly dropped or renamed.
//!
//! # Record order
//!
//! The catalog owns the sequence it was given: [`Catalog::mods`] returns the
//! scanner's records in exactly the order they were passed to
//! [`Catalog::new`], and a repeated [`ModId`] is an error rather than a
//! deduplication. Nothing here re-sorts the whole record list, so the scanner
//! is responsible for handing over a stable canonical-identity order.
//!
//! Only the copy groups and resolution are independent of that input order:
//! sorting happens once per package id at construction, by source preference,
//! then natural path order, then the raw path, so shuffling the input cannot
//! move a copy.
//!
//! # Looking a token up
//!
//! [`Catalog::resolve_token`] normalises the token through
//! [`PackageId::normalize`] — the catalog defines no second spelling of trimming
//! and lowercasing — and reads one trailing `_steam` off the normalised text.
//!
//! - A bare token prefers `Official`, `Local`, `SteamCMD`, `Git`, `Workshop`.
//! - A `_steam` token prefers `Workshop`, `Local`, `SteamCMD`, `Git` and never
//!   falls back to game `Data` content.
//! - `_steam` is only ever read from the end: `a_steam_b` stays part of the
//!   identity. No other qualifier (`_git`, `_local`) is invented here.
//! - Copies that tie on source order compare by natural path component order,
//!   so `mod2` precedes `mod10`, and only then by the raw canonical path. Digit
//!   runs compare by significant-digit count and then as bytes, and are never
//!   parsed, so an absurdly long version segment cannot overflow. The same rule
//!   reads every component, valid UTF-8 or not, because a comparator that
//!   changes representation per pair is not a total order.
//!
//! Records whose metadata is unusable are kept, listed by
//! [`Catalog::copies`] and retrievable by [`Catalog::get`], but they never
//! answer a token: a package id that is installed only as an unusable record
//! reports [`UnresolvedReason::NoEligibleCopy`], which is a different statement
//! from [`UnresolvedReason::NotInstalled`].
//!
//! Resolution picks the preferred copy; it does not forbid the others, and they
//! stay inspectable. A `ModsConfig.xml` `<li>` carries only a package id — plus
//! the trailing marker already spent on source preference — so it cannot name
//! which of several same-stem physical copies to load. The owner has confirmed
//! that the later session work rejects a physically unencodable copy choice up
//! front instead of encoding a silent pick; that restriction belongs to session
//! and save, not to this catalog, which keeps every copy reachable and every
//! unresolved token preservable.

use std::cmp::Ordering;
use std::collections::HashMap;
use std::path::Path;

use crate::domain::types::{Error, ModId, ModMetadata, PackageId, Source};
use crate::integrations::config::ConfigSnapshot;

/// Why an active-list token has no physical copy to show.
///
/// The reason describes the catalog's state, never a repair the UI should
/// attempt: an unresolved token keeps its original text in
/// [`ActiveEntry::Unresolved`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnresolvedReason {
    /// The token holds nothing but spacing, so it names no package id.
    EmptyToken,
    /// The token is the `_steam` marker with no package id stem before it.
    MarkerOnlyToken,
    /// No installed copy declares this package id.
    NotInstalled,
    /// Copies declare this package id, but none of them can answer this
    /// lookup: every copy is an unusable metadata record, or a `_steam` token
    /// matched only copies that a qualified lookup refuses (game `Data`
    /// content).
    NoEligibleCopy,
}

/// One `<li>` of the active list, resolved against the catalog or not.
///
/// `original_token` is the decoded config text exactly as it was read — case,
/// surrounding spacing, a `_steam` suffix and empty entries all survive — and
/// is the only thing an unresolved entry carries besides its reason. A resolved
/// entry names the physical copy by [`ModId`], never by package id, because the
/// choice between copies is what this resolution is for.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ActiveEntry {
    /// The token names an installed, usable copy.
    Resolved {
        mod_id: ModId,
        original_token: String,
    },
    /// The token cannot be shown as an installed copy, for `reason`.
    Unresolved {
        original_token: String,
        reason: UnresolvedReason,
    },
}

impl ActiveEntry {
    /// The physical copy this entry resolved to, when it resolved.
    #[must_use]
    pub fn mod_id(&self) -> Option<&ModId> {
        match self {
            Self::Resolved { mod_id, .. } => Some(mod_id),
            Self::Unresolved { .. } => None,
        }
    }

    /// The active-list text as it was read.
    #[must_use]
    pub fn original_token(&self) -> &str {
        match self {
            Self::Resolved { original_token, .. } | Self::Unresolved { original_token, .. } => {
                original_token
            }
        }
    }
}

/// The physical copies of one package id, with both lookups decided once.
#[derive(Debug)]
struct CopyGroup {
    /// Every known copy, in bare-token preference order.
    copies: Vec<usize>,
    /// The usable copies, in bare-token preference order.
    resolvable: Vec<usize>,
    /// The usable copies a `_steam` token may pick, in qualified preference
    /// order. Game `Data` content is never in it.
    qualified: Vec<usize>,
}

/// The empty position list, for a package id no installed copy declares.
const NO_COPIES: &[usize] = &[];

/// The trailing marker that makes a token a qualified request instead of a bare
/// package id. It is matched on [`PackageId::normalize`]d text, which is already
/// lowercased, so every spelling of `_steam`, `_Steam` and `_STEAM` reaches the
/// same lookup.
const STEAM_MARKER: &str = "_steam";

/// Bare-token source preference: `Official`, `Local`, `SteamCMD`, `Git`,
/// `Workshop`.
fn default_rank(source: Source) -> u8 {
    match source {
        Source::Official => 0,
        Source::Local => 1,
        Source::SteamCmd => 2,
        Source::Git => 3,
        Source::Workshop => 4,
    }
}

/// Qualified (`_steam`) source preference: `Workshop`, `Local`, `SteamCMD`,
/// `Git`. Game `Data` content cannot answer a qualified token, so it has no
/// rank and is never a fallback.
fn qualified_rank(source: Source) -> Option<u8> {
    match source {
        Source::Workshop => Some(0),
        Source::Local => Some(1),
        Source::SteamCmd => Some(2),
        Source::Git => Some(3),
        Source::Official => None,
    }
}

/// Orders two physical copies for a bare token: preferred source, then natural
/// path order, then the raw canonical path so the order is total.
fn default_preference(a: &ModMetadata, b: &ModMetadata) -> Ordering {
    default_rank(a.source)
        .cmp(&default_rank(b.source))
        .then_with(|| path_order(a.id.as_path(), b.id.as_path()))
        .then_with(|| a.id.as_path().cmp(b.id.as_path()))
}

/// Orders two physical copies for a `_steam` token. `None` from
/// [`qualified_rank`] means the copy is not eligible at all; callers filter
/// those out, so this never has to order an ineligible pair.
fn qualified_preference(a: &ModMetadata, b: &ModMetadata) -> Ordering {
    qualified_rank(a.source)
        .cmp(&qualified_rank(b.source))
        .then_with(|| path_order(a.id.as_path(), b.id.as_path()))
        .then_with(|| a.id.as_path().cmp(b.id.as_path()))
}

/// Natural order of two canonical directory paths, component by component, so
/// `mod2` precedes `mod10`. The raw path order is the caller's final tiebreak:
/// two different directories can read as equal here (`mod2` and `mod02` are the
/// same number), and the catalog must still order them deterministically.
fn path_order(a: &Path, b: &Path) -> Ordering {
    let mut left = a.components();
    let mut right = b.components();
    loop {
        let ordering = match (left.next(), right.next()) {
            (Some(a), Some(b)) => component_order(a.as_os_str(), b.as_os_str()),
            (None, None) => return Ordering::Equal,
            (None, Some(_)) => return Ordering::Less,
            (Some(_), None) => return Ordering::Greater,
        };
        if ordering != Ordering::Equal {
            return ordering;
        }
    }
}

/// Natural order of one path component, over its raw encoded bytes.
///
/// Every component goes through the same algorithm, valid UTF-8 or not: a
/// comparator that compares valid pairs naturally and any invalid pair by raw
/// text is not a total order at all. With `mod2`, `mod10` and `mod1` plus an
/// undecodable byte that gives `mod2 < mod10`, `mod10 < mod1\xFF` and
/// `mod1\xFF < mod2`, so the sorted copy order would depend on the order the
/// records happened to arrive in. `OsStr::as_encoded_bytes` is the byte form of
/// the identity itself, so no path is dropped and lossy display text is never
/// consulted.
fn component_order(a: &std::ffi::OsStr, b: &std::ffi::OsStr) -> Ordering {
    natural_cmp(a.as_encoded_bytes(), b.as_encoded_bytes())
}

/// Natural order of two byte runs: a run of ASCII digits compares as the number
/// it spells, any other run compares as the bytes it is.
///
/// A digit run is never parsed into a number, so a forty-digit version in a
/// directory name cannot overflow anything: a run with more significant digits
/// is the larger one. Runs only break at an ASCII digit boundary, which is
/// never inside a multi-byte UTF-8 sequence, and byte order is the same as text
/// order for the ASCII digits themselves, so valid names keep comparing the way
/// they did.
fn natural_cmp(a: &[u8], b: &[u8]) -> Ordering {
    let mut left = a;
    let mut right = b;
    loop {
        match (left.is_empty(), right.is_empty()) {
            (true, true) => return Ordering::Equal,
            (true, false) => return Ordering::Less,
            (false, true) => return Ordering::Greater,
            (false, false) => {}
        }
        let (left_run, left_rest) = split_run(left);
        let (right_run, right_rest) = split_run(right);
        let ordering = if is_digits(left_run) && is_digits(right_run) {
            number_cmp(left_run, right_run)
        } else {
            left_run.cmp(right_run)
        };
        if ordering != Ordering::Equal {
            return ordering;
        }
        left = left_rest;
        right = right_rest;
    }
}

/// The leading run of `bytes`, which is either all ASCII digits or holds no
/// ASCII digit at all, and whatever follows it.
fn split_run(bytes: &[u8]) -> (&[u8], &[u8]) {
    let digits = bytes.first().is_some_and(u8::is_ascii_digit);
    let end = bytes
        .iter()
        .position(|byte| byte.is_ascii_digit() != digits)
        .unwrap_or(bytes.len());
    bytes.split_at(end)
}

fn is_digits(run: &[u8]) -> bool {
    !run.is_empty() && run.iter().all(u8::is_ascii_digit)
}

/// Compares two ASCII digit runs by value, without converting either one to a
/// number: fewer significant digits is the smaller value, and equal-length runs
/// compare digit by digit.
fn number_cmp(a: &[u8], b: &[u8]) -> Ordering {
    let a = without_leading_zeros(a);
    let b = without_leading_zeros(b);
    a.len().cmp(&b.len()).then_with(|| a.cmp(b))
}

/// The same digits with every leading zero removed, so `0002` and `2` are one
/// number and the raw path tie decides between their directories.
fn without_leading_zeros(run: &[u8]) -> &[u8] {
    let end = run
        .iter()
        .position(|byte| *byte != b'0')
        .unwrap_or(run.len());
    &run[end..]
}

/// The installed copies, indexed by directory identity and by package id.
#[derive(Debug)]
pub struct Catalog {
    records: Vec<ModMetadata>,
    by_mod_id: HashMap<ModId, usize>,
    by_package_id: HashMap<PackageId, CopyGroup>,
}

impl Catalog {
    /// Takes the ordered physical records the scanner produced.
    ///
    /// The given sequence is what [`Catalog::mods`] returns: the catalog never
    /// re-sorts the record list, so the scanner owns the presentation order of
    /// rows. Only copy order and token resolution are independent of it.
    ///
    /// A [`ModId`] identifies a directory, so the same one twice is a
    /// contradictory input; it is reported rather than deduplicated, because
    /// dropping a row here would drop a real installed copy. Records whose
    /// metadata is unusable stay in the catalog and stay retrievable; they are
    /// simply not eligible to answer a token.
    pub fn new(mods: Vec<ModMetadata>) -> Result<Catalog, Error> {
        let records = mods;
        let mut by_mod_id: HashMap<ModId, usize> = HashMap::with_capacity(records.len());
        let mut grouped: HashMap<PackageId, Vec<usize>> = HashMap::new();

        for (index, record) in records.iter().enumerate() {
            if let Some(existing) = by_mod_id.insert(record.id.clone(), index) {
                return Err(Error::InvalidInput {
                    context: "Catalog::new".to_string(),
                    message: format!(
                        "the installed directory {} is listed twice, at position {existing} and position {index}",
                        record.id,
                    ),
                });
            }
            // A record without a package id belongs to no group: it keeps its
            // own identity and is never folded into a synthetic one.
            if let Some(package_id) = &record.parsed.package_id {
                grouped.entry(package_id.clone()).or_default().push(index);
            }
        }

        // Each group is ordered once here, so a lookup never rescans the catalog
        // or re-sorts a copy group.
        let mut by_package_id: HashMap<PackageId, CopyGroup> =
            HashMap::with_capacity(grouped.len());
        for (package_id, mut copies) in grouped {
            copies.sort_by(|&a, &b| default_preference(&records[a], &records[b]));
            let resolvable: Vec<usize> = copies
                .iter()
                .copied()
                .filter(|&index| records[index].is_valid())
                .collect();
            let mut qualified: Vec<usize> = resolvable
                .iter()
                .copied()
                .filter(|&index| qualified_rank(records[index].source).is_some())
                .collect();
            qualified.sort_by(|&a, &b| qualified_preference(&records[a], &records[b]));
            by_package_id.insert(
                package_id,
                CopyGroup {
                    copies,
                    resolvable,
                    qualified,
                },
            );
        }

        Ok(Catalog {
            records,
            by_mod_id,
            by_package_id,
        })
    }

    /// Every physical record, in the order the scanner listed them.
    ///
    /// This is the input sequence, unchanged: no global sort is imposed on the
    /// records, and a row is never dropped or merged.
    #[must_use]
    pub fn mods(&self) -> &[ModMetadata] {
        &self.records
    }

    /// The record for one canonical directory identity.
    #[must_use]
    pub fn get(&self, id: &ModId) -> Option<&ModMetadata> {
        self.by_mod_id.get(id).map(|&index| &self.records[index])
    }

    /// Every known physical copy that declares `package_id`, in bare-token
    /// preference order: `Official`, `Local`, `SteamCMD`, `Git`, `Workshop`,
    /// then natural path order (`mod2` before `mod10`), then the raw canonical
    /// path. Copies whose metadata is unusable are included, because inspecting
    /// them is the point of asking for copies.
    ///
    /// The iterator yields references into the catalog and never clones a
    /// record; it is empty for a package id no copy declares.
    #[must_use]
    pub fn copies(&self, package_id: &PackageId) -> Copies<'_> {
        Copies {
            records: &self.records,
            positions: self
                .by_package_id
                .get(package_id)
                .map_or(NO_COPIES, |group| group.copies.as_slice())
                .iter(),
        }
    }

    /// Resolves one active-list token to a physical copy.
    ///
    /// The token is read through the existing [`PackageId`] normalisation, so
    /// its case and surrounding spacing are not this module's concern; the text
    /// stored in the returned entry is the token as it arrived.
    ///
    /// A trailing `_steam` is the only spelling that changes the lookup: the
    /// token then asks for the best copy a qualified lookup allows, and never
    /// falls back to game `Data` content. Any other `_steam` — `a_steam_b`, or a
    /// package id that simply contains it — is part of the identity, and the
    /// marker is never stripped from inside a token.
    #[must_use]
    pub fn resolve_token(&self, token: &str) -> ActiveEntry {
        let original_token = token.to_string();
        let Some(normalized) = PackageId::normalize(token) else {
            return ActiveEntry::Unresolved {
                original_token,
                reason: UnresolvedReason::EmptyToken,
            };
        };

        let (package_id, qualified) = match normalized.as_str().strip_suffix(STEAM_MARKER) {
            // `x_steam` asks for the best `x` a qualified lookup may use. The
            // stem goes through the same normalisation, so a stem left with
            // nothing in it is a marker alone, not a package id.
            Some(stem) => match PackageId::normalize(stem) {
                Some(package_id) => (package_id, true),
                None => {
                    return ActiveEntry::Unresolved {
                        original_token,
                        reason: UnresolvedReason::MarkerOnlyToken,
                    };
                }
            },
            None => (normalized, false),
        };

        self.preferred_copy(&package_id, qualified, original_token)
    }

    /// The copy this catalog offers for `package_id` in one lookup style, or why
    /// there is none.
    fn preferred_copy(
        &self,
        package_id: &PackageId,
        qualified: bool,
        original_token: String,
    ) -> ActiveEntry {
        let group = self.by_package_id.get(package_id);
        let ordered: &[usize] = match group {
            Some(group) => {
                if qualified {
                    &group.qualified
                } else {
                    &group.resolvable
                }
            }
            None => NO_COPIES,
        };
        match ordered.first() {
            Some(&index) => ActiveEntry::Resolved {
                mod_id: self.records[index].id.clone(),
                original_token,
            },
            // Copies declare this package id but none can answer this lookup;
            // that is a different statement from never having heard of it.
            None if group.is_some() => ActiveEntry::Unresolved {
                original_token,
                reason: UnresolvedReason::NoEligibleCopy,
            },
            None => ActiveEntry::Unresolved {
                original_token,
                reason: UnresolvedReason::NotInstalled,
            },
        }
    }
}

/// [`Catalog::copies`]: the copies of one package id, in preference order.
pub struct Copies<'catalog> {
    records: &'catalog [ModMetadata],
    positions: std::slice::Iter<'catalog, usize>,
}

impl<'catalog> Iterator for Copies<'catalog> {
    type Item = &'catalog ModMetadata;

    fn next(&mut self) -> Option<Self::Item> {
        self.positions.next().map(|&index| &self.records[index])
    }

    fn size_hint(&self) -> (usize, Option<usize>) {
        self.positions.size_hint()
    }
}

impl ExactSizeIterator for Copies<'_> {
    fn len(&self) -> usize {
        self.positions.len()
    }
}

/// Resolves every entry of a loaded active list, in order.
///
/// The returned vector has exactly as many entries as
/// [`ConfigSnapshot::active_tokens`], in the same order, with the same token
/// text repeated where the file repeats it. The snapshot is not touched.
#[must_use]
pub fn resolve_active(snapshot: &ConfigSnapshot, catalog: &Catalog) -> Vec<ActiveEntry> {
    snapshot
        .active_tokens
        .iter()
        .map(|token| catalog.resolve_token(token))
        .collect()
}
