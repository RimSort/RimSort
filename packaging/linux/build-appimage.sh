#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_DIST="${1:?Usage: build-appimage.sh <app.dist path> <version>}"
VERSION="${2:?Usage: build-appimage.sh <app.dist path> <version>}"

APPIMAGETOOL_VERSION="1.9.1"

# Detect architecture from the host or allow override via ARCH env var
ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
x86_64) APPIMAGE_ARCH="x86_64" ;;
aarch64) APPIMAGE_ARCH="aarch64" ;;
armv7l) APPIMAGE_ARCH="armhf" ;;
i686) APPIMAGE_ARCH="i686" ;;
*)
	echo "ERROR: Unsupported architecture: ${ARCH}" >&2
	exit 1
	;;
esac

APP_DIST="$(cd "$APP_DIST" && pwd)"
BUILD_DIR="${REPO_ROOT}/build"
APPDIR="${BUILD_DIR}/RimSort-${APPIMAGE_ARCH}.AppDir"
APPIMAGETOOL="${BUILD_DIR}/appimagetool-${APPIMAGE_ARCH}.AppImage"
OUTPUT="${BUILD_DIR}/RimSort-${VERSION}-${APPIMAGE_ARCH}.AppImage"

DESKTOP_FILE="${REPO_ROOT}/data/io.github.rimsort.RimSort.desktop"
ICON_FILE="${REPO_ROOT}/themes/default-icons/RimSort_Icon_64x64.svg"
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

# Copy entire Nuitka output into usr/share/RimSort/ to preserve relative path
# layout. Nuitka standalone mode places the executable alongside its bundled
# .so files and expects them to remain as siblings.
echo "Copying Nuitka output to AppDir..."
mkdir -p "${APPDIR}/usr/share/RimSort"
cp -a "${APP_DIST}/." "${APPDIR}/usr/share/RimSort/"

# Create usr/bin symlink pointing to the actual binary
mkdir -p "${APPDIR}/usr/bin"
ln -rs "${APPDIR}/usr/share/RimSort/RimSort" "${APPDIR}/usr/bin/RimSort"

# Install desktop integration files
echo "Installing desktop integration files..."
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${APPDIR}/usr/share/metainfo"

cp "$DESKTOP_FILE" "${APPDIR}/usr/share/applications/"
cp "$ICON_FILE" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/io.github.rimsort.RimSort.svg"
cp "$METAINFO_FILE" "${APPDIR}/usr/share/metainfo/"

# Include update script for self-update support
echo "Including update script..."
cp "${REPO_ROOT}/update.sh" "${APPDIR}/usr/share/RimSort/"

# Create AppRun entry point — a wrapper that sets cwd to the AppDir root and
# execs the Nuitka binary. We use a custom AppRun instead of linuxdeploy's
# --executable flag to avoid patchelf rewriting Nuitka's RPATH layout.
cat >"${APPDIR}/AppRun" <<'APPRUN_EOF'
#!/usr/bin/env bash
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="${SELF%/*}"
cd "$HERE"
exec "${HERE}/usr/share/RimSort/RimSort" "$@"
APPRUN_EOF
chmod +x "${APPDIR}/AppRun"

# Symlink desktop file and icon to AppDir root (required by AppImage spec)
ln -sf usr/share/applications/io.github.rimsort.RimSort.desktop "${APPDIR}/io.github.rimsort.RimSort.desktop"
ln -sf usr/share/icons/hicolor/scalable/apps/io.github.rimsort.RimSort.svg "${APPDIR}/io.github.rimsort.RimSort.svg"
# .DirIcon must be PNG per AppImage spec (some file managers don't render SVG)
cp "${REPO_ROOT}/themes/default-icons/AppIcon_a.png" "${APPDIR}/.DirIcon"

# Download appimagetool if not present
if [[ ! -f "$APPIMAGETOOL" ]]; then
	echo "Downloading appimagetool ${APPIMAGETOOL_VERSION} (${APPIMAGE_ARCH})..."
	curl -fSL -o "$APPIMAGETOOL" \
		"https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-${APPIMAGE_ARCH}.AppImage"
	chmod +x "$APPIMAGETOOL"
fi

# Determine how to run appimagetool.
# Try direct execution first (with FUSE bypass), fall back to extracting if
# that fails (e.g. inside Docker containers where even extract-and-run can
# fail on older appimagetool builds).
APPIMAGETOOL_CMD="$APPIMAGETOOL"
export APPIMAGE_EXTRACT_AND_RUN=1

if ! "$APPIMAGETOOL_CMD" --version &>/dev/null; then
	echo "Direct execution failed, extracting appimagetool..."
	if ! (cd "$BUILD_DIR" && "$APPIMAGETOOL" --appimage-extract); then
		echo "WARNING: --appimage-extract returned non-zero" >&2
	fi
	APPIMAGETOOL_CMD="${BUILD_DIR}/squashfs-root/AppRun"
	if [[ ! -f "$APPIMAGETOOL_CMD" ]]; then
		echo "ERROR: Failed to extract appimagetool" >&2
		exit 1
	fi
fi

# Remove .ts translation source files — only compiled .qm files are needed at runtime
echo "Removing .ts locale source files..."
find "${APPDIR}" -name "*.ts" -type f | while read -r ts_file; do
	qm_file="${ts_file%.ts}.qm"
	if [[ -f "$qm_file" ]]; then
		rm -f "$ts_file"
	fi
done

# Build the AppImage using appimagetool directly.
# We skip linuxdeploy because Nuitka already bundles all dependencies —
# linuxdeploy's --executable flag would run patchelf and corrupt Nuitka's RPATHs.
echo "Running appimagetool..."
export VERSION
ARCH="$APPIMAGE_ARCH" "$APPIMAGETOOL_CMD" \
	--mksquashfs-opt -Xcompression-level --mksquashfs-opt 19 \
	"$APPDIR" "$OUTPUT"

echo "=== AppImage built successfully ==="
ls -lh "$OUTPUT"
