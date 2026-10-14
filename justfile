[windows]
set shell := ["cmd.exe", "/c"]

fmt:
    cargo fmt --all

lint:
    cargo clippy --locked --workspace --all-targets -- -D warnings

test:
    cargo test --locked --workspace

check:
    cargo fmt --all -- --check
    just lint
    just test
    cargo build --locked

build:
    cargo build --locked --release
