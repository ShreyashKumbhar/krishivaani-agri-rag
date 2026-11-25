# KrishiVaani - run the backend test suite (Windows PowerShell)
# Usage:  .\scripts\test.ps1
#         .\scripts\test.ps1 -Eval        # also run the 50-case evaluation
param(
    [switch]$Eval
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

Write-Host "== Backend tests ==" -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
try {
    & $python -m pytest
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($code -ne 0) { exit $code }

if ($Eval) {
    Write-Host ""
    Write-Host "== Evaluation (writes docs/EVALUATION_REPORT.md) ==" -ForegroundColor Cyan
    Push-Location (Join-Path $Root "backend")
    try {
        & $python -X utf8 -m app.evaluation
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "All backend tests passed." -ForegroundColor Green
