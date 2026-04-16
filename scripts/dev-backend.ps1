$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RootDir "black")

$PythonBin = if ($env:YISI_PYTHON_BIN) {
    $env:YISI_PYTHON_BIN
} elseif (Test-Path (Join-Path $RootDir ".venv/Scripts/python.exe")) {
    Join-Path $RootDir ".venv/Scripts/python.exe"
} elseif (Test-Path (Join-Path $RootDir ".venv/bin/python")) {
    Join-Path $RootDir ".venv/bin/python"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} else {
    throw "Python not found. Please install Python 3 or set YISI_PYTHON_BIN."
}

$port = if ($env:YISI_BACKEND_PORT) { $env:YISI_BACKEND_PORT } else { "8000" }
Write-Host "Using Python: $PythonBin"
& $PythonBin -m uvicorn main:app --host 0.0.0.0 --port $port --reload
