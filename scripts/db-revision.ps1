# Autogenerate a migration from the ORM models, then STOP AND READ IT.
# Autogenerate is a draft tool: it cannot know about data migrations, index
# choices, or the extensions revision, and it will happily generate a drop.
param([Parameter(Mandatory = $true)][string]$Message)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location "$root\backend"

python -m uv run alembic revision --autogenerate -m $Message
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nReview the new file in migrations/versions/ before running db-migrate.ps1." -ForegroundColor Yellow
