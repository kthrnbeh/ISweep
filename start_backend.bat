@echo off
setlocal

REM Launch backend in a dedicated terminal window.
set "ROOT_DIR=%~dp0"
set "RUN_SCRIPT=%ROOT_DIR%run_backend.bat"

if not exist "%RUN_SCRIPT%" (
  echo [ISweep] Missing script: "%RUN_SCRIPT%"
  endlocal & exit /b 1
)

start "ISweep Backend" cmd /k ""%RUN_SCRIPT%""
echo [ISweep] Backend window launched.

endlocal & exit /b 0
