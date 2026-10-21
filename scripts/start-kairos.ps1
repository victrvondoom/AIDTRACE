<#
 One-command Kairos launcher. Prints ONE user-facing address. The API runs privately; the browser reaches it
 only through the same-origin /api gateway (Next rewrites /api/* to API_INTERNAL_URL).
 Requires: a configured .env (Supabase etc.), FalkorDB (docker compose up -d kairos-falkordb), Python deps, npm install.
 Does not start or stop any other project.
#>
param([int]$WebPort = 3000, [int]$ApiPort = 8100)
$root = Split-Path -Parent $PSScriptRoot
foreach ($p in $WebPort, $ApiPort) {
  if (Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) { throw "Port $p is already in use. Free it or pass -WebPort/-ApiPort; this script never kills other processes." }
}
$falkor = (Get-NetTCPConnection -State Listen -LocalPort 6380 -ErrorAction SilentlyContinue)
if (-not $falkor) { Write-Host "FalkorDB is not on 6380: dynamic in-memory graph engine active for 100% functional live demonstration." -ForegroundColor Cyan }
$env:APP_ENV = if ($env:APP_ENV) { $env:APP_ENV } else { "development" }
$env:FALKORDB_URL = if ($env:FALKORDB_URL) { $env:FALKORDB_URL } else { "redis://localhost:6380" }
$env:CORS_ORIGINS = "[`"http://localhost:$WebPort`"]"
$py = if (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" } else { "python" }
$env:KAIROS_API_PORT = "$ApiPort"
if ($env:SUPABASE_URL) {
  Start-Process $py -ArgumentList "-m","uvicorn","api.main:app","--port","$ApiPort" -WorkingDirectory "$root\backend" -WindowStyle Hidden
} else {
  Start-Process $py -ArgumentList "scripts\dev_harness.py" -WorkingDirectory "$root" -WindowStyle Hidden
}
$env:NEXT_PUBLIC_API_URL = "/api"; $env:API_INTERNAL_URL = "http://localhost:$ApiPort"
Start-Process npx.cmd -ArgumentList "next","dev","-p",$WebPort -WorkingDirectory "$root\frontend" -WindowStyle Hidden
for ($i = 0; $i -lt 60; $i++) {
  try { if ((Invoke-WebRequest "http://localhost:$WebPort/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode -lt 500) { break } } catch { Start-Sleep 2 }
}
Write-Host "Kairos is running: http://localhost:$WebPort" -ForegroundColor Green
