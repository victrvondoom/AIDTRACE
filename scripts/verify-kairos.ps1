<# Runs every test that backs the integrated features. Needs FalkorDB on 6380 (docker compose up -d kairos-falkordb)
   and the Python and npm dependencies installed. Prints a result per suite; exit code is non-zero on any failure. #>
$root = Split-Path -Parent $PSScriptRoot
$env:FALKORDB_TEST_URL = if ($env:FALKORDB_TEST_URL) { $env:FALKORDB_TEST_URL } else { "redis://127.0.0.1:6380" }
$env:GREENCHAIN_DATA_DIR = "$root\backend\domains\greenchain\data"
$failed = 0
$py = if (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" } else { "python" }
Push-Location "$root\backend"
& $py -m pytest tests/test_graphlab_algorithms.py tests/test_sources_catalog.py tests/test_consumer_port.py tests/test_greenchain_integration.py tests/greenchain tests/test_fraud_integration.py tests/fraud tests/test_resolveai_platform.py tests/test_drift_store.py -q -p no:cacheprovider; if ($LASTEXITCODE) { $failed++ }
Pop-Location
Push-Location $root
& $py -m pytest tests/test_authz_boundary.py tests/test_tenant_isolation.py -q -p no:cacheprovider; if ($LASTEXITCODE) { $failed++ }
Pop-Location
Push-Location "$root\frontend"
npx tsc --noEmit; if ($LASTEXITCODE) { $failed++ }
npx vitest run; if ($LASTEXITCODE) { $failed++ }
Pop-Location
if ($failed) { Write-Host "$failed suite(s) failed" -ForegroundColor Red; exit 1 } else { Write-Host "All suites passed" -ForegroundColor Green }