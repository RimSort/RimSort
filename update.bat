@echo off
setlocal enabledelayedexpansion

REM ========================================================================
REM RimSort Updater Script (Windows 10 & 11 Compatible)
REM Safely backs up and updates RimSort from provided temp path
REM Usage: update.bat <temp_update_path> <log_path>
REM ========================================================================

goto main

REM Function to get timestamp
:GetTimestamp
set "timestamp=%date% %time%"
goto :eof

:main
set "TEMP_UPDATE_PATH=%~1"
set "LOG_PATH=%~2"
if "%TEMP_UPDATE_PATH%" == "" (
    echo ERROR: Temp update path is required as first argument.
    pause
    exit /b 1
)
call :GetTimestamp
if defined LOG_PATH (
    echo [%timestamp%] INFO: Starting RimSort update process... >> "%LOG_PATH%"
    echo [%timestamp%] INFO: Temp update path: %TEMP_UPDATE_PATH% >> "%LOG_PATH%"
) else (
    echo [%timestamp%] INFO: Starting RimSort update process...
    echo [%timestamp%] INFO: Temp update path: %TEMP_UPDATE_PATH%
)

REM Get path of the currently running script
set "current_dir=%~dp0"
set "current_dir_no_slash=%current_dir:~0,-1%"
set "executable_path=%current_dir%RimSort.exe"

REM Use provided temp update path
set "update_source_folder=%TEMP_UPDATE_PATH%"

if defined LOG_PATH (
    echo Current directory: %%CD%% >> "%LOG_PATH%"
    echo Update source folder: %update_source_folder% >> "%LOG_PATH%"
) else (
    echo Current directory: %CD%
    echo Update source folder: %update_source_folder%
)

REM Attempt to stop RimSort if it's already running
call :KillRimSort

REM Check if update folder exists
if not exist "%update_source_folder%" (
    if defined LOG_PATH (
        echo ERROR: Update source folder does not exist: %update_source_folder% >> "%LOG_PATH%"
    ) else (
        echo ERROR: Update source folder does not exist: %update_source_folder%
    )
    pause
    exit /b 1
)

REM Check if RimSort.exe exists in the update folder
if not exist "%update_source_folder%\RimSort.exe" (
    if defined LOG_PATH (
        echo ERROR: RimSort.exe not found in update source folder. >> "%LOG_PATH%"
    ) else (
        echo ERROR: RimSort.exe not found in update source folder.
    )
    pause
    exit /b 1
)

REM Show update information
echo.
echo ========================================================================
echo RimSort Update Ready
echo Source: %update_source_folder%
echo Target: %current_dir%
echo.
echo The update will start automatically in 5 seconds...
echo ========================================================================
if defined LOG_PATH (
    echo. >> "%LOG_PATH%"
    echo RimSort Update Ready >> "%LOG_PATH%"
    echo Source: %update_source_folder% >> "%LOG_PATH%"
    echo Target: %current_dir% >> "%LOG_PATH%"
    echo. >> "%LOG_PATH%"
    echo The update will start automatically in 5 seconds... >> "%LOG_PATH%"
    echo ======================================================================== >> "%LOG_PATH%"
)
ping -n 6 127.0.0.1 >nul

REM Begin update by mirroring files from temp update folder to app folder
echo.
echo Updating RimSort files...
echo Source: %update_source_folder%
echo Target: %current_dir_no_slash%
if defined LOG_PATH (
    echo. >> "%LOG_PATH%"
    echo Updating RimSort files... >> "%LOG_PATH%"
    echo Source: %update_source_folder% >> "%LOG_PATH%"
    echo Target: %current_dir_no_slash% >> "%LOG_PATH%"
)
robocopy "%update_source_folder%" "%current_dir_no_slash%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1 >nul 2>&1
set "robocopy_exit=!errorlevel!"
echo Robocopy exit code: !robocopy_exit!
if defined LOG_PATH (
    echo Robocopy exit code: !robocopy_exit! >> "%LOG_PATH%"
)

REM Detailed robocopy exit code checking
if !robocopy_exit! EQU 0 (
    if defined LOG_PATH (
        echo INFO: No files were copied. Source and destination are identical. >> "%LOG_PATH%"
    ) else (
        echo INFO: No files were copied. Source and destination are identical.
    )
) else if !robocopy_exit! EQU 1 (
    if defined LOG_PATH (
        echo SUCCESS: Files copied successfully. >> "%LOG_PATH%"
    ) else (
        echo SUCCESS: Files copied successfully.
    )
) else if !robocopy_exit! EQU 2 (
    if defined LOG_PATH (
        echo WARNING: Extra files or directories detected. >> "%LOG_PATH%"
    ) else (
        echo WARNING: Extra files or directories detected.
    )
) else if !robocopy_exit! EQU 3 (
    if defined LOG_PATH (
        echo SUCCESS: Files copied successfully with extra files detected. >> "%LOG_PATH%"
    ) else (
        echo SUCCESS: Files copied successfully with extra files detected.
    )
) else if !robocopy_exit! EQU 4 (
    if defined LOG_PATH (
        echo WARNING: Mismatched files or directories detected. >> "%LOG_PATH%"
    ) else (
        echo WARNING: Mismatched files or directories detected.
    )
) else if !robocopy_exit! EQU 5 (
    if defined LOG_PATH (
        echo WARNING: Copy successful with mismatched files detected. >> "%LOG_PATH%"
    ) else (
        echo WARNING: Copy successful with mismatched files detected.
    )
) else if !robocopy_exit! GEQ 8 (
    if defined LOG_PATH (
        echo ERROR: Update failed with critical errors (exit code !robocopy_exit!). >> "%LOG_PATH%"
    ) else (
        echo ERROR: Update failed with critical errors (exit code !robocopy_exit!).
    )
    pause
    exit /b 1
) else (
    if defined LOG_PATH (
        echo WARNING: Unknown robocopy exit code: !robocopy_exit! >> "%LOG_PATH%"
    ) else (
        echo WARNING: Unknown robocopy exit code: !robocopy_exit!
    )
)

REM Give time for filesystem to sync
ping -n 4 127.0.0.1 >nul

REM Verify the new executable exists
if exist "%executable_path%" (
    if defined LOG_PATH (
        echo RimSort.exe verified. >> "%LOG_PATH%"
    ) else (
        echo RimSort.exe verified.
    )
) else (
    if defined LOG_PATH (
        echo ERROR: RimSort.exe not found after update. >> "%LOG_PATH%"
    ) else (
        echo ERROR: RimSort.exe not found after update.
    )
    pause
    exit /b 1
)

REM Cleanup temp update files
echo.
echo Cleaning up temporary files...
echo Removing: %update_source_folder%
if defined LOG_PATH (
    echo. >> "%LOG_PATH%"
    echo Cleaning up temporary files... >> "%LOG_PATH%"
    echo Removing: %update_source_folder% >> "%LOG_PATH%"
)
rd /s /q "%update_source_folder%" 2>nul
if exist "%update_source_folder%" (
    if defined LOG_PATH (
        echo WARNING: Failed to remove temporary folder. >> "%LOG_PATH%"
    ) else (
        echo WARNING: Failed to remove temporary folder.
    )
) else (
    if defined LOG_PATH (
        echo Temporary files cleaned up. >> "%LOG_PATH%"
    ) else (
        echo Temporary files cleaned up.
    )
)

REM Launch updated RimSort
echo.
echo Launching RimSort...
if defined LOG_PATH (
    echo. >> "%LOG_PATH%"
    echo Launching RimSort... >> "%LOG_PATH%"
)

REM Start RimSort
start "" "%executable_path%"
ping -n 3 127.0.0.1 >nul

REM Confirm process launch
tasklist /fi "imagename eq RimSort.exe" /fo csv | find /i "RimSort.exe" >nul
if errorlevel 1 (
    if defined LOG_PATH (
        echo WARNING: RimSort may not have started. >> "%LOG_PATH%"
        echo You can start it manually from: %executable_path% >> "%LOG_PATH%"
    ) else (
        echo WARNING: RimSort may not have started.
        echo You can start it manually from: %executable_path%
    )
    pause
) else (
    if defined LOG_PATH (
        echo RimSort update completed and launched successfully! >> "%LOG_PATH%"
    ) else (
        echo RimSort update completed and launched successfully!
    )
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
    ping -n 3 127.0.0.1 >nul
)
goto :eof
