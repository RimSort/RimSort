@echo off
REM Build rimsort_steam.dll on Windows
REM Requires STEAMWORKS_SDK_PATH to be set and Visual Studio Build Tools installed

if "%STEAMWORKS_SDK_PATH%"=="" (
    echo ERROR: STEAMWORKS_SDK_PATH not set
    exit /b 1
)

set SDK_HEADERS=%STEAMWORKS_SDK_PATH%\public\steam
set SDK_REDIST=%STEAMWORKS_SDK_PATH%\redistributable_bin\win64

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

cl /D_USRDLL /D_WINDLL /I"%SDK_HEADERS%" rimsort_steam.cpp "%SDK_REDIST%\steam_api64.lib" /link /DLL /OUT:rimsort_steam.dll

if %ERRORLEVEL% neq 0 (
    echo Build failed
    exit /b 1
)

echo Build succeeded: rimsort_steam.dll
