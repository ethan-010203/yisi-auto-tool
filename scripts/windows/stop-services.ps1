param(
    [ValidateSet("production", "staging")]
    [string]$Environment = "production"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$normalizedEnvironment = Get-ServiceEnvironment $Environment
Set-ServiceEnvironmentVariables $normalizedEnvironment

$results = @(
    Stop-ManagedProcess "worker"
    Stop-ManagedProcess "backend"
)

$meta = Read-ServiceMeta
if ($meta) {
    $meta | Add-Member -NotePropertyName stoppedAt -NotePropertyValue (Get-Date).ToString("o") -Force
    Write-ServiceMeta $meta
}

Write-Host "Stopping $normalizedEnvironment services..."
foreach ($result in $results) {
    $label = if ($result.Stopped) { "Stopped" } else { "Still running" }
    Write-Host (" - {0}: {1} ({2})" -f $result.Name, $label, $result.Message)
}

$backendStatus = Get-ManagedProcessStatus "backend"
$workerStatus = Get-ManagedProcessStatus "worker"
$health = Invoke-AppHealth (Get-AppUrl) 2

if (-not $backendStatus.Running -and -not $workerStatus.Running) {
    Write-Host ""
    Write-Host "All managed $normalizedEnvironment services are stopped."
    if ($health.Success) {
        Write-Host "API is still responding at $(Get-AppUrl). It may have been started manually outside these scripts."
    }
    exit 0
}

Write-Host ""
Write-Host "Some services are still running. Check status-services.bat for details."
exit 1
