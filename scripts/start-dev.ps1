# KrishiVaani - development mode (Windows PowerShell)
# Starts the FastAPI backend with reload and the Vite dev server.
# Usage:  .\scripts\start-dev.ps1
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
}

Write-Host "Starting API on http://127.0.0.1:$ApiPort (reload) ..." -ForegroundColor Cyan
$api = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--reload", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $Root -PassThru -NoNewWindow

try {
    Write-Host "Starting Vite on http://127.0.0.1:$WebPort ..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "frontend")
    try {
        npm run dev -- --port $WebPort
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($api -and -not $api.HasExited) {
        Write-Host "Stopping API process ..."
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
}
