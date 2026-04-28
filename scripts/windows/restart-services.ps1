param(
    [ValidateSet("production", "staging")]
    [string]$Environment = "production",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$normalizedEnvironment = Get-ServiceEnvironment $Environment
Set-ServiceEnvironmentVariables $normalizedEnvironment

Write-Host "Restarting Yisi automation $normalizedEnvironment services..."

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build-frontend.ps1") -Environment $normalizedEnvironment
}

& (Join-Path $PSScriptRoot "stop-services.ps1") -Environment $normalizedEnvironment

Write-Host ""
Write-Host "Starting services again..."
& (Join-Path $PSScriptRoot "start-services.ps1") -Environment $normalizedEnvironment -SkipBuild
