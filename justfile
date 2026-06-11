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

# Container image for super-linter (matches CI version)
superlinter_image := "ghcr.io/super-linter/super-linter:slim-v8.6.0"

# Run super-linter locally via container (ruff, ruff-format, jscpd, bash,
# json, yaml, checkov, gitleaks). Mypy/Pyright run natively because they
# need the local venv to resolve imports.
[unix]
super-lint:
    #!/usr/bin/env bash
    set -euo pipefail
    # Detect container runtime
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        RUNTIME=docker
    elif command -v podman &>/dev/null && podman info &>/dev/null 2>&1; then
        RUNTIME=podman
    else
        echo "Error: docker or podman required but neither is running" >&2
        exit 1
    fi
    PLATFORM_FLAG=""
    if [ "$(uname -m)" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; then
        PLATFORM_FLAG="--platform linux/amd64"
    fi
    # Mount the git common dir for worktree support
    GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
    $RUNTIME run --rm $PLATFORM_FLAG \
        -e RUN_LOCAL=true \
        -e DEFAULT_BRANCH=main \
        -e LOG_LEVEL=NOTICE \
        -e LINTER_RULES_PATH=. \
        -e VALIDATE_PYTHON_RUFF=true \
        -e VALIDATE_PYTHON_RUFF_FORMAT=true \
        -e VALIDATE_BASH=true \
        -e VALIDATE_JSCPD=true \
        -e VALIDATE_JSON=true \
        -e VALIDATE_YAML=true \
        -e VALIDATE_CHECKOV=true \
        -e VALIDATE_GITLEAKS=true \
        -e PYTHON_RUFF_CONFIG_FILE=pyproject.toml \
        -e PYTHON_RUFF_FORMAT_CONFIG_FILE=pyproject.toml \
        -e FILTER_REGEX_EXCLUDE="LICENSE.md|super-linter-output/|github_conf/" \
        -e IGNORE_GITIGNORED_FILES=true \
        -v "$(pwd)":/tmp/lint \
        -v "${GIT_COMMON_DIR}:${GIT_COMMON_DIR}" \
        {{superlinter_image}}

# Run static type checking (mypy)
typecheck:
    uv run mypy --config-file pyproject.toml .

# Run Pyright type checker on app and tests
pyright:
    uv run python -m pyright -p pyproject.toml .

# Check and automatically fix linting issues (ruff check --fix)
ruff-fix:
    uv run ruff check {{ruff_config}} . --fix

# Automatically fix formatting issues (ruff format)
ruff-format-fix:
    uv run ruff format {{ruff_config}} .

# Fix Markdown documentation issues (markdownlint-cli2 --fix)
markdownlint-fix:
    npx markdownlint-cli2@latest --fix

# Automatically fix shell script formatting issues (shfmt)
shfmt-fix:
    fd -e sh --exclude .venv --exclude submodules -x shfmt -w {}

# Run all code quality checks: super-linter + typecheck + pyright
[unix]
check: super-lint typecheck pyright
    @echo "Use 'just fix' to automatically fix linting and formatting issues!"

# Run all code quality checks available on Windows: typecheck + pyright
[windows]
check: typecheck pyright
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