#!/bin/bash

# ========================================================================
# RimSort Update Script for macOS and Linux
# This script safely updates RimSort by replacing the current installation
# with files from a temporary directory.
# ========================================================================

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
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

# Function to validate update source
validate_update_source() {
    log_info "Validating update source..."
    
    if [ ! -d "$UPDATE_SOURCE_FOLDER" ]; then
        log_error "Update source folder does not exist: $UPDATE_SOURCE_FOLDER"
        log_error "Please ensure the update was downloaded correctly."
        exit 1
    fi
    
    # Check if update source contains expected files
    if [ "$OS" = "Darwin" ]; then
        # On macOS, UPDATE_SOURCE_FOLDER points directly to RimSort.app
        if [ ! -d "$UPDATE_SOURCE_FOLDER/Contents/MacOS" ]; then
            log_error "Update source does not look like an app bundle: $UPDATE_SOURCE_FOLDER"
            exit 1
        fi
        if [ ! -x "$UPDATE_SOURCE_FOLDER/Contents/MacOS/RimSort" ]; then
            log_warning "RimSort binary not marked executable; attempting later in set_permissions"
        fi
    else
        if [ ! -f "$UPDATE_SOURCE_FOLDER/$EXECUTABLE_NAME" ]; then
            log_error "Update source folder is missing $EXECUTABLE_NAME"
            exit 1
        fi
    fi
    
    log_success "Update source validated"
}

# Function to create backup
create_backup() {
    local backup_dir="$1"
    local source_dir="$2"
    
    log_info "Creating backup of current installation..."
    
    if [ -d "$source_dir" ]; then
        if cp -r "$source_dir" "$backup_dir" 2>/dev/null; then
            log_success "Backup created: $backup_dir"
        else
            log_warning "Could not create backup"
        fi
    else
        log_warning "Source directory not found, skipping backup"
    fi
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
        cd "$(dirname "$app_path")"
        ./"$(basename "$app_path")" &
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
echo "========================================================================"
echo "RimSort Update Script"
echo "========================================================================"

# Detect the operating system
OS=$(uname)
log_info "Operating system: $OS"

# Set variables based on OS
if [ "$OS" = "Darwin" ]; then
    # macOS detected
    EXECUTABLE_NAME="RimSort.app"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"               # .../RimSort.app/Contents/MacOS
    APP_BUNDLE_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"      # .../RimSort.app
    INSTALL_PARENT_DIR="$(dirname "$APP_BUNDLE_DIR")"            # Parent of .app (e.g. /Applications)
    INSTALL_DIR="$APP_BUNDLE_DIR"                                  # For common messaging/backup
    UPDATE_SOURCE_FOLDER="${TMPDIR:-/tmp}/$EXECUTABLE_NAME"

    log_info "macOS detected"
    log_info "App bundle: $APP_BUNDLE_DIR"
    log_info "Install parent: $INSTALL_PARENT_DIR"
    log_info "Update source: $UPDATE_SOURCE_FOLDER"
else
    # Assume Linux if not macOS
    EXECUTABLE_NAME="RimSort"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    INSTALL_DIR="$SCRIPT_DIR"
    UPDATE_SOURCE_FOLDER="/tmp/RimSort"
    
    log_info "Linux detected"
    log_info "Installation directory: $INSTALL_DIR"
    log_info "Update source: $UPDATE_SOURCE_FOLDER"
fi

# Kill running processes
kill_rimsort

# Validate update source
validate_update_source

# Display update confirmation
echo
echo "========================================================================"
echo "RimSort Update Ready"
echo "========================================================================"
echo "Source: $UPDATE_SOURCE_FOLDER"
echo "Target: $INSTALL_DIR"
echo
echo "The update will start in 5 seconds. Press any key to cancel."
echo "========================================================================"

if read -r -t 5 -n 1; then
    echo
    log_info "Update cancelled by user."
    exit 1
fi

echo

# Create backup
BACKUP_DIR="$INSTALL_DIR.backup.$(date +%Y%m%d_%H%M%S)"
create_backup "$BACKUP_DIR" "$INSTALL_DIR"

# Perform the update
log_info "Performing update..."

if [ "$OS" = "Darwin" ]; then
    # macOS update process
    # Safety guard: never operate on root or /Applications itself
    if [ -z "$APP_BUNDLE_DIR" ] || [ "$APP_BUNDLE_DIR" = "/" ] || [ "$INSTALL_PARENT_DIR" = "/" ]; then
        log_error "Unsafe install paths detected. Aborting update."
        exit 1
    fi

    # Remove old app bundle
    if [ -d "$APP_BUNDLE_DIR" ]; then
        if ! rm -rf "$APP_BUNDLE_DIR"; then
            log_error "Failed to remove old app bundle at $APP_BUNDLE_DIR"
            exit 1
        fi
    fi

    # Move new app bundle into install parent dir
    if ! mv "$UPDATE_SOURCE_FOLDER" "$INSTALL_PARENT_DIR"; then
        log_error "Failed to move update files to $INSTALL_PARENT_DIR"
        exit 1
    fi

    # Set permissions on the newly installed app bundle
    set_permissions "$INSTALL_PARENT_DIR/$EXECUTABLE_NAME"
    launch_app "$INSTALL_PARENT_DIR/$EXECUTABLE_NAME"
    
else
    # Linux update process
    if [ -d "$INSTALL_DIR" ]; then
        # Remove old files but keep the directory structure
        find "$INSTALL_DIR" -type f -not -name "update.sh" -delete 2>/dev/null || true
        find "$INSTALL_DIR" -type d -empty -delete 2>/dev/null || true
    fi
    
    if ! cp -r "$UPDATE_SOURCE_FOLDER"/* "$INSTALL_DIR"/; then
        log_error "Failed to copy update files to $INSTALL_DIR"
        exit 1
    fi
    
    set_permissions "$INSTALL_DIR"
    launch_app "$INSTALL_DIR/$EXECUTABLE_NAME"
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
rm -rf "$UPDATE_SOURCE_FOLDER" 2>/dev/null || log_warning "Could not remove temporary folder: $UPDATE_SOURCE_FOLDER"

log_success "RimSort update completed successfully!"
echo "========================================================================"

exit 0
