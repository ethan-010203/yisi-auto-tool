param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$root = Get-WorkspaceRoot
$runDir = Get-RunDir
$python = Get-PythonCommand
$hostIp = Get-PreferredLanIp
$port = if ($env:YISI_BACKEND_PORT) { [string]$env:YISI_BACKEND_PORT } else { "8000" }
$appUrl = "http://$hostIp`:$port"

$backendPidFile = Get-PidFile "backend"
$workerPidFile = Get-PidFile "worker"
$backendLog = Get-LogFile "backend"
$backendErrorLog = Get-ErrorLogFile "backend"
$workerLog = Get-LogFile "worker"
$workerErrorLog = Get-ErrorLogFile "worker"
$preflightHealth = Invoke-AppHealth $appUrl 1
$externalBackendDetected = $false

if (-not $SkipBuild) {
    $distIndex = Join-Path $root "front\dist\index.html"
    if (-not (Test-Path $distIndex)) {
        & (Join-Path $PSScriptRoot "build-frontend.ps1")
    }
}

if (Test-Path $backendPidFile) {
    $existingBackendPid = (Get-Content -LiteralPath $backendPidFile -Raw).Trim()
    if (Test-RunningProcess $existingBackendPid) {
        Write-Host "Backend already running with PID $existingBackendPid"
    } else {
        Remove-Item -LiteralPath $backendPidFile -Force
    }
}

if (-not (Test-Path $backendPidFile) -and $preflightHealth.Success) {
    $externalBackendDetected = $true
    Write-Host "Detected an existing backend response at $appUrl that is not managed by this script."
    Write-Host "Skipping backend start to avoid port conflicts."
}

if (Test-Path $workerPidFile) {
    $existingWorkerPid = (Get-Content -LiteralPath $workerPidFile -Raw).Trim()
    if (Test-RunningProcess $existingWorkerPid) {
        Write-Host "Worker already running with PID $existingWorkerPid"
    } else {
        Remove-Item -LiteralPath $workerPidFile -Force
    }
}

if (-not (Test-Path $backendPidFile) -and -not $externalBackendDetected) {
    $backendArgs = @(
        $python.Arguments +
        @("-m", "uvicorn", "black.main:app", "--host", $hostIp, "--port", $port)
    ) | Where-Object { $_ -ne $null -and $_ -ne "" }

    $backendProcess = Start-Process `
        -FilePath $python.FilePath `
        -ArgumentList $backendArgs `
        -WorkingDirectory $root `
        -RedirectStandardOutput $backendLog `
        -RedirectStandardError $backendErrorLog `
        -PassThru `
        -WindowStyle Minimized

    $backendProcess.Id | Set-Content -LiteralPath $backendPidFile -Encoding ascii
    Write-Host "Backend started with PID $($backendProcess.Id)"
}

if (-not (Test-Path $workerPidFile)) {
    $workerArgs = @(
        $python.Arguments +
        @("black\worker.py", "--poll-interval", "1.0")
    ) | Where-Object { $_ -ne $null -and $_ -ne "" }

    $workerProcess = Start-Process `
        -FilePath $python.FilePath `
        -ArgumentList $workerArgs `
        -WorkingDirectory $root `
        -RedirectStandardOutput $workerLog `
        -RedirectStandardError $workerErrorLog `
        -PassThru `
        -WindowStyle Minimized

    $workerProcess.Id | Set-Content -LiteralPath $workerPidFile -Encoding ascii
    Write-Host "Worker started with PID $($workerProcess.Id)"
}

$meta = [ordered]@{
    startedAt = (Get-Date).ToString("o")
    workspace = $root
    host = $hostIp
    port = $port
    appUrl = $appUrl
    backendPid = if (Test-Path $backendPidFile) { Get-Content -LiteralPath $backendPidFile -Raw } else { $null }
    backendManaged = -not $externalBackendDetected
    workerPid = if (Test-Path $workerPidFile) { Get-Content -LiteralPath $workerPidFile -Raw } else { $null }
    backendLog = $backendLog
    backendErrorLog = $backendErrorLog
    workerLog = $workerLog
    workerErrorLog = $workerErrorLog
}
Write-ServiceMeta $meta

Start-Sleep -Seconds 2
$health = Invoke-AppHealth $appUrl 3

Write-Host ""
Write-Host "Services are ready."
Write-Host "App URL: $appUrl"
Write-Host "Backend log: $backendLog"
Write-Host "Backend error log: $backendErrorLog"
Write-Host "Worker log: $workerLog"
Write-Host "Worker error log: $workerErrorLog"
Write-Host ("Health check: {0}" -f $(if ($health.Success) { "OK" } else { "Failed" }))
if (-not $health.Success) {
    Write-Host "Health detail: $($health.Message)"
}
Start-Process $appUrl | Out-Null
