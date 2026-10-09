@echo off
setlocal

REM Launch the backend independently of VS Code or a visible terminal window.
set "ROOT_DIR=%~dp0"
set "HIDDEN_SCRIPT=%ROOT_DIR%run_backend_hidden.ps1"

if not exist "%HIDDEN_SCRIPT%" (
  echo [ISweep] Missing script: "%HIDDEN_SCRIPT%"
  endlocal & exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HIDDEN_SCRIPT%" -Once
if errorlevel 1 (
  echo [ISweep] Backend launch failed.
  endlocal & exit /b 1
)
echo [ISweep] Backend is healthy and running in the background.

endlocal & exit /b 0
