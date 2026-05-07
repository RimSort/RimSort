#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_DIST="${1:?Usage: build-appimage.sh <app.dist path> <version>}"
VERSION="${2:?Usage: build-appimage.sh <app.dist path> <version>}"

APP_DIST="$(cd "$APP_DIST" && pwd)"
BUILD_DIR="${REPO_ROOT}/build"
APPDIR="${BUILD_DIR}/RimSort-x86_64.AppDir"
LINUXDEPLOY="${BUILD_DIR}/linuxdeploy-x86_64.AppImage"
OUTPUT="${BUILD_DIR}/RimSort-${VERSION}-x86_64.AppImage"

DESKTOP_FILE="${REPO_ROOT}/data/io.github.rimsort.RimSort.desktop"
ICON_FILE="${REPO_ROOT}/themes/default-icons/AppIcon_a.png"
METAINFO_FILE="${REPO_ROOT}/data/io.github.rimsort.RimSort.metainfo.xml"

echo "=== Building AppImage for RimSort ${VERSION} ==="
echo "  app.dist: ${APP_DIST}"
echo "  AppDir:   ${APPDIR}"

# Validate inputs
if [[ ! -d "$APP_DIST" ]]; then
    echo "ERROR: app.dist directory not found: ${APP_DIST}" >&2
    exit 1
fi

if [[ ! -f "${APP_DIST}/RimSort" ]]; then
    echo "ERROR: RimSort executable not found in ${APP_DIST}" >&2
    exit 1
fi

for f in "$DESKTOP_FILE" "$ICON_FILE" "$METAINFO_FILE"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: Required file not found: $f" >&2
        exit 1
    fi
done

# Clean previous AppDir
rm -rf "$APPDIR" "$OUTPUT"
mkdir -p "$APPDIR"

# Copy entire Nuitka output into usr/bin/ to preserve relative path layout
echo "Copying Nuitka output to AppDir..."
mkdir -p "${APPDIR}/usr/bin"
cp -a "${APP_DIST}/." "${APPDIR}/usr/bin/"

# Install desktop integration files
echo "Installing desktop integration files..."
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${APPDIR}/usr/share/metainfo"

cp "$DESKTOP_FILE" "${APPDIR}/usr/share/applications/"
cp "$ICON_FILE" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/io.github.rimsort.RimSort.png"
cp "$METAINFO_FILE" "${APPDIR}/usr/share/metainfo/"

# Download linuxdeploy if not cached
if [[ ! -f "$LINUXDEPLOY" ]]; then
    echo "Downloading linuxdeploy..."
    curl -fSL -o "$LINUXDEPLOY" \
        "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
    chmod +x "$LINUXDEPLOY"
fi

# Build the AppImage
echo "Running linuxdeploy..."
export LDAI_OUTPUT="$OUTPUT"
export LINUXDEPLOY_OUTPUT_VERSION="$VERSION"

# Use --appimage-extract-and-run to avoid FUSE dependency in CI
APPIMAGE_EXTRACT_AND_RUN=1 "$LINUXDEPLOY" \
    --appdir "$APPDIR" \
    --executable "${APPDIR}/usr/bin/RimSort" \
    --desktop-file "${APPDIR}/usr/share/applications/io.github.rimsort.RimSort.desktop" \
    --icon-file "${APPDIR}/usr/share/icons/hicolor/256x256/apps/io.github.rimsort.RimSort.png" \
    --output appimage

echo "=== AppImage built successfully ==="
ls -lh "$OUTPUT"
