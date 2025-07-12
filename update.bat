@echo off
setlocal enabledelayedexpansion

REM ========================================================================
REM RimSort Update Script for Windows
REM This script safely updates RimSort by replacing the current installation
REM with files from a temporary directory.
REM ========================================================================

echo Starting RimSort update process...

REM Get the current directory and executable path
set "current_dir=%~dp0"
set "current_dir_no_slash=%current_dir:~0,-1%"
set "executable_path=%current_dir%RimSort.exe"

REM Set the update source folder
set "update_source_folder=%TEMP%\RimSort"

REM Function to kill RimSort process safely
call :KillRimSort

REM Validate update source folder
if not exist "%update_source_folder%" (
    echo ERROR: Update source folder does not exist: %update_source_folder%
    echo Please ensure the update was downloaded correctly.
    pause
    exit /b 1
)

REM Check if update source contains expected files
if not exist "%update_source_folder%\RimSort.exe" (
    echo ERROR: Update source folder is missing RimSort.exe
    echo Update folder: %update_source_folder%
    pause
    exit /b 1
)

REM Display update confirmation with timeout
echo.
echo ========================================================================
echo RimSort Update Ready
echo ========================================================================
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

REM Create backup of current installation (optional safety measure)
set "backup_folder=%current_dir%backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "backup_folder=%backup_folder: =0%"
echo.
echo Creating backup of current installation...
if exist "%executable_path%" (
    mkdir "%backup_folder%" 2>nul
    copy "%executable_path%" "%backup_folder%\" >nul 2>&1
    if errorlevel 1 (
        echo Warning: Could not create backup
    ) else (
        echo Backup created: %backup_folder%
    )
)

REM Perform the update with robust error handling
echo.
echo Updating RimSort files...
robocopy "%update_source_folder%" "%current_dir_no_slash%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1

REM Check if robocopy was successful
if errorlevel 8 (
    echo ERROR: Update failed with critical errors
    echo Please check file permissions and try again
    pause
    exit /b 1
) else if errorlevel 4 (
    echo WARNING: Some files may not have been copied correctly
    echo The update may have partially succeeded
) else (
    echo Update completed successfully
)

REM Verify the updated executable exists and is accessible
if not exist "%executable_path%" (
    echo ERROR: Updated RimSort.exe not found after update
    echo Please reinstall RimSort manually
    pause
    exit /b 1
)

REM Clean up temporary files
echo.
echo Cleaning up temporary files...
rd /s /q "%update_source_folder%" 2>nul
if exist "%update_source_folder%" (
    echo Warning: Could not remove temporary folder: %update_source_folder%
)

REM Launch the updated RimSort
echo.
echo Launching updated RimSort...
start "" "%executable_path%"

REM Verify the application started
timeout /t 2 /nobreak >nul
tasklist /fi "imagename eq RimSort.exe" /fo csv | find /i "RimSort.exe" >nul
if errorlevel 1 (
    echo Warning: RimSort may not have started successfully
    echo You can manually launch it from: %executable_path%
    pause
) else (
    echo RimSort update completed successfully!
)

exit /b 0

REM ========================================================================
REM Functions
REM ========================================================================

:KillRimSort
echo Stopping RimSort process...
taskkill /F /im RimSort.exe >nul 2>&1
if errorlevel 1 (
    echo No running RimSort process found
) else (
    echo RimSort process stopped
    REM Wait a moment for process to fully terminate
    timeout /t 2 /nobreak >nul
)
goto :eof
