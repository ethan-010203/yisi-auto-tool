param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$meta = Read-ServiceMeta
$appUrl = Get-AppUrl
$backendStatus = Get-ManagedProcessStatus "backend"
$workerStatus = Get-ManagedProcessStatus "worker"
$frontendIndex = Join-Path $root "front\dist\index.html"
$health = Invoke-AppHealth $appUrl

function Write-ServiceLine($title, $status) {
    $state = if ($status.Running) { "Running" } else { "Stopped" }
    $pidText = if ($status.Pid) { $status.Pid } else { "-" }
    Write-Host ("{0}: {1} (PID: {2})" -f $title, $state, $pidText)
    Write-Host ("  Stdout log: {0}" -f $status.LogFile)
    Write-Host ("  Stderr log: {0}" -f (Get-ErrorLogFile $status.Name))
}

Write-Host "Yisi Automation Service Status"
Write-Host "Workspace: $root"
Write-Host "App URL: $appUrl"
if ($meta -and $meta.startedAt) {
    Write-Host "Last start: $($meta.startedAt)"
}
if ($meta -and $meta.stoppedAt) {
    Write-Host "Last stop: $($meta.stoppedAt)"
}
Write-Host ("Frontend build: {0}" -f $(if (Test-Path $frontendIndex) { "Ready" } else { "Missing" }))
Write-Host ""

Write-ServiceLine "Backend" $backendStatus
Write-ServiceLine "Worker" $workerStatus
Write-Host ""

if ($health.Success) {
    Write-Host "Health check: OK"
    if (-not $backendStatus.Running) {
        Write-Host "  Note: API is responding, but it is not tracked by the managed backend PID file."
    }
    if ($health.Response.message) {
        Write-Host "  Message: $($health.Response.message)"
    }
    if ($health.Response.frontend) {
        Write-Host ("  Frontend dist: {0}" -f $health.Response.frontend.distExists)
        Write-Host ("  Frontend index: {0}" -f $health.Response.frontend.indexExists)
    }
    if ($health.Response.mode) {
        Write-Host ("  Queue mode: {0}" -f $health.Response.mode.queue)
        Write-Host ("  Worker mode: {0}" -f $health.Response.mode.worker)
    }
} else {
    Write-Host "Health check: Failed"
    Write-Host "  $($health.Message)"
}
