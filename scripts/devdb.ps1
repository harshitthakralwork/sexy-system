# SparkXFlow Nexus — local development PostgreSQL, with no administrator rights.
#
# Uses the `postgresql-binaries` dev-only Python package, which ships real
# PostgreSQL 18 binaries. This is a DEVELOPMENT database: production still runs
# the container image from docker-compose.yml. The binaries are a third-party
# repackaging, so they stay under the `dev` dependency extra and must never
# appear in a runtime dependency set.
#
# Usage:
#   ./scripts/devdb.ps1            start (initialising the cluster on first run)
#   ./scripts/devdb.ps1 -Status    report whether it is running
#   ./scripts/devdb.ps1 -Stop      stop it
#   ./scripts/devdb.ps1 -Reset     delete the data directory (DESTROYS ALL DATA)
#
# Listens on 127.0.0.1 only, with trust authentication. That is acceptable only
# because it never binds a routable interface; do not reuse this setup anywhere
# a real request could reach it.
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$Reset
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backend = Join-Path $root "backend"
$data = Join-Path $backend ".devdb\data"
$logfile = Join-Path $backend ".devdb\pg.log"
$port = 5432
$user = "sparkx"
$dbname = "sparkxflow"

function Get-BinDir {
    Push-Location $backend
    try {
        $lines = python -m uv run python -c "import postgresql_binaries as p; print(p.bin())" 2>&1
        $found = $null
        foreach ($line in $lines) {
            $text = "$line".Trim()
            if ($text -and (Test-Path $text)) { $found = $text; break }
        }
        if (-not $found) { throw "postgresql-binaries is not installed. Run ./scripts/bootstrap.ps1" }
        return $found
    }
    finally { Pop-Location }
}

function Set-BinPath {
    param([string]$Bin)
    # Required, not cosmetic. The postmaster spawns one child process per
    # connection; those children resolve their DLLs from the bin directory.
    # Without it on PATH every backend dies with 0xC0000142 (DLL init failed)
    # and the postmaster tears itself down — the server looks healthy while
    # refusing every actual query.
    $env:PATH = "$Bin;$(Split-Path -Parent $Bin)\lib;$([System.Environment]::GetEnvironmentVariable('PATH'))"
}

function Test-Running {
    param([string]$Bin)
    & "$Bin\pg_ctl.exe" -D $data status *> $null
    return ($LASTEXITCODE -eq 0)
}

$bin = Get-BinDir
Set-BinPath -Bin $bin

if ($Reset) {
    if (-not (Test-Path $data)) { Write-Host "No data directory to remove."; exit 0 }
    Write-Host "This deletes every table, migration and record in the development database." -ForegroundColor Red
    $confirm = Read-Host "Type 'reset' to confirm"
    if ($confirm -ne "reset") { Write-Host "Aborted."; exit 1 }
    if (Test-Running -Bin $bin) { & "$bin\pg_ctl.exe" -D $data stop -m fast | Out-Null }
    Remove-Item -Recurse -Force $data
    Write-Host "Development cluster removed." -ForegroundColor Green
    exit 0
}

if ($Status) {
    if (Test-Running -Bin $bin) { Write-Host "PostgreSQL is running on 127.0.0.1:$port" -ForegroundColor Green }
    else { Write-Host "PostgreSQL is not running." -ForegroundColor Yellow }
    exit 0
}

if ($Stop) {
    if (Test-Running -Bin $bin) {
        & "$bin\pg_ctl.exe" -D $data stop -m fast | Out-Null
        Write-Host "Stopped." -ForegroundColor Green
    }
    else { Write-Host "Was not running." }
    exit 0
}

if (-not (Test-Path $data)) {
    Write-Host "Initialising cluster at $data" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $data) | Out-Null
    & "$bin\initdb.exe" -D $data -U $user --auth=trust --encoding=UTF8 --no-sync
    if ($LASTEXITCODE -ne 0) { throw "initdb failed" }
}

if (-not (Test-Running -Bin $bin)) {
    & "$bin\pg_ctl.exe" -D $data -l $logfile -w -t 60 start `
        -o "-p $port -c listen_addresses=127.0.0.1"
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed; see $logfile" }
}

# Checked rather than blindly created, so repeat starts stay quiet.
$exists = & "$bin\psql.exe" -h 127.0.0.1 -p $port -U $user -d postgres -Atc `
    "SELECT 1 FROM pg_database WHERE datname = '$dbname'"
if (-not $exists) {
    & "$bin\createdb.exe" -h 127.0.0.1 -p $port -U $user -O $user $dbname
    if ($LASTEXITCODE -ne 0) { throw "createdb failed" }
    Write-Host "Created database $dbname" -ForegroundColor Green
}

& "$bin\psql.exe" -h 127.0.0.1 -p $port -U $user -d $dbname -qc "CREATE EXTENSION IF NOT EXISTS pgcrypto"
& "$bin\psql.exe" -h 127.0.0.1 -p $port -U $user -d $dbname -qc "CREATE EXTENSION IF NOT EXISTS pg_trgm"

$version = & "$bin\psql.exe" -h 127.0.0.1 -p $port -U $user -d $dbname -Atc "SELECT version()"
Write-Host "PostgreSQL ready: $version" -ForegroundColor Green
Write-Host "Connection string: postgresql+asyncpg://$user@127.0.0.1:$port/$dbname"
