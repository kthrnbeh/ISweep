@echo off
setlocal

REM Launch the backend independently of VS Code or a visible terminal window.
set "ROOT_DIR=%~dp0"
set "HIDDEN_SCRIPT=%ROOT_DIR%run_backend_hidden.ps1"

if not exist "%HIDDEN_SCRIPT%" (
  echo [ISweep] Missing script: "%HIDDEN_SCRIPT%"
  endlocal & exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','%HIDDEN_SCRIPT%' -WindowStyle Hidden"
if errorlevel 1 (
  echo [ISweep] Backend launch failed.
  endlocal & exit /b 1
)
echo [ISweep] Backend launch requested in the background.

endlocal & exit /b 0
