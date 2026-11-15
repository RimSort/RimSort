#!/bin/bash

# ========================================================================
# RimSort Update Script for macOS and Linux
# This script safely updates RimSort by replacing the current installation
# with files from a temporary directory.
# Usage: update.sh <temp_update_path> [log_path] [install_dir]
# On macOS, install_dir must be the original application bundle.
# ========================================================================

set -euo pipefail # Exit on error, undefined variables, and pipe failures

# Dry-run mode
DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
	DRY_RUN=true
	echo "DRY RUN MODE: No actual changes will be made"
	shift
fi

# Required temp update path (first argument)
if [ -z "${1:-}" ]; then
	echo "ERROR: Temp update path is required as first argument"
	exit 1
fi
TEMP_UPDATE_PATH="$1"

# Optional logging to file (second argument)
if [ -n "${2:-}" ]; then
	LOG_PATH="$2"
	exec > >(tee -a "$LOG_PATH") 2>&1
fi

# Function to verify SHA256 checksum
verify_checksum() {
	local file_path="$1"
	local checksum_file="$2"

	if [ ! -f "$checksum_file" ]; then
		log_warning "Checksum file not found: $checksum_file"
		return 0
	fi

	# Try sha256sum first, then shasum as fallback
	local checksum_cmd=""
	if command -v sha256sum >/dev/null 2>&1; then
		checksum_cmd="sha256sum"
	elif command -v shasum >/dev/null 2>&1; then
		checksum_cmd="shasum -a 256"
	else
		log_warning "Neither sha256sum nor shasum available, skipping checksum verification"
		return 0
	fi

	log_info "Verifying SHA256 checksum for $file_path"
	if $DRY_RUN; then
		log_info "DRY RUN: Would verify checksum"
		return 0
	fi

	local expected_checksum
	expected_checksum=$(cat "$checksum_file" | tr -d '\n\r')
	local actual_checksum
	actual_checksum=$($checksum_cmd "$file_path" | awk '{print $1}')

	if [ "$actual_checksum" != "$expected_checksum" ]; then
		log_error "Checksum verification failed for $file_path"
		log_error "Expected: $expected_checksum"
		log_error "Actual: $actual_checksum"
		return 1
	fi

	log_success "Checksum verification passed"
	return 0
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions with timestamps
log_info() {
	printf '%b[%s INFO]%b %s\n' "$BLUE" "$(date '+%Y-%m-%d %H:%M:%S')" "$NC" "$1"
}

log_success() {
	printf '%b[%s SUCCESS]%b %s\n' "$GREEN" "$(date '+%Y-%m-%d %H:%M:%S')" "$NC" "$1"
}

log_warning() {
	printf '%b[%s WARNING]%b %s\n' "$YELLOW" "$(date '+%Y-%m-%d %H:%M:%S')" "$NC" "$1"
}

log_error() {
	printf '%b[%s ERROR]%b %s\n' "$RED" "$(date '+%Y-%m-%d %H:%M:%S')" "$NC" "$1"
}

TRANSACTION_DIR=""
INSTALL_TARGET=""
INSTALL_DEVICE=""
BACKUP_PATH=""
DIRECTORY_REPLACEMENT=false
UPDATE_COMMITTED=false
APPIMAGE_BACKUP_OWNED=false
APPIMAGE_BACKUP_READY=false

device_id() {
	if [ "$OS" = "Darwin" ]; then
		stat -f '%d' "$1"
	else
		stat -c '%d' "$1"
	fi
}

check_install_device() {
	if [ "$(device_id "$INSTALL_TARGET")" = "$INSTALL_DEVICE" ] &&
		[ "$(device_id "$(dirname "$INSTALL_TARGET")")" = "$INSTALL_DEVICE" ]; then
		return 0
	fi
	log_error "Installation and parent must remain on the same filesystem. Update mounted installation roots manually."
	return 1
}

cleanup_update() {
	local status="$1"
	local preserve_recovery=false
	trap - EXIT HUP INT TERM
	set +e

	if ! $UPDATE_COMMITTED && $DIRECTORY_REPLACEMENT && [ -d "$BACKUP_PATH" ]; then
		if [ "$(device_id "$BACKUP_PATH" 2>/dev/null)" != "$INSTALL_DEVICE" ] ||
			[ "$(device_id "$(dirname "$INSTALL_TARGET")" 2>/dev/null)" != "$INSTALL_DEVICE" ]; then
			log_error "Recovery filesystem changed; automatic restoration is unsafe."
			preserve_recovery=true
		elif [ -e "$INSTALL_TARGET" ] || [ -L "$INSTALL_TARGET" ]; then
			log_error "Cannot restore over an existing destination: $INSTALL_TARGET"
			preserve_recovery=true
		elif mv "$BACKUP_PATH" "$(dirname "$INSTALL_TARGET")/"; then
			log_warning "Restored the previous installation: $INSTALL_TARGET"
		else
			log_error "Could not restore the previous installation."
			preserve_recovery=true
		fi
	fi

	if $APPIMAGE_BACKUP_OWNED && ! $APPIMAGE_BACKUP_READY; then
		if [ "$(device_id "$BACKUP_PATH" 2>/dev/null)" = "$INSTALL_DEVICE" ]; then
			rm -f "$BACKUP_PATH" || log_warning "Could not remove incomplete backup: $BACKUP_PATH"
		else
			log_warning "Could not safely remove incomplete backup: $BACKUP_PATH"
		fi
	fi
	if $preserve_recovery; then
		log_error "Previous installation preserved at: $BACKUP_PATH"
		log_error "Recovery files retained in: $TRANSACTION_DIR"
		status=1
	elif [ -n "$TRANSACTION_DIR" ]; then
		if [ "$(device_id "$TRANSACTION_DIR" 2>/dev/null)" = "$INSTALL_DEVICE" ]; then
			rm -rf "$TRANSACTION_DIR" || log_warning "Could not remove recovery directory: $TRANSACTION_DIR"
		else
			log_warning "Could not safely remove recovery directory: $TRANSACTION_DIR"
		fi
	fi
	if [ "$status" -ne 0 ]; then
		log_error "Update failed."
		if $APPIMAGE_BACKUP_READY; then
			log_error "Previous AppImage preserved at: $BACKUP_PATH"
		fi
	fi
	exit "$status"
}

trap 'cleanup_update "$?"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Function to kill RimSort process safely
kill_rimsort() {
	log_info "Stopping RimSort process..."

	if [ "$OS" = "Darwin" ]; then
		if killall -q RimSort 2>/dev/null; then
			log_success "RimSort process stopped"
		else
			log_warning "RimSort process not found or could not be killed"
		fi
	else
		if killall -q "$EXECUTABLE_NAME" 2>/dev/null; then
			log_success "$EXECUTABLE_NAME process stopped"
		else
			log_warning "$EXECUTABLE_NAME process not found or could not be killed"
		fi
	fi

	# Wait for process to fully terminate
	sleep 2
}

# Function to set permissions
set_permissions() {
	local target_dir="$1"

	log_info "Setting executable permissions..."

	if [ "$OS" = "Darwin" ]; then
		if [ ! -f "$target_dir/Contents/MacOS/RimSort" ]; then
			log_error "Replacement RimSort executable is missing."
			return 1
		fi
		chmod +x "$target_dir/Contents/MacOS/RimSort"
		chmod +x "$target_dir/Contents/MacOS/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
		chmod +x "$target_dir/Contents/MacOS/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
	else
		if [ ! -f "$target_dir/$EXECUTABLE_NAME" ]; then
			log_error "Replacement RimSort executable is missing."
			return 1
		fi
		chmod +x "$target_dir/$EXECUTABLE_NAME"
		chmod +x "$target_dir/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
		chmod +x "$target_dir/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
	fi
}

replace_directory() {
	local source_path
	local name
	INSTALL_TARGET="$(cd "$1" && pwd -P)"
	source_path="$(cd "$2" && pwd -P)"
	if [ "$INSTALL_TARGET" = "/" ]; then
		log_error "Cannot replace the filesystem root."
		return 1
	fi
	case "$source_path/" in
	"$INSTALL_TARGET/"*)
		log_error "Update source must be outside the installation."
		return 1
		;;
	esac
	case "$INSTALL_TARGET/" in
	"$source_path/"*)
		log_error "Installation must be outside the update source."
		return 1
		;;
	esac

	INSTALL_DEVICE="$(device_id "$INSTALL_TARGET")"
	check_install_device
	TRANSACTION_DIR="$(mktemp -d "$(dirname "$INSTALL_TARGET")/.rimsort-update.XXXXXX")"
	name="$(basename "$INSTALL_TARGET")"
	mkdir "$TRANSACTION_DIR/new" "$TRANSACTION_DIR/old"
	local staged_path="$TRANSACTION_DIR/new/$name"
	BACKUP_PATH="$TRANSACTION_DIR/old/$name"
	DIRECTORY_REPLACEMENT=true
	log_info "Recovery directory: $TRANSACTION_DIR"
	cp -a "$source_path/." "$staged_path"
	set_permissions "$staged_path"
	check_install_device
	kill_rimsort
	mv "$INSTALL_TARGET" "$TRANSACTION_DIR/old/"
	mv "$staged_path" "$(dirname "$INSTALL_TARGET")/"
	UPDATE_COMMITTED=true
	log_success "New installation activated: $INSTALL_TARGET"
}

# Function to launch application
launch_app() {
	local app_path="$1"

	log_info "Launching updated RimSort..."

	if [ "$OS" = "Darwin" ]; then
		open "$app_path" &
	else
		# Check if running as root - GUI apps cannot run as root
		if [ "$EUID" -eq 0 ]; then
			log_warning "Cannot launch GUI application as root. Please launch RimSort manually as a regular user."
			read -r -p "Press any key to continue..."
			return
		fi
		cd "$(dirname "$app_path")"
		nohup ./"$(basename "$app_path")" >/dev/null 2>&1 &
	fi

	sleep 2

	# Verify the application started
	if [ "$OS" = "Darwin" ]; then
		if pgrep -f "RimSort" >/dev/null; then
			log_success "RimSort started successfully!"
		else
			log_warning "RimSort may not have started successfully"
		fi
	else
		if pgrep -f "$EXECUTABLE_NAME" >/dev/null; then
			log_success "RimSort started successfully!"
		else
			log_warning "$EXECUTABLE_NAME may not have started successfully"
		fi
	fi
}

# Main script starts here
echo "========================================================================
"
echo "RimSort Update Script"
echo "========================================================================
"

# Detect the operating system
OS=$(uname)
log_info "Operating system: $OS"
log_info "Current working directory: $(pwd)"
log_info "User: $(whoami)"
log_info "TMPDIR: ${TMPDIR:-not set}"

# Set variables based on OS
if [ "$OS" = "Darwin" ]; then
	# macOS detected
	EXECUTABLE_NAME="RimSort.app"
	APP_BUNDLE_DIR="${3:-}"
	if [[ "$APP_BUNDLE_DIR" != /* ]] || [ ! -d "$APP_BUNDLE_DIR" ]; then
		log_error "An existing absolute application bundle path is required as the third argument."
		exit 1
	fi
	APP_BUNDLE_DIR="$(cd "$APP_BUNDLE_DIR" && pwd -P)"
	if [[ "$APP_BUNDLE_DIR" != *.app ]] || [ ! -f "$APP_BUNDLE_DIR/Contents/MacOS/RimSort" ]; then
		log_error "Invalid RimSort application bundle: $APP_BUNDLE_DIR"
		exit 1
	fi
	INSTALL_PARENT_DIR="$(dirname "$APP_BUNDLE_DIR")"
	INSTALL_DIR="$APP_BUNDLE_DIR"
	UPDATE_SOURCE_FOLDER="$TEMP_UPDATE_PATH"

	log_info "macOS detected"
	log_info "App bundle: $APP_BUNDLE_DIR"
	log_info "Install parent: $INSTALL_PARENT_DIR"
	log_info "Update source: $UPDATE_SOURCE_FOLDER"
else
	# Assume Linux if not macOS
	EXECUTABLE_NAME="RimSort"
	SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
	INSTALL_DIR="${3:-$SCRIPT_DIR}"
	UPDATE_SOURCE_FOLDER="$TEMP_UPDATE_PATH"

	log_info "Linux detected"
	log_info "Installation directory: $INSTALL_DIR"
	log_info "Update source: $UPDATE_SOURCE_FOLDER"
fi

if $DRY_RUN; then
	log_info "DRY RUN: Would stage $TEMP_UPDATE_PATH and replace ${APPIMAGE:-$INSTALL_DIR}"
	exit 0
fi

# ======================================================================
# AppImage self-update mode
# When $APPIMAGE is set, we are running inside an AppImage.  The update
# source ($TEMP_UPDATE_PATH) is a single .AppImage file, not a directory.
# We replace the running AppImage atomically via rename.
# ======================================================================
if [ -n "${APPIMAGE:-}" ]; then
	NEW_APPIMAGE="$TEMP_UPDATE_PATH"
	BACKUP_PATH="${APPIMAGE}.bak"

	log_info "AppImage update mode"
	log_info "Current AppImage: $APPIMAGE"
	log_info "New AppImage: $NEW_APPIMAGE"

	# Validate new AppImage file exists
	if [ ! -f "$NEW_APPIMAGE" ]; then
		log_error "New AppImage file not found: $NEW_APPIMAGE"
		exit 1
	fi
	if [ "$NEW_APPIMAGE" -ef "$APPIMAGE" ]; then
		log_error "Update source is the installed AppImage."
		exit 1
	fi

	# Validate write permission to AppImage directory
	APPIMAGE_DIR="$(cd "$(dirname "$APPIMAGE")" && pwd -P)"
	if [ ! -w "$APPIMAGE_DIR" ]; then
		log_error "No write permission to AppImage directory: $APPIMAGE_DIR"
		log_error "Move RimSort to a user-writable location or update manually."
		exit 1
	fi
	if [ -e "$BACKUP_PATH" ] || [ -L "$BACKUP_PATH" ]; then
		log_error "Backup already exists: $BACKUP_PATH"
		exit 1
	fi

	INSTALL_TARGET="$APPIMAGE"
	INSTALL_DEVICE="$(device_id "$INSTALL_TARGET")"
	check_install_device
	TRANSACTION_DIR="$(mktemp -d "$APPIMAGE_DIR/.rimsort-update.XXXXXX")"
	mkdir "$TRANSACTION_DIR/new"
	STAGED_APPIMAGE="$TRANSACTION_DIR/new/$(basename "$APPIMAGE")"
	cp -p "$NEW_APPIMAGE" "$STAGED_APPIMAGE"
	chmod +x "$STAGED_APPIMAGE"
	check_install_device

	log_info "Backing up current AppImage to: $BACKUP_PATH"
	if ! ln -P "$APPIMAGE" "$BACKUP_PATH" 2>/dev/null; then
		if ! (
			set -C
			: >"$BACKUP_PATH"
		) 2>/dev/null; then
			log_error "Backup already exists or cannot be created: $BACKUP_PATH"
			exit 1
		fi
		APPIMAGE_BACKUP_OWNED=true
		cp -Pp "$APPIMAGE" "$BACKUP_PATH"
	fi
	APPIMAGE_BACKUP_READY=true

	log_info "Installing new AppImage to: $APPIMAGE"
	check_install_device
	kill_rimsort
	mv "$STAGED_APPIMAGE" "$APPIMAGE_DIR/"
	UPDATE_COMMITTED=true
	rm -f "$NEW_APPIMAGE" || log_warning "Could not remove update source: $NEW_APPIMAGE"

	log_success "AppImage replaced successfully"

	# Launch new AppImage
	log_info "Launching updated AppImage..."
	if [ "$(id -u)" -eq 0 ]; then
		log_warning "Cannot launch GUI application as root. Please launch RimSort manually as a regular user."
		read -r -p "Press any key to continue..."
	elif ! $DRY_RUN; then
		nohup "$APPIMAGE" >/dev/null 2>&1 &
		sleep 2
		if pgrep -xf "$APPIMAGE" >/dev/null; then
			log_success "RimSort started successfully!"
		else
			log_warning "RimSort may not have started successfully"
		fi
	fi

	log_success "AppImage update completed successfully!"
	echo "========================================================================"
	exit 0
fi

# Check if update source exists
if [ ! -d "$UPDATE_SOURCE_FOLDER" ]; then
	log_error "Update source folder does not exist: $UPDATE_SOURCE_FOLDER"
	exit 1
fi

log_info "Update source folder exists: $UPDATE_SOURCE_FOLDER"

# Adjust source folder if it contains a RimSort subdirectory (unwrapped structure)
if [ -d "$UPDATE_SOURCE_FOLDER/RimSort" ]; then
	UPDATE_SOURCE_FOLDER="$UPDATE_SOURCE_FOLDER/RimSort"
	log_info "Adjusted update source to subdirectory: $UPDATE_SOURCE_FOLDER"
fi

# On macOS, adjust the source if it contains a RimSort.app bundle to copy its
# contents rather than nesting RimSort.app inside the target .app directory.
if [ "$OS" = "Darwin" ] && [ -d "$UPDATE_SOURCE_FOLDER/RimSort.app" ]; then
	UPDATE_SOURCE_FOLDER="$UPDATE_SOURCE_FOLDER/RimSort.app"
	log_info "Adjusted update source to .app bundle: $UPDATE_SOURCE_FOLDER"
fi

# Verify checksum if available
checksum_file="$UPDATE_SOURCE_FOLDER/checksum.sha256"
if [ -f "$checksum_file" ]; then
	# Find the main file to verify (assuming it's the executable or app bundle)
	if [ "$OS" = "Darwin" ]; then
		main_file="$UPDATE_SOURCE_FOLDER/RimSort.app"
	else
		main_file="$UPDATE_SOURCE_FOLDER/RimSort"
	fi
	if [ -e "$main_file" ]; then
		verify_checksum "$main_file" "$checksum_file" || exit 1
	else
		log_warning "Main file not found for checksum verification"
	fi
fi

# Display update confirmation
echo
echo "========================================================================
"
echo "RimSort Update Ready"
echo "========================================================================
"
echo "Source: $UPDATE_SOURCE_FOLDER"
echo "Target: $INSTALL_DIR"
echo
echo "Starting update..."
echo "========================================================================
"
echo

# Perform the update
log_info "Performing update..."
log_info "Source: $UPDATE_SOURCE_FOLDER"
log_info "Target: $INSTALL_DIR"

if [ "$OS" = "Darwin" ]; then
	# macOS update process
	log_info "Starting macOS update process"
	# Safety guard: never operate on root or /Applications itself
	if [ -z "$APP_BUNDLE_DIR" ] || [ "$APP_BUNDLE_DIR" = "/" ] || [ "$INSTALL_PARENT_DIR" = "/" ]; then
		log_error "Unsafe install paths detected. Aborting update."
		exit 1
	fi

	TARGET_BUNDLE="$APP_BUNDLE_DIR"
	replace_directory "$TARGET_BUNDLE" "$UPDATE_SOURCE_FOLDER"
	LAUNCH_PATH="$TARGET_BUNDLE"

else
	# Linux update process
	log_info "Starting Linux update process"

	replace_directory "$INSTALL_DIR" "$UPDATE_SOURCE_FOLDER"
	LAUNCH_PATH="$INSTALL_DIR/$EXECUTABLE_NAME"
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
log_info "Removing: $UPDATE_SOURCE_FOLDER"
if rm -rf "$UPDATE_SOURCE_FOLDER" 2>/dev/null; then
	log_success "Temporary files cleaned up"
else
	log_warning "Could not remove temporary folder: $UPDATE_SOURCE_FOLDER"
fi

launch_app "$LAUNCH_PATH"
log_success "RimSort update completed successfully!"
echo "========================================================================
"

cleanup_update 0
