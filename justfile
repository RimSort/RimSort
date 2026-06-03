# ─── Shell Configuration ─────────────────────────────────────────────────
# Unix: just's default (sh -c). Windows: powershell.exe (ships with all
# modern Windows). Multi-line recipes use [unix]/[windows] guards with
# shebang overrides where needed.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# ─── Global Variables ────────────────────────────────────────────────────
# Shared flag values to keep recipes DRY and consistent.
ruff_config := "--config pyproject.toml"
pytest_opts := "--doctest-modules --no-qt-log"

# ─── Default Target (lists all available recipes) ────────────────────────
@default:
    just --list

# ═══════════════════════════════════════════════════════════════════════════
# Core Development
# ═══════════════════════════════════════════════════════════════════════════

# Run the RimSort application
run: dev-setup
    uv run python -m app

# Run tests with doctest modules enabled
test: dev-setup
    uv run pytest {{pytest_opts}} -s

# Run tests with verbose output and short tracebacks
test-verbose: dev-setup
    uv run pytest {{pytest_opts}} -v --tb=short -s

# Run tests with full coverage reports (XML, HTML, and terminal)
test-coverage: dev-setup
    uv run pytest {{pytest_opts}} --junitxml=junit/test-results.xml --cov=app --cov-report=xml --cov-report=html --cov-report=term-missing

# ═══════════════════════════════════════════════════════════════════════════
# Code Quality
# ═══════════════════════════════════════════════════════════════════════════

# Check code for linting issues (ruff check)
ruff:
    uv run ruff check {{ruff_config}} .

# Check code for formatting issues (ruff format)
ruff-format:
    uv run ruff format {{ruff_config}} . --check

# Check and automatically fix linting issues (ruff check --fix)
ruff-fix:
    uv run ruff check {{ruff_config}} . --fix

# Automatically fix formatting issues (ruff format)
ruff-format-fix:
    uv run ruff format {{ruff_config}} .

# Check Markdown documentation for linting issues (markdownlint-cli2)
markdownlint:
    npx markdownlint-cli2@latest

# Fix Markdown documentation issues (markdownlint-cli2 --fix)
markdownlint-fix:
    npx markdownlint-cli2@latest --fix

# Run static type checking (mypy)
typecheck:
    uv run mypy --config-file pyproject.toml .

# Run Pyright type checker on app and tests
pyright:
    uv run pyright -p pyproject.toml .

# Detect copy-paste code duplication (jscpd) — exits with error if any
# clones are found (--threshold 0 means zero tolerance for duplicates).
# Matches the CI's jscpd check configuration.
jscpd:
    npx jscpd@latest app/ tests/ --threshold 0 --ignore 'tests/controllers/settings_tabs/test_*.py'

# Check shell script (.sh) formatting (shfmt) — diff-only, no changes made
shfmt:
    fd -e sh --exclude .venv --exclude submodules -x shfmt -d {}

# Automatically fix shell script formatting issues (shfmt)
shfmt-fix:
    fd -e sh --exclude .venv --exclude submodules -x shfmt -w {}

# Run all code quality checks: ruff + ruff-format + typecheck + pyright + jscpd + shfmt + markdown lint
check: ruff ruff-format typecheck pyright jscpd shfmt markdownlint
    @echo "Use 'just fix' to automatically fix linting and formatting issues!"

# Automatically fix linting and formatting issues (ruff-fix + ruff-format-fix + shfmt -w + markdown fixes)
fix: ruff-fix ruff-format-fix shfmt-fix markdownlint-fix
    @echo "Auto-fixes applied!"

# Run full CI pipeline locally: all quality checks + tests with coverage
ci: check test-coverage
    @echo "CI simulation complete!"

# ═══════════════════════════════════════════════════════════════════════════
# Dependency Management
# ═══════════════════════════════════════════════════════════════════════════

# Install all dependencies (including dev and build groups) after ensuring
# git submodules are initialized.
dev-setup: submodules-init
    uv venv --allow-existing
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
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, *.egg-info, .pytest_cache, .mypy_cache, .ruff_cache, htmlcov, .coverage, coverage.xml, junit
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

# Create source tarball including submodules for RPM building
[linux]
rpm-tarball VERSION='1.0.0':
    #!/usr/bin/env bash
    set -euo pipefail

    # Nuitka requires a 4-part version (e.g. "1.0.0.1"), so auto-append ".1"
    # when only 3 parts are provided.
    PART_COUNT=$(echo "{{VERSION}}" | tr '.' '\n' | wc -l)
    if [ "$PART_COUNT" -eq 3 ]; then
        FULL_VERSION="{{VERSION}}.1"
    else
        FULL_VERSION="{{VERSION}}"
    fi

    TARBALL="$HOME/rpmbuild/SOURCES/rimsort-${FULL_VERSION}.tar.gz"

    echo "Creating source tarball with submodules for version ${FULL_VERSION}..."

    TMPDIR=$(mktemp -d)
    trap 'rm -rf "$TMPDIR"' EXIT

    # Archive main repository
    git archive --prefix="RimSort-${FULL_VERSION}/" HEAD | tar -x -C "$TMPDIR"

    # Archive each git submodule into the correct path under the prefix
    git submodule foreach --quiet \
        "git archive --prefix=\"RimSort-${FULL_VERSION}/\$displaypath/\" HEAD \
         | tar -x -C \"$TMPDIR\""

    # Package everything into a single tarball
    tar -czf "$TARBALL" -C "$TMPDIR" "RimSort-${FULL_VERSION}"

    echo "Tarball created: ${TARBALL}"
    ls -lh "$TARBALL"

# Build RPM package for Fedora/RHEL (e.g. "just build-rpm 1.0.63" or "just build-rpm 1.0.63.1")
# Note: version normalization logic is duplicated from rpm-tarball because
# bash shebang recipes cannot invoke other just recipes.
[linux]
build-rpm VERSION='1.0.0': check (rpm-tarball VERSION)
    #!/usr/bin/env bash
    set -euo pipefail

    # Auto-append ".1" if version has only 3 parts (Nuitka compatibility)
    PART_COUNT=$(echo "{{VERSION}}" | tr '.' '\n' | wc -l)
    if [ "$PART_COUNT" -eq 3 ]; then
        FULL_VERSION="{{VERSION}}.1"
    else
        FULL_VERSION="{{VERSION}}"
    fi

    echo "Setting up RPM build environment..."
    mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

    echo "Building RPM package for version ${FULL_VERSION}..."
    rpmbuild -bb packaging/rpm/rimsort.spec --define "version ${FULL_VERSION}"

    echo "RPM build complete!"
    RPM_FILE=$(find ~/rpmbuild/RPMS/x86_64/ -name "rimsort-${FULL_VERSION}-*.rpm" | head -n 1)
    if [ -n "$RPM_FILE" ]; then
        echo "Built RPM: ${RPM_FILE}"
        ls -lh "$RPM_FILE"
    else
        echo "Warning: Could not find built RPM"
    fi

# Build AppImage from existing Nuitka output (Linux only)
[linux]
build-appimage VERSION='1.0.0':
    bash packaging/appimage/build-appimage.sh build/app.dist "{{VERSION}}"

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
[unix]
i18n-update:
    #!/usr/bin/env bash
    set -euo pipefail
    shopt -s nullglob
    uv run pyside6-lupdate app/ -ts locales/*.ts

[windows]
i18n-update:
    uv run pyside6-lupdate app/ -ts (Get-ChildItem locales/*.ts | ForEach-Object { $_.FullName })

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