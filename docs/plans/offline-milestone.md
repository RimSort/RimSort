# Offline Mod Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first offline workflow: configure paths, discover and inspect installed mods, edit and validate the active list, topologically sort it, safely save it, and launch RimWorld.

**Architecture:** Keep one Cargo package with a library for UI-independent domain/application logic and a thin Slint binary. Filesystem and process operations live behind focused integration boundaries; background work returns owned results to the UI thread. Do not introduce an async runtime, generic plugin system, or conflict-detector dependency.

**Tech Stack:** Rust edition 2024, existing locked Slint dependencies, standard-library threads/channels/processes, XML parsing, JSON settings, and temporary-file replacement. New dependencies listed below require approval with this plan before implementation.

**Spec:** `docs/design/rust-rewrite.md`.

## Global Constraints

- Windows, macOS, and Linux remain target platforms.
- Native Rust/Slint; no Python runtime or Qt required by the replacement app.
- The first usable milestone is offline; no network service, account, Steam client session, or metadata download is required.
- Reading installed Workshop files is discovery, not Steam integration.
- Topological sorting only. Standalone alphabetical sorting is excluded from eventual parity; alphabetical tie-breaking inside eligible topological levels remains.
- Layout A: available/inactive mods and active load order visible together, with a mod-details inspector.
- Launch with unsaved edits offers only **Save and launch** or **Cancel**. Failed saving prevents launch and preserves edits.
- Closing with unsaved edits offers **Save and close**, **Discard and close**, or **Cancel**. Failed saving keeps the app open.
- Warning confirmation is configurable and enabled by default; warnings remain visible when confirmation is disabled. Warning bypass never bypasses save failures.
- Conflict-detector integration belongs to a later milestone. Do not change or depend on its repository during this milestone.
- Reference Python source is pinned to `1e0085d58b2687a04ed86a2b0af06769c42c4708`. Tests run only against fixtures and temporary directories.
- No runtime dependencies, production code, or lockfile changes until the owner approves this plan. Commit only explicit task paths after verification; never push without authorization.

## Review Focus

1. Duplicate/case-varied package IDs and `_steam` tokens must resolve deterministically without activating two copies or rewriting an unrelated ID.
2. Malformed or unreadable mod/config files must produce diagnostics and never silently erase the loaded configuration.
3. Unresolved active entries and absent ordering targets must not disappear during editing, sorting, or saving.
4. Failed or stale saves must preserve edits, leave the original file intact before replacement, and prevent launch/close success.
5. Late worker results and filtered row indices must not mutate a newer session or the wrong selected mod.

Each task below pins the applicable cases with named acceptance tests. Native platform smoke checks are separate from headless tests.

## Proposals requiring approval

These are concrete builder choices, not previously approved user decisions:

- **Dependencies:** `quick-xml` for event-based XML parsing, `serde` with derive plus `serde_json` for settings, `thiserror` for explicit error types, `directories` for platform app-data locations, and `tempfile` for safe replacement and test fixtures. Resolve compatible releases when implementing Task 1, record their exact versions in Cargo.lock, and verify official documentation against those releases. Do not upgrade Slint as part of this milestone.
- **Configuration:** one setup, manually entered game/content/config/local/optional Workshop paths, explicit target game version, and optional executable override. Persist new rewrite settings separately from Python settings. No existing-settings migration, path autodetection, or launch wrappers in this milestone.
- **Duplicate resolution:** retain existing source priority and natural-path tie-breaking; show the selected source and keep every installed copy inspectable. Activation and explicit replacement must reject a new selection unless a supported package-id token, optionally qualified with `_steam`, resolves back to that exact ModId. Explain the format limitation immediately rather than silently saving a different copy. Existing unresolved tokens remain preservable. Save encodable Workshop duplicate selections with `_steam` where needed.
- **Incomplete lists:** retain unresolved entries as visible placeholders. Saving retains their exact tokens unless explicitly removed; sorting an unresolved or ambiguous active list fails without changing it.
- **Save safety:** edit only `<activeMods>` in an existing ModsConfig.xml, preserve the rest of the XML bytes, create a sibling `.rimsort-rust.bak` backup, detect external changes, and replace using a same-directory temporary file. Do not promise durability through power loss or cooperation from another process that ignores our checks.
- **Missing config:** show an empty read-only startup state and a clear missing-config error; do not create a game config automatically. Initial-config creation is outside this milestone.
- **Controls:** resizable three-pane layout, single selection with visible activate/deactivate and move-up/down controls, drag reordering, independent searches, Ctrl/Cmd+S to save, and keyboard selection. Multi-select/bulk editing is tracked for later parity.
- **Launch:** explicit executable override supports unusual installs; defaults cover native platform executables. No Proton/Wine, Steam initialization, wrappers, or custom arguments in this milestone. Launch success means the OS accepted process creation, not that RimWorld finished loading.
- **Refresh:** replace a dirty working list only after Save, Discard, or Cancel; cancelling preserves it. Disable conflicting edits while scan/save/launch jobs run and expose scan/sort cancellation.

## Reference evidence

Consult these files at the pinned commit, using Git history if the Python checkout moves:

| Concern | Source and tests |
| --- | --- |
| Metadata and version overrides | `app/models/metadata/metadata_factory.py`; `tests/models/metadata/test_metadata_factory.py`, `test_byversion_precedence.py` |
| Source priority and active resolution | `app/models/metadata/metadata_structure.py`, `app/controllers/metadata_controller.py`; `tests/controllers/test_metadata_controller.py`, `test_metadata_parity.py` |
| Graph compilation and sorting | `app/models/metadata/metadata_mediator.py`, `app/controllers/sort_controller.py`, `app/sort/topo_sort.py`; `tests/sort/test_topo_sort.py`, `test_sort_integration.py` |
| Save format | `app/services/import_export_service.py`, `app/utils/schema.py`, `app/utils/xml.py`; `tests/utils/test_schema.py`, `test_xml.py` |
| Game executable selection | `app/utils/generic.py` (`get_executable_path`, `launch_game_process`) |

Known behavior not to reproduce: the pinned `save_to_mods_config` calls an XML writer whose default logs rather than propagates errors. Rewrite save failures must be explicit. Python config generation also reconstructs the document; preserving unrelated fields is an intentional improvement proposed here.

## File structure

All paths are repository-relative. Do not create these files until implementation approval.

| Files | Responsibility |
| --- | --- |
| `src/lib.rs`, `src/main.rs` | Testable library exports and binary startup/error handling |
| `src/domain/mod.rs`, `types.rs`, `metadata.rs`, `catalog.rs` | Identity, metadata, installed-copy resolution and active-list tokens |
| `src/domain/validation.rs`, `sorting.rs` | Structured issues, dependency graph and deterministic sorting |
| `src/integrations/mod.rs`, `xml.rs`, `scan.rs`, `config.rs`, `settings.rs`, `launch.rs` | File parsing, discovery, safe persistence and process invocation |
| `src/application/mod.rs`, `session.rs`, `workflow.rs`, `jobs.rs` | Editing state, explicit save/launch/close transitions and workers |
| `src/ui/mod.rs`, `bridge.rs` | Slint models, callbacks and main-thread result delivery |
| `ui/main.slint`, `mod-row.slint`, `settings.slint`, `prompts.slint` | Three-pane workspace and supporting dialogs |
| `tests/support/mod.rs`, `tests/fixtures/**` | Small synthetic XML/config fixtures and temporary install helpers |
| `tests/metadata.rs`, `catalog.rs`, `editing.rs`, `sorting.rs`, `config.rs`, `settings.rs`, `workflow.rs`, `jobs.rs`, `ui.rs`, `offline_workflow.rs` | Behavioral acceptance suites |
| `justfile`, `.github/workflows/rust.yml`, `README.md` | Rust checks, platform CI and runnable documentation |
| `docs/parity.md`, `docs/testing/offline-smoke.md` | Capability ledger and real-platform smoke procedure |

## Shared interfaces

Define these types in Task 1; later tasks extend behavior, not invent incompatible identities:

- `ModId`: canonical discovered directory path; never a list index or package ID.
- `PackageId`: trimmed, case-normalized identifier. Keep original config tokens separately.
- `Source`: Official, Local, SteamCmd, Git, Workshop.
- `GameVersion`: numeric major/minor plus original display value; invalid versions are errors, not regex wildcards.
- `ParsedMetadata`: optional PackageId, display fields, supported versions, dependencies with alternatives, ordering constraints, incompatibilities and metadata diagnostics. Invalid metadata remains distinguishable from valid parsed records.
- `ModMetadata`: ModId, Source and ParsedMetadata, attached by the scanner.
- `ActiveEntry`: resolved `(ModId, original_token)` or unresolved `(original_token, reason)`.
- `Issue`: category, affected ModIds/config tokens, message data, and severity. File/operation errors are not suppressible compatibility warnings.
- `Catalog`: preserves the supplied installed-record order (the scanner provides stable canonical-ID order) plus indexes by ModId and PackageId. Copy-group ordering and resolution are independent of input enumeration order; `mods()` does not globally re-sort arbitrary input. Build indexes once, not with repeated nested scans.
- `Session`: catalog, active entries, saved entries, loaded config snapshot, target version and revision. Dirty status compares working and saved entries, not a sticky boolean.
- `Settings`: schema version, configured paths, target version, executable override, `confirm_warnings = true`.
- `Error`: explicit variants for XML, filesystem, invalid input, conflict/stale result and process launch; retain path/context and underlying errors.

Public functions return `Result` where operations can fail. Core types contain no Slint types. The plan permits internal signature refinements only when all callers/tests are updated together without changing the specified behavior.

## Task 1: Fixture-driven metadata and project test foundation

**Files:** Cargo.toml/Cargo.lock, src/lib.rs, src/domain/{mod,types,metadata}.rs, src/integrations/{mod,xml}.rs, tests/support/mod.rs, tests/fixtures/metadata/**, tests/metadata.rs, justfile.

**Consumes:** XML bytes and a target GameVersion.
**Produces:** `parse_about(bytes: &[u8], version: &GameVersion) -> Result<ParsedMetadata, Error>`; the scanner later supplies ModId and Source to form ModMetadata. Also produces `GameVersion::parse(&str) -> Result<GameVersion, Error>` and PackageId normalization.

- [ ] Establish library/test layout and approved dependencies. Preserve the existing binary and Slint lock selection. Add `just fmt`, `lint`, `test`, and `check` recipes invoking Cargo directly.
- [ ] Write failing tests `normalizes_package_ids`, `parses_single_and_multiple_list_items`, `empty_version_override_replaces_base`, `nonmatching_version_uses_base`, `force_load_survives_override`, `alternative_dependency_ids_are_preserved`, `official_metadata_without_name_is_visible`, and `malformed_xml_is_an_error`. Use tiny hand-authored fixtures, not real user files.
- [ ] Pin assertions: `Author.Mod` normalizes to `author.mod`; target `1.5.1234` selects `v1.5`; matching empty version lists erase base requirements; forceLoad fields remain after that override; literal `1.50` is not a match for `1.5`. Reject DTD/entity declarations rather than accessing external resources.
- [ ] Run `cargo test --locked --test metadata`; verify failures name missing behavior, not a broken test harness.
- [ ] Implement parsing for name, packageId, authors, description, supportedVersions, dependencies/alternatives, loadBefore/loadAfter/forceLoadBefore/forceLoadAfter, incompatibleWith, and the pinned reference's versioned fields: modDependenciesByVersion, loadBeforeByVersion, loadAfterByVersion, incompatibleWithByVersion and descriptionsByVersion. forceLoadBefore/forceLoadAfter remain base-only and additive; do not invent forceLoad*ByVersion or identity ByVersion support. A missing packageId is an invalid visible mod record, not a shared synthetic identity; an absent optional field is not a fatal error.
- [ ] Run the targeted suite, then `just check`. Review differences from reference tests and record intentional improvements in docs/parity.md. Commit `feat: parse local RimWorld mod metadata` after checks.

## Task 2: Read-only discovery, settings and active-list resolution

**Files:** src/domain/catalog.rs, src/integrations/{scan,settings,config}.rs, tests/{catalog,settings,config}.rs, tests/fixtures/install/**, docs/parity.md.

**Consumes:** Settings, metadata parser and existing ModsConfig bytes.
**Produces:** `scan_install(settings: &Settings) -> Result<ScanResult, Error>`; `parse_config(bytes: &[u8]) -> Result<ConfigSnapshot, Error>`; `resolve_active(snapshot: &ConfigSnapshot, catalog: &Catalog) -> Vec<ActiveEntry>`; load/save rewrite settings functions.

- [ ] Write failing tests for Core/DLC + Local + Workshop discovery, missing optional Workshop root, invalid configured required roots, corrupt About.xml alongside valid mods, symlink/root overlap deduplication, case-varied IDs, duplicate source selection, settings persistence/defaults, and non-destructive config load.
- [ ] Pin source priority: bare IDs prefer Official, Local, SteamCmd, Git, Workshop; trailing `_steam` prefers Workshop, Local, SteamCmd, Git. Match only a trailing suffix, never replace an internal `_steam` substring. Within a source, compare natural path components and a deterministic final path tie-break. Assert that otherwise-equal Local copies at `mod2` and `mod10` select `mod2`, and input enumeration order does not change the result.
- [ ] Pin config assertions: ordered active tokens, missing-token placeholders at their original positions, repeated tokens preserved with a diagnostic, empty activeMods accepted, unknown XML fields retained, and no writes during scan/load. Reject multiple activeMods containers and malformed config.
- [ ] Run `cargo test --locked --test catalog --test settings --test config` and confirm red tests.
- [ ] Discover direct child mod roots under configured game Data, local mods and optional Workshop roots. Canonicalize paths to avoid repeated records; classify Git/SteamCmd folders from local markers without opening a Git repository or invoking Steam. Invalid individual mods remain inspectable with diagnostics; a failed required root aborts installation replacement.
- [ ] Resolve tokens via catalog indexes; unresolved tokens remain visible. Preserve raw config bytes as the loaded snapshot. Store new settings under a distinct `RimSortRust` application directory; inject a temporary path in tests. Corrupt settings report an error, never silently overwrite the file.
- [ ] Pass targeted tests and `just check`, then commit `feat: discover installed mods and load active configuration`.

## Task 3: Editing state and deterministic validation/sorting

**Files:** src/domain/{validation,sorting}.rs, src/application/{mod,session}.rs, tests/{editing,sorting}.rs, tests/fixtures/sorting/**.

**Consumes:** Catalog, target version and ActiveEntry list.
**Produces:** `validate(catalog: &Catalog, active: &[ActiveEntry], version: &GameVersion) -> Vec<Issue>`; `sort_active(catalog: &Catalog, active: &[ActiveEntry]) -> Result<Vec<ActiveEntry>, SortError>`; Session activate/deactivate/replace-copy/move/reset operations.

- [ ] Write failing editing tests: activate once, reject a second copy without explicit replacement, reject unencodable activation/replacement without mutation, allow encodable default/Workshop replacement, deactivate, move up/down at boundaries, dirty state clears when edits are reversed, failed commands do not mutate state, unresolved placeholders can be explicitly removed, and filtering never changes domain identity.
- [ ] Write sorting fixtures and exact expected IDs: A depends on B, names `Alpha`/`Zulu` -> `[B, A]`; independent names `Zulu`/`Alpha` -> alphabetical `[Alpha, Zulu]`; equal names -> PackageId then ModId tie-break; cycle A↔B -> error and unchanged input; unresolved/repeated active IDs -> error and unchanged input; absent optional loadAfter target -> no phantom activated mod.
- [ ] Add validation tests for missing required dependencies, alternative satisfaction, inactive dependencies, incompatible pairs, numeric version mismatch, duplicate installed copies, and violated before/after relationships. Alternatives are OR, not requirements to activate all alternatives. Only already-active providers participate in sorting. If several providers are active, choose the primary packageId first, then the first active alternative in declaration order, and use that same provider for validation and graph construction. Missing supportedVersions produces an unknown-version warning, not an invented compatibility match.
- [ ] Run `cargo test --locked --test editing --test sorting`, verify red, then implement.
- [ ] Build a graph of resolved active copies. Encode dependency and before/after edges, including forceLoad fields, without inventing edges for absent mods. Keep installed official content ahead of user mods using the reference official tier behavior; preserve constraints within the official tier and detect contradictory tier constraints rather than silently violating edges.
- [ ] Use level-based Kahn traversal: snapshot all currently ready nodes, sort that level by normalized name/PackageId/ModId, then remove the entire level before constructing the next. Do not substitute a heap that interleaves newly eligible nodes into the previous level. Complexity target O(V + E + V log V); avoid enumerating every possible graph cycle.
- [ ] Sorting never activates missing dependencies or removes entries. Return a bounded cycle diagnostic identifying involved mods. Preserve source selection and original tokens through reordering.
- [ ] Pass all tests and `just check`; commit `feat: edit validate and topologically sort mod lists`.

## Task 4: Failure-safe configuration persistence

**Files:** src/integrations/config.rs, tests/config.rs, tests/fixtures/config/**.

**Consumes:** ConfigSnapshot and current active entries.
**Produces:** `prepare_save(snapshot: &ConfigSnapshot, active: &[ActiveEntry], catalog: &Catalog) -> Result<PreparedSave, Error>`; `commit_save(path: &Path, snapshot: &ConfigSnapshot, prepared: &PreparedSave) -> Result<ConfigSnapshot, Error>`.

- [ ] Add red tests: rewrite only activeMods; preserve version/knownExpansions/unknown elements/comments and UTF-8 content outside that span; XML-escape tokens; preserve unresolved raw tokens; emit `_steam` for duplicate Workshop selections; verify backup equals original bytes; reject externally changed files.
- [ ] Add deterministic fault injection at backup creation, temporary write, file sync, and replacement. Every pre-replacement failure leaves the target unchanged. Every failure leaves Session dirty and does not invoke launch or close effects. Test faults through narrow operation seams, not chmod alone, which behaves differently under privileged accounts.
- [ ] Run targeted tests and verify red. Implement validated event parsing with byte-span replacement of activeMods; never serialize the rest of the document through a lossy object model. Validate prepared output before replacement.
- [ ] Compare current file bytes with the loaded snapshot immediately before commit. A mismatch requires Refresh or Cancel, never an implicit overwrite. Create/replace the backup safely, then sync a same-directory temporary file and persist it over the target. Do not delete the destination first. Preserve target permissions where supported and reject symlink destinations with a clear error.
- [ ] On successful replacement return the committed snapshot from known prepared bytes; do not require a post-commit read to label the save successful. The saved entry snapshot advances only on this success. Record the narrow remaining cross-process race rather than claiming a lock on the game's writer.
- [ ] Pass targeted tests, then `just check`; commit `feat: safely persist active mod configuration`.

## Task 5: Save/launch/close workflow and native launch adapter

**Files:** src/application/workflow.rs, src/integrations/launch.rs, tests/workflow.rs.

**Consumes:** Session, current validation results, Settings and user decisions.
**Produces:** explicit `WorkflowEvent`, `WorkflowEffect` and workflow reducer; `build_launch(settings: &Settings, platform: Platform) -> Result<LaunchCommand, Error>`; launch adapter using std::process::Command.

- [ ] Write red workflow tests for clean launch, dirty launch prompting, save success then launch, save failure never launching, Cancel retaining edits, close Save/Discard/Cancel, close save failure staying open, refresh gating, warning confirmation enabled/disabled, and suppression never suppressing operation errors.
- [ ] Define effects for PromptUnsavedLaunch, PromptUnsavedClose, PromptUnsavedRefresh, PromptWarnings, Save, Launch, Refresh and Close. Tests assert exact ordered effect sequences, not only final booleans. Dirty launch has no LaunchWithoutSave transition.
- [ ] Confirm warnings once per operation against the current revision. A changed revision invalidates a previous acknowledgement. Save and launch uses one confirmation, not two identical prompts; warning dismissal cancels the entire operation. A failed launch after successful save leaves the list clean and reports launch failure.
- [ ] Run `cargo test --locked --test workflow` and verify red, then implement reducer and adapters.
- [ ] Default native executable selection: Windows RimWorldWin64.exe then RimWorldWin.exe; Linux RimWorldLinux64 then RimWorldLinux with executable permission checks; macOS configured .app bundle through `/usr/bin/open` with a new application instance. Executable override supports explicit paths with spaces and non-ASCII text. Use argument vectors, never shell command concatenation.
- [ ] Separate macOS bundle location from game content root when configuring paths. Windows/Linux child working directory is the game root. Launch is independent of the manager lifetime; never wait for the game on the UI thread. Prevent duplicate launch requests while a spawn operation is pending.
- [ ] Test command construction for all three platforms without spawning a real game. Use a harmless fixture process to test actual spawn failure and acceptance on the host platform. Pass `just check`; commit `feat: enforce safe save launch and close workflows`.

## Task 6: Background jobs and Slint workspace

**Files:** src/application/jobs.rs, src/ui/{mod,bridge}.rs, src/main.rs, ui/{main,mod-row,settings,prompts}.slint, tests/{jobs,ui}.rs.

**Consumes:** Session operations, workflow effects, integration functions and owned job results.
**Produces:** the runnable layout-A workspace with callback adapters and revision-tagged background jobs.

- [ ] Write red job tests: cancelled scan never installs results, stale scan/sort result is ignored, save success applies only to the matching revision, and application shutdown does not panic when a worker posts a late completion. Job results carry JobId and revision; filesystem writes cannot be treated as cancelled after successful replacement.
- [ ] Implement standard-library workers for scan, validation/sort, save and spawn. Keep Slint ModelRc/VecModel and other UI handles on the UI thread; deliver owned data using weak-handle event-loop dispatch. Bound progress updates and cooperative scan/sort cancellation checks. Avoid per-row whole-catalog copies.
- [ ] Write UI adapter tests for stable ModId mapping through filtering, activation/deactivation, reorder commands, dirty labels, warning setting persistence, disabling conflicting actions during jobs, and no partial visible state on failed refresh.
- [ ] Build a resizable three-pane window: inactive search/list; active search/numbered list and Sort; inspector with name/source/package/version/description and diagnostics. Display unresolved entries as removable placeholders, invalid mods as inspectable but not activatable rows, and duplicate-copy selection through an explicit replacement prompt.
- [ ] Add path/version/executable settings, Refresh, Save to game, Launch game, status/progress, warning details and scan/sort cancellation. Use plain-text description rendering for this milestone. Avoid adding future Tools tabs or nonfunctional buttons.
- [ ] Support buttons plus drag reorder and keyboard selection, activation/deactivation, move up/down and save. Filtering narrows rows without changing order or targets; map every callback back to ModId/active-entry identity, never a filtered index alone.
- [ ] Route native window-close requests through the workflow. Cancel the native close until Close is emitted; do not let the window disappear while a failed save is pending. Test clean close and the three dirty-close actions.
- [ ] Compile and run Slint adapter tests using the version-matched official testing backend. If simulated drag events require an additional Slint testing dependency, seek approval before adding it; keep domain reorder tests independent of backend availability.
- [ ] Perform a real host-platform window smoke check and confirm the window remains interactive during a fixture scan. No browser screenshot proves native Slint behavior. Run `just check` and commit `feat: add native Slint mod management workspace`.

## Task 7: End-to-end acceptance, platform CI and documentation

**Files:** tests/offline_workflow.rs, .github/workflows/rust.yml, README.md, docs/parity.md, docs/testing/offline-smoke.md.

**Consumes:** complete milestone library and UI.
**Produces:** executable acceptance evidence, cross-platform Rust CI and user-facing setup instructions.

- [ ] Write an end-to-end temporary-install test: load a real-format fixture config, scan mods, inspect a selected record, activate and reorder, detect an issue, topologically sort, acknowledge warnings, save, then route launch through a recording adapter. Assert on disk order, preserved unrelated XML, backup bytes, clean state and exactly one launch after successful save.
- [ ] Add failure variants for malformed config, missing active entry, cyclic rules, stale config, failed save and cancelled prompts. Assert no accidental launch and no lost pending edits. Include a 2,000-mod synthetic catalog test without fragile wall-clock limits; assert correct counts, deterministic sorting and no duplicate identities.
- [ ] Add Windows/macOS/Linux CI using a fixed reviewed stable toolchain compatible with the lockfile. Run cargo fmt --all --check, cargo clippy --locked --all-targets -- -D warnings, cargo test --locked and cargo build --locked. Install only documented Slint platform prerequisites; do not run real game processes in CI.
- [ ] Document copy-paste setup/run commands, path configuration, warning setting, save/close/launch rules, backup location and first-milestone limitations. Preserve license metadata. Mark each supported capability with its acceptance test; leave future capabilities unimplemented and standalone alphabetical sorting explicitly excluded.
- [ ] Write native smoke procedures for all three platforms: real window, fixture scan/edit/reorder/sort, save prompts, failed-save behavior, warning setting, close behavior and a harmless launch target. Record which platforms were actually exercised; mark others unverified rather than claiming native coverage from library tests.
- [ ] Run the full Rust gate, review scoped diff, complete an independent whole-branch review using the owner's selected execution method, then commit `test: verify offline mod management workflow` after resolving findings.

## Completion and execution gate

- [ ] Self-review every approved requirement against its owning task and acceptance tests.
- [ ] Owner approves the concrete proposals above, including runtime dependencies and UI controls.
- [ ] Owner chooses Native or Subagent-driven execution. Native means implementation in the current session with one independent whole-branch review at the end; Subagent-driven means per-task independent reviews plus a whole-branch review.
- [ ] Every task's red/green test cycle and quality gate has evidence.
- [ ] Full Rust CI checks pass on the platforms actually run; native smoke status is recorded separately.
- [ ] No unrelated changes, Python runtime, alphabetic sorting mode, network integrations or conflict-detector implementation enter this milestone.
- [ ] Commits contain only scoped changes; no push or PR without further authorization.
