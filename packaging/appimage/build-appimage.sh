#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_DIST="${1:?Usage: build-appimage.sh <app.dist path> <version>}"
VERSION="${2:?Usage: build-appimage.sh <app.dist path> <version>}"

# Detect architecture from the host or allow override via ARCH env var
ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
    x86_64)  APPIMAGE_ARCH="x86_64" ;;
    aarch64) APPIMAGE_ARCH="aarch64" ;;
    armv7l)  APPIMAGE_ARCH="armhf" ;;
    i686)    APPIMAGE_ARCH="i686" ;;
    *)
        echo "ERROR: Unsupported architecture: ${ARCH}" >&2
        exit 1
        ;;
esac

APP_DIST="$(cd "$APP_DIST" && pwd)"
BUILD_DIR="${REPO_ROOT}/build"
APPDIR="${BUILD_DIR}/RimSort-${APPIMAGE_ARCH}.AppDir"
APPIMAGETOOL="${BUILD_DIR}/appimagetool-${APPIMAGE_ARCH}.AppImage"
APPIMAGETOOL_EXTRACTED="${BUILD_DIR}/appimagetool-extracted/AppRun"
OUTPUT="${BUILD_DIR}/RimSort-${VERSION}-${APPIMAGE_ARCH}.AppImage"

DESKTOP_FILE="${REPO_ROOT}/data/io.github.rimsort.RimSort.desktop"
ICON_FILE="${REPO_ROOT}/themes/default-icons/AppIcon_a.png"
METAINFO_FILE="${REPO_ROOT}/data/io.github.rimsort.RimSort.metainfo.xml"

echo "=== Building AppImage for RimSort ${VERSION} (${APPIMAGE_ARCH}) ==="
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

# Copy entire Nuitka output into usr/bin/ to preserve relative path layout.
# Nuitka standalone mode places the executable alongside its bundled .so files
# and expects them to remain as siblings — do NOT split into usr/bin and usr/lib.
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

# Create AppRun entry point — a simple wrapper that execs the Nuitka binary.
# We use a custom AppRun instead of linuxdeploy's --executable flag to avoid
# patchelf rewriting Nuitka's RPATH layout.
cat > "${APPDIR}/AppRun" << 'APPRUN_EOF'
#!/usr/bin/env bash
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="${SELF%/*}"
exec "${HERE}/usr/bin/RimSort" "$@"
APPRUN_EOF
chmod +x "${APPDIR}/AppRun"

# Symlink desktop file and icon to AppDir root (required by AppImage spec)
ln -sf usr/share/applications/io.github.rimsort.RimSort.desktop "${APPDIR}/io.github.rimsort.RimSort.desktop"
ln -sf usr/share/icons/hicolor/256x256/apps/io.github.rimsort.RimSort.png "${APPDIR}/io.github.rimsort.RimSort.png"
ln -sf io.github.rimsort.RimSort.png "${APPDIR}/.DirIcon"

# Download appimagetool if not present (either as AppImage or pre-extracted)
if [[ ! -f "$APPIMAGETOOL_EXTRACTED" && ! -f "$APPIMAGETOOL" ]]; then
    echo "Downloading appimagetool (${APPIMAGE_ARCH})..."
    curl -fSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Determine how to run appimagetool:
# 1. If pre-extracted (e.g. in environments where AppImage execution is problematic), use that
# 2. Otherwise use APPIMAGE_EXTRACT_AND_RUN=1 to avoid FUSE dependency
if [[ -f "$APPIMAGETOOL_EXTRACTED" ]]; then
    APPIMAGETOOL_CMD="$APPIMAGETOOL_EXTRACTED"
else
    APPIMAGETOOL_CMD="$APPIMAGETOOL"
    export APPIMAGE_EXTRACT_AND_RUN=1
fi

# Build the AppImage using appimagetool directly.
# We skip linuxdeploy because Nuitka already bundles all dependencies —
# linuxdeploy's --executable flag would run patchelf and corrupt Nuitka's RPATHs.
echo "Running appimagetool..."
export VERSION="$VERSION"
ARCH="$APPIMAGE_ARCH" "$APPIMAGETOOL_CMD" "$APPDIR" "$OUTPUT"

echo "=== AppImage built successfully ==="
ls -lh "$OUTPUT"
