# RimSort Rust rewrite

The Rust rewrite of RimSort is built with [Slint](https://slint.dev/).

## Prerequisites

Install [Rust stable](https://rustup.rs/) with the `rustfmt` and `clippy`
components. [just](https://just.systems/) provides convenient local task commands;
Cargo can also be used directly.

Native builds need a platform compiler/linker: Visual Studio Build Tools with
Desktop development with C++ on Windows, Xcode Command Line Tools on macOS, and
build essentials on Linux. On Ubuntu:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends build-essential pkg-config libfontconfig1-dev libxkbcommon-dev
```

See the [Slint build guide](https://github.com/slint-ui/slint/blob/v1.18.1/docs/building.md)
for platform requirements. Cargo.lock currently resolves Slint to 1.18.1; its
default backend is Winit and Qt is not required.

## Run and develop

```sh
cargo run --locked
```

The first build downloads and compiles dependencies.

| Command | Purpose | Cargo equivalent |
| --- | --- | --- |
| `just fmt` | Format Rust source | `cargo fmt --all` |
| `just lint` | Clippy, denying warnings | `cargo clippy --locked --workspace --all-targets -- -D warnings` |
| `just test` | Run workspace tests | `cargo test --locked --workspace` |
| `just check` | Check formatting, lint, then test | `cargo fmt --all -- --check`, then the lint and test commands above |
| `just build` | Build a native release executable | `cargo build --locked --release` |

`just check` does not rewrite formatting. Release executables are written to
`target/release/rimsort-rust` (`rimsort-rust.exe` on Windows).

Dependencies are resolved from the tracked lockfile. Rust stable and hosted runner
images can change, so this is not a bit-for-bit reproducible build guarantee.
The application is currently a minimal window; the test harness has no behavioral
tests yet. Compilation and tests do not prove a visible window or game operations.

## CI and downloadable builds

The **Rust CI** GitHub Actions workflow runs on pull requests, pushes to
`feature/rust-rewrite-foundation`, and manual dispatch. Update the push branch
filter when integrating this workflow onto another branch.

Formatting runs once on Linux. Clippy, tests, and native release builds run on
Ubuntu 24.04 x86_64, Windows Server 2022 x86_64/MSVC, and macOS 15 Apple Silicon.
Actions are pinned to commit SHAs, tokens are read-only, checkout does not persist
credentials, and PRs do not save dependency caches. Superseded runs are cancelled.

To download a build, open **Actions → Rust CI → a successful run → Artifacts** and
select the target-labelled artifact. Artifacts are retained for 14 days. Each
contains a `.tar.gz` archive (Linux/macOS) or `.zip` archive (Windows) with the
executable, license, and build metadata/runtime notes. Unpack the downloaded
artifact ZIP, then the inner platform archive.

See [build artifact notes](docs/build-artifacts.md) for runtime dependencies and
limitations. These unsigned raw binaries are not installers, signed app bundles,
or published releases; Linux builds are not universally distro-portable.
