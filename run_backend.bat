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

REM Prefer backend-local virtual environment, then repo-level environment.
if exist "%BACKEND_DIR%\.venv\Scripts\activate.bat" (
  call "%BACKEND_DIR%\.venv\Scripts\activate.bat"
) else if exist "%ROOT_DIR%.venv\Scripts\activate.bat" (
  call "%ROOT_DIR%.venv\Scripts\activate.bat"
)

echo [ISweep] Starting backend from "%BACKEND_DIR%"
python app.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [ISweep] Backend exited with code %EXIT_CODE%.
) else (
  echo [ISweep] Backend stopped.
)

endlocal & exit /b %EXIT_CODE%