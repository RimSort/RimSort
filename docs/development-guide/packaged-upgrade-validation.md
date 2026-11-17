---
title: Packaged Upgrade Validation
layout: default
parent: Development Guide
permalink: development-guide/packaged-upgrade-validation
---

# Packaged Upgrade Validation

The post-build upgrade matrix exercises the actual packaged updater on Windows,
macOS arm64 and Ubuntu 22.04/24.04. It complements the native AppImage tests and the
[MSI installation tests](msi-validation).

## Automated contract

`tests/integration/test_packaged_upgrade.py` runs four scenarios per archive format:

- Back up a SHA256-pinned v1.17.4 installation using the current compiled backup
  service, then run the current installer against that old directory and verify
  the candidate starts normally. This is installer compatibility coverage.
- Update the candidate installation, exercising the current updater implementation.
- Reject a corrupt download without changing the installation.
- Inject a partial copy failure, verify the previous installation survives on POSIX,
  restore the backup produced by RimSort, and launch the restored GUI normally.
  Windows portable updates require this explicit manual-style recovery after a
  partial in-place copy; the test does not claim automatic Windows rollback.

The tests round-trip every produced backup and compare it with the complete previous
file manifest. They also verify candidate file hashes, fixture settings and mod-file
preservation, normal GUI initialization and clean shutdown. Current macOS upgrades
and restored bundles must pass strict signature verification.

ZIP recovery backups retain source file permissions, including the Linux executable
bit. Recovery uses the archived permissions; it does not repair modes in the harness.

`tests/integration/test_updater_msi.py` adds the current packaged updater's download,
backup and MSI handoff to the installer-first Windows job. It installs the real CI
candidate, then upgrades to a test copy with fresh ProductCode and PackageCode GUIDs.
Payload, component identities, version, upgrade rules and action sequence stay the
same; RimSort's same-version major-upgrade support handles this transaction. The
test checks the staged fixture MSI, original `msiexec` arguments, registration,
payload, backup and normal installed GUI startup/close before uninstalling. The
installer-first test separately covers v1.17.4 to the unmodified candidate MSI.

## Instrumentation and isolation

The existing helper entrypoint configures a disposable Core fixture and invokes the
compiled updater after its GUI initializes. A local HTTP server supplies the candidate;
release discovery and interactive confirmation are outside these tests. Normal startup
after installation uses the executable's ordinary entrypoint with source imports cleared.

Process-stop adapters validate the fixture PID, creation time, executable path and
environment marker before signalling it. Teardown captures verified supervisor
descendants before stopping parents, including system shells whose environments
are hidden by macOS. Direct installers retain their process handle, and POSIX
supervisor timeouts stop their child tree before returning. Backup and fixture setup
use the same runner, and GUI timeouts capture descendants before terminating the
GUI process. Relaunches retain
temporary app data and capture exit codes. On macOS the generated AppleScript is
compiled, and its real installer command runs under Bash; the Terminal window and
Launch Services `open` operation are replaced by supervised execution. Its working
directory stays in the fixture because the retired bundle directory can be deleted.
Native Quit uses AppKit's `NSRunningApplication.terminate()`. Windows uses `WM_CLOSE`;
Linux uses X11 window ownership checks and the application's quit shortcut.
Linux script launches replay the exact generated command, shell mode and working
directory through a supervisor so both successful and failed installer exit codes
are asserted. The macOS supervisor's installer result is also checked before teardown.
The copy-fault adapter writes only a prefix of the fixture executable before reporting
failure; Windows recovery checks that the installed executable was actually damaged.

MSI handoff uses the existing test-only launch transform and explicit temporary
`INSTALLFOLDER`. The original updater command is checked before forwarding to this
isolated installer invocation. Production automatic-launch syntax, custom destination
discovery (#1794) and UAC are outside this instrumentation boundary.

Windows/Linux native cases require a disposable GitHub runner and explicit inputs.
Local macOS runs require `RIMSORT_UPGRADE_ROOT`, `RIMSORT_UPGRADE_CANDIDATE_DIR`, and a
pytest `--basetemp` inside that root. All fixture data, downloads, environments and
diagnostics stay there. MSI registry/cache/shortcut writes and GitHub setup-action
tool directories are unavoidable OS/runner-managed writes on disposable CI machines.
Successful fixture directories are removed after their processes stop. Failure output
contains bounded installer/app logs; no evidence archive is uploaded.

## Remaining manual checks

Use disposable installations and profiles when checking protected/custom/external-drive
destinations, actual UAC/sudo prompts and cancellation, Terminal/Launch Services behavior,
Gatekeeper/notarization, absent terminal tools, and hardware interruption/power loss.
Already-elevated runners and simulated copy failures do not establish those behaviors.

The immutable v1.17.4 updater predates the backup-thread, launcher, destination and
archive-metadata fixes. Native macOS probes reproduced malformed launcher arguments
with spaced paths and a Qt painting crash during its default backup. These old-binary
failures are not a passing CI gate and are not fixed retroactively by the new code.
Set `RIMSORT_UPGRADE_LEGACY=1` and select `-k legacy` to run the opt-in diagnostic;
macOS may write an OS-managed crash report outside the fixture when it fails.

The required baseline case tests the current backup/installer against old files;
it does not assert a successful end-to-end run through v1.17.4's buggy updater.
Current-updater cases cover spaces and, on POSIX, apostrophes/Unicode and a custom
macOS bundle name. Windows portable shell-special paths remain connected to #1844/#2611.
