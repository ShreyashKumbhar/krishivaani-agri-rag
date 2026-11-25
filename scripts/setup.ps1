# KrishiVaani - one-time local setup (Windows PowerShell)
# Usage:  .\scripts\setup.ps1
#         .\scripts\setup.ps1 -SkipFrontend
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== KrishiVaani setup ==" -ForegroundColor Cyan
Write-Host "Project root: $Root"

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment at .venv ..."
    python -m venv .venv
}

Write-Host "Installing backend requirements ..."
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -r (Join-Path $Root "backend\requirements.txt")

if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm is required for the frontend build. Install Node.js 20+ or rerun with -SkipFrontend."
    }
    Write-Host "Installing frontend dependencies ..."
    Push-Location (Join-Path $Root "frontend")
    try {
        npm ci
        Write-Host "Building frontend ..."
        npm run build
    }
    finally {
        Pop-Location
    }
}

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Write-Host "Created .env from .env.example (defaults need no API keys)."
}
else {
    Write-Host ".env already exists; leaving it unchanged."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start the app with:  .\scripts\start.ps1"
Write-Host "Open:                http://127.0.0.1:8000"
