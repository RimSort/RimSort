# List all available recipes (default)
@default:
    just --list

# Core Development

# Run the RimSort application
run: dev-setup
    uv run python -m app

# Run tests with coverage reporting to terminal
test: dev-setup
    uv run pytest --doctest-modules -s --no-qt-log

# Run tests with verbose output and short tracebacks
test-verbose: dev-setup
    uv run pytest --doctest-modules -v --tb=short -s --no-qt-log

# Run tests with full coverage reports (XML, HTML, and terminal)
test-coverage: dev-setup
    uv run pytest --doctest-modules --junitxml=junit/test-results.xml --cov=app --cov-report=xml --cov-report=html --cov-report=term-missing --no-qt-log

# Code Quality

# Check code for linting issues
lint:
    uv run ruff check .

# Check and automatically fix linting issues
lint-fix:
    uv run ruff check . --fix

# Check code formatting without making changes
format:
    uv run ruff format . --check

# Format code automatically
format-fix:
    uv run ruff format .

# Run type checking with mypy
typecheck:
    uv run mypy --config-file pyproject.toml .

# Run all code quality checks (lint, format, typecheck)
check: lint format typecheck

# Automatically fix linting and formatting issues
fix: lint-fix format-fix
    @echo "Auto-fixes applied!"

# Run full CI pipeline (all checks + tests with coverage)
ci: check test-coverage
    @echo "CI simulation complete!"

## Dependency Management
# Install all dependencies including dev and build groups
dev-setup: submodules-init
    uv venv --allow-existing
    uv sync --locked --dev --group build

# Update all dependencies to latest compatible versions
update:
    uv lock --upgrade

# Remove all build artifacts, caches, and generated files
clean:
    rm -rf build/ dist/ *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache
    rm -rf htmlcov .coverage coverage.xml
    rm -rf junit/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build/Distribution

# Build RimSort executable
build *ARGS='': submodules-init check
    uv run python distribute.py {{ARGS}}

# Build RimSort executable with specific version (e.g., "1.2.3.4")
build-version VERSION: submodules-init check
    uv run python distribute.py --product-version="{{VERSION}}"

# Create source tarball with submodules for RPM building
rpm-tarball VERSION='1.0.0':
    #!/usr/bin/env bash
    set -euo pipefail

    # Auto-append .1 if version has only 3 parts (for Nuitka compatibility)
    PART_COUNT=$(echo "{{VERSION}}" | tr '.' '\n' | wc -l)
    if [ "$PART_COUNT" -eq 3 ]; then
        FULL_VERSION="{{VERSION}}.1"
    else
        FULL_VERSION="{{VERSION}}"
    fi

    TARBALL="$HOME/rpmbuild/SOURCES/rimsort-$FULL_VERSION.tar.gz"

    echo "Creating source tarball with submodules for version $FULL_VERSION..."

    # Create temporary directory
    TMPDIR=$(mktemp -d)
    trap 'rm -rf "$TMPDIR"' EXIT

    # Archive main repository
    git archive --prefix="RimSort-$FULL_VERSION/" HEAD | tar -x -C "$TMPDIR"

    # Archive submodules
    git submodule foreach --quiet "git archive --prefix=\"RimSort-$FULL_VERSION/\$displaypath/\" HEAD | tar -x -C \"$TMPDIR\""

    # Create the final tarball
    cd "$TMPDIR"
    tar -czf "$TARBALL" "RimSort-$FULL_VERSION"

    echo "Tarball created: $TARBALL"
    ls -lh "$TARBALL"

# Build RPM package for Fedora/RHEL (e.g., just build-rpm 1.0.63 or just build-rpm 1.0.63.1)
build-rpm VERSION='1.0.0': check (rpm-tarball VERSION)
    #!/usr/bin/env bash
    set -euo pipefail

    # Auto-append .1 if version has only 3 parts (for Nuitka compatibility)
    PART_COUNT=$(echo "{{VERSION}}" | tr '.' '\n' | wc -l)
    if [ "$PART_COUNT" -eq 3 ]; then
        FULL_VERSION="{{VERSION}}.1"
    else
        FULL_VERSION="{{VERSION}}"
    fi

    echo "Setting up RPM build environment..."
    mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

    echo "Building RPM package for version $FULL_VERSION..."
    rpmbuild -bb packaging/rpm/rimsort.spec --define "version $FULL_VERSION"

    echo "RPM build complete!"
    RPM_FILE=$(find ~/rpmbuild/RPMS/x86_64/ -name "rimsort-$FULL_VERSION-*.rpm" | head -n 1)
    if [ -n "$RPM_FILE" ]; then
        echo "Built RPM: $RPM_FILE"
        ls -lh "$RPM_FILE"
    else
        echo "Warning: Could not find built RPM"
    fi

# Utilities

# Initialize and update git submodules (run after cloning)
submodules-init:
    #!/usr/bin/env bash
    if git submodule status | grep -q '^-'; then
        echo "Initializing submodules..."
        git submodule update --init --recursive
    else
        echo "Submodules already initialized, skipping"
    fi

# Show help for distribute.py build script
build-help:
    uv run python ./distribute.py --help
