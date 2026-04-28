param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$stagingDist = Get-FrontendDistDir "staging"
$productionDist = Get-FrontendDistDir "production"
$releaseRoot = Join-Path $root ".releases\production"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$releaseDir = Join-Path $releaseRoot $timestamp
$backupDist = Join-Path $releaseDir "frontend"

function Assert-PathInsideWorkspace($PathToCheck) {
    $resolvedRoot = [System.IO.Path]::GetFullPath($root)
    $resolvedPath = [System.IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside workspace: $resolvedPath"
    }
}

if (-not (Test-Path (Join-Path $stagingDist "index.html"))) {
    throw "Staging build not found at $stagingDist. Run restart-staging-services.bat and test it first."
}

Assert-PathInsideWorkspace $productionDist
Assert-PathInsideWorkspace $releaseDir

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

if (Test-Path $productionDist) {
    Copy-Item -LiteralPath $productionDist -Destination $backupDist -Recurse -Force
}

$manifest = [ordered]@{
    releasedAt = (Get-Date).ToString("o")
    stagingDist = $stagingDist
    productionDist = $productionDist
    backupDist = if (Test-Path $backupDist) { $backupDist } else { $null }
    gitCommit = (& git rev-parse --short HEAD 2>$null)
    gitStatus = (& git status --short 2>$null)
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $releaseDir "manifest.json") -Encoding utf8

if (Test-Path $productionDist) {
    Remove-Item -LiteralPath $productionDist -Recurse -Force
}
Copy-Item -LiteralPath $stagingDist -Destination $productionDist -Recurse -Force

Write-Host "Published staging frontend to production."
Write-Host "Production dist: $productionDist"
Write-Host "Previous production backup: $backupDist"
Write-Host ""
Write-Host "Restarting production services on port 8000..."
& (Join-Path $PSScriptRoot "restart-services.ps1") -Environment production -SkipBuild
