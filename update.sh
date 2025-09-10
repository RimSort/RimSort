#!/bin/bash

# ========================================================================
# RimSort Update Script for macOS and Linux (non-interactive with logging)
# Safely updates RimSort by replacing the current installation with files
# from a temporary directory and logs all steps to a persistent log file.
# ========================================================================

set -euo pipefail  # Exit on error, undefined variables, and pipe failures
IFS=$'\n\t'

# Detect the operating system early (used for logging path and behavior)
OS="$(uname)"

# Colors for output (not used in logs)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Choose persistent log directory per platform
if [[ "${OS}" == "Darwin" ]]; then
    LOG_DIR="${HOME}/Library/Logs/RimSort"
else
    # Use XDG_STATE_HOME if available, otherwise default to ~/.local/state
    LOG_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/RimSort/logs"
fi
mkdir -p "${LOG_DIR}" 2>/dev/null || true
LOG_FILE="${LOG_DIR}/updater.log"

# Helper to append to log without affecting set -e
_log_append() { echo "$1" >>"${LOG_FILE}" || true; }

# Timestamp helper
_now() { date -Iseconds; }

# Logging functions (echo to console and append to log without color codes)
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    local ts
    ts="$(_now)"
    _log_append "${ts} [INFO] $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    local ts
    ts="$(_now)"
    _log_append "${ts} [SUCCESS] $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    local ts
    ts="$(_now)"
    _log_append "${ts} [WARNING] $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    local ts
    ts="$(_now)"
    _log_append "${ts} [ERROR] $1"
}

log_header() {
    local ts
    ts="$(_now)"
    echo "===============================================================" >>"${LOG_FILE}" || true
    echo "RimSort updater started ${ts}" >>"${LOG_FILE}" || true
    echo "OS: ${OS}" >>"${LOG_FILE}" || true
    echo "Script: $0" >>"${LOG_FILE}" || true
}

log_header

# Function to kill RimSort process safely (with logging)
kill_rimsort() {
    log_info "Stopping RimSort process..."

    if [[ "${OS}" == "Darwin" ]]; then
        if killall -q RimSort 2>/dev/null; then
            log_success "RimSort process stopped"
        else
            log_warning "RimSort process not found or could not be killed"
        fi
    else
        if killall -q "${EXECUTABLE_NAME}" 2>/dev/null; then
            log_success "${EXECUTABLE_NAME} process stopped"
        else
            log_warning "${EXECUTABLE_NAME} process not found or could not be killed"
        fi
    fi

    # Wait for process to fully terminate
    sleep 2
}

# Function to validate update source
validate_update_source() {
    log_info "Validating update source..."

    if [[ ! -d "${UPDATE_SOURCE_FOLDER}" ]]; then
        log_error "Update source folder does not exist: ${UPDATE_SOURCE_FOLDER}"
        log_error "Please ensure the update was downloaded correctly."
        exit 1
    fi

    # Check if update source contains expected files
    if [[ "${OS}" == "Darwin" ]]; then
        # On macOS, UPDATE_SOURCE_FOLDER points directly to RimSort.app
        if [[ ! -d "${UPDATE_SOURCE_FOLDER}/Contents/MacOS" ]]; then
            log_error "Update source does not look like an app bundle: ${UPDATE_SOURCE_FOLDER}"
            exit 1
        fi
        if [[ ! -x "${UPDATE_SOURCE_FOLDER}/Contents/MacOS/RimSort" ]]; then
            log_warning "RimSort binary not marked executable; attempting later in set_permissions"
        fi
    else
        if [[ ! -f "${UPDATE_SOURCE_FOLDER}/${EXECUTABLE_NAME}" ]]; then
            log_error "Update source folder is missing ${EXECUTABLE_NAME}"
            exit 1
        fi
    fi

    log_success "Update source validated"
}

# Function to set permissions
set_permissions() {
    local target_dir="$1"

    log_info "Setting executable permissions in: ${target_dir}"

    if [[ "${OS}" == "Darwin" ]]; then
        chmod +x "${target_dir}/Contents/MacOS/RimSort" 2>/dev/null || log_warning "Could not set permissions for RimSort"
        chmod +x "${target_dir}/Contents/MacOS/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
        chmod +x "${target_dir}/Contents/MacOS/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
    else
        chmod +x "${target_dir}/${EXECUTABLE_NAME}" 2>/dev/null || log_warning "Could not set permissions for ${EXECUTABLE_NAME}"
        chmod +x "${target_dir}/todds/todds" 2>/dev/null || log_warning "Could not set permissions for todds"
        chmod +x "${target_dir}/QtWebEngineProcess" 2>/dev/null || log_warning "Could not set permissions for QtWebEngineProcess"
    fi
}

# Function to launch application
launch_app() {
    local app_path="$1"

    log_info "Launching updated RimSort: ${app_path}"

    if [[ "${OS}" == "Darwin" ]]; then
        open "${app_path}" &
    else
        cd "$(dirname "${app_path}")"
        ./"$(basename "${app_path}")" &
    fi

    sleep 2

    # Verify the application started
    if [[ "${OS}" == "Darwin" ]]; then
        if pgrep -f "RimSort" >/dev/null; then
            log_success "RimSort started successfully!"
        else
            log_warning "RimSort may not have started successfully"
        fi
    else
        if pgrep -f "${EXECUTABLE_NAME}" >/dev/null; then
            log_success "RimSort started successfully!"
        else
            log_warning "${EXECUTABLE_NAME} may not have started successfully"
        fi
    fi
}

# Main script starts here
log_info "RimSort Update Script"
log_info "Operating system: ${OS}"

# Set variables based on OS
if [[ "${OS}" == "Darwin" ]]; then
    # macOS detected
    EXECUTABLE_NAME="RimSort.app"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"               # .../RimSort.app/Contents/MacOS
    APP_BUNDLE_DIR="$(dirname "$(dirname "${SCRIPT_DIR}")")"    # .../RimSort.app
    INSTALL_PARENT_DIR="$(dirname "${APP_BUNDLE_DIR}")"           # Parent of .app (e.g. /Applications)
    INSTALL_DIR="${APP_BUNDLE_DIR}"                                # For common messaging/backup
    UPDATE_SOURCE_FOLDER="${TMPDIR:-/tmp}/${EXECUTABLE_NAME}"

    log_info "macOS detected"
    log_info "App bundle: ${APP_BUNDLE_DIR}"
    log_info "Install parent: ${INSTALL_PARENT_DIR}"
    log_info "Update source: ${UPDATE_SOURCE_FOLDER}"
else
    # Assume Linux if not macOS
    EXECUTABLE_NAME="RimSort"
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    INSTALL_DIR="${SCRIPT_DIR}"
    UPDATE_SOURCE_FOLDER="/tmp/RimSort"

    log_info "Linux detected"
    log_info "Installation directory: ${INSTALL_DIR}"
    log_info "Update source: ${UPDATE_SOURCE_FOLDER}"
fi

# Kill running processes
kill_rimsort

# Validate update source
validate_update_source

# Display (non-interactive) update information
log_info "Proceeding with update (non-interactive)"
log_info "Source: ${UPDATE_SOURCE_FOLDER}"
log_info "Target: ${INSTALL_DIR}"

# Perform the update
log_info "Performing update..."

if [[ "${OS}" == "Darwin" ]]; then
    # macOS update process
    # Safety guard: never operate on root or /Applications itself
    if [[ -z "${APP_BUNDLE_DIR}" ]] || [[ "${APP_BUNDLE_DIR}" == "/" ]] || [[ "${INSTALL_PARENT_DIR}" == "/" ]]; then
        log_error "Unsafe install paths detected. Aborting update."
        exit 1
    fi

    # Remove old app bundle
    if [[ -d "${APP_BUNDLE_DIR}" ]]; then
        if ! rm -rf "${APP_BUNDLE_DIR}"; then
            log_error "Failed to remove old app bundle at ${APP_BUNDLE_DIR}"
            exit 1
        fi
        log_info "Removed old app bundle: ${APP_BUNDLE_DIR}"
    fi

    # Move new app bundle into install parent dir
    if ! mv "${UPDATE_SOURCE_FOLDER}" "${INSTALL_PARENT_DIR}"; then
        log_error "Failed to move update files to ${INSTALL_PARENT_DIR}"
        exit 1
    fi
    log_info "Moved update to: ${INSTALL_PARENT_DIR}/${EXECUTABLE_NAME}"

    # Set permissions on the newly installed app bundle
    set_permissions "${INSTALL_PARENT_DIR}/${EXECUTABLE_NAME}"
    launch_app "${INSTALL_PARENT_DIR}/${EXECUTABLE_NAME}"

else
    # Linux update process
    if [[ -d "${INSTALL_DIR}" ]]; then
        # Remove old files but keep the directory structure
        find "${INSTALL_DIR}" -type f -not -name "update.sh" -delete 2>/dev/null || true
        find "${INSTALL_DIR}" -type d -empty -delete 2>/dev/null || true
        log_info "Removed old files from: ${INSTALL_DIR}"
    fi

    if ! cp -r "${UPDATE_SOURCE_FOLDER}"/* "${INSTALL_DIR}"/; then
        log_error "Failed to copy update files to ${INSTALL_DIR}"
        exit 1
    fi
    log_info "Copied update files to: ${INSTALL_DIR}"

    set_permissions "${INSTALL_DIR}"
    launch_app "${INSTALL_DIR}/${EXECUTABLE_NAME}"
fi

# Clean up temporary files
log_info "Cleaning up temporary files..."
rm -rf "${UPDATE_SOURCE_FOLDER}" 2>/dev/null || log_warning "Could not remove temporary folder: ${UPDATE_SOURCE_FOLDER}"

log_success "RimSort update completed successfully!"

exit 0
