//! Read-only snapshot of a `ModsConfig.xml` active mod list.
//!
//! A config file is small, opaque user data: we keep the bytes exactly as they
//! were read, record which bytes the `<activeMods>` element occupies, and report
//! the tokens in file order. Nothing here resolves a token against an installed
//! mod, normalizes case or edits the file; that belongs to the catalog, editing
//! and persistence tasks.
//!
//! XML validity is the shared strict reader's job ([`crate::integrations::xml`]):
//! a document type declaration, an entity reference outside the predefined set,
//! a malformed attribute or stray content outside the root is an error, never a
//! silently skipped construct. Locating the active list needs byte positions and
//! untrimmed entry text, which the element tree does not carry, so the same
//! bytes are read a second time as events. These files are tiny, and two linear
//! passes beat a lossy whole-document model.

use std::borrow::Cow;
use std::collections::HashMap;
use std::ops::Range;

use quick_xml::escape::EscapeError;
use quick_xml::events::{BytesStart, Event};
use quick_xml::reader::Reader;

use crate::domain::types::Error;
use crate::integrations::xml;

/// The element a `ModsConfig.xml` is built around.
const ROOT_NAME: &str = "ModsConfigData";
/// The element whose bytes a save replaces.
const ACTIVE_MODS_NAME: &str = "activeMods";
/// The only element allowed inside the active list.
const ENTRY_NAME: &str = "li";
/// The element naming the game release that wrote the file.
const VERSION_NAME: &str = "version";
/// A UTF-8 byte order mark, which the reader consumes without counting it.
const UTF8_BOM: &[u8] = &[0xEF, 0xBB, 0xBF];

/// Something true of a loaded active list that the user should see.
///
/// A diagnostic never drops an entry: the token keeps its position in
/// [`ConfigSnapshot::active_tokens`], and deciding what two identity-equivalent
/// copies mean is the catalog's later business.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConfigDiagnostic {
    /// The same decoded token text appeared before, at `first_index`. Every
    /// later copy reports that original first occurrence, blanks included.
    RepeatedToken {
        token: String,
        first_index: usize,
        index: usize,
    },
    /// The entry at `index` carries no non-whitespace text, so it can resolve
    /// to nothing. Emptiness is reported for the entry itself; an exact repeat
    /// of it is still reported as `RepeatedToken` as well.
    EmptyToken { index: usize },
}

/// One loaded `ModsConfig.xml`, kept as the bytes it was read from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigSnapshot {
    /// The file exactly as loaded, declaration, BOM, comments and all.
    pub raw: Vec<u8>,
    /// Byte range of the whole `<activeMods>` element, tags included.
    ///
    /// Saving (Task 4) replaces precisely these bytes and copies everything
    /// outside the range unchanged, so positions are byte offsets into `raw`,
    /// not character counts.
    pub active_mods_span: Range<usize>,
    /// `<li>` text in document order, entity-decoded but otherwise untouched:
    /// case, surrounding whitespace and every `_steam` spelling survive
    /// verbatim.
    pub active_tokens: Vec<String>,
    /// `<version>` text as written, padding included, when the file carries a
    /// root-level version with something in it. Never parsed into a release and
    /// never invented when absent; the first root-level version is the config's
    /// version even when it is blank.
    pub version: Option<String>,
    /// Diagnostics about the active list, in entry order.
    pub diagnostics: Vec<ConfigDiagnostic>,
}

/// Reads `ModsConfig.xml` bytes into a snapshot.
///
/// The bytes are the whole input: no file is opened and nothing is written. A
/// document that is not a `ModsConfigData` config, that lacks `<activeMods>`,
/// that declares it more than once, or that hides markup where a token belongs,
/// is an error rather than a partially loaded list.
pub fn parse_config(bytes: &[u8]) -> Result<ConfigSnapshot, Error> {
    let root = xml::parse_document(bytes)?;
    if !root.has_name(ROOT_NAME) {
        return Err(Error::XmlSyntax {
            element: root.name().to_string(),
            message: format!(
                "expected a {ROOT_NAME} root element, found {:?}",
                root.name()
            ),
        });
    }

    let containers = root.children_named(ACTIVE_MODS_NAME).count();
    if containers != 1 {
        let message = if containers == 0 {
            format!(
                "{ROOT_NAME} has no {ACTIVE_MODS_NAME} element, so no active list is configured"
            )
        } else {
            format!(
                "{ROOT_NAME} declares {containers} {ACTIVE_MODS_NAME} elements; exactly one is expected"
            )
        };
        return Err(Error::XmlSyntax {
            element: root.name().to_string(),
            message,
        });
    }

    let ConfigFields {
        active_mods_span,
        tokens,
        version,
    } = read_config_fields(bytes)?;
    let diagnostics = token_diagnostics(&tokens);

    Ok(ConfigSnapshot {
        raw: bytes.to_vec(),
        active_mods_span,
        active_tokens: tokens,
        // A version with only spacing in it is not a display string.
        version: version.filter(|text| !text.trim().is_empty()),
        diagnostics,
    })
}

/// Flags repeated and blank entries while keeping every position.
///
/// One pass over the entries in file order, so the diagnostics come out in that
/// same order; `first_index` is a scratch table of at most one entry per
/// distinct token text, which keeps the lookup linear instead of comparing each
/// entry against everything before it.
fn token_diagnostics(tokens: &[String]) -> Vec<ConfigDiagnostic> {
    let mut first_index: HashMap<&str, usize> = HashMap::new();
    let mut diagnostics = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.trim().is_empty() {
            diagnostics.push(ConfigDiagnostic::EmptyToken { index });
        }
        match first_index.get(token.as_str()) {
            Some(&seen_at) => diagnostics.push(ConfigDiagnostic::RepeatedToken {
                token: token.clone(),
                first_index: seen_at,
                index,
            }),
            None => {
                first_index.insert(token.as_str(), index);
            }
        }
    }
    diagnostics
}

/// The located config fields: the active list's bytes, the text of its entries,
/// and the file's own version string.
struct ConfigFields {
    active_mods_span: Range<usize>,
    tokens: Vec<String>,
    version: Option<String>,
}

/// Where the byte scan stands relative to the active list.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Position {
    /// Outside the list, before it or inside unrelated fields.
    Elsewhere,
    /// Between `<activeMods>` and `</activeMods>`, not inside an entry.
    InList,
    /// Inside a `<li>` entry, collecting its text.
    InEntry,
}

/// The two texts the byte scan collects: the entry being read and the root's own
/// `<version>` text.
#[derive(Default)]
struct Texts {
    entry: String,
    version: String,
}

/// Reads the active list's byte span, its entry texts and the root's own
/// `<version>` text out of an already validated document.
///
/// Element names are matched the way the shared reader matches them, ignoring
/// ASCII case, so a second `<activemods>` is a duplicate list rather than an
/// unknown field. Comments and processing instructions carry no text and are
/// skipped wherever they appear. The scan runs to the end of the document: a
/// version element written after the list is still this config's version, as
/// long as no earlier root-level one claimed it.
fn read_config_fields(bytes: &[u8]) -> Result<ConfigFields, Error> {
    // The reader consumes a leading byte order mark without counting it in its
    // positions, so every offset it reports needs the mark's length added back.
    let bom = usize::from(bytes.starts_with(UTF8_BOM)) * UTF8_BOM.len();
    let mut reader = Reader::from_reader(bytes);
    // Same strictness as the shared reader: a comment still has to be legal XML.
    reader.config_mut().check_comments = true;

    // How many elements are open while the event is read: the root is one, so
    // a Start seen at one open element is a direct child of the root, and that
    // is the only place the active list belongs.
    let mut open = 0usize;
    let mut position = Position::Elsewhere;
    let mut list_start = 0;
    let mut texts = Texts::default();
    let mut tokens: Vec<String> = Vec::new();
    let mut span: Option<Range<usize>> = None;
    // The first root-level `<version>` owns the version field, blank or not, and
    // `version_open` is the depth whose character data belongs to it.
    let mut version: Option<String> = None;
    let mut version_taken = false;
    let mut version_open = 0;

    loop {
        // The reader's position is the byte just after the previous event, and
        // every byte of the document belongs to some event, so this is also the
        // offset where the event read next begins.
        let start = bom + reader.buffer_position() as usize;
        let event = match reader.read_event() {
            Ok(event) => event,
            Err(source) => return Err(list_error(position, source.to_string())),
        };
        let end = bom + reader.buffer_position() as usize;
        let self_closing = matches!(event, Event::Empty(_));

        match event {
            Event::Eof => break,
            Event::Start(tag) | Event::Empty(tag) => {
                let name = declared_name(&tag, position)?;
                match position {
                    Position::InEntry => {
                        return Err(nested_markup(position));
                    }
                    Position::InList => {
                        if !name_is(&name, ENTRY_NAME) {
                            return Err(unsupported_child(position, &name));
                        }
                        if self_closing {
                            tokens.push(String::new());
                        } else {
                            texts.entry.clear();
                            position = Position::InEntry;
                            open += 1;
                        }
                    }
                    Position::Elsewhere => {
                        let is_the_list =
                            open == 1 && span.is_none() && name_is(&name, ACTIVE_MODS_NAME);
                        if !is_the_list {
                            // An unrelated field: remember its depth, ignore its
                            // content, and let the raw bytes carry it forward.
                            if open == 1 && !version_taken && name_is(&name, VERSION_NAME) {
                                version_taken = true;
                                if self_closing {
                                    version = Some(String::new());
                                } else {
                                    texts.version.clear();
                                    version_open = open + 1;
                                }
                            }
                            if !self_closing {
                                open += 1;
                            }
                        } else if self_closing {
                            span = Some(start..end);
                        } else {
                            list_start = start;
                            position = Position::InList;
                            open += 1;
                        }
                    }
                }
            }
            Event::End(_) => {
                match position {
                    Position::InEntry => {
                        tokens.push(std::mem::take(&mut texts.entry));
                        position = Position::InList;
                    }
                    Position::InList => {
                        span = Some(list_start..end);
                        position = Position::Elsewhere;
                    }
                    Position::Elsewhere => {}
                }
                if version_taken && version.is_none() && open == version_open {
                    version = Some(std::mem::take(&mut texts.version));
                    version_open = 0;
                }
                open = open.saturating_sub(1);
            }
            Event::Text(text) => {
                let decoded = text.decode().map_err(|source| {
                    list_error(position, format!("text is not valid UTF-8: {source}"))
                })?;
                collect_text(&mut texts, position, open, version_open, &decoded)?;
            }
            Event::CData(data) => {
                // Character data inside CDATA is literal: entities stay as they
                // are, exactly as the shared reader treats them.
                let decoded = data.decode().map_err(|source| {
                    list_error(position, format!("CDATA is not valid UTF-8: {source}"))
                })?;
                collect_text(&mut texts, position, open, version_open, &decoded)?;
            }
            Event::GeneralRef(reference) => {
                let name = reference.decode().map_err(|source| {
                    list_error(
                        position,
                        format!("entity reference is not valid UTF-8: {source}"),
                    )
                })?;
                let expanded = expand_reference(&name, position)?;
                collect_text(&mut texts, position, open, version_open, &expanded)?;
            }
            // Comments, processing instructions and declarations carry no entry
            // text, and the shared reader has already refused any document type
            // and validated what it accepted.
            Event::Comment(_) | Event::PI(_) | Event::Decl(_) | Event::DocType(_) => {}
        }
    }

    let active_mods_span = span.ok_or_else(|| {
        list_error(
            position,
            format!("{ACTIVE_MODS_NAME} is not a closed element, so its bytes cannot be located"),
        )
    })?;

    Ok(ConfigFields {
        active_mods_span,
        tokens,
        version,
    })
}

/// Adds one run of character data to the entry or the version element being
/// read, or checks that text between entries is only formatting.
///
/// Outside the list, only the version element's own depth is collected; text in
/// a field nested deeper belongs to that unknown field and stays in the raw
/// bytes instead.
fn collect_text(
    texts: &mut Texts,
    position: Position,
    open: usize,
    version_open: usize,
    text: &str,
) -> Result<(), Error> {
    match position {
        Position::InEntry => {
            texts.entry.push_str(text);
            Ok(())
        }
        Position::InList if is_formatting(text) => Ok(()),
        Position::InList => Err(list_error(
            position,
            format!("{ACTIVE_MODS_NAME} holds {ENTRY_NAME} entries, not the text {text:?}"),
        )),
        Position::Elsewhere if version_open == open && open > 0 => {
            texts.version.push_str(text);
            Ok(())
        }
        Position::Elsewhere => Ok(()),
    }
}

/// True for text made only of the whitespace XML allows between markup.
fn is_formatting(text: &str) -> bool {
    text.chars()
        .all(|ch| matches!(ch, ' ' | '\t' | '\r' | '\n'))
}

fn unsupported_child(position: Position, name: &str) -> Error {
    list_error(
        position,
        format!("only a {ENTRY_NAME} entry may appear inside {ACTIVE_MODS_NAME}, found {name}"),
    )
}

fn nested_markup(position: Position) -> Error {
    list_error(
        position,
        format!("a {ENTRY_NAME} entry holds text, not nested elements"),
    )
}

/// The declared name of an opening or self-closing element.
fn declared_name(tag: &BytesStart<'_>, position: Position) -> Result<String, Error> {
    std::str::from_utf8(tag.name().as_ref())
        .map(str::to_string)
        .map_err(|source| list_error(position, source.to_string()))
}

/// True when `name` is the wanted element, ignoring ASCII case.
fn name_is(name: &str, wanted: &str) -> bool {
    name.eq_ignore_ascii_case(wanted)
}

/// Where a byte-scan problem was found, as an element path.
fn list_context(position: Position) -> String {
    match position {
        Position::Elsewhere => ROOT_NAME.to_string(),
        Position::InList => format!("{ROOT_NAME}/{ACTIVE_MODS_NAME}"),
        Position::InEntry => format!("{ROOT_NAME}/{ACTIVE_MODS_NAME}/{ENTRY_NAME}"),
    }
}

fn list_error(position: Position, message: impl Into<String>) -> Error {
    Error::XmlSyntax {
        element: list_context(position),
        message: message.into(),
    }
}

/// Expands one reference between `&` and `;`, following the shared reader:
/// character references and the predefined XML entities resolve, and anything
/// that would need the refused DTD is reported instead of substituted.
fn expand_reference(name: &str, position: Position) -> Result<String, Error> {
    match quick_xml::escape::unescape(&format!("&{name};")) {
        Ok(Cow::Borrowed(text)) => Ok(text.to_string()),
        Ok(Cow::Owned(text)) => Ok(text),
        Err(EscapeError::UnrecognizedEntity(_, entity)) => Err(Error::UnsupportedEntity {
            name: entity,
            element: list_context(position),
        }),
        Err(source) => Err(list_error(position, source.to_string())),
    }
}
