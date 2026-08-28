@echo off
setlocal

REM Start the ISweep backend without requiring VS Code or a visible terminal.
set "ROOT_DIR=%~dp0"

if not exist "%ROOT_DIR%start_backend.bat" (
  echo [ISweep] Missing script: "%ROOT_DIR%start_backend.bat"
  endlocal & exit /b 1
)

call "%ROOT_DIR%start_backend.bat"

echo [ISweep] Startup sequence launched.
echo [ISweep] Backend runs independently of VS Code and the browser popup.

endlocal & exit /b 0
