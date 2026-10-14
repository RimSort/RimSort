# RimSort Rust rewrite: high-level design

## Status

The high-level direction and first usable milestone are approved. This document
records them as the basis for implementation planning. The owner approved
layout A: simultaneous available and active lists with a mod-details inspector.
The implementation plan requires separate approval before product code changes.

## Intent

Replace RimSort with a native Rust/Slint desktop application that has a better UI
and eventual feature parity. Preserve what users can accomplish rather than
copying the Python application's widget structure or implementation quirks.
Windows, macOS, and Linux remain target platforms.

The rewrite branch contains a root-level Cargo project and minimal Slint window.
The Python app remains on the main branch and in Git history as reference.
Reference baseline for this design: `1e0085d58b2687a04ed86a2b0af06769c42c4708`.
Later upstream changes must be evaluated explicitly, not silently included.

## Eventual scope

Every existing capability is in scope, including niche tools:

- Mod discovery, metadata inspection, search/filtering, activation, manual order,
  dividers, colors, and translation status.
- Sorting and validation using About.xml, dependencies, incompatibilities,
  game versions, community/user rules, and load-order tiers.
- Steam Workshop browsing, collections, subscriptions, SteamCMD, update checking,
  Git/GitHub installation and version switching, and ZIP installation.
- Instances, switching, cloning, backups/restores, mod-list history, list
  open/append/save, save-file imports, Rentry, sharing, and game launch arguments.
- Metadata databases, rule editing, alternative-mod suggestions, version-warning
  exemptions, database building/updating, and existing CLI workflows.
- Texture optimization, DDS cleanup, logs, uploads, troubleshooting, file search,
  game-version downloads, Steam verification, settings, localization, application
  updates, and platform packaging.

This is a capability grouping, not the final exhaustive acceptance checklist.
Build that checklist from the pinned Python source and tests before declaring
parity. Record each capability as unimplemented, partial, or verified.

## First usable milestone: offline local workflow

An installed game and installed mods are sufficient. No network service, account,
Steam client session, or metadata download is required for this milestone.
Reading already-installed Workshop files is part of local discovery; acquiring
Workshop content is deferred.

A user can:

1. Configure the RimWorld installation, game configuration, and mod locations.
2. Discover installed game content and mods and read their About.xml metadata.
3. Load the existing active configuration and inspect mod details.
4. Activate/deactivate mods and manually reorder the active list.
5. See locally detectable dependency, incompatibility, version, duplicate, and
   ordering problems.
6. Sort the active list using local metadata.
7. Explicitly save the edited active list in RimWorld's configuration format.
8. Launch the configured game executable.

Community/user rule ingestion, Steam metadata supplementation, advanced launch
settings, instance management, and rich import/export are required in later
milestones and excluded from the first milestone.

**Owner decision:** use topological sorting with deterministic alphabetical
ordering within each eligible topological level, consistent with the existing
topological sorter. Report cycles explicitly and preserve the current ordering
when sorting fails. Alphabetical tie-breaking never overrides dependency edges.

**Explicit parity exception:** abandon the standalone alphabetical sorting mode.
It is excluded from all rewrite milestones and the eventual-parity checklist.
This exception does not remove alphabetical tie-breaking within topological
sorting.

## Existing Rust conflict detector

The owner's existing `rimworld-conflict-detector` project is relevant prior work.
At inspection, its HEAD was `d3dbd89`. Its Rust workspace separates `rcd-core`,
`rcd-xml`, `rcd-harmony`, CLI, and C FFI crates. It provides mod/metadata and
ModsConfig parsing, content-folder resolution, load-order validation, and
structured conflict reports with diagnostics and progress callbacks.

Its deeper analysis includes direct Def replacements, XPath overlaps, patches
on replaced Defs, and Harmony patch conflicts. These complement sorting and
metadata-based validation; a detected overlap is not automatically a sorting
instruction or a defect that needs fixing.

**Owner decision:** conflict-detector integration is a later milestone, not part
of the first offline milestone. Basic mod management must work without it.

Builder recommendation: evaluate direct Rust-library integration before writing
a competing analysis engine or introducing a CLI subprocess/C FFI bridge. Keep
the detector independently usable. Evaluate overlapping metadata and identity
models when planning integration, without making its APIs a first-milestone
requirement. The conflict-detector milestone plan must specify dependency
packaging, a pinned version, and API ownership before adding the dependency.
Integrated analysis must use the current edited active load order and clearly
separate findings from scan failures and expected overrides.

## Architectural direction

Separate responsibilities without creating speculative abstractions:

- **Domain/core:** mod identity, metadata, lists, rules, sorting, validation.
  No Slint dependencies or widget state.
- **Application:** user operations, current editing state, background jobs,
  progress/cancellation, and coordination of core and integrations.
- **Integrations:** filesystem/XML, Steam, SteamCMD, Git/GitHub, external tools,
  and network services behind focused boundaries.
- **Slint UI:** presentation, navigation, selection, interaction, and mapping
  application state to visible models.

These are responsibility boundaries, not a mandate for four crates. Exact
modules/crates and dependency choices belong to implementation planning and
must remain proportional to the milestone.

## UI and safety direction

UI goals proposed by the builder:

- Scanning, sorting, downloads, and other long-running work must not freeze the UI.
- Distinguish pending edits from the configuration saved to the game.
- Present explanations and relevant actions for warnings, not only colored icons.
- Provide consistent progress and error reporting, and cancellation where safe.
- Keep common actions discoverable without crowding the workspace with utilities.
- Support keyboard use and large mod libraries.

**Owner decision:** use mockup layout A: available/inactive mods and the active
load order visible together, with a separate mod-details inspector. This keeps
list editing and mod selection in the same workspace instead of switching
between Library and Load Order views. Before UI implementation, obtain owner
approval for pane resizing, selection and transfer controls, keyboard actions,
and unsaved-change handling. The mockup's colors and sample data are not
production requirements.

**Owner decision:** clicking Launch game with unsaved mod-list edits presents
only **Save and launch** and **Cancel**. Launching without saving is not allowed.
Save and launch starts the game only after the configuration write succeeds.
A failed save leaves the edits pending, reports the error, and does not launch
the game. Cancel preserves the pending edits and does not launch the game.

**Owner decision:** closing the app with unsaved mod-list edits offers **Save
and close**, **Discard and close**, and **Cancel**. Discard closes without writing
the pending changes to the game configuration. Save and close exits only after
a successful configuration write; a failed save keeps the app open with the
edits pending. Cancel keeps the app open and preserves the pending edits.

**Owner decision:** dependency, incompatibility, and version warnings do not
block saving or launching outright. A configuration option controls whether the
user must acknowledge these warnings before proceeding; disabling it skips the
confirmation but keeps warnings visible. This option never bypasses
configuration-write failures or the mandatory unsaved-edit launch gate.

**Owner decision:** warning confirmation is enabled by default.

Safety requirements proposed by the builder:

- Scanning and sorting do not silently modify game files or mod contents.
- An invalid or failed scan/save/sort produces an actionable error, not success.
- Failed sorting leaves the user's current ordering intact.
- Unknown or missing active entries are not silently discarded on load/save.
- Saving protects existing configuration from partial writes and preserves
  unrelated configuration fields; determine exact backup/recovery behavior in
  the milestone plan using existing behavior as reference.
- Tests never operate on the user's real configuration or mod directories.

## Delivery sequence

1. Read-only path configuration, discovery, lists, and details.
2. Complete first milestone: edit, validate, sort, save, and launch.
3. Instances, history, backup/restore, and imports/exports.
4. Steam, SteamCMD, Git/GitHub, and ZIP acquisition workflows.
5. Conflict-detector integration after the first offline milestone. When planning
   post-core work, obtain owner approval for its priority relative to acquisition
   and instance-management features.
6. Advanced utilities and release readiness.

This is sequencing guidance, not a fixed schedule. Full parity is the destination,
not a requirement that all functionality ship at once.

## Verification

Use the Python code, formats, and tests as behavioral evidence. Do not port known
bugs just to match outputs; any intentional difference must be explicit.

The first-milestone plan must include fixture-based metadata/config parsing,
sorting/validation scenarios, failed-write safety, and an end-to-end local
workflow. Rust formatting, linting, automated tests, and a real window/launch
smoke check are distinct checks. Compiling a test harness with zero tests is not
proof that the UI displays or that game operations work.

Cross-platform support is an implementation constraint. Report the platforms
actually exercised rather than claiming untested platforms passed.

## Non-goals and open design work

- No Python runtime or Qt required by the replacement app.
- No line-for-line port of the current MVC structure or giant view classes.
- No new unrelated capabilities or support for other games in this scope.
- No production integrations, packaging, or feature implementations during design.
- Resolve detailed UI behavior and first-milestone contracts before product code:
  path conventions, duplicate identity/selection, game-version interpretation,
  metadata edge cases, sorting tie-breaks, save/recovery, and launch mechanics.

Ground each contract in the pinned Python source and tests. The first-milestone
plan must document the chosen behavior and acceptance tests for each contract.
Obtain owner approval for user-visible differences before implementing them.
