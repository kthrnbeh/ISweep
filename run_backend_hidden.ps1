$ErrorActionPreference = 'Stop'

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'ISweep_backend'
$healthUrl = 'http://127.0.0.1:5000/health'
$stdoutPath = Join-Path $rootDir 'isweep_backend.log'
$stderrPath = Join-Path $rootDir 'isweep_backend_error.log'
$mutex = New-Object System.Threading.Mutex($false, 'Global\ISweepBackendWatchdog')
$ownsMutex = $false

try {
  $ownsMutex = $mutex.WaitOne(0)
} catch {
  $ownsMutex = $false
}

if (-not $ownsMutex) {
  exit 0
}

function Test-BackendHealthy {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Test-WorkingPython([string]$candidate) {
  if ([string]::IsNullOrWhiteSpace($candidate) -or -not (Test-Path -LiteralPath $candidate)) {
    return $false
  }

  try {
    & $candidate -c 'import flask, numpy, dotenv' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

function Resolve-WorkingPython {
  $candidates = @(
    (Join-Path $backendDir '.venv\Scripts\python.exe'),
    (Join-Path $rootDir '.venv\Scripts\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
    (Join-Path $env:ProgramFiles 'Python311\python.exe')
  )

  $appx = Get-AppxPackage -Name 'PythonSoftwareFoundation.Python.3.11' -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty InstallLocation
  foreach ($installLocation in @($appx)) {
    if ($installLocation) {
      $candidates += Join-Path $installLocation 'python3.11.exe'
      $candidates += Join-Path $installLocation 'python.exe'
    }
  }

  $windowsAppPython = Get-ChildItem -Path (Join-Path $env:ProgramFiles 'WindowsApps') `
    -Filter 'python3.11.exe' -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
  $candidates += @($windowsAppPython)

  $pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($pathPython) {
    $candidates += $pathPython.Source
  }

  foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
    if (Test-WorkingPython $candidate) {
      return $candidate
    }
  }

  return $null
}

if (-not (Test-Path -LiteralPath (Join-Path $backendDir 'app.py'))) {
  throw "Missing backend entrypoint: $backendDir\app.py"
}

try {
  while ($true) {
    if (-not (Test-BackendHealthy)) {
      $pythonExe = Resolve-WorkingPython
      if ($pythonExe) {
        Start-Process -FilePath $pythonExe `
          -ArgumentList 'app.py' `
          -WorkingDirectory $backendDir `
          -WindowStyle Hidden `
          -RedirectStandardOutput $stdoutPath `
          -RedirectStandardError $stderrPath | Out-Null
      } else {
        Add-Content -LiteralPath $stderrPath -Value "[$(Get-Date -Format o)] No working Python interpreter with Flask, NumPy, and python-dotenv was found."
      }
    }

    Start-Sleep -Seconds 15
  }
} finally {
  if ($ownsMutex) {
    $mutex.ReleaseMutex()
  }
  $mutex.Dispose()
}
