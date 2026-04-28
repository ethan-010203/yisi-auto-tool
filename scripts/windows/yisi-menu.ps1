param(
    [string]$Action
)

$ErrorActionPreference = "Stop"
$scriptRoot = $PSScriptRoot

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding = [Console]::OutputEncoding
} catch {
}

function T {
    param([string]$Base64)
    return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Base64))
}

function Invoke-YisiAction {
    param([string]$SelectedAction)

    switch ($SelectedAction.ToLowerInvariant()) {
        { $_ -in @("staging", "test") } {
            & (Join-Path $scriptRoot "restart-services.ps1") -Environment staging
            return
        }
        { $_ -in @("production", "prod") } {
            & (Join-Path $scriptRoot "restart-services.ps1") -Environment production
            return
        }
        "publish" {
            & (Join-Path $scriptRoot "publish-production.ps1")
            return
        }
        "rollback" {
            & (Join-Path $scriptRoot "rollback-production.ps1")
            return
        }
        "status" {
            & (Join-Path $scriptRoot "status-services.ps1") -Environment staging
            Write-Host ""
            & (Join-Path $scriptRoot "status-services.ps1") -Environment production
            return
        }
        "stop-staging" {
            & (Join-Path $scriptRoot "stop-services.ps1") -Environment staging
            return
        }
        "stop-production" {
            & (Join-Path $scriptRoot "stop-services.ps1") -Environment production
            return
        }
        "start-staging" {
            & (Join-Path $scriptRoot "start-services.ps1") -Environment staging
            return
        }
        "start-production" {
            & (Join-Path $scriptRoot "start-services.ps1") -Environment production
            return
        }
        default {
            throw "$(T '5pyq55+l5pON5L2cOiA=')$SelectedAction"
        }
    }
}

if ($Action) {
    Invoke-YisiAction $Action
    exit 0
}

while ($true) {
    Clear-Host
    Write-Host (T "5qSF5oCd6Ieq5Yqo5YyW5bel5YW3")
    Write-Host ""
    Write-Host (T "ICAxLiDph43lkK/mtYvor5XniYggICAgLSBhdXRvLXRlc3QuZXRoYW4wMTAyMDMub25saW5lIDogODAwMQ==")
    Write-Host (T "ICAyLiDph43lkK/nlJ/kuqfniYggICAgLSBhdXRvLmV0aGFuMDEwMjAzLm9ubGluZSA6IDgwMDA=")
    Write-Host (T "ICAzLiDlj5HluIPmtYvor5XniYjliLDnlJ/kuqfniYg=")
    Write-Host (T "ICA0LiDlm57mu5rnlJ/kuqfniYjliY3nq68=")
    Write-Host (T "ICA1LiDmn6XnnIvmtYvor5XniYjlkoznlJ/kuqfniYjnirbmgIE=")
    Write-Host (T "ICA2LiDlgZzmraLmtYvor5XniYg=")
    Write-Host (T "ICA3LiDlgZzmraLnlJ/kuqfniYg=")
    Write-Host (T "ICA4LiDlkK/liqjmtYvor5XniYg=")
    Write-Host (T "ICA5LiDlkK/liqjnlJ/kuqfniYg=")
    Write-Host (T "ICAwLiDpgIDlh7o=")
    Write-Host ""

    $choice = Read-Host (T "6K+36YCJ5oup5pON5L2c")

    switch ($choice) {
        "1" { Invoke-YisiAction "staging"; break }
        "2" { Invoke-YisiAction "production"; break }
        "3" { Invoke-YisiAction "publish"; break }
        "4" { Invoke-YisiAction "rollback"; break }
        "5" { Invoke-YisiAction "status"; break }
        "6" { Invoke-YisiAction "stop-staging"; break }
        "7" { Invoke-YisiAction "stop-production"; break }
        "8" { Invoke-YisiAction "start-staging"; break }
        "9" { Invoke-YisiAction "start-production"; break }
        "0" { exit 0 }
        default {
            Write-Host (T "5peg5pWI6YCJ5oup77yM6K+36YeN5paw6L6T5YWl44CC")
            Start-Sleep -Seconds 1
            continue
        }
    }

    Write-Host ""
    Read-Host (T "5oyJ5Zue6L2m6ZSu6L+U5Zue6I+c5Y2V")
}
