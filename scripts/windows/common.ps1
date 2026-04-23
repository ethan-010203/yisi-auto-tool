$ErrorActionPreference = "Stop"

function Get-WorkspaceRoot {
    return Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Get-RunDir {
    $runDir = Join-Path (Get-WorkspaceRoot) ".run\windows"
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    return $runDir
}

function Get-PreferredLanIp {
    if ($env:YISI_BIND_HOST) {
        return $env:YISI_BIND_HOST
    }

    try {
        $config = Get-NetIPConfiguration -ErrorAction Stop |
            Where-Object {
                $_.NetAdapter.Status -eq "Up" -and
                $_.IPv4Address -and
                $_.IPv4DefaultGateway -and
                $_.IPv4Address.IPAddress -ne "127.0.0.1" -and
                $_.IPv4Address.IPAddress -notlike "169.254.*"
            } |
            Select-Object -First 1

        if ($config -and $config.IPv4Address) {
            return $config.IPv4Address.IPAddress
        }
    } catch {
    }

    return "127.0.0.1"
}

function Get-PythonCommand {
    $root = Get-WorkspaceRoot

    if ($env:YISI_PYTHON_BIN) {
        return @{
            FilePath = $env:YISI_PYTHON_BIN
            Arguments = @()
            Display = $env:YISI_PYTHON_BIN
        }
    }

    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{
            FilePath = $venvPython
            Arguments = @()
            Display = $venvPython
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{
            FilePath = "py"
            Arguments = @("-3")
            Display = "py -3"
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{
            FilePath = "python"
            Arguments = @()
            Display = "python"
        }
    }

    throw "Python not found. Please install Python or set YISI_PYTHON_BIN."
}

function Get-NpmCommand {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        return "npm"
    }

    throw "npm not found. Please install Node.js."
}

function Get-ServiceMetaPath {
    return Join-Path (Get-RunDir) "service-meta.json"
}

function Read-ServiceMeta {
    $path = Get-ServiceMetaPath
    if (-not (Test-Path $path)) {
        return $null
    }
    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Write-ServiceMeta($meta) {
    $path = Get-ServiceMetaPath
    $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding utf8
}

function Get-PidFile($name) {
    return Join-Path (Get-RunDir) "$name.pid"
}

function Get-LogFile($name) {
    return Join-Path (Get-RunDir) "$name.log"
}

function Get-ErrorLogFile($name) {
    return Join-Path (Get-RunDir) "$name.error.log"
}

function Read-PidValue($name) {
    $path = Get-PidFile $name
    if (-not (Test-Path $path)) {
        return $null
    }

    $raw = (Get-Content -LiteralPath $path -Raw).Trim()
    if (-not $raw) {
        return $null
    }

    return $raw
}

function Remove-PidFile($name) {
    $path = Get-PidFile $name
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

function Test-RunningProcess($processId) {
    if (-not $processId) {
        return $false
    }

    try {
        $null = Get-Process -Id $processId -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-ManagedProcessStatus($name) {
    $pidValue = Read-PidValue $name
    $logFile = Get-LogFile $name

    return [pscustomobject]@{
        Name = $name
        Pid = $pidValue
        Running = (Test-RunningProcess $pidValue)
        PidFile = Get-PidFile $name
        LogFile = $logFile
    }
}

function Stop-ManagedProcess($name) {
    $status = Get-ManagedProcessStatus $name

    if (-not $status.Pid) {
        return [pscustomobject]@{
            Name = $name
            WasRunning = $false
            Stopped = $true
            Message = "PID file not found"
        }
    }

    if (-not $status.Running) {
        Remove-PidFile $name
        return [pscustomobject]@{
            Name = $name
            WasRunning = $false
            Stopped = $true
            Message = "Process already stopped"
        }
    }

    try {
        Stop-Process -Id $status.Pid -ErrorAction Stop
        Start-Sleep -Milliseconds 900
        if (Test-RunningProcess $status.Pid) {
            Stop-Process -Id $status.Pid -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
        }

        $stopped = -not (Test-RunningProcess $status.Pid)
        if ($stopped) {
            Remove-PidFile $name
        }

        return [pscustomobject]@{
            Name = $name
            WasRunning = $true
            Stopped = $stopped
            Message = if ($stopped) { "Stopped" } else { "Stop requested but process is still running" }
        }
    } catch {
        return [pscustomobject]@{
            Name = $name
            WasRunning = $true
            Stopped = $false
            Message = $_.Exception.Message
        }
    }
}

function Get-AppUrl {
    $meta = Read-ServiceMeta
    if ($meta -and $meta.appUrl) {
        return [string]$meta.appUrl
    }

    $hostIp = Get-PreferredLanIp
    $port = if ($env:YISI_BACKEND_PORT) { [string]$env:YISI_BACKEND_PORT } else { "8000" }
    return "http://$hostIp`:$port"
}

function Invoke-AppHealth($appUrl, $timeoutSeconds = 2) {
    try {
        $response = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec $timeoutSeconds
        return [pscustomobject]@{
            Success = $true
            Message = "Health check OK"
            Response = $response
        }
    } catch {
        return [pscustomobject]@{
            Success = $false
            Message = $_.Exception.Message
            Response = $null
        }
    }
}
