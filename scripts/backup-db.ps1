# SparkXFlow Nexus — Database Backup Script
#
# Generates a timestamped, custom-format PostgreSQL backup under backend/var/backups/.
# Verifies the dump with pg_restore --list before confirming success.
# Never exposes passwords or credentials in output or logs.
#
# Usage:
#   ./scripts/backup-db.ps1
#   ./scripts/backup-db.ps1 -Database sparkxflow -User sparkx
[CmdletBinding()]
param(
    [string]$Database = "sparkxflow",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$User = "sparkx",
    [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backend = Join-Path $root "backend"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $backend "var\backups"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

function Get-BinDir {
    Push-Location $backend
    try {
        $lines = python -m uv run python -c "import postgresql_binaries as p; print(p.bin())" 2>&1
        $found = $null
        foreach ($line in $lines) {
            $text = "$line".Trim()
            if ($text -and (Test-Path $text)) { $found = $text; break }
        }
        if (-not $found) {
            $cmd = Get-Command "pg_dump.exe" -ErrorAction SilentlyContinue
            if ($cmd) { return Split-Path -Parent $cmd.Source }
            throw "PostgreSQL binaries not found. Ensure backend toolchain or postgresql-binaries is installed."
        }
        return $found
    }
    finally { Pop-Location }
}

$bin = Get-BinDir
$env:PATH = "$bin;$(Split-Path -Parent $bin)\lib;$env:PATH"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "${Database}_${timestamp}.dump"
$backupPath = Join-Path $OutputDir $fileName

if (Test-Path $backupPath) {
    throw "Backup destination already exists: $backupPath. Refusing to overwrite."
}

Write-Host "Starting backup for database '$Database'..." -ForegroundColor Cyan

# Custom format: -F c (compressed archive with TOC, suitable for pg_restore)
# -b: include large objects; -v: verbose; --no-owner: portable restore
$dumpArgs = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-F", "c",
    "-b",
    "-f", $backupPath,
    $Database
)

& "$bin\pg_dump.exe" @dumpArgs
if ($LASTEXITCODE -ne 0) {
    if (Test-Path $backupPath) {
        Remove-Item -Force $backupPath
    }
    throw "pg_dump failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path $backupPath)) {
    throw "Backup completed but output file not found: $backupPath"
}

$fileItem = Get-Item $backupPath
$fileSize = $fileItem.Length

# Verify archive integrity with pg_restore --list
Write-Host "Verifying backup archive..." -ForegroundColor Cyan
$tocLines = & "$bin\pg_restore.exe" --list $backupPath
if ($LASTEXITCODE -ne 0) {
    throw "Backup verification failed: pg_restore --list returned exit code $LASTEXITCODE."
}

$entryCount = ($tocLines | Where-Object { $_ -and -not $_.StartsWith(";") }).Count

Write-Host "==========================================" -ForegroundColor Green
Write-Host "Backup completed and verified successfully" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Database:     $Database"
Write-Host "Path:         $backupPath"
Write-Host "Size:         $fileSize bytes ($([math]::Round($fileSize / 1KB, 2)) KB)"
Write-Host "Timestamp:    $(Get-Date -Date $fileItem.CreationTime -Format 'yyyy-MM-dd HH:mm:ss UTCzz')"
Write-Host "TOC Entries:  $entryCount"
Write-Host "Status:       VERIFIED" -ForegroundColor Green

[PSCustomObject]@{
    Database   = $Database
    Path       = $backupPath
    Size       = $fileSize
    Timestamp  = $timestamp
    Verified   = $true
    EntryCount = $entryCount
}

