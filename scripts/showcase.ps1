# Repeatable demo setup for recording the launch video.
# Gets everything into a clean, camera-ready state, then prints the click-path.
#
# Prereqs (once): the normal dev install (see README Quickstart), ANTHROPIC_API_KEY
# in .env (for the live author/SelfHeal moments), and the demo project's repo_url
# pointing at this repo so SelfHeal can clone it.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host "== FlakeLens showcase setup ==" -ForegroundColor Cyan

# 1. Fresh seeded data so the dashboard looks alive and identical every take.
if (Test-Path "data\flakelens.db") {
    Write-Host "Reseeding demo data (fresh state for the recording)..."
    Remove-Item "data\flakelens.db" -Force
}
Remove-Item -Recurse -Force "data\agent-workspaces" -ErrorAction SilentlyContinue
.\.venv\Scripts\python -m flakelens.seed | Out-Null

# 2. Serve the starter-kit site so the author agent has a real app to drive.
$existing = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*http.server*9099*" }
if (-not $existing) {
    Start-Process -WindowStyle Hidden -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "-m","http.server","9099","--directory","examples/starter-kit/site"
    Start-Sleep 2
}
Write-Host "Demo app serving at http://localhost:9099/"

# 3. Point the demo project at this repo (for SelfHeal) and confirm servers.
try {
    Invoke-RestMethod -Method PATCH "http://localhost:8787/api/v1/projects/demo-web" `
        -ContentType 'application/json' -Body '{"repo_url": "C:\\Users\\brahm\\claude code"}' | Out-Null
    Write-Host "demo-web repo_url set (SelfHeal can clone)."
} catch {
    Write-Host "!! Backend not running — start it first: .\scripts\dev.ps1" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "== Ready to record. Click-path for the video: ==" -ForegroundColor Green
Write-Host @"
  0:00  Dashboard → Overview (demo-web): show the Health grade + 'What should I do today?'
  0:15  Write a test (AI): type "A user can log in with standard_user / secret and see the
        catalog", URL http://localhost:9099/ → Write my test → show the agent driving the
        browser, the generated test, and the 'verified green' badge.
  0:45  Runs → open the failing run → click a failure → ✨ Analyze → 🩹 Launch SelfHeal →
        show the live log, the diff, and (with a GITHUB_TOKEN) the PR link.
  1:10  Quarantine board + Incidents: the closed loop and root-cause clustering.
  1:20  End card: 'FlakeLens — every tool tells you a test is flaky. FlakeLens fixes it.'
"@ -ForegroundColor Gray
"Open http://localhost:5173  and start recording."
