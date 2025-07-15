@echo off
setlocal enabledelayedexpansion

REM ========================================================================
REM RimSort Updater Script (Windows 10 & 11 Compatible)
REM Safely backs up and updates RimSort from %TEMP%\RimSort
REM ========================================================================

echo Starting RimSort update process...

REM Get path of the currently running script
set "current_dir=%~dp0"
set "current_dir_no_slash=%current_dir:~0,-1%"
set "executable_path=%current_dir%RimSort.exe"

REM Path to the update files (should be copied here externally)
set "update_source_folder=%TEMP%\RimSort"

REM Attempt to stop RimSort if it's already running
call :KillRimSort

REM Check if update folder exists
if not exist "%update_source_folder%" (
    echo ERROR: Update source folder does not exist: %update_source_folder%
    pause
    exit /b 1
)

REM Check if RimSort.exe exists in the update folder
if not exist "%update_source_folder%\RimSort.exe" (
    echo ERROR: RimSort.exe not found in update source folder.
    pause
    exit /b 1
)

REM Show confirmation before proceeding with update
echo.
echo ========================================================================
echo RimSort Update Ready
echo Source: %update_source_folder%
echo Target: %current_dir%
echo.
echo The update will start in 5 seconds. Press any key to cancel.
echo ========================================================================
choice /t 5 /d y /n >nul
if errorlevel 2 (
    echo Update cancelled by user.
    pause
    exit /b 1
)

REM Get parent directory and generate backup folder name
for %%a in ("%current_dir_no_slash%\..") do set "parent_dir=%%~fa"
for %%b in ("%current_dir_no_slash%") do set "current_folder_name=%%~nxb"
set "current_folder_name=%current_folder_name: =0%"
set "backup_folder_name=%current_folder_name%_Backup"

REM Use WMIC to get system-local datetime in a consistent format
for /f %%a in ('wmic os get localdatetime ^| find "."') do set dt=%%a
set "year=%dt:~0,4%"
set "month=%dt:~4,2%"
set "day=%dt:~6,2%"
set "hour=%dt:~8,2%"
set "minute=%dt:~10,2%"

REM Compose full backup folder path
set "backup_folder=%parent_dir%\%backup_folder_name%_%year%%month%%day%_%hour%%minute%"

REM Create backup of the current installation
echo.
echo Creating backup: %backup_folder%
robocopy "%current_dir_no_slash%\." "%backup_folder%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1
if errorlevel 8 (
    echo ERROR: Backup failed.
    pause
    exit /b 1
)

REM Begin update by mirroring files from temp update folder to app folder
echo.
echo Updating RimSort files...
robocopy "%update_source_folder%" "%current_dir_no_slash%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1
set "robocopy_exit=!errorlevel!"

REM Check if robocopy had serious issues
if %robocopy_exit% GEQ 8 (
    echo ERROR: Update failed with critical errors.
    pause
    exit /b 1
) else if %robocopy_exit% GEQ 4 (
    echo WARNING: Some files may not have copied properly.
) else (
    echo Update completed successfully.
)

REM Give time for filesystem to sync
timeout /t 3 /nobreak >nul

REM Verify the new executable exists
if exist "%executable_path%" (
    echo RimSort.exe verified.
) else (
    echo ERROR: RimSort.exe not found after update.
    pause
    exit /b 1
)

REM Cleanup temp update files
echo.
echo Cleaning up temporary files...
rd /s /q "%update_source_folder%" 2>nul

REM Launch updated RimSort
echo.
echo Launching RimSort in 5 seconds. Press any key to cancel.
choice /t 5 /d y /n >nul
if errorlevel 2 (
    echo Launch cancelled by user.
    pause
    exit /b 1
)

REM Start RimSort
start "" "%executable_path%"
timeout /t 2 /nobreak >nul

REM Confirm process launch
tasklist /fi "imagename eq RimSort.exe" /fo csv | find /i "RimSort.exe" >nul
if errorlevel 1 (
    echo WARNING: RimSort may not have started.
    echo You can start it manually from: %executable_path%
    pause
) else (
    echo RimSort update completed and launched successfully!
)

exit /b 0

REM --------------------------
REM Function to kill RimSort
REM --------------------------
:KillRimSort
echo Stopping RimSort process...
taskkill /F /im RimSort.exe >nul 2>&1
if errorlevel 1 (
    echo No running RimSort process found.
) else (
    echo RimSort process terminated.
    timeout /t 2 /nobreak >nul
)
goto :eof
