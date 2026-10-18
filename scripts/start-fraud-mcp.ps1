<#
 Starts the fraud MCP server (stdio) in its own environment. Point an MCP client (Claude Code, Claude Desktop) at the
 printed command. The server exposes read tools and propose_freeze only; approval stays in the Kairos UI.
 Usage:  .\scripts\start-fraud-mcp.ps1 -Site site_demo
#>
param([string]$Site = "site_demo", [string]$Python = "python")
$root = Split-Path -Parent $PSScriptRoot
if (-not $env:FALKORDB_URL) { $env:FALKORDB_URL = "redis://localhost:6380" }
$env:FRAUD_GRAPH_NAME = "fraud_$Site"          # the same per-site graph the Kairos fraud workspace uses
$env:PYTHONPATH = "$root\backend"
& $Python -c "import mcp, falkordb" 2>$null
if ($LASTEXITCODE) { throw "Install the MCP environment first: $Python -m pip install -r backend\requirements-mcp.txt (use a venv separate from the Kairos one)." }
& $Python -m domains.fraud.mcp_server
