@echo off
setlocal enabledelayedexpansion

REM ========================================================================
REM RimSort Updater Script (Windows 10 & 11 Compatible)
REM Non-interactive updater with colorized console logging and persistent logs
REM Logs are saved to: %LOCALAPPDATA%\RimSort\Logs\updater.log
REM ========================================================================

REM Enable ANSI escape sequence support (Windows 10+ terminals support VT by default)
for /F "delims=" %%A in ('echo prompt $E^| cmd') do set "ESC=%%A"
set "C_INFO=%ESC%[34m"
set "C_SUCCESS=%ESC%[32m"
set "C_WARN=%ESC%[33m"
set "C_ERROR=%ESC%[31m"
set "C_RESET=%ESC%[0m"

REM Resolve paths
set "current_dir=%~dp0"
set "current_dir_no_slash=%current_dir:~0,-1%"
set "executable_path=%current_dir%RimSort.exe"

REM Path to the update files (extracted externally)
if "%TMPDIR%" == "" (
  set "update_source_folder=%TEMP%\RimSort"
) else (
  set "update_source_folder=%TMPDIR%\RimSort"
)

REM Initialize persistent logging
set "log_dir=%LOCALAPPDATA%\RimSort\Logs"
if not exist "%log_dir%" mkdir "%log_dir%" >nul 2>&1
set "UPDATER_LOG=%log_dir%\updater.log"
call :LogHeader

call :LogInfo "Starting RimSort update process..."
call :LogInfo "Source: %update_source_folder%"
call :LogInfo "Target: %current_dir%"

REM Stop RimSort if running
call :KillRimSort

REM Validate update source
if not exist "%update_source_folder%" (
  call :LogError "Update source folder does not exist: %update_source_folder%"
  exit /b 1
)

REM Validate RimSort.exe exists in the update source
if not exist "%update_source_folder%\RimSort.exe" (
  call :LogError "RimSort.exe not found in update source folder: %update_source_folder%"
  exit /b 1
)

REM Begin update by mirroring files from temp update folder to app folder
call :LogInfo "Updating RimSort files..."
>> "%UPDATER_LOG%" echo --- robocopy begin ---
>> "%UPDATER_LOG%" echo robocopy "%update_source_folder%" "%current_dir_no_slash%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1
robocopy "%update_source_folder%" "%current_dir_no_slash%" /MIR /NFL /NDL /NJH /NJS /nc /ns /np /R:3 /W:1 >> "%UPDATER_LOG%" 2>&1
set "robocopy_exit=!errorlevel!"
>> "%UPDATER_LOG%" echo robocopy exit code: !robocopy_exit!
>> "%UPDATER_LOG%" echo --- robocopy end ---

if !robocopy_exit! GEQ 8 (
  call :LogError "Update failed with critical errors. robocopy exit: !robocopy_exit!"
  exit /b 1
) else if !robocopy_exit! GEQ 4 (
  call :LogWarn "Some files may not have copied properly. robocopy exit: !robocopy_exit!"
) else (
  call :LogSuccess "Update copy completed successfully."
)

REM Give time for filesystem to sync
timeout /t 3 /nobreak >nul

REM Verify the new executable exists
if exist "%executable_path%" (
  call :LogSuccess "RimSort.exe verified at: %executable_path%"
) else (
  call :LogError "RimSort.exe not found after update at: %executable_path%"
  exit /b 1
)

REM Cleanup temp update files
call :LogInfo "Cleaning up temporary files: %update_source_folder%"
rd /s /q "%update_source_folder%" 2>>"%UPDATER_LOG%"

REM Launch updated RimSort with pre-launch delay to ensure copy completion
call :LogInfo "Launching RimSort after 5s delay: %executable_path%"
timeout /t 5 /nobreak >nul
start "" "%executable_path%"
>> "%UPDATER_LOG%" echo start command issued.

REM Short post-launch wait then verify process
timeout /t 2 /nobreak >nul
tasklist /fi "imagename eq RimSort.exe" /fo csv | find /i "RimSort.exe" >nul
if errorlevel 1 (
  call :LogWarn "RimSort may not have started. Manual path: %executable_path%"
) else (
  call :LogSuccess "RimSort update completed and launched successfully!"
)

exit /b 0

REM --------------------------
REM Logging helpers
REM --------------------------
:LogHeader
>> "%UPDATER_LOG%" echo ================================================================
>> "%UPDATER_LOG%" echo RimSort updater started %DATE% %TIME%
>> "%UPDATER_LOG%" echo Script: %~f0
>> "%UPDATER_LOG%" echo Current Dir: %current_dir%
>> "%UPDATER_LOG%" echo Source: %update_source_folder%
>> "%UPDATER_LOG%" echo Target: %current_dir_no_slash%
>> "%UPDATER_LOG%" echo ================================================================
exit /b 0

:LogInfo
set "_msg=%~1"
echo %C_INFO%[INFO]%C_RESET% %_msg%
>> "%UPDATER_LOG%" echo %DATE% %TIME% [INFO] %_msg%
exit /b 0

:LogWarn
set "_msg=%~1"
echo %C_WARN%[WARNING]%C_RESET% %_msg%
>> "%UPDATER_LOG%" echo %DATE% %TIME% [WARNING] %_msg%
exit /b 0

:LogError
set "_msg=%~1"
echo %C_ERROR%[ERROR]%C_RESET% %_msg%
>> "%UPDATER_LOG%" echo %DATE% %TIME% [ERROR] %_msg%
exit /b 0

:LogSuccess
set "_msg=%~1"
echo %C_SUCCESS%[SUCCESS]%C_RESET% %_msg%
>> "%UPDATER_LOG%" echo %DATE% %TIME% [SUCCESS] %_msg%
exit /b 0

REM --------------------------
REM Function to kill RimSort
REM --------------------------
:KillRimSort
call :LogInfo "Stopping RimSort process..."
taskkill /F /im RimSort.exe >nul 2>&1
if errorlevel 1 (
  call :LogWarn "No running RimSort process found."
) else (
  call :LogSuccess "RimSort process terminated."
  timeout /t 2 /nobreak >nul
)
exit /b 0
