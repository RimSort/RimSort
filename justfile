# List all available recipes (default)
@default:
    just --list

# Core Development

# Run the RimSort application
run *ARGS='': dev-setup
    uv run python -m app {{ARGS}}

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

# SteamworksPy Build

# Cross-compile SteamworksPy Windows DLL using MinGW-w64 on Linux
build-steamworkspy-windows: submodules-init
    #!/usr/bin/env bash
    set -euo pipefail

    STEAMWORKSPY_PATH="submodules/SteamworksPy/library"
    SDK_PATH="${STEAMWORKSPY_PATH}/sdk"
    SDK_URL="https://github.com/oceancabbage/RimSort/raw/steamworks-sdk/steamworks_sdk_155.zip"

    # Check platform
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        echo "Error: This recipe requires Linux with MinGW-w64"
        echo "On macOS/Windows, use native Windows build tools instead"
        exit 1
    fi

    # Check MinGW-w64 is installed
    if ! command -v x86_64-w64-mingw32-g++ &> /dev/null; then
        echo "Error: MinGW-w64 cross-compiler not found"
        echo ""
        echo "Install with:"
        echo "  Fedora: sudo dnf install mingw64-gcc mingw64-gcc-c++ mingw64-winpthreads-static"
        echo "  Ubuntu/Debian: sudo apt install mingw-w64"
        exit 1
    fi

    echo "Building SteamworksPy64.dll for Windows using MinGW-w64 cross-compiler..."

    # Download SDK if not present
    if [ ! -d "$SDK_PATH" ]; then
        echo "Downloading Steamworks SDK v155..."
        curl -L "$SDK_URL" -o /tmp/steamworks_sdk.zip
        echo "Extracting Steamworks SDK..."
        unzip -q /tmp/steamworks_sdk.zip -d "$STEAMWORKSPY_PATH"
        rm /tmp/steamworks_sdk.zip
    else
        echo "Steamworks SDK already present at $SDK_PATH"
    fi

    # Verify SDK structure
    if [ ! -f "$SDK_PATH/public/steam/steam_api.h" ]; then
        echo "ERROR: SDK headers not found at expected location"
        exit 1
    fi

    if [ ! -f "$SDK_PATH/redistributable_bin/win64/steam_api64.lib" ]; then
        echo "ERROR: steam_api64.lib not found at expected location"
        exit 1
    fi

    # Cross-compile
    echo "Cross-compiling SteamworksPy64.dll..."
    cd "$STEAMWORKSPY_PATH"

    # Create temporary source with Unix-style includes and cstdint
    echo "Creating temporary source file with Unix-style includes..."
    sed -e 's|#include "sdk\\steam\\steam_api.h"|#include <cstdint>\n#include "sdk/steam/steam_api.h"|g' \
        SteamworksPy.cpp > SteamworksPy_cross.cpp

    x86_64-w64-mingw32-g++ \
        -std=c++11 \
        -shared \
        -o SteamworksPy64.dll \
        SteamworksPy_cross.cpp \
        -I./sdk/public \
        -L./sdk/redistributable_bin/win64 \
        -lsteam_api64 \
        -static-libgcc \
        -static-libstdc++ \
        -Wl,--subsystem,windows

    # Clean up temporary file
    rm -f SteamworksPy_cross.cpp

    if [ ! -f "SteamworksPy64.dll" ]; then
        echo "ERROR: Build failed - SteamworksPy64.dll not created"
        exit 1
    fi

    # Copy to libs
    cd -
    echo "Copying SteamworksPy64.dll to libs/..."
    mkdir -p libs
    cp "${STEAMWORKSPY_PATH}/SteamworksPy64.dll" libs/

    echo ""
    echo "✓ Windows DLL built successfully via cross-compilation"
    echo "  Output: libs/SteamworksPy64.dll"
    echo ""
    echo "Verify the binary:"
    echo "  file libs/SteamworksPy64.dll"
    echo "  ls -lh libs/SteamworksPy64.dll"

# Build SteamworksPy library from source for the current platform
build-steamworkspy: submodules-init
    #!/usr/bin/env bash
    set -euo pipefail

    STEAMWORKSPY_DIR="submodules/SteamworksPy/library"

    echo "Building SteamworksPy from source..."

    # Detect platform
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        PLATFORM="linux"
        STEAM_API="libsteam_api.so"
        PROCESSOR=$(uname -m)
        OUTPUT_LIB="SteamworksPy_${PROCESSOR}.so"
        SYMLINK_NAME="SteamworksPy.so"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        PLATFORM="darwin"
        STEAM_API="libsteam_api.dylib"
    else
        echo "Error: Unsupported platform: $OSTYPE"
        echo "This recipe currently supports Linux and macOS only."
        exit 1
    fi

    # Check if SDK headers exist
    if [ ! -f "$STEAMWORKSPY_DIR/sdk/steam/steam_api.h" ]; then
        echo "Error: Steamworks SDK headers not found in $STEAMWORKSPY_DIR/sdk/"
        echo ""
        echo "The Steamworks SDK must be vendored in the repository."
        echo "Download it from: https://partner.steamgames.com/downloads/steamworks_sdk.zip"
        echo "Then extract to: $STEAMWORKSPY_DIR/"
        echo ""
        echo "After extraction, run: mkdir -p $STEAMWORKSPY_DIR/sdk/steam && cp -r $STEAMWORKSPY_DIR/sdk/public/steam/* $STEAMWORKSPY_DIR/sdk/steam/"
        exit 1
    fi

    # Check if libsteam_api exists in library directory
    if [ ! -f "$STEAMWORKSPY_DIR/$STEAM_API" ]; then
        echo "Error: $STEAM_API not found in $STEAMWORKSPY_DIR"
        echo "The library should be present in the Steamworks SDK under sdk/redistributable_bin/"
        exit 1
    fi

    # Platform-specific compilation
    if [[ "$PLATFORM" == "linux" ]]; then
        echo "Detected platform: Linux ($PROCESSOR)"
        echo "Compiling SteamworksPy for Linux..."
        cd "$STEAMWORKSPY_DIR"
        g++ -std=c++11 -o "$OUTPUT_LIB" -shared -fPIC SteamworksPy.cpp -l steam_api -L.

        if [ ! -f "$OUTPUT_LIB" ]; then
            echo "Error: Compilation failed - $OUTPUT_LIB not found"
            exit 1
        fi

        echo "Compilation successful: $OUTPUT_LIB"

        # Return to project root
        cd ../../..

        # Copy to libs/
        echo "Copying $OUTPUT_LIB to libs/..."
        mkdir -p libs
        cp "$STEAMWORKSPY_DIR/$OUTPUT_LIB" "libs/"

        # Create symlink in libs/
        cd libs
        ln -sf "$OUTPUT_LIB" "$SYMLINK_NAME"
        echo "Created symlink: libs/$SYMLINK_NAME -> $OUTPUT_LIB"
        cd ..

        # Copy to project root for SteamworksPy v2.0+ compatibility
        echo "Copying libraries to project root..."
        cp "libs/$OUTPUT_LIB" "$SYMLINK_NAME"
        cp "libs/$STEAM_API" "$STEAM_API"

        echo ""
        echo "✓ SteamworksPy build complete!"
        echo "  - libs/$OUTPUT_LIB"
        echo "  - libs/$SYMLINK_NAME -> $OUTPUT_LIB"
        echo "  - $SYMLINK_NAME (project root)"
        echo "  - $STEAM_API (project root)"

    elif [[ "$PLATFORM" == "darwin" ]]; then
        HOST_ARCH=$(uname -m)
        echo "Detected platform: macOS ($HOST_ARCH)"

        cd "$STEAMWORKSPY_DIR"

        if [[ "$HOST_ARCH" == "arm64" ]]; then
            echo "Building for both ARM64 and x86_64 on Apple Silicon..."

            # Build ARM64 version natively
            echo "  Building ARM64..."
            g++ -std=c++11 -o SteamworksPy_arm.dylib -shared -fPIC SteamworksPy.cpp -l steam_api -L.
            if [ ! -f "SteamworksPy_arm.dylib" ]; then
                echo "Error: ARM64 build failed"
                exit 1
            fi

            # Build x86_64 version using Rosetta
            echo "  Building x86_64 (via Rosetta)..."
            arch -x86_64 /bin/bash -c "cd \"$STEAMWORKSPY_DIR\" && g++ -std=c++11 -o SteamworksPy_i386.dylib -shared -fPIC SteamworksPy.cpp -l steam_api -L."
            if [ ! -f "SteamworksPy_i386.dylib" ]; then
                echo "Error: x86_64 build failed"
                exit 1
            fi

            # Create universal binary
            echo "  Creating universal binary..."
            lipo -create SteamworksPy_arm.dylib SteamworksPy_i386.dylib -output SteamworksPy.dylib
            if [ ! -f "SteamworksPy.dylib" ]; then
                echo "Error: Failed to create universal binary"
                exit 1
            fi

            # Verify it contains both architectures
            echo "  Verifying universal binary..."
            lipo -info SteamworksPy.dylib

            # Return to project root
            cd ../../..

            # Copy all three files to libs/
            echo "Copying libraries to libs/..."
            mkdir -p libs
            cp "$STEAMWORKSPY_DIR/SteamworksPy_arm.dylib" "libs/"
            cp "$STEAMWORKSPY_DIR/SteamworksPy_i386.dylib" "libs/"
            cp "$STEAMWORKSPY_DIR/SteamworksPy.dylib" "libs/"

            # Copy to project root for SteamworksPy v2.0+ compatibility
            echo "Copying libraries to project root..."
            cp "libs/SteamworksPy.dylib" "SteamworksPy.dylib"
            cp "$STEAMWORKSPY_DIR/$STEAM_API" "$STEAM_API"

            echo ""
            echo "✓ SteamworksPy build complete!"
            echo "  - libs/SteamworksPy_arm.dylib (ARM64)"
            echo "  - libs/SteamworksPy_i386.dylib (x86_64)"
            echo "  - libs/SteamworksPy.dylib (universal binary)"
            echo "  - SteamworksPy.dylib (project root)"
            echo "  - $STEAM_API (project root)"

        else
            # Intel Mac - build x86_64 only
            echo "Building for x86_64 only on Intel Mac..."

            g++ -std=c++11 -o SteamworksPy_i386.dylib -shared -fPIC SteamworksPy.cpp -l steam_api -L.
            if [ ! -f "SteamworksPy_i386.dylib" ]; then
                echo "Error: x86_64 build failed"
                exit 1
            fi

            echo "Compilation successful: SteamworksPy_i386.dylib"

            # Return to project root
            cd ../../..

            # Copy library to libs/
            echo "Copying SteamworksPy_i386.dylib to libs/..."
            mkdir -p libs
            cp "$STEAMWORKSPY_DIR/SteamworksPy_i386.dylib" "libs/"

            # Create symlink for generic name
            cd libs
            ln -sf SteamworksPy_i386.dylib SteamworksPy.dylib
            echo "Created symlink: libs/SteamworksPy.dylib -> SteamworksPy_i386.dylib"
            cd ..

            # Copy to project root for SteamworksPy v2.0+ compatibility
            echo "Copying libraries to project root..."
            cp "libs/SteamworksPy.dylib" "SteamworksPy.dylib"
            cp "$STEAMWORKSPY_DIR/$STEAM_API" "$STEAM_API"

            echo ""
            echo "✓ SteamworksPy build complete!"
            echo "  - libs/SteamworksPy_i386.dylib (x86_64)"
            echo "  - libs/SteamworksPy.dylib -> SteamworksPy_i386.dylib"
            echo "  - SteamworksPy.dylib (project root)"
            echo "  - $STEAM_API (project root)"
        fi
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
