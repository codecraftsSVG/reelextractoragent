# Start backend (8000) + frontend (5173) locally with SQLite test DB.
$ErrorActionPreference = 'Stop'

Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(8000,5173) } | ForEach-Object {
  try { Stop-Process -Id $_.OwningProcess -Force } catch {}
}
Start-Sleep -Seconds 2

$env:DATABASE_URL = 'sqlite:///./storage/test_reel.db'
$be = Start-Process -FilePath '.venv\Scripts\python' `
  -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' `
  -RedirectStandardOutput 'storage/logs/backend.out' -RedirectStandardError 'storage/logs/backend.err' -PassThru
Write-Output "backend pid=$($be.Id) on :8000"

$ok = $false
for ($i=0; $i -lt 25; $i++) {
  try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { Write-Output "backend UP: $($r.Content)"; $ok = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) {
  Write-Output "backend FAILED; err:"; Get-Content storage/logs/backend.err -ErrorAction SilentlyContinue | Select-Object -Last 15; exit 1
}

Write-Output "starting frontend..."
Push-Location frontend
$fe = Start-Process -FilePath 'cmd.exe' `
  -ArgumentList '/c','npm run dev -- --host 127.0.0.1 --port 5173' `
  -RedirectStandardOutput '..\storage\logs\frontend.out' -RedirectStandardError '..\storage\logs\frontend.err' -PassThru
Pop-Location
Write-Output "frontend pid=$($fe.Id) on :5173"

$ok = $false
for ($i=0; $i -lt 35; $i++) {
  try {
    $f = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
    if ($f.StatusCode -eq 200 -and $f.Content -match 'root') { Write-Output "frontend UP :5173"; $ok = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) {
  Write-Output "frontend FAILED; err:"; Get-Content storage/logs/frontend.err | Select-Object -Last 15; exit 1
}

Write-Output "--- end-to-end (vite proxy -> fastapi) ---"
$p = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/jobs' -UseBasicParsing -TimeoutSec 5
Write-Output "proxy 5173/jobs -> $($p.StatusCode) $($p.Content)"
$b = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/jobs' -UseBasicParsing -TimeoutSec 5
Write-Output "direct 8000/jobs -> $($b.StatusCode) $($b.Content)"
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(8000,5173) } |
  Format-Table LocalAddress,LocalPort,OwningProcess -AutoSize
Write-Output "open http://127.0.0.1:5173/ in your browser"
