$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $RootDir ".run"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$BackendLog = Join-Path $RunDir "backend.log"
$FrontendLog = Join-Path $RunDir "frontend.log"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"
$backendPort = if ($env:YISI_BACKEND_PORT) { $env:YISI_BACKEND_PORT } else { "8000" }
$frontendPort = if ($env:YISI_FRONTEND_PORT) { $env:YISI_FRONTEND_PORT } else { "5173" }
$backendReloadFlag = if ($env:YISI_BACKEND_RELOAD_FLAG) { $env:YISI_BACKEND_RELOAD_FLAG } else { "" }

function Test-UvicornPython {
    param([string]$PythonCandidate)

    if (-not $PythonCandidate) {
        return $false
    }

    try {
        $null = & $PythonCandidate -c "import uvicorn" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$PythonBin = if ($env:YISI_PYTHON_BIN) {
    $env:YISI_PYTHON_BIN
} elseif ((Test-Path (Join-Path $RootDir ".venv/Scripts/python.exe")) -and (Test-UvicornPython (Join-Path $RootDir ".venv/Scripts/python.exe"))) {
    Join-Path $RootDir ".venv/Scripts/python.exe"
} elseif ((Test-Path (Join-Path $RootDir ".venv/bin/python")) -and (Test-UvicornPython (Join-Path $RootDir ".venv/bin/python"))) {
    Join-Path $RootDir ".venv/bin/python"
} elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-UvicornPython "python")) {
    "python"
} else {
    throw "No usable Python with uvicorn found. Install dependencies first."
}

function Get-PortProcess {
    param([int]$Port)

    try {
        return Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    } catch {
        return $null
    }
}

function Get-LanIp {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Select-Object -ExpandProperty IPAddress -First 1

        if ($ip) {
            return $ip
        }
    } catch {
    }

    return "localhost"
}

function Start-ManagedProcess {
    param(
        [string]$Label,
        [string]$WorkingDir,
        [string]$FilePath,
        [string]$Arguments,
        [string]$LogPath,
        [string]$PidFile
    )

    if (Test-Path $PidFile) {
        $existingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            Write-Host "$Label already running: PID $existingPid"
            return
        }
    }

    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDir -RedirectStandardOutput $LogPath -RedirectStandardError $LogPath -PassThru
    Set-Content -Path $PidFile -Value $process.Id
    Start-Sleep -Seconds 2

    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Write-Host "$Label started. Log: $LogPath"
        return
    }

    Remove-Item -Path $PidFile -ErrorAction SilentlyContinue
    Write-Host "$Label failed to start. Log: $LogPath"
    if (Test-Path $LogPath) {
        Get-Content -Path $LogPath -TotalCount 120
    }
}

$lanHost = Get-LanIp

Write-Host "Using Python: $PythonBin"
if (Get-PortProcess -Port $backendPort) {
    Write-Host "Backend already running on port $backendPort"
} else {
    Start-ManagedProcess -Label "Backend" -WorkingDir (Join-Path $RootDir "black") -FilePath $PythonBin -Arguments "-m uvicorn main:app --host 0.0.0.0 --port $backendPort $backendReloadFlag" -LogPath $BackendLog -PidFile $BackendPidFile
}

if (Get-PortProcess -Port $frontendPort) {
    Write-Host "Frontend already running on port $frontendPort"
} else {
    Start-ManagedProcess -Label "Frontend" -WorkingDir (Join-Path $RootDir "front") -FilePath "npm.cmd" -Arguments "run dev" -LogPath $FrontendLog -PidFile $FrontendPidFile
}

Write-Host "Backend LAN:  http://$lanHost:$backendPort"
Write-Host "Frontend LAN: http://$lanHost:$frontendPort"
