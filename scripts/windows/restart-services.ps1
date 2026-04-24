param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

Write-Host "Restarting Yisi automation services..."

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build-frontend.ps1")
}

& (Join-Path $PSScriptRoot "stop-services.ps1")

Write-Host ""
Write-Host "Starting services again..."
& (Join-Path $PSScriptRoot "start-services.ps1") -SkipBuild
