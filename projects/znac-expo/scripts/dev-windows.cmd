@echo off
setlocal

cd /d "%~dp0.."

if not exist "node_modules\expo\package.json" (
    echo ERROR: Dependencies are not installed.
    echo Run scripts\bootstrap-windows.cmd first.
    exit /b 1
)

call npm.cmd run start -- %*
exit /b %ERRORLEVEL%
