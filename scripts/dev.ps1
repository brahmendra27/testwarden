# Start TestWarden backend + frontend for local development (SQLite, no Docker needed).
$root = Split-Path $PSScriptRoot -Parent

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root'; .\.venv\Scripts\python -m uvicorn testwarden.main:app --port 8787 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root\frontend'; npm run dev"

Write-Host "Backend:  http://localhost:8787/api/v1/health"
Write-Host "Frontend: http://localhost:5173"
