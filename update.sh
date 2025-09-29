#!/bin/bash

# ========================================================================
# RimSort Update Script for macOS and Linux
# This script safely updates RimSort by replacing the current installation
# with files from a temporary directory.
# Usage: update.sh <temp_update_path> [log_path] [install_dir]
# ========================================================================

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

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

# Trap errors to exit cleanly
trap 'log_error "Update failed. Exiting."; exit 1' ERR

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions with timestamps
log_info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S') INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S') SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S') WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S') ERROR]${NC} $1"
}

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
        chmod +x "$target_dir/Contents/MacOS/RimSort" 2>/dev/null || log_warning "Could not set permissions for RimSort"
        chmod +x "$target_dir/Contents/MacOS/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
        chmod +x "$target_dir/Contents/MacOS/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
    else
        chmod +x "$target_dir/$EXECUTABLE_NAME" 2>/dev/null || log_warning "Could not set permissions for $EXECUTABLE_NAME"
        chmod +x "$target_dir/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
        chmod +x "$target_dir/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
    fi
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
        nohup ./"$(basename "$app_path")" > /dev/null 2>&1 &
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
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"               # .../RimSort.app/Contents/MacOS
    APP_BUNDLE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"      # .../RimSort.app
    INSTALL_PARENT_DIR="$(dirname "$APP_BUNDLE_DIR")"            # Parent of .app (e.g. /Applications)
    INSTALL_DIR="$APP_BUNDLE_DIR"                                  # For common messaging
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

# Kill running processes
kill_rimsort

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

RSYNC_OPTS="-av"
if $DRY_RUN; then
    RSYNC_OPTS="$RSYNC_OPTS --dry-run"
fi

if [ "$OS" = "Darwin" ]; then
    # macOS update process
    log_info "Starting macOS update process"
    # Safety guard: never operate on root or /Applications itself
    if [ -z "$APP_BUNDLE_DIR" ] || [ "$APP_BUNDLE_DIR" = "/" ] || [ "$INSTALL_PARENT_DIR" = "/" ]; then
        log_error "Unsafe install paths detected. Aborting update."
        exit 1
    fi

    TARGET_BUNDLE="$INSTALL_PARENT_DIR/$EXECUTABLE_NAME"
    if [ -d "$TARGET_BUNDLE" ]; then
        log_info "Removing old app bundle: $TARGET_BUNDLE"
        if ! $DRY_RUN && ! rm -rf "$TARGET_BUNDLE"; then
            log_error "Failed to remove old app bundle at $TARGET_BUNDLE"
            exit 1
        fi
        if $DRY_RUN; then
            log_info "DRY RUN: Would remove $TARGET_BUNDLE"
        else
            log_success "Old app bundle removed"
        fi
    fi

    log_info "Syncing new app bundle to: $TARGET_BUNDLE"
    mkdir -p "$INSTALL_PARENT_DIR"
    if ! rsync "$RSYNC_OPTS" "$UPDATE_SOURCE_FOLDER/" "$TARGET_BUNDLE/"; then
        log_error "Failed to sync update files to $TARGET_BUNDLE"
        exit 1
    fi
    log_success "New app bundle synced"

    # Set permissions on the newly installed app bundle
    set_permissions "$TARGET_BUNDLE"
    launch_app "$TARGET_BUNDLE"

else
    # Linux update process
    log_info "Starting Linux update process"

    log_info "Syncing update files with rsync"
    if ! rsync "$RSYNC_OPTS" --delete "$UPDATE_SOURCE_FOLDER/" "$INSTALL_DIR/"; then
        log_error "Failed to sync update files to $INSTALL_DIR"
        exit 1
    fi
    log_success "Update files synced"

    set_permissions "$INSTALL_DIR"
    launch_app "$INSTALL_DIR/$EXECUTABLE_NAME"
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
log_info "Removing: $UPDATE_SOURCE_FOLDER"
if rm -rf "$UPDATE_SOURCE_FOLDER" 2>/dev/null; then
    log_success "Temporary files cleaned up"
else
    log_warning "Could not remove temporary folder: $UPDATE_SOURCE_FOLDER"
fi



log_success "RimSort update completed successfully!"
echo "========================================================================
"

# Clear trap on successful exit
trap - ERR

exit 0
