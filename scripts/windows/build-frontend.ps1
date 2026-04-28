param(
    [ValidateSet("production", "staging")]
    [string]$Environment = "production"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$frontDir = Join-Path $root "front"
$npm = Get-NpmCommand
$normalizedEnvironment = Get-ServiceEnvironment $Environment
$distDir = Get-FrontendDistDir $normalizedEnvironment
$env:VITE_OUT_DIR = Split-Path -Leaf $distDir

Write-Host "Building $normalizedEnvironment frontend in $frontDir"
Write-Host "Output directory: $distDir"
Push-Location $frontDir
try {
    & $npm run build
} finally {
    Pop-Location
    Remove-Item Env:\VITE_OUT_DIR -ErrorAction SilentlyContinue
}

Write-Host "Frontend build completed."
