param(
    [string]$Release
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$productionDist = Get-FrontendDistDir "production"
$releaseRoot = Join-Path $root ".releases\production"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$currentBackupRoot = Join-Path $root ".releases\production-rollback-current"
$currentBackupDist = Join-Path $currentBackupRoot $timestamp

function Assert-PathInsideWorkspace($PathToCheck) {
    $resolvedRoot = [System.IO.Path]::GetFullPath($root)
    $resolvedPath = [System.IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside workspace: $resolvedPath"
    }
}

if (-not (Test-Path $releaseRoot)) {
    throw "No production release backups found at $releaseRoot."
}

if ($Release) {
    $releaseDir = Join-Path $releaseRoot $Release
} else {
    $releaseDir = Get-ChildItem -LiteralPath $releaseRoot -Directory |
        Sort-Object Name -Descending |
        Where-Object { Test-Path (Join-Path $_.FullName "frontend\index.html") } |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $releaseDir) {
    throw "No usable frontend backup found under $releaseRoot."
}

$backupDist = Join-Path $releaseDir "frontend"
if (-not (Test-Path (Join-Path $backupDist "index.html"))) {
    throw "Selected release does not contain a frontend backup: $backupDist"
}

Assert-PathInsideWorkspace $productionDist
Assert-PathInsideWorkspace $currentBackupDist

if (Test-Path $productionDist) {
    New-Item -ItemType Directory -Force -Path $currentBackupRoot | Out-Null
    Copy-Item -LiteralPath $productionDist -Destination $currentBackupDist -Recurse -Force
}

if (Test-Path $productionDist) {
    Remove-Item -LiteralPath $productionDist -Recurse -Force
}
Copy-Item -LiteralPath $backupDist -Destination $productionDist -Recurse -Force

Write-Host "Rolled production frontend back to: $releaseDir"
Write-Host "Previous current production dist saved at: $currentBackupDist"
Write-Host ""
Write-Host "Restarting production services on port 8000..."
& (Join-Path $PSScriptRoot "restart-services.ps1") -Environment production -SkipBuild
