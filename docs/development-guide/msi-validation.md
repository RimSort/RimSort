---
title: MSI Installation Validation
layout: default
parent: Development Guide
permalink: development-guide/msi-validation
---

# MSI Installation Validation

The Windows post-build MSI job uses a SHA256-pinned stable v1.17.4 MSI and the
actual CI-built candidate. `tests/integration/test_windows_msi.py` checks initial
installation, upgrade, registered executable location, exact candidate file hashes,
removal of obsolete payload files, normal GUI startup/close, rejection of a corrupt
package, and uninstall. Fixture user files must survive upgrade, rejection and uninstall.

MSI operations run silently. Both installs explicitly set `INSTALLFOLDER` to a temporary path containing spaces
and an apostrophe. A test-only MSI transform redirects the final launch action through
a supervisor that supplies an isolated dev profile, verifies the original computed
`RIMSORTTARGET`, launches the actual installed executable through its ordinary
entrypoint, and records its exit. File tables, payload bytes, upgrade rules and the
rest of the installation sequence are unchanged. The production auto-launch command
and the in-app download/backup/MSI handoff are outside this installer-first test.

The native case runs only with explicit MSI inputs on a disposable, already elevated
GitHub Windows runner. It refuses pre-existing related products. Windows Installer's
system registry/cache and shortcut writes are unavoidable; test products are uninstalled
in teardown. All payloads, app profiles, source, virtual environments and diagnostics
are kept under the runner's temporary task root. GitHub's setup actions also use
runner-managed tool directories. The runner is discarded after the job.

Default source tests skip the native installer case and run the metadata/profile/launch
controls instead. Native validation requires `RIMSORT_MSI_BASELINE`,
`RIMSORT_MSI_CANDIDATE`, and `RIMSORT_MSI_EXPECTED_DIR`; the CI workflow supplies these.
Custom-location discovery (#1794), interactive UAC and failure during a partially
executed transaction remain separate validation work. Rejecting an invalid MSI before
installation does not establish transaction rollback behavior.
