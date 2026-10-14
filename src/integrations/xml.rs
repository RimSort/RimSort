//! Strict event-level reading of `About.xml` bytes into an element tree.
//!
//! The reader refuses document type declarations, general entity references
//! that are not predefined, malformed attributes and content outside the root
//! element, so a mod file can never make us resolve an external resource.
//! Interpretation of the resulting tree lives in [`crate::domain::metadata`].

use std::borrow::Cow;

use quick_xml::XmlVersion;
use quick_xml::escape::EscapeError;
use quick_xml::events::{BytesStart, Event};
use quick_xml::reader::Reader;

use crate::domain::types::Error;

/// One XML element: its declared name, the character data directly inside it,
/// and its child elements in document order.
#[derive(Clone, Debug)]
pub struct XmlElement {
    name: String,
    text: String,
    children: Vec<XmlElement>,
}

impl XmlElement {
    fn new(name: String) -> Self {
        Self {
            name,
            text: String::new(),
            children: Vec::new(),
        }
    }

    /// The name exactly as declared in the file.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Concatenated character data of this element, with the outer whitespace
    /// of the whole run trimmed. This is value normalization inside an element,
    /// not the document envelope: the rules next to the root element are
    /// stricter than Unicode trimming.
    #[must_use]
    pub fn text(&self) -> &str {
        self.text.trim()
    }

    #[must_use]
    pub fn children(&self) -> &[XmlElement] {
        &self.children
    }

    /// About.xml tag spelling is inconsistent in the wild (`ModMetaData` and
    /// `ModMetadata` both ship), so name comparison ignores ASCII case.
    #[must_use]
    pub fn has_name(&self, name: &str) -> bool {
        self.name.eq_ignore_ascii_case(name)
    }

    /// The first child matching `name`, ignoring ASCII case.
    #[must_use]
    pub fn child(&self, name: &str) -> Option<&XmlElement> {
        self.children.iter().find(|child| child.has_name(name))
    }

    /// All children matching `name`, ignoring ASCII case, in document order.
    pub fn children_named(&self, name: &str) -> impl Iterator<Item = &XmlElement> {
        self.children
            .iter()
            .filter(move |child| child.has_name(name))
    }
}

/// Parses XML bytes into the document's single root element.
///
/// Outside the root only XML whitespace, comments, processing instructions and
/// one declaration at the very first position are legal, so stray content cannot
/// be dropped silently.
pub fn parse_document(bytes: &[u8]) -> Result<XmlElement, Error> {
    let mut reader = Reader::from_reader(bytes);
    // Comments are ignored as content but still have to be legal XML.
    reader.config_mut().check_comments = true;
    // Text is deliberately not trimmed per event: a value such as
    // "Tom &amp; Jerry" arrives as several events, and the whole run is trimmed
    // once by `XmlElement::text` so the inner spacing survives.
    let mut open: Vec<XmlElement> = Vec::new();
    let mut root: Option<XmlElement> = None;
    // The XML declaration is allowed once, with nothing but whitespace before it.
    let mut prolog_used = false;

    loop {
        let event = match reader.read_event() {
            Ok(event) => event,
            Err(source) => return Err(syntax_error(&open, source.to_string())),
        };
        match event {
            Event::Eof => break,
            Event::Start(start) => {
                let name = validate_element(&start, &open)?;
                prolog_used = true;
                open.push(XmlElement::new(name));
            }
            Event::Empty(start) => {
                let name = validate_element(&start, &open)?;
                prolog_used = true;
                attach(&mut open, &mut root, XmlElement::new(name))?;
            }
            Event::End(_) => {
                let finished = open.pop().ok_or_else(|| {
                    syntax_error(&open, "closing tag has no matching opening tag")
                })?;
                prolog_used = true;
                attach(&mut open, &mut root, finished)?;
            }
            Event::Text(text) => {
                let decoded = decoded_text(text.decode(), &open)?;
                match open.last_mut() {
                    Some(current) => current.text.push_str(&decoded),
                    // Outside the root only XML's four whitespace characters are
                    // legal, and any of them still consumes the single position an
                    // XML declaration may occupy.
                    None if is_xml_whitespace(&decoded) => {
                        if !decoded.is_empty() {
                            prolog_used = true;
                        }
                    }
                    None => {
                        return Err(syntax_error(
                            &open,
                            "character data outside the root element",
                        ));
                    }
                }
            }
            Event::CData(data) => {
                // Character data inside CDATA is literal: entities are not
                // expanded there.
                let decoded = decoded_text(data.decode(), &open)?;
                match open.last_mut() {
                    Some(current) => current.text.push_str(&decoded),
                    None => {
                        return Err(syntax_error(
                            &open,
                            "CDATA section outside the root element",
                        ));
                    }
                }
            }
            Event::GeneralRef(reference) => {
                let name = decoded_text(reference.decode(), &open)?;
                if open.is_empty() {
                    return Err(syntax_error(
                        &open,
                        "entity reference outside the root element",
                    ));
                }
                let element = context(&open);
                let expanded = expand_reference(&name, &element)?;
                if let Some(current) = open.last_mut() {
                    current.text.push_str(&expanded);
                }
            }
            Event::Decl(_) => {
                if prolog_used {
                    return Err(syntax_error(
                        &open,
                        "an XML declaration is allowed once, before any other content",
                    ));
                }
                prolog_used = true;
            }
            Event::PI(_) | Event::Comment(_) => {
                prolog_used = true;
            }
            Event::DocType(_) => {
                return Err(Error::DocTypeNotAllowed {
                    element: context(&open),
                });
            }
        }
    }

    if !open.is_empty() {
        return Err(syntax_error(
            &open,
            "element is not closed before the end of the document",
        ));
    }

    root.ok_or_else(|| syntax_error(&open, "document has no root element"))
}

/// Stores a finished element in its parent, or records it as the root,
/// rejecting a second root element.
fn attach(
    open: &mut [XmlElement],
    root: &mut Option<XmlElement>,
    element: XmlElement,
) -> Result<(), Error> {
    let enclosing = context(open);
    if let Some(parent) = open.last_mut() {
        parent.children.push(element);
        return Ok(());
    }
    if root.is_some() {
        return Err(Error::XmlSyntax {
            element: enclosing,
            message: format!(
                "document has more than one root element ({})",
                element.name()
            ),
        });
    }
    *root = Some(element);
    Ok(())
}

/// Element path of the position currently being read, used as error context.
fn context(open: &[XmlElement]) -> String {
    if open.is_empty() {
        return "<document>".to_string();
    }
    open.iter()
        .map(|element| element.name())
        .collect::<Vec<&str>>()
        .join("/")
}

fn syntax_error(open: &[XmlElement], message: impl Into<String>) -> Error {
    Error::XmlSyntax {
        element: context(open),
        message: message.into(),
    }
}

/// True when `text` contains only the four characters XML allows between markup:
/// space, tab, carriage return and line feed. Unlike `str::trim`, this rejects
/// U+00A0 and other Unicode spacing, which are character data here and therefore
/// malformed next to the root element.
fn is_xml_whitespace(text: &str) -> bool {
    text.chars()
        .all(|ch| matches!(ch, ' ' | '\t' | '\r' | '\n'))
}

/// Reads an element's declared name and validates its attributes, even on
/// elements whose fields we ignore: a duplicated or malformed attribute, or a
/// DTD entity smuggled into an attribute value, must not pass silently. The
/// values themselves are not kept, so only their shape is checked.
fn validate_element(start: &BytesStart<'_>, open: &[XmlElement]) -> Result<String, Error> {
    let name = std::str::from_utf8(start.name().as_ref())
        .map(str::to_string)
        .map_err(|source| syntax_error(open, source.to_string()))?;

    for attribute in start.attributes() {
        let attribute = attribute.map_err(|source| syntax_error(open, source.to_string()))?;
        // A literal `<` is forbidden in an attribute value before any entity
        // normalization, so a `<` decoded from `&lt;` stays legal.
        if attribute.value.contains(&b'<') {
            let key = String::from_utf8_lossy(attribute.key.as_ref());
            return Err(syntax_error(
                open,
                format!("attribute {key:?} contains a literal '<'"),
            ));
        }
        attribute
            .normalized_value(XmlVersion::Implicit1_0)
            .map_err(|source| match source {
                quick_xml::Error::Escape(EscapeError::UnrecognizedEntity(_, entity)) => {
                    Error::UnsupportedEntity {
                        name: entity,
                        element: context(open),
                    }
                }
                other => syntax_error(open, other.to_string()),
            })?;
    }

    Ok(name)
}

fn decoded_text(
    decoded: Result<Cow<'_, str>, impl std::fmt::Display>,
    open: &[XmlElement],
) -> Result<String, Error> {
    decoded
        .map(Cow::into_owned)
        .map_err(|source| syntax_error(open, source.to_string()))
}

/// Expands one reference between `&` and `;`. Character references and the five
/// predefined XML entities are resolved; anything else would need the DTD we
/// refuse, so it is an error rather than a silent substitution.
fn expand_reference(name: &str, element: &str) -> Result<String, Error> {
    match quick_xml::escape::unescape(&format!("&{name};")) {
        Ok(Cow::Borrowed(text)) => Ok(text.to_string()),
        Ok(Cow::Owned(text)) => Ok(text),
        Err(EscapeError::UnrecognizedEntity(_, entity)) => Err(Error::UnsupportedEntity {
            name: entity,
            element: element.to_string(),
        }),
        Err(source) => Err(Error::XmlSyntax {
            element: element.to_string(),
            message: source.to_string(),
        }),
    }
}
