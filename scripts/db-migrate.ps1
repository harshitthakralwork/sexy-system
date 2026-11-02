# Apply all pending migrations to the database in .env.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location "$root\backend"

python -m uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nMigration failed. Is PostgreSQL running? ./scripts/infra-up.ps1" -ForegroundColor Yellow
    Write-Host "Windows-native alternative: docs/RUNBOOK-DOCKER.md"
    exit $LASTEXITCODE
}

python -m uv run alembic current
