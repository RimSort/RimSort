@echo off

REM Ensure the application is killed
taskkill /F /im RimSort.exe

REM Set the update source folder
set "update_source_folder=%TEMP%\RimSort"

REM Display a message indicating the update operation is starting in 10 seconds
echo Updating RimSort in 5 seconds. Press any key to cancel.

REM Sleep for 5 seconds unless user input
timeout /t 5

REM Move files from the update source folder to the current directory
copy "%update_source_folder%\*" "%cd%"

REM Execute RimSort.exe from the current directory
start "" "%cd%\RimSort.exe"
