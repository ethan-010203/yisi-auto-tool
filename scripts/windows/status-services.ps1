param(
    [ValidateSet("production", "staging")]
    [string]$Environment = "production"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding = [Console]::OutputEncoding
} catch {
}

function T {
    param([string]$Base64)
    return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Base64))
}

$normalizedEnvironment = Get-ServiceEnvironment $Environment
Set-ServiceEnvironmentVariables $normalizedEnvironment

$root = Get-WorkspaceRoot
$meta = Read-ServiceMeta
$appUrl = Get-AppUrl
$backendStatus = Get-ManagedProcessStatus "backend"
$workerStatus = Get-ManagedProcessStatus "worker"
$frontendIndex = Join-Path (Get-FrontendDistDir $normalizedEnvironment) "index.html"
$health = Invoke-AppHealth $appUrl

function Get-EnvironmentLabel($environment) {
    if ($environment -eq "staging") {
        return (T "5rWL6K+V54mI")
    }
    return (T "55Sf5Lqn54mI")
}

function Get-ServiceTitle($name) {
    if ($name -eq "backend") {
        return (T "5ZCO56uv5pyN5Yqh")
    }
    if ($name -eq "worker") {
        return (T "5Lu75YqhIFdvcmtlcg==")
    }
    return $name
}

function Write-ServiceLine($title, $status) {
    $state = if ($status.Running) { T "6L+Q6KGM5Lit" } else { T "5bey5YGc5q2i" }
    $pidText = if ($status.Pid) { $status.Pid } else { "-" }
    Write-Host ("{0}: {1} (PID: {2})" -f $title, $state, $pidText)
    Write-Host ("  {0}: {1}" -f (T "5qCH5YeG6L6T5Ye65pel5b+X"), $status.LogFile)
    Write-Host ("  {0}: {1}" -f (T "6ZSZ6K+v5pel5b+X"), (Get-ErrorLogFile $status.Name))
}

$environmentLabel = Get-EnvironmentLabel $normalizedEnvironment

Write-Host ("{0}({1})" -f (T "5piT5oCd6Ieq5Yqo5YyW5pyN5Yqh54q25oCB"), $environmentLabel)
Write-Host ("{0}: {1}" -f (T "5bel5L2c55uu5b2V"), $root)
Write-Host ("{0}: {1}" -f (T "6K6/6Zeu5Zyw5Z2A"), $appUrl)
Write-Host ("{0}: {1}" -f (T "5YmN56uv5p6E5bu655uu5b2V"), (Get-FrontendDistDir $normalizedEnvironment))
Write-Host ("{0}: {1}" -f (T "6YWN572u55uu5b2V"), (Get-ConfigDir $normalizedEnvironment))
Write-Host ("{0}: {1}" -f (T "5pWw5o2u55uu5b2V"), (Get-DataDir $normalizedEnvironment))
Write-Host ("{0}: {1}" -f (T "5pel5b+X55uu5b2V"), (Get-LogsDir $normalizedEnvironment))
if ($meta -and $meta.startedAt) {
    Write-Host ("{0}: {1}" -f (T "5LiK5qyh5ZCv5Yqo5pe26Ze0"), $meta.startedAt)
}
if ($meta -and $meta.stoppedAt) {
    Write-Host ("{0}: {1}" -f (T "5LiK5qyh5YGc5q2i5pe26Ze0"), $meta.stoppedAt)
}
Write-Host ("{0}: {1}" -f (T "5YmN56uv5p6E5bu654q25oCB"), $(if (Test-Path $frontendIndex) { T "5bey5bCx57uq" } else { T "57y65aSx" }))
Write-Host ""

Write-ServiceLine (Get-ServiceTitle "backend") $backendStatus
Write-ServiceLine (Get-ServiceTitle "worker") $workerStatus
Write-Host ""

if ($health.Success) {
    Write-Host ("{0}: {1}" -f (T "5YGl5bq35qOA5p+l"), (T "5q2j5bi4"))
    if (-not $backendStatus.Running) {
        Write-Host ("  {0}" -f (T "5o+Q56S6OiBBUEkg5pyJ5ZON5bqU77yM5L2G5b2T5YmN5LiN5Y+X5ZCO56uvIFBJRCDmlofku7bnrqHnkIbjgII="))
    }
    if ($health.Response.message) {
        Write-Host ("  {0}: {1}" -f (T "6L+U5Zue5raI5oGv"), $health.Response.message)
    }
    if ($health.Response.frontend) {
        Write-Host ("  {0}: {1}" -f (T "5YmN56uv55uu5b2V5a2Y5Zyo"), $health.Response.frontend.distExists)
        Write-Host ("  {0}: {1}" -f (T "5YmN56uv5YWl5Y+j5a2Y5Zyo"), $health.Response.frontend.indexExists)
    }
    if ($health.Response.mode) {
        Write-Host ("  {0}: {1}" -f (T "6L+Q6KGM546v5aKD"), $health.Response.mode.environment)
        Write-Host ("  {0}: {1}" -f (T "6Zif5YiX5qih5byP"), $health.Response.mode.queue)
        Write-Host ("  {0}: {1}" -f (T "V29ya2VyIOaooeW8jw=="), $health.Response.mode.worker)
    }
} else {
    Write-Host ("{0}: {1}" -f (T "5YGl5bq35qOA5p+l"), (T "5aSx6LSl"))
    Write-Host "  $($health.Message)"
}
