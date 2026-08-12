@echo off
setlocal

REM Install or remove an autostart shortcut for ISweep.
set "ROOT_DIR=%~dp0"
set "TARGET=%ROOT_DIR%start_isweep.bat"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\Start ISweep.lnk"

if /I "%~1"=="remove" goto :REMOVE

if not exist "%TARGET%" (
  echo [ISweep] Missing script: "%TARGET%"
  endlocal & exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%ROOT_DIR%'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,220'; $s.Save()"
if errorlevel 1 (
  echo [ISweep] Failed to create startup shortcut.
  endlocal & exit /b 1
)

echo [ISweep] Startup shortcut installed at:
echo %SHORTCUT%
echo [ISweep] It will run "%TARGET%" after Windows sign-in.
endlocal & exit /b 0

:REMOVE
if exist "%SHORTCUT%" (
  del /f /q "%SHORTCUT%"
  if errorlevel 1 (
    echo [ISweep] Could not remove startup shortcut:
    echo %SHORTCUT%
    endlocal & exit /b 1
  )
  echo [ISweep] Startup shortcut removed.
) else (
  echo [ISweep] No startup shortcut found to remove.
)

endlocal & exit /b 0