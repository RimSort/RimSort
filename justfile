# ─── Shell Configuration ─────────────────────────────────────────────────
# Unix: just's default (sh -c). Windows: powershell.exe (ships with all
# modern Windows). Multi-line recipes use [unix]/[windows] guards with
# shebang overrides where needed.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# ─── Global Variables ────────────────────────────────────────────────────
# Shared flag values to keep recipes DRY and consistent.
ruff_config := "--config pyproject.toml"
pytest_opts := "--doctest-modules --no-qt-log"
cov_opts := "--junitxml=junit/test-results.xml --cov=app --cov-report=xml --cov-report=html --cov-report=term-missing"

# ─── Default Target (lists all available recipes) ────────────────────────
@default:
    just --list

# ═══════════════════════════════════════════════════════════════════════════
# Core Development
# ═══════════════════════════════════════════════════════════════════════════

# Run the RimSort application
run: dev-setup
    uv run python -m app

# Run tests with doctest modules enabled and output capture disabled
test: dev-setup
    uv run pytest {{pytest_opts}} -s

# Run tests with verbose output and short tracebacks
test-verbose: dev-setup
    uv run pytest {{pytest_opts}} -v --tb=short -s

# Run tests with full coverage reports (XML, HTML, and terminal)
test-coverage: dev-setup
    uv run pytest {{pytest_opts}} {{cov_opts}}

# ═══════════════════════════════════════════════════════════════════════════
# Code Quality
# ═══════════════════════════════════════════════════════════════════════════

# Flake gate: the pinned git-hooks (ruff, ruff-format, mypy, pyright, shellcheck,
# shfmt, markdownlint, jscpd, gitleaks, actionlint, check-json, check-yaml,
# checkov, nixfmt, deadnix, statix, repo guards) plus pytest and the packaged
# app build. This is exactly what the Nix Flake Check CI job runs; the tools
# are pinned by uv.lock (via uv2nix) and nixpkgs instead of a container image.
# Contributors without Nix keep the per-tool recipes and rely on CI.
[unix]
nix-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v nix >/dev/null 2>&1; then
        echo "warning: nix not found; skipping 'nix flake check' (CI runs it as the authoritative gate)" >&2
        exit 0
    fi
    nix flake check

# Run static type checking (mypy)
typecheck:
    uv run mypy --config-file pyproject.toml .

# Run Pyright type checker on app and tests
pyright:
    uv run python -m pyright -p pyproject.toml .

# Run ruff lint checks (ruff check)
ruff:
    uv run ruff check {{ruff_config}} .

# Check code for formatting issues (ruff format --check)
ruff-format:
    uv run ruff format {{ruff_config}} --check .

# Check and automatically fix linting issues (ruff check --fix)
ruff-fix:
    uv run ruff check {{ruff_config}} . --fix

# Automatically fix formatting issues (ruff format)
ruff-format-fix:
    uv run ruff format {{ruff_config}} .

# Check Markdown documentation for issues (markdownlint-cli2)
markdownlint:
    npx --yes markdownlint-cli2@0.23.2

# Fix Markdown documentation issues (markdownlint-cli2 --fix)
markdownlint-fix:
    npx --yes markdownlint-cli2@0.23.2 --fix

# Check shell script formatting (shfmt, fails on any differences)
[unix]
shfmt:
    #!/usr/bin/env bash
    set -euo pipefail
    mapfile -t sh_files < <(fd -e sh --exclude .venv --exclude submodules)
    if [ ${#sh_files[@]} -eq 0 ]; then
        echo "shfmt: no shell scripts found"
        exit 0
    fi
    # shfmt -l prints files whose formatting differs and exits 1 if any exist
    shfmt -l "${sh_files[@]}"

[windows]
shfmt:
    $env:PATH = "$env:PATH;$env:LOCALAPPDATA\RimSortTools"; $files = @(fd -e sh --exclude .venv --exclude submodules); if ($files.Count -eq 0) { Write-Output "shfmt: no shell scripts found" } else { shfmt -l $files; if ($LASTEXITCODE -ne 0) { exit 1 } }

# Automatically fix shell script formatting issues (shfmt)
[unix]
shfmt-fix:
    fd -e sh --exclude .venv --exclude submodules -X shfmt -w

[windows]
shfmt-fix:
    $env:PATH = "$env:PATH;$env:LOCALAPPDATA\RimSortTools"; fd -e sh --exclude .venv --exclude submodules -X shfmt -w

# Run copy/paste detection (jscpd) using the project's .jscpd.json config
jscpd:
    npx --yes jscpd@5.3.0 . --config .jscpd.json

# Run all code quality checks: nix flake check + typecheck + pyright + repo guards
[unix]
check: nix-check typecheck pyright deferred-imports eventbus-subscribers
    @echo "Use 'just fix' to automatically fix linting and formatting issues!"

# Run all code quality checks available on Windows: typecheck + pyright + ruff + ruff-format + jscpd + markdownlint + shfmt + repo guards
[windows]
check: typecheck pyright ruff ruff-format jscpd markdownlint shfmt deferred-imports eventbus-subscribers
    @echo "Use 'just fix' to automatically fix linting and formatting issues!"

# Check for new function-local from app/ imports (circular-import regression guard)
deferred-imports:
    uv run python check_deferred_imports.py

# Check that EventBus subscribers are Qt objects or explicitly retained
# (an unretained plain-class subscriber is garbage collected and goes silent)
eventbus-subscribers:
    uv run python check_eventbus_subscribers.py

# Automatically fix linting and formatting issues, then verify the markdown check passes
# (ruff-fix + ruff-format-fix + shfmt -w + markdownlint-fix + markdownlint check)
fix: ruff-fix ruff-format-fix shfmt-fix markdownlint-fix markdownlint
    @echo "Auto-fixes applied!"

# Run full CI pipeline locally: all quality checks + tests with coverage
ci: check test-coverage
    @echo "CI simulation complete!"

# ═══════════════════════════════════════════════════════════════════════════
# Dependency Management
# ═══════════════════════════════════════════════════════════════════════════

# Install all dependencies (including dev and build groups) after ensuring
# git submodules are initialized. `uv sync` creates/reuses `.venv` itself:
# a fresh one if missing, or the existing one without rewriting `python.exe`,
# which avoids failing when that file is locked by another process (os error 32).
# In the Nix dev shell (RIMSORT_NIX_SHELL) the environment is built from
# uv.lock by Nix and is read-only, so the sync step is skipped there.
[unix]
dev-setup: submodules-init
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${RIMSORT_NIX_SHELL:-}" ]; then
        uv sync --locked --dev --group build
    fi
    just i18n-compile  # not a dependency — must run after uv sync so pyside6-lrelease is available

[windows]
dev-setup: submodules-init
    uv sync --locked --dev --group build
    just i18n-compile  # not a dependency — must run after uv sync so pyside6-lrelease is available

# Update all dependencies to their latest compatible versions
update:
    uv lock --upgrade

# Remove all build artifacts, caches, and generated files
[unix]
clean:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -rf build/ dist/ *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache
    rm -rf htmlcov .coverage coverage.xml
    rm -rf junit/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

[windows]
clean:
    Get-ChildItem -Force | Where-Object { $_.Name -in @("build", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov", ".coverage", "coverage.xml", "junit") -or $_.Name -like "*.egg-info" } | Remove-Item -Recurse -Force
    Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# ═══════════════════════════════════════════════════════════════════════════
# Build / Distribution
# ═══════════════════════════════════════════════════════════════════════════

# Build RimSort executable (inits submodules and runs all checks first)
build *ARGS='': submodules-init check i18n-compile
    uv run python distribute.py {{ARGS}}

# Build RimSort executable with a specific version string, e.g. "1.2.3.4"
# (inits submodules and runs all checks first)
build-version VERSION: submodules-init check i18n-compile
    uv run python distribute.py --product-version="{{VERSION}}"

# Build AppImage from existing Nuitka output (Linux only)
[linux]
build-appimage VERSION='1.0.0':
    bash packaging/linux/build-appimage.sh build/app.dist "{{VERSION}}"

# ═══════════════════════════════════════════════════════════════════════════
# Internationalization
# ═══════════════════════════════════════════════════════════════════════════

# Compile translation .ts files into .qm binary files (required for app to load translations)
[unix]
i18n-compile:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    rm -f locales/*.qm
    for ts_file in locales/*.ts; do
        qm_file="${ts_file%.ts}.qm"
        uv run pyside6-lrelease "$ts_file" -qm "$qm_file"
    done

[windows]
i18n-compile:
    Remove-Item -Force -ErrorAction SilentlyContinue locales/*.qm; Get-ChildItem locales/*.ts | ForEach-Object { uv run pyside6-lrelease $_.FullName -qm ($_.FullName -replace '\.ts$', '.qm') }

# Extract translatable strings from source code into .ts files (for translators)
# -extensions py is required: lupdate's directory scan does not include .py
# in its default extension list, so without it every entry is marked obsolete
[unix]
i18n-update:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    uv run pyside6-lupdate -extensions py app/ -ts locales/*.ts

[windows]
i18n-update:
    uv run pyside6-lupdate -extensions py app/ -ts (Get-ChildItem locales/*.ts | ForEach-Object { $_.FullName })

# ═══════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════

# Install shared git hooks (pre-commit quality gate)
install-hooks:
    git config core.hooksPath .githooks
    @echo "Git hooks installed — commits will run 'just check' automatically."

# Initialize and update git submodules (required after the first clone)
submodules-init:
    git submodule update --init --recursive

# Show help for distribute.py build script
build-help:
    uv run python ./distribute.py --help
