# One-shot demo: seed data, start servers, run the sample Playwright suite.
# Prerequisites (once):
#   python -m venv .venv
#   .\.venv\Scripts\pip install -e ".\backend[dev]" -e ".\packages\pytest-testwarden[dev]" pytest-playwright
#   .\.venv\Scripts\python -m playwright install chromium
#   cd frontend; npm install
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not (Test-Path "$root\data\testwarden.db")) {
    Write-Host "Seeding demo data..."
    .\.venv\Scripts\python -m testwarden.seed
}

& "$PSScriptRoot\dev.ps1"

Write-Host "Waiting for backend..."
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-RestMethod "http://localhost:8787/api/v1/health" -TimeoutSec 2 | Out-Null
        break
    } catch { Start-Sleep -Milliseconds 500 }
}

$env:TESTWARDEN_API_KEY = (Get-Content "$root\data\demo_api_key.txt" -Raw).Trim()
Write-Host "Running the sample Playwright suite (1 flaky + 1 broken test on purpose)..."
Set-Location "$root\examples\sample-playwright-project"
& "$root\.venv\Scripts\python" -m pytest -q
Set-Location $root

Write-Host ""
Write-Host "Open http://localhost:5173 - the newest run in 'demo-web' is the one just reported."
