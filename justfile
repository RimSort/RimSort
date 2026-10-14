[windows]
set shell := ["cmd.exe", "/c"]

# Format Rust source.
fmt:
    cargo fmt --all

# Deny warnings in all workspace targets.
lint:
    cargo clippy --locked --workspace --all-targets -- -D warnings

# Run workspace tests without changing the lockfile.
test:
    cargo test --locked --workspace

# Check formatting without rewriting files, then lint and test.
check:
    cargo fmt --all -- --check
    just lint
    just test

# Build a release executable for the current host.
build:
    cargo build --locked --release
