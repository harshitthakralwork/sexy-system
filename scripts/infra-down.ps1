# Stop infrastructure. Data lives in named volumes and survives.
# Usage: ./scripts/infra-down.ps1          (stop)
#        ./scripts/infra-down.ps1 -Purge   (stop and delete volumes — destroys the database)
param([switch]$Purge)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $root

if ($Purge) {
    Write-Host "Purging volumes: PostgreSQL data and Redis queue state will be deleted." -ForegroundColor Red
    $confirm = Read-Host "Type 'purge' to confirm"
    if ($confirm -ne "purge") { Write-Host "Aborted."; exit 1 }
    docker compose down -v
} else {
    docker compose down
}
