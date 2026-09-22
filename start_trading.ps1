<#
Start the whole paper-trading stack: database, cache, API (with the autonomous
trader) and dashboard.

    powershell -ExecutionPolicy Bypass -File .\start_trading.ps1

The trader idles outside NSE regular hours and begins trading by itself at the
9:15 IST open, so this only needs to be running before then. Nothing here places
a real-money order: there is no broker integration in this system.
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Wait-For($url, $name, $tries = 40) {
    for ($i = 0; $i -lt $tries; $i++) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true }
        catch { Start-Sleep -Milliseconds 1500 }
    }
    Write-Host "  $name did not come up" -ForegroundColor Red
    return $false
}

Write-Host "1/4  Docker (TimescaleDB + Redis)..." -ForegroundColor Cyan
$dockerOk = $false
try { docker version --format '{{.Server.Version}}' | Out-Null; $dockerOk = $true } catch {}
if (-not $dockerOk) {
    $exe = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    if (Test-Path $exe) {
        Start-Process $exe
        for ($i = 0; $i -lt 60; $i++) {
            try { docker version --format '{{.Server.Version}}' | Out-Null; $dockerOk = $true; break }
            catch { Start-Sleep -Seconds 5 }
        }
    }
}
if (-not $dockerOk) { throw "Docker is not available; start Docker Desktop and re-run." }
docker compose up -d postgres redis | Out-Null

Write-Host "2/4  Waiting for the database..." -ForegroundColor Cyan
for ($i = 0; $i -lt 40; $i++) {
    $s = docker inspect -f '{{.State.Health.Status}}' tradebot-postgres-1 2>$null
    if ($s -eq "healthy") { break }
    Start-Sleep -Seconds 3
}

Write-Host "3/4  API + autonomous trader on :8001..." -ForegroundColor Cyan
$env:PYTHONPATH = "$root\backend"
$log = Join-Path $root "logs"
New-Item -ItemType Directory -Force $log | Out-Null
$api = Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001" `
    -WorkingDirectory $root `
    -RedirectStandardOutput "$log\api.log" -RedirectStandardError "$log\api.err.log" `
    -WindowStyle Hidden -PassThru
if (-not (Wait-For "http://127.0.0.1:8001/health" "API")) { throw "API failed to start; see logs\api.err.log" }

Write-Host "4/4  Dashboard on :3000..." -ForegroundColor Cyan
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8001"
$npm = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
$web = Start-Process -FilePath $npm -ArgumentList "run", "start" `
    -WorkingDirectory "$root\frontend" `
    -RedirectStandardOutput "$log\web.log" -RedirectStandardError "$log\web.err.log" `
    -WindowStyle Hidden -PassThru
Wait-For "http://localhost:3000/" "Dashboard" | Out-Null

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:3000"
Write-Host "  API docs  : http://127.0.0.1:8001/docs"
Write-Host "  Trader    : http://127.0.0.1:8001/api/v1/orchestrator/autotrader/status"
Write-Host "  PIDs      : api=$($api.Id) web=$($web.Id)   logs in .\logs\"
Write-Host ""
try {
    $st = Invoke-RestMethod "http://127.0.0.1:8001/api/v1/orchestrator/autotrader/status" -TimeoutSec 10
    Write-Host ("  running={0}  session={1}  strategies={2}  interval={3}s" -f `
        $st.running, $st.market_session, $st.strategies, $st.interval_seconds)
} catch {}
