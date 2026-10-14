# RimSort development build artifacts

These archives contain an unsigned native executable, LICENSE.md, and this file
as BUILD-NOTES.md. CI appends the commit SHA, target triple, and compiler version.
The outer GitHub Actions artifact download is a ZIP containing the platform
archive; unpack both layers before running the executable.

| Runner baseline | Target | Inner archive |
| --- | --- | --- |
| Ubuntu 24.04 | x86_64-unknown-linux-gnu | .tar.gz |
| Windows Server 2022 (MSVC) | x86_64-pc-windows-msvc | .zip |
| macOS 15 (Apple Silicon) | aarch64-apple-darwin | .tar.gz |

Each inner archive has one top-level directory named
`rimsort-rust-<target>-<commit-sha>`, containing `rimsort-rust` (or
`rimsort-rust.exe`), `LICENSE.md`, and `BUILD-NOTES.md`.

## Running

Extract the archive, then launch `rimsort-rust` or `rimsort-rust.exe` from its
extracted directory. Unix tar archives preserve executable permissions. Linux
needs a graphical X11 or Wayland session and the runtime libraries used by the
Slint Winit backend: system fonts, fontconfig, xkbcommon, display integration and
a suitable graphics driver. The Ubuntu build uses glibc; it is not a static or
universal Linux binary. Older distributions and musl-based systems are not
supported by this artifact. Use `ldd ./rimsort-rust` to diagnose missing shared
libraries; distribution package names vary. Qt is not required by the currently
locked Slint defaults.

Windows and macOS downloads are not signed or notarized and may be blocked or
warned about by operating-system security controls. Only run builds from a commit
and workflow you trust; these archives do not establish publisher identity.
Windows may require the Microsoft Visual C++ runtime. macOS artifacts are raw
Apple Silicon executables, not .app bundles; Intel Macs are not covered.

## Limitations

These are development artifacts, not installers, published releases, or a
supported distribution format. They expire after 14 days. PR artifacts are built
from GitHub's PR merge commit; build metadata identifies the source actually
compiled. Fork PR artifacts are untrusted code, even if the workflow succeeds.

The workflow compiles release binaries and runs formatting, Clippy, and workspace
tests, including metadata behavior. The UI is currently a minimal Slint window.
A successful workflow does not prove a visible window, runtime
compatibility on another machine, or any game operations. Stable Rust and runner
images change over time, so locked dependencies do not imply bit-for-bit
reproducible binaries. Platform build success must be checked in the actual
hosted run; local Linux validation does not verify Windows or macOS.
