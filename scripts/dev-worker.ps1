$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
  (Join-Path $projectRoot ".venv\\Scripts\\python.exe"),
  "py -3",
  "python"
)

foreach ($candidate in $pythonCandidates) {
  if ($candidate -like "*.exe" -and -not (Test-Path $candidate)) {
    continue
  }

  try {
    if ($candidate -like "*.exe") {
      & $candidate "$projectRoot\\black\\worker.py"
    } else {
      Invoke-Expression "$candidate `"$projectRoot\\black\\worker.py`""
    }
    exit $LASTEXITCODE
  } catch {
    continue
  }
}

throw "Unable to start worker. Please ensure Python is available."
