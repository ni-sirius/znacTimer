@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "PROJECT_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "BUNDLE_DIR=%PROJECT_ROOT%\dist\bundle\windows-x64\znacTime"
set "BUNDLE_EXE=%BUNDLE_DIR%\znacTime.exe"
set "RUN_AFTER_BUILD="

if "%~1"=="" goto build
if /I "%~1"=="--run" goto enable_run
goto usage

:enable_run
set "RUN_AFTER_BUILD=1"
shift
if not "%~1"=="" goto usage

:build
if not exist "%PROJECT_PYTHON%" (
    >&2 echo Error: project Python was not found at "%PROJECT_PYTHON%".
    >&2 echo Run uv sync --locked --group build first.
    exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PROJECT_PYTHON%" packaging\build.py --target windows-x64 --mode unsigned
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%BUILD_EXIT_CODE%"=="0" exit /b %BUILD_EXIT_CODE%
if not defined RUN_AFTER_BUILD exit /b 0

if not exist "%BUNDLE_EXE%" (
    >&2 echo Error: built executable was not found at "%BUNDLE_EXE%".
    exit /b 1
)

start "" /D "%BUNDLE_DIR%" "%BUNDLE_EXE%"
exit /b 0

:usage
>&2 echo Usage: %~nx0 [--run]
exit /b 2
