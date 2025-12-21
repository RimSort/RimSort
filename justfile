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
build: submodules-init check
    uv run python distribute.py

# Build RimSort executable with specific version (e.g., "1.2.3.4")
build-version VERSION: submodules-init check
    uv run python distribute.py --product-version="{{VERSION}}"

# Utilities

# Initialize and update git submodules (run after cloning)
submodules-init:
    git submodule update --init --recursive
