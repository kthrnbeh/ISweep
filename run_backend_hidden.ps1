$ErrorActionPreference = 'Stop'

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'ISweep_backend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
  $pythonExe = Join-Path $rootDir '.venv\Scripts\python.exe'
}
if (-not (Test-Path $pythonExe)) {
  $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
}

if (-not (Test-Path (Join-Path $backendDir 'app.py'))) {
  throw "Missing backend entrypoint: $backendDir\app.py"
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -in @('python.exe', 'pythonw.exe') -and
    $_.CommandLine -match 'ISweep_backend.*app\.py'
  }

if ($existing) {
  exit 0
}

$stdoutPath = Join-Path $rootDir 'isweep_backend.log'
$stderrPath = Join-Path $rootDir 'isweep_backend_error.log'
Start-Process -FilePath $pythonExe `
  -ArgumentList 'app.py' `
  -WorkingDirectory $backendDir `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutPath `
  -RedirectStandardError $stderrPath
