# AppImage Self-Update Support

**Date:** 2026-05-20
**Status:** Draft

## Problem

RimSort has a working self-update system for ZIP-based (Linux/macOS) and MSI/ZIP-based (Windows) installations. AppImage builds are produced in CI and uploaded to GitHub releases, but the updater has no AppImage awareness. If a user running the AppImage triggers "Check for Updates," it downloads a ZIP and tries to rsync files into the AppDir — which silently fails because AppImages are immutable squashfs archives.

## Goal

Enable seamless self-update for users running RimSort as an AppImage. The update should download the new `.AppImage` from GitHub releases and atomically replace the running file, with the same UX as the existing update flow (progress bar, confirmation dialogs, relaunch).

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Update mechanism | Direct full download from GitHub releases | Simpler than zsync2 delta updates; no extra tooling; consistent with existing ZIP download |
| Replacement strategy | `update.sh` auto-detects `$APPIMAGE` | Keeps filesystem swap logic in the shell script, consistent with existing Darwin/Linux branches |
| Backup strategy | Rename old AppImage to `.bak` | Single-file rename is instant; no need for ZIP backup of an already-compressed squashfs |
| Asset selection | Auto-detect: `.AppImage` when `$APPIMAGE` is set, ZIP otherwise | Each install type updates to its own format |
| Permission failures | Show clear error, no sudo escalation | Simple and predictable; user can move AppImage to writable location |

## Architecture

### Detection

The `$APPIMAGE` environment variable is set automatically by the AppImage runtime. It contains the absolute path to the running `.AppImage` file. This is the single source of truth for AppImage detection.

### Update Flow (AppImage)

```
User clicks "Check for Updates"
    │
    ▼
UpdateManager.do_check_for_update()
    │
    ├─ Fetch latest release from GitHub API (unchanged)
    ├─ Compare versions (unchanged)
    ├─ Prompt user (unchanged)
    │
    ▼
_get_platform_download_url()
    │
    ├─ Detect $APPIMAGE is set
    ├─ Look for .AppImage asset in release
    ├─ Fall back to .zip if no .AppImage found (with warning)
    │
    ▼
_perform_update()  [AppImage path]
    │
    ├─ Download .AppImage to memory (unchanged download logic)
    ├─ Write to $APPIMAGE.new (same directory, same filesystem)
    ├─ chmod +x
    ├─ SKIP ZIP extraction step
    ├─ SKIP backup step (rename to .bak handles it)
    ├─ Confirm with user (unchanged)
    │
    ▼
_launch_update_script()
    │
    ├─ Launch update.sh with $APPIMAGE.new as update source
    ├─ update.sh detects $APPIMAGE, enters AppImage branch:
    │     1. Wait for RimSort process to exit
    │     2. Rename $APPIMAGE → $APPIMAGE.bak
    │     3. Move $APPIMAGE.new → $APPIMAGE
    │     4. chmod +x $APPIMAGE
    │     5. Launch new $APPIMAGE
    │
    ▼
RimSort exits, new version launches
    │
    ▼
Next startup: clean up $APPIMAGE.bak if present
```

### Update Flow (Non-AppImage)

Completely unchanged. The `$APPIMAGE` variable is not set for directory-based installs, so all existing code paths remain as-is.

## File Changes

### 1. `app/utils/app_info.py`

Add AppImage detection:

- **`is_appimage`** property → `bool`: returns `True` if `$APPIMAGE` env var is set and non-empty
- **`appimage_path`** property → `Path | None`: returns `Path(os.environ["APPIMAGE"])` if running as AppImage
- **Startup cleanup**: in `__init__` or a dedicated method, check if `$APPIMAGE.bak` exists and delete it. This cleans up after a successful update.

### 2. `app/utils/update_utils.py`

**Constants:**
- Add `APPIMAGE_EXTENSION = ".AppImage"`

**`UpdateManager._get_platform_download_url()`:**
- Before existing Linux ZIP matching, check `AppInfo().is_appimage`
- If true, search assets for `.AppImage` extension using existing `_find_best_asset_match()` with `APPIMAGE_EXTENSION`
- If no AppImage asset found, fall through to existing ZIP logic and log a warning

**`UpdateManager._perform_update()`:**
- Add an `is_appimage` branch alongside the existing `is_msi` handling
- When AppImage: write `self._update_content` directly to `$APPIMAGE.new`, set `chmod +x`, set `self._extracted_path` to the new file path
- Skip `_extract_zip()` and `_normalize_structure()` calls
- Skip `_create_backup_with_progress()` call (the `.bak` rename in `update.sh` is the backup)

**`UpdateManager._launch_update_script()`:**
- For AppImage mode, the "update source path" is the new `.AppImage` file (not a temp directory)
- Pass it to `update.sh` the same way — the shell script will handle the rest
- `_get_script_info()` may need adjustment: for AppImage, `install_dir` is the directory containing `$APPIMAGE`, and the update script should still be found at `AppInfo().application_folder / "update.sh"` (inside the mounted AppDir at runtime)

**Note on script location:** When running as an AppImage, `update.sh` lives inside the mounted squashfs at `$APPDIR/usr/share/RimSort/update.sh`. We need to copy it to a temp location before launching (since the mount will go away when the app exits). The existing elevation logic already copies scripts to temp — extend this to always copy for AppImage mode.

### 3. `update.sh`

Add AppImage detection early in the Linux branch (around line 319):

```bash
if [ -n "${APPIMAGE:-}" ]; then
    # AppImage self-update mode
    # $1 = path to new .AppImage file
    # $2 = path to update log

    NEW_APPIMAGE="$1"
    LOG_FILE="$2"

    log "AppImage update mode"
    log "Current AppImage: $APPIMAGE"
    log "New AppImage: $NEW_APPIMAGE"

    # Validate new file exists and is executable
    if [ ! -f "$NEW_APPIMAGE" ]; then
        log "ERROR: New AppImage not found: $NEW_APPIMAGE"
        exit 1
    fi

    # Rename current → .bak
    BACKUP_PATH="${APPIMAGE}.bak"
    log "Backing up current AppImage to: $BACKUP_PATH"
    mv "$APPIMAGE" "$BACKUP_PATH"

    # Move new → current
    log "Installing new AppImage to: $APPIMAGE"
    mv "$NEW_APPIMAGE" "$APPIMAGE"
    chmod +x "$APPIMAGE"

    # Launch new AppImage (detached so it outlives this script)
    log "Launching updated AppImage..."
    nohup "$APPIMAGE" >/dev/null 2>&1 &

    log "Update complete."
    exit 0
fi
```

The rest of the Linux branch (rsync-based directory replacement) remains unchanged — it only runs when `$APPIMAGE` is not set.

### 4. `packaging/appimage/build-appimage.sh`

Ensure `update.sh` is included in the AppImage build. Currently the build script copies the entire Nuitka output (`app.dist/`) into the AppDir, and `update.sh` lives at the repo root. Need to verify it gets included — if not, add a `cp` for it.

### 5. `app/utils/system_info.py`

No changes needed. AppImage detection belongs in `AppInfo` (app-level concern), not `SystemInfo` (platform-level concern).

## Error Handling

| Scenario | Handling |
|----------|----------|
| No `.AppImage` asset in release | Fall back to ZIP download; log warning. ZIP update will fail gracefully (existing rsync-into-AppDir failure). |
| No write permission to AppImage directory | Show error: "Cannot update: no write permission to `<dir>`. Move RimSort to a user-writable location or update manually." |
| Download failure | Unchanged — existing retry/error dialog |
| Corrupt download | Existing size validation. Optionally verify AppImage magic bytes (`AI\x02`) at offset 8. |
| `$APPIMAGE.new` already exists (interrupted previous update) | Overwrite it — it's from a failed previous attempt |
| Rename fails (EXDEV — cross-device) | Won't happen: `.new` file is in same directory as `$APPIMAGE` |

## Testing

### Unit Tests

- **`AppInfo.is_appimage`**: Mock `$APPIMAGE` env var, verify detection
- **`AppInfo.appimage_path`**: Verify returns correct `Path` when set, `None` when unset
- **Asset selection**: Mock GitHub API response with both `.AppImage` and `.zip` assets, verify correct one is selected based on `is_appimage`
- **`_perform_update` AppImage branch**: Verify extraction is skipped, file is written directly, backup is skipped

### Shell Script Tests

- Test `update.sh` AppImage branch with dummy files: verify rename, move, chmod sequence
- Test error case: new file doesn't exist
- Test error case: no write permission

### Integration Test

- Build AppImage locally using `packaging/appimage/build-appimage.sh`
- Run it, trigger "Check for Updates"
- Verify: correct asset downloaded, file replaced, app relaunches on new version
- Verify: `.bak` cleaned up on next startup

## Out of Scope

- Delta updates (zsync2/appimageupdatetool) — full download only for now
- Flatpak/Snap self-update — different packaging systems, different update mechanisms
- Automatic update without user confirmation — existing UX (prompt + confirm) is preserved
- RPM self-update — RPMs are managed by the system package manager
