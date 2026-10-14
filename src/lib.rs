//! Library core of the RimSort Rust rewrite.
//!
//! The crate is split by responsibility:
//!
//! - [`domain`]: mod identity, parsed About.xml metadata, game versions and
//!   diagnostics. No filesystem traversal and no UI types.
//! - [`integrations`]: parsing of files that live outside the application,
//!   currently `About.xml` documents.
//!
//! The Slint binary in `src/main.rs` is the only consumer of UI types; nothing
//! exported here depends on Slint.

pub mod domain;
pub mod integrations;
