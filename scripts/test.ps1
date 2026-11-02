# Quality gates for the whole project (roadmap section 11).
# Runs lint, type check and tests for both stacks. Fails fast and honestly.
Set-StrictMode -Version Latest

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$failures = @()

function Invoke-Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host "`n== $Name ==" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Name (exit $LASTEXITCODE)" -ForegroundColor Red
        $script:failures += $Name
    } else {
        Write-Host "PASS: $Name" -ForegroundColor Green
    }
}

Push-Location "$root\backend"
try {
    Invoke-Step "backend: ruff" { python -m uv run ruff check app tests migrations }
    Invoke-Step "backend: mypy" { python -m uv run mypy app }
    Invoke-Step "backend: pytest" { python -m uv run pytest }
}
finally { Pop-Location }

Push-Location "$root\frontend"
try {
    Invoke-Step "frontend: eslint" { npm run lint }
    Invoke-Step "frontend: tsc" { npx tsc --noEmit }
}
finally { Pop-Location }

Write-Host "`n================ SUMMARY ================"
if ($failures.Count -eq 0) {
    Write-Host "All quality gates passed." -ForegroundColor Green
    exit 0
}
Write-Host ("Failed: " + ($failures -join ", ")) -ForegroundColor Red
exit 1
