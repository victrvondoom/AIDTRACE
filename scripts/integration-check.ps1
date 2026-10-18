<# Verifies the integrated backend slice. Needs FalkorDB on 6380 (docker compose up -d kairos-falkordb). Prints one result per suite. #>
$root = Split-Path -Parent $PSScriptRoot
$env:FALKORDB_TEST_URL = if ($env:FALKORDB_TEST_URL) { $env:FALKORDB_TEST_URL } else { "redis://127.0.0.1:6380" }
$py = if (Test-Path "$root\.venv\Scripts\python.exe") { "$root\.venv\Scripts\python.exe" } else { "python" }
Push-Location "$root\backend"
& $py -m pytest tests/test_graphlab_algorithms.py tests/test_sources_catalog.py tests/test_consumer_port.py tests/test_drift_store.py -q -p no:cacheprovider
Pop-Location
Push-Location "$root"
& $py -m pytest tests/test_authz_boundary.py tests/test_tenant_isolation.py -q -p no:cacheprovider
Pop-Location
Push-Location "$root\frontend"; npx vitest run; npx tsc --noEmit; Pop-Location
