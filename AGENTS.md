# AGENTS.md

## Project Overview

RimSort is a free and open-source multi-platform mod manager and sorter for RimWorld. It reads RimWorld `About.xml` metadata, sorts mod lists using graph/topological algorithms plus community/user rules databases, and integrates with the Steam Workshop (via SteamworksPy and SteamCMD), Git mods, and optional static metadata databases (`SteamDB`, `Community Rules`).

- **Stack:** Python `==3.12.*` (pinned in `pyproject.toml`), PySide6 6.11 / Qt6 GUI, Nuitka 4.x packaging, [uv](https://docs.astral.sh/uv/) for deps, [just](https://just.systems/) task runner. Targets Windows, macOS, and Linux — no platform-locked code without a guard.
- **Architecture:** pragmatic MVC under `app/` (`views` = PySide6 widgets, `controllers` = glue/logic, `models` = data classes, `services` = reusable operations, `utils` = helpers, `sort` = ordering algorithms, `windows` = top-level dialogs, `cli` = `build-db` etc.). Tests in `tests/` mirror the `app/` layout.

## Setup

- Clone with submodules: `git clone --recurse-submodules https://github.com/RimSort/RimSort`
- If submodules are missing: `git submodule update --init --recursive`
- Prerequisites: git, Python 3.12, [uv](https://docs.astral.sh/uv/), [just](https://just.systems/). Full `just check` also needs Node/npx (jscpd, markdownlint) and shfmt.
- `just dev-setup` — creates venv, `uv sync --locked --dev --group build`, compiles locales. Do this first.
- `just install-hooks` — installs the pre-commit hook (runs `just check` before every commit; requires `just` and `pwsh` on PATH).
- Always use the local venv via `uv run ...` — never activate the venv manually or use a bare `pytest`/`ruff`.
- Claude Code reads `CLAUDE.md`, not `AGENTS.md` — bridge it with `@AGENTS.md` at the top of `CLAUDE.md` or a symlink (Windows symlinks need Developer Mode).

Never run `uv lock --upgrade` (== `just update`) as part of a task — dependency bumps are handled by dependabot.

## Running the App

- `just run` (== `uv run python -m app`)
- Use dev mode so you don't touch real user data: `uv run python -m app --dev` — redirects settings/logs/databases/mod-lists to `dev/` (gitignored) and enables debug logging. Env overrides: `RIMSORT_DEV`, `RIMSORT_DEV_DIR`.

## Testing

- Full suite: `just test` (== `uv run pytest --doctest-modules --no-qt-log -s`)
- Verbose: `just test-verbose`; with coverage: `just test-coverage`
- Single file: `uv run pytest --doctest-modules --no-qt-log tests/views/test_mods_panel_search.py -s`
- Single test: append `-k "name_or_substring"` to the above.
- Never run bare `pytest` — the project's `addopts` manage `--import-mode=importlib`, `pythonpath`, and `testpaths`.
- Qt tests use the `qtbot` fixture (pytest-qt); `qapp`, `mock_app_info`, `fresh_event_bus`, `mock_metadata_controller`, `mock_steamcmd_interface` are defined in `tests/conftest.py`. Tests must never launch real Steam URLs or dialogs — `tests/conftest.py` autouse fixtures block both.
- Add or update tests for any logic you change.

## Code Quality (MUST pass before finishing)

`just check` runs the quality gate (Windows: `typecheck`, `pyright`, `ruff`, `ruff-format`, `jscpd`, `markdownlint`, `shfmt`, `deferred-imports`; Unix adds super-linter, which covers the same plus bash, json, yaml, github-actions, checkov, and gitleaks). `just fix` auto-fixes ruff check/format, shfmt, and markdownlint.

| Command | Purpose |
| --- | --- |
| `just ruff` | Ruff lint check (`ruff check`, config in `pyproject.toml`) |
| `just ruff-format` | Ruff format check (`ruff format --check`) |
| `just ruff-fix` / `just ruff-format-fix` | Ruff lint/format auto-fix (config in `pyproject.toml`) |
| `just typecheck` | mypy against `pyproject.toml` |
| `just pyright` | pyright (standard mode) against `pyproject.toml` |
| `just jscpd` | Copy-paste detection — CI enforces **0% duplication** (config in `.jscpd.json`). If code repeats, extract a shared helper. |
| `just deferred-imports` | Guard against new function-local `from app…` imports (see Traps) |
| `just markdownlint` | Markdown lint for `docs/**` and root `*.md` (rules in `.markdownlint.json`; options in `.markdownlint-cli2.jsonc`) |
| `just shfmt` | Shell script formatting (fails when any script would be reformatted) |

Run at minimum `just fix` + `just test` + `just typecheck` + `just pyright` (or the full `just check`, then `just test`) and get everything green before declaring a change complete. CI runs ruff, ruff-format, mypy, pyright, jscpd, gitleaks, markdownlint, and pytest on ubuntu/macos/windows.

## Code Style

- Ruff (config in `pyproject.toml`): line-length 88, indent 4, `quote-style = "double"`, isort (`I`) enabled; `E402` and `BLE001` are intentionally ignored project-wide — do not re-enable, and do not add project-wide `# noqa` for other rules.
- Type annotations required on all function/method signatures (mypy enforces `disallow_untyped_defs`, `disallow_untyped_calls`, etc.).
- Use modern Python: PEP 604 unions (`str | None`), built-in generics (`list[str]`), `collections.abc` — avoid importing from `typing`. Never `Optional[str]`, never `from typing import ...`.
- Docstrings: Sphinx reST format (Google-style accepted in tests). Example: `def sync(force: bool) -> None: """Run a full sync.\n\n:param force: Ignore caches.\n"""`
- `sys.platform == "win32"`-only code must be platform-guarded; the codebase targets Windows, macOS, and Linux.
- All user-facing strings must go through Qt translations (see i18n below). Log and exception messages stay in English.
- Prefer type-explicit, readable logic over clever one-liners.

## i18n

- Every user-facing string must use `QCoreApplication.translate("ContextName", "English source string")` — the context is normally the class name (e.g. `"ModsPanel"`, `"InstanceService"`). Some modules alias `translate = QCoreApplication.translate`; follow the local convention.
- After adding/changing translatable strings: run `just i18n-update` (runs `pyside6-lupdate` to merge into `locales/*.ts`, source language is `en_US`), then `just i18n-compile` (regenerates `.qm`). As a contributor, commit **both** the `.ts` and `.qm` changes.
- `translation_helper.py` is the CLI tool for translation workflows (check/completeness, validate, auto-translate). Only edit `.ts` files; `.qm` are generated artifacts.
- Preserve `%s`, `{0}`, `\n`, and HTML placeholders exactly in any translated string you touch.
- Do not change translation text of existing strings unless the English source changed.

## Project Layout

- `app/` — application source (Python package).
- `tests/` — pytest suite mirroring `app/`. Fixtures live in `tests/conftest.py`; test data in `tests/data/`.
- `locales/` — Qt `.ts` (source) + `.qm` (compiled) translation files.
- `themes/` — Qt stylesheet themes and default icons.
- `docs/` — Jekyll documentation site source (`development-guide/`, `user-guide/`). Doc pages use Jekyll frontmatter (`title`, `layout: default`, `parent`, `permalink`).
- `packaging/` — release packaging (AppImage, MSI, macOS bundle optimize).
- `todds/` — texture-optimization binary location (runtime only).
- `libs/`, `submodules/` — vendor/extras, see Boundaries.
- `app/utils/github/` — GitHub provider, models, installer, updater; `app/utils/steam/` — Steam integration (`steam/workshop/`, `steam/steamcmd/`).
- `distribute.py` — release build driver; `rimsort.nuitka-package.config.yml` and header comments in `app/__main__.py` hold Nuitka config.

## Git / PR Conventions

- Feature-specific PRs only — one PR = one change. Every PR must reference a corresponding issue (or sub-task).
- Conventional Commits, lowercase prefix: `feat:`, `fix:`, `docs:`, `chore:`, `i18n:`, `build(deps):`, `build(deps-dev):`. Do not include a scope unless it's meaningful (e.g. `build(deps)` for bump PRs).
- Do not submit dependency-bump PRs — dependabot and maintainers handle them.
- Semantic versioning is automated from keywords in commit messages: `(major)` for breaking, `(minor)` for features; the rest are implicit patches. Version only monitors `app/`, `libs/`, `submodules/`, `themes/`.
- Tests + all quality checks must pass and the PR should be ready before requesting review; use a draft otherwise.

## Boundaries

- 🚫 **Never** — edit `submodules/` (vendored: SteamworksPy, steamfiles) or the prebuilt Steamworks binaries in `libs/`; submit dep-bump PRs; commit secrets/API keys (name env variables only), `.venv`, `dev/`, `build/`, `dist/`, `version.xml` (generated, gitignored).
- ⚠️ **Ask first** — changing public/`__init__.py` API signatures, adding a runtime dependency, editing `distribute.py` or Nuitka config, running a release/build/publish workflow, bumping dependencies, or doing large refactors beyond the task.
- ✅ **Always** — use `uv run ...` for everything, add/update tests for changed logic, run the Definition of Done checks below before declaring done.
- Avoid importing Qt-heavy modules at module scope where it creates cycles/startup cost — see `check_deferred_imports.py` (Traps).
- Do not run `just update`, `just build`, or release workflows as part of normal tasks.

## Definition of Done

1. `just fix` + `just typecheck` + `just pyright` + `just deferred-imports` all pass (or full `just check`).
2. `just test` passes (full suite).
3. The diff contains no unrelated reformatting, comments, or scope creep.
4. New translatable strings have been run through `just i18n-update` and `just i18n-compile`. (Note: the i18n rule in the AGENTS.md spec — run these and commit both `.ts`/`.qm`.)

## Traps

- **Deferred imports are judged, not banned:** `check_deferred_imports.py` fails on any *new* function-local `import app…` not in its `ALLOWED` set. Genuine circular-import fixes go in `ALLOWED`; start-up hot-path imports may stay deferred. If you add one, you must update `ALLOWED` or CI (`just deferred-imports`) fails.
- Never reformat code wholesale or add comments explaining what the code does — match surrounding style and only change what your feature touches.
- Don't create new top-level data dirs/files under the repo root; app data goes through `AppInfo` (which tests redirect via `mock_app_info`).
- Keep `docs/` edits lint-clean (markdownlint) and only touch `docs/index.md`/locale variants when truly needed.
