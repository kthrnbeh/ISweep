@echo off
setlocal

REM Start core local-dev pieces used by ISweep.
set "ROOT_DIR=%~dp0"

if not exist "%ROOT_DIR%start_backend.bat" (
  echo [ISweep] Missing script: "%ROOT_DIR%start_backend.bat"
  endlocal & exit /b 1
)

call "%ROOT_DIR%start_backend.bat"

REM Open quick checks and local pages.
start "" "http://127.0.0.1:5000/health"

if exist "%ROOT_DIR%docs\index.html" (
  start "" "%ROOT_DIR%docs\index.html"
)

start "" "chrome://extensions/"

echo [ISweep] Startup sequence launched.
echo [ISweep] If your frontend uses Live Server, open the docs URL from your VS Code Live Server session.

endlocal & exit /b 0
