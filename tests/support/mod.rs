//! Shared helpers for the behavioral test suites.

use std::path::{Path, PathBuf};

/// Absolute path of a fixture inside `tests/fixtures`.
pub fn fixture(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(relative)
}

/// Bytes of the hand-authored `About.xml` for one metadata case.
pub fn about_fixture(case: &str) -> Vec<u8> {
    let path = fixture(&format!("metadata/{case}/About.xml"));
    std::fs::read(&path).unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()))
}
