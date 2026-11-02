# Celery worker on the Windows host (fallback path).
#
# `--pool=solo` is required here: Celery's default prefork pool does not support
# Windows. One job at a time, which is acceptable for local development and is
# why the real pool lives in the Linux container (`docker compose up worker`).
# Concurrency on the host is a documented limitation, not a silent downgrade.
param([int]$Concurrency = 1)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location "$root\backend"

if ($Concurrency -gt 1) {
    Write-Warning "Windows host worker uses --pool=solo; concurrency is fixed at 1. Use the container for parallel workers."
}

python -m uv run celery -A app.workers.celery_app.celery_app worker --loglevel INFO --pool solo
