@echo off
setlocal

REM Resolve repository and backend paths.
set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%ISweep_backend"

if not exist "%BACKEND_DIR%\app.py" (
  echo [ISweep] Could not find backend entrypoint: "%BACKEND_DIR%\app.py"
  endlocal & exit /b 1
)

cd /d "%BACKEND_DIR%"

REM Prefer an explicit virtual-environment interpreter so Windows startup does
REM not depend on PATH or the Microsoft Store Python alias.
set "PYTHON_EXE="
if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
) else if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python.exe"
)

echo [ISweep] Starting backend from "%BACKEND_DIR%"
echo [ISweep] Using Python: "%PYTHON_EXE%"
"%PYTHON_EXE%" app.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [ISweep] Backend exited with code %EXIT_CODE%.
) else (
  echo [ISweep] Backend stopped.
)

endlocal & exit /b %EXIT_CODE%