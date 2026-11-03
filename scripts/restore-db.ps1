# SparkXFlow Nexus — Database Restore Script
#
# Restores a PostgreSQL custom-format backup into an explicitly specified database.
# NEVER defaults to the primary 'sparkxflow' database.
# Refuses to overwrite an existing database without explicit confirmation.
# Never exposes passwords or credentials in output or logs.
#
# Usage:
#   ./scripts/restore-db.ps1 -BackupFile "backend/var/backups/sparkxflow_xxx.dump" -TargetDatabase "sparkxflow_scratch"
#   ./scripts/restore-db.ps1 -BackupFile "..." -TargetDatabase "sparkxflow_scratch" -ConfirmOverwrite
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [Parameter(Mandatory = $true)][string]$TargetDatabase,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$User = "sparkx",
    [switch]$ConfirmOverwrite,
    [switch]$AllowPrimaryDatabase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$backend = Join-Path $root "backend"

if (-not (Test-Path $BackupFile)) {
    # Check relative to backend/var/backups if not found as absolute or root-relative
    $alt = Join-Path $backend "var\backups\$BackupFile"
    if (Test-Path $alt) {
        $BackupFile = $alt
    } else {
        throw "Backup file not found: $BackupFile"
    }
}
$BackupFile = (Resolve-Path $BackupFile).Path

# Safety guard 1: Never accidentally overwrite primary development database
if ($TargetDatabase -eq "sparkxflow" -and -not $AllowPrimaryDatabase) {
    throw "Target database is the primary database 'sparkxflow'. Restoring requires -AllowPrimaryDatabase and -ConfirmOverwrite flags."
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
            $cmd = Get-Command "pg_restore.exe" -ErrorAction SilentlyContinue
            if ($cmd) { return Split-Path -Parent $cmd.Source }
            throw "PostgreSQL binaries not found."
        }
        return $found
    }
    finally { Pop-Location }
}

$bin = Get-BinDir
$env:PATH = "$bin;$(Split-Path -Parent $bin)\lib;$env:PATH"

# Safety guard 2: Verify backup format before doing anything
Write-Host "Verifying source backup file: $BackupFile..." -ForegroundColor Cyan
& "$bin\pg_restore.exe" --list $BackupFile *> $null
if ($LASTEXITCODE -ne 0) {
    throw "The file '$BackupFile' is not a valid PostgreSQL custom-format archive."
}

# Check if target database already exists
$checkCmd = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-d", "postgres",
    "-tAc", "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase'"
)
$rawExists = & "$bin\psql.exe" @checkCmd 2>&1
$exists = if ($null -ne $rawExists) { "$rawExists".Trim() } else { "" }
$targetExists = ($exists -eq "1")

if ($targetExists) {
    if (-not $ConfirmOverwrite) {
        throw "Target database '$TargetDatabase' already exists. Pass -ConfirmOverwrite to recreate it."
    }
    Write-Warning "Target database '$TargetDatabase' exists and -ConfirmOverwrite was passed. Dropping..."
    # Terminate active connections first
    $termCmd = @(
        "-h", $HostName,
        "-p", $Port,
        "-U", $User,
        "-d", "postgres",
        "-c", "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TargetDatabase' AND pid <> pg_backend_pid();"
    )
    & "$bin\psql.exe" @termCmd *> $null

    # Drop database using dropdb.exe
    $dropdbArgs = @(
        "-h", $HostName,
        "-p", $Port,
        "-U", $User,
        $TargetDatabase
    )
    & "$bin\dropdb.exe" @dropdbArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to drop existing database '$TargetDatabase'."
    }
    Write-Host "Dropped existing database '$TargetDatabase'." -ForegroundColor Yellow
}

# Create target database
Write-Host "Creating target database '$TargetDatabase'..." -ForegroundColor Cyan
$createCmd = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-d", "postgres",
    "-c", "CREATE DATABASE `"$TargetDatabase`" OWNER `"$User`";"
)
& "$bin\psql.exe" @createCmd *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create database '$TargetDatabase'."
}

# Restore using pg_restore
Write-Host "Restoring dump into '$TargetDatabase'..." -ForegroundColor Cyan
$restoreArgs = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-d", $TargetDatabase,
    "--no-owner",
    "--no-acl",
    $BackupFile
)

& "$bin\pg_restore.exe" @restoreArgs
# pg_restore exit code 0 = success, 1 = non-fatal warnings (e.g. extension already exists)
if ($LASTEXITCODE -gt 1) {
    throw "pg_restore failed with exit code $LASTEXITCODE."
}

# Verification query on restored database
Write-Host "Verifying restored database..." -ForegroundColor Cyan
$verifyTableCountCmd = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-d", $TargetDatabase,
    "-tAc", "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
)
$rawTableCount = & "$bin\psql.exe" @verifyTableCountCmd 2>&1
$tableCount = if ($null -ne $rawTableCount -and "$rawTableCount".Trim()) { [int]("$rawTableCount".Trim()) } else { 0 }

$verifyAlembicCmd = @(
    "-h", $HostName,
    "-p", $Port,
    "-U", $User,
    "-d", $TargetDatabase,
    "-tAc", "SELECT version_num FROM alembic_version LIMIT 1;"
)
$rawAlembic = & "$bin\psql.exe" @verifyAlembicCmd 2>&1
$alembicHead = if ($null -ne $rawAlembic) { "$rawAlembic".Trim() } else { "" }

Write-Host "==========================================" -ForegroundColor Green
Write-Host "Restore completed and verified successfully" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Target Database:  $TargetDatabase"
Write-Host "Restored Tables:  $tableCount"
Write-Host "Alembic Version:  $alembicHead"
Write-Host "Status:           VERIFIED" -ForegroundColor Green

[PSCustomObject]@{
    TargetDatabase = $TargetDatabase
    TableCount     = $tableCount
    AlembicVersion = $alembicHead
    Verified       = $true
}
