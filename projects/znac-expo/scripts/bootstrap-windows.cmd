@echo off
setlocal

cd /d "%~dp0.."

set "NODE_VERSION=not installed"
call :check_node
if not errorlevel 1 goto node_ready

echo Node.js %NODE_VERSION% does not meet the Expo SDK 57 requirement.
where winget.exe >nul 2>nul
if errorlevel 1 goto node_manual_install

choice /c YN /n /m "Install or upgrade Node.js LTS with winget? [Y/N] "
if errorlevel 2 goto node_install_declined

echo Installing the current Node.js LTS release...
call winget.exe install --id OpenJS.NodeJS.LTS --exact --source winget --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto node_install_failed

rem A new installation may not update PATH in the current command process.
set "PATH=%ProgramFiles%\nodejs;%PATH%"
call :check_node
if errorlevel 1 goto node_restart_required

:node_ready
echo Using Node.js %NODE_VERSION%.

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm is not installed or is not available on PATH.
    exit /b 1
)

if not exist "package.json" (
    echo ERROR: package.json was not found in %CD%.
    exit /b 1
)

if not exist "package-lock.json" (
    echo ERROR: package-lock.json was not found in %CD%.
    exit /b 1
)

echo Installing the locked dependency tree...
call npm.cmd ci
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    exit /b 1
)

echo.
echo Bootstrap completed successfully.
echo Start the app with scripts\dev-windows.cmd
exit /b 0

:check_node
where node.exe >nul 2>nul
if errorlevel 1 exit /b 1
for /f "delims=" %%V in ('node.exe -p "process.versions.node"') do set "NODE_VERSION=%%V"
node.exe -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 22 || (major === 22 && minor >= 13) ? 0 : 1)"
if errorlevel 1 exit /b 1
exit /b 0

:node_manual_install
echo ERROR: winget is unavailable, so Node.js cannot be installed automatically.
echo Install Node.js 22.13 or newer, then run this script again.
exit /b 1

:node_install_declined
echo Node.js installation was declined. Bootstrap stopped without making changes.
exit /b 1

:node_install_failed
echo ERROR: winget could not install or upgrade Node.js LTS.
echo Install Node.js 22.13 or newer manually, then run this script again.
exit /b 1

:node_restart_required
echo Node.js was installed, but the required version is not available in this terminal.
echo Open a new terminal and run this script again.
exit /b 1
