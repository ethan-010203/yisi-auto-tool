$ErrorActionPreference = "SilentlyContinue"

$RootDir = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $RootDir ".run"
$backendPort = if ($env:YISI_BACKEND_PORT) { $env:YISI_BACKEND_PORT } else { "8000" }
$frontendPort = if ($env:YISI_FRONTEND_PORT) { $env:YISI_FRONTEND_PORT } else { "5173" }

function Stop-ManagedProcess {
    param(
        [string]$Label,
        [string]$PidFile
    )

    if (Test-Path $PidFile) {
        $pidValue = Get-Content $PidFile
        if ($pidValue) {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            }
            Write-Host "$Label stopped: PID $pidValue"
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Stop-PortProcess {
    param(
        [string]$Label,
        [int]$Port
    )

    try {
        $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pidValue in $pids) {
            if ($pidValue) {
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
                if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
                    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                }
                Write-Host "$Label port listener stopped: PID $pidValue (port $Port)"
            }
        }
    } catch {
    }
}

Stop-ManagedProcess -Label "Backend" -PidFile (Join-Path $RunDir "backend.pid")
Stop-ManagedProcess -Label "Frontend" -PidFile (Join-Path $RunDir "frontend.pid")
Stop-PortProcess -Label "Backend" -Port $backendPort
Stop-PortProcess -Label "Frontend" -Port $frontendPort
