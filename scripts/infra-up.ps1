# Start the local infrastructure: PostgreSQL, Redis, self-hosted SearXNG.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $root

if (-not (Test-Path "$root\.env")) {
    throw "No .env found. Run ./scripts/bootstrap.ps1 first."
}

# SearXNG refuses to boot with an empty secret key and would crash-loop with a
# message that does not mention the real cause. Check before starting it.
$secretLine = Select-String -Path "$root\.env" -Pattern '^\s*SEARXNG_SECRET\s*=\s*(.+)?' |
    Select-Object -First 1
$secret = if ($secretLine) { ($secretLine.Matches[0].Groups[1].Value).Trim() } else { "" }

if ([string]::IsNullOrWhiteSpace($secret)) {
    Write-Warning "SEARXNG_SECRET is empty in .env. Starting PostgreSQL and Redis only."
    Write-Host "  Generate one: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    Write-Host "  Then re-run this script to bring SearXNG up."
    $services = @("postgres", "redis")
} else {
    $services = @("postgres", "redis", "searxng")
}

docker compose up -d @services
if ($LASTEXITCODE -ne 0) {
    Write-Host "`ndocker compose failed. Is Docker Desktop running?" -ForegroundColor Yellow
    Write-Host "Start it, or follow docs/RUNBOOK-DOCKER.md for the Windows-native fallback."
    exit $LASTEXITCODE
}

docker compose ps
