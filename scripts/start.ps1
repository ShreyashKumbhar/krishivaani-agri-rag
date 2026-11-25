# KrishiVaani - production-style local start (Windows PowerShell)
# Serves the built React app and the API from one FastAPI process.
# Usage:  .\scripts\start.ps1 [-Port 8000] [-Host 127.0.0.1] [-Reload]
param(
    [int]$Port = 8000,
    [string]$Host = "127.0.0.1",
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

$dist = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $dist)) {
    Write-Warning "frontend\dist is missing. Run .\scripts\setup.ps1 or 'npm run build' in frontend\."
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Host "Created .env from .env.example."
}

$uvicornArgs = @(
    "-m", "uvicorn", "app.main:app",
    "--app-dir", "backend",
    "--host", $Host,
    "--port", "$Port"
)
if ($Reload) { $uvicornArgs += "--reload" }

Write-Host "Starting KrishiVaani on http://${Host}:${Port}" -ForegroundColor Cyan
Write-Host "API docs: http://${Host}:${Port}/docs"
& $python @uvicornArgs
