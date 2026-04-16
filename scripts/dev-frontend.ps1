$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RootDir "front")

function Get-PreferredLanIp {
    if ($env:YISI_BIND_HOST) {
        return $env:YISI_BIND_HOST
    }

    try {
        $currentBlock = @()
        $blocks = @()
        foreach ($line in (ipconfig)) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                if ($currentBlock.Count -gt 0) {
                    $blocks += ,@($currentBlock)
                    $currentBlock = @()
                }
                continue
            }

            $currentBlock += $line
        }
        if ($currentBlock.Count -gt 0) {
            $blocks += ,@($currentBlock)
        }

        foreach ($block in $blocks) {
            $ipv4Line = $block | Where-Object { $_ -match "IPv4" -and $_ -match "(\d{1,3}\.){3}\d{1,3}" } | Select-Object -First 1
            $gatewayLine = $block | Where-Object { ($_ -match "Default Gateway" -or $_ -match "默认网关") -and $_ -match "(\d{1,3}\.){3}\d{1,3}" } | Select-Object -First 1

            if ($ipv4Line -and $gatewayLine) {
                $ipMatch = [regex]::Match($ipv4Line, "(\d{1,3}\.){3}\d{1,3}")
                if ($ipMatch.Success -and $ipMatch.Value -notlike "169.254.*" -and $ipMatch.Value -ne "127.0.0.1") {
                    return $ipMatch.Value
                }
            }
        }
    } catch {
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

$bindHost = Get-PreferredLanIp
$backendPort = if ($env:YISI_BACKEND_PORT) { $env:YISI_BACKEND_PORT } else { "8000" }
$env:YISI_BIND_HOST = $bindHost
$env:VITE_HOST = $bindHost
$env:VITE_PROXY_TARGET = "http://${bindHost}:${backendPort}"

npm run dev
