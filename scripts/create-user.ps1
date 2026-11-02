# Create the first SparkXFlow account against a running local API.
#
# Registration is open by default so a fresh install can be claimed once. After
# that, set SPARKX_ALLOW_REGISTRATION=false in .env: an always-open signup turns
# a private tool into a hosted one the moment a port is forwarded.
#
#   ./scripts/create-user.ps1 -Email you@example.com -DisplayName "You"
#   ./scripts/create-user.ps1 -Email you@example.com -Password "chosen here"
#
# There is no password-change endpoint yet (a Phase 2 gap), so pass -Password if
# you want something other than the generated one.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [string]$DisplayName = "",
    [string]$Password = ""
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$apiBase = if ($env:SPARKX_API_BASE) { $env:SPARKX_API_BASE } else { "http://127.0.0.1:8000" }

if ([string]::IsNullOrWhiteSpace($DisplayName)) {
    $DisplayName = ($Email -split "@")[0]
}

$generated = $false
if ([string]::IsNullOrWhiteSpace($Password)) {
    # 16 characters from an ambiguous-free alphabet; the backend requires 12.
    $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#"
    $Password = -join (1..16 | ForEach-Object { $chars | Get-Random })
    $generated = $true
}

$body = @{ email = $Email; password = $Password; display_name = $DisplayName } | ConvertTo-Json

try {
    $created = Invoke-RestMethod -Uri "$apiBase/api/v1/auth/register" -Method Post `
        -ContentType "application/json" -Body $body
    Write-Host "Created account $($created.id)" -ForegroundColor Green
} catch {
    $response = $_.Exception.Response
    if ($null -ne $response) {
        $status = [int]$response.StatusCode
        # The body carries the real reason (invalid email, password too short,
        # registration closed). Without it the operator sees only a socket error.
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $detail = $reader.ReadToEnd()
        $reader.Close()

        if ($status -eq 409) {
            Write-Host "An account with $Email already exists. Sign in instead." -ForegroundColor Yellow
            exit 0
        }
        Write-Host "Registration failed (HTTP $status):" -ForegroundColor Red
        Write-Host "  $detail"
        Write-Host "`nNote: reserved domains such as .test, .example and .local are rejected"
        Write-Host "by email validation. Use a normal address, e.g. you@sparkxflow.dev"
        exit 1
    }
    Write-Host "Could not reach the API at $apiBase. Is ./scripts/dev-backend.ps1 running?" -ForegroundColor Red
    throw
}

if ($generated) {
    Write-Host "`nSign in with:" -ForegroundColor Cyan
    Write-Host "  email:    $Email"
    Write-Host "  password: $Password"
    Write-Host "`nShown once, and not stored in the repository. There is no password-change"
    Write-Host "endpoint yet, so record it somewhere safe."
} else {
    Write-Host "Sign in as $Email with the password you supplied." -ForegroundColor Cyan
}
