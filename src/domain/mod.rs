//! UI-independent domain vocabulary, metadata interpretation and the catalog
//! of installed copies.

pub mod catalog;
pub mod metadata;
pub mod types;

// The catalog is the seam every later task reads installed copies through, so
// its vocabulary is reachable as `domain::*` as well as `domain::catalog::*`.
pub use catalog::{ActiveEntry, Catalog, Copies, UnresolvedReason, resolve_active};
