# SparkXFlow Nexus — first-run setup (Windows)
# Creates .env from the template and installs both toolchains. Idempotent.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $root

Write-Host "== SparkXFlow Nexus bootstrap ==" -ForegroundColor Cyan

if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "Created .env from .env.example" -ForegroundColor Green
    Write-Host "Fill in SPARKX_SIGNING_SECRET and SEARXNG_SECRET before starting the stack." -ForegroundColor Yellow
    Write-Host "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
} else {
    Write-Host ".env already exists; left untouched" -ForegroundColor DarkGray
}

Write-Host "`n-- Backend (uv, Python 3.12 pinned by backend/pyproject.toml) --" -ForegroundColor Cyan
Push-Location "$root\backend"
try {
    python -m uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
}
finally { Pop-Location }

Write-Host "`n-- Frontend (npm) --" -ForegroundColor Cyan
Push-Location "$root\frontend"
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
}
finally { Pop-Location }

Write-Host "`nBootstrap complete." -ForegroundColor Green
Write-Host "Next: install Docker Desktop (docs/RUNBOOK-DOCKER.md), then ./scripts/infra-up.ps1"
