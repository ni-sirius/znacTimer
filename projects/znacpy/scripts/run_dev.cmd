@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "PROJECT_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PROJECT_PYTHON%" (
    >&2 echo Error: project Python was not found at "%PROJECT_PYTHON%".
    >&2 echo Run uv sync --locked --group build first.
    exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PROJECT_PYTHON%" -m znactime %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %APP_EXIT_CODE%
