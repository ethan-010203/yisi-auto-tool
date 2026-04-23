$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$frontDir = Join-Path $root "front"
$npm = Get-NpmCommand

Write-Host "Building frontend in $frontDir"
Push-Location $frontDir
try {
    & $npm run build
} finally {
    Pop-Location
}

Write-Host "Frontend build completed."
