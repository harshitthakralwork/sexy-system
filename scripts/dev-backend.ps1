# FastAPI dev server with reload, on the host.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location "$root\backend"

python -m uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
