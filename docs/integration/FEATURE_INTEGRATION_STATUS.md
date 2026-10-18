# Feature integration status (2026-10-18)

Integrated and tested = native UI + real backend + tests. Everything else is listed as unfinished.

| Feature | Status | Evidence |
|---|---|---|
| ResolveAI consumer remedy | Integrated, tested | `backend/tests/test_consumer_port.py` 19 passed (live FalkorDB); browser: revision hash and verdict reasons changed after an evidence edit |
| Graph engines (10) | Integrated, tested | `test_graphlab_algorithms.py` (min-cut matches a brute-force oracle; blast radius matches the drift engine); `min_cut` also browser-verified |
| Source library and ledger | Integrated, tested | `test_sources_catalog.py`; SHA-256 of every README checked |
| Evidence drift on the site graph | Integrated, tested | Lab blast radius equals `FalkorDriftStore.find_impacts` on real FalkorDB |
| Fraud / Cybersecurity workspaces | **Partial** | Engines run on synthetic or pasted graphs. No production data feed |
| Agent runtime, MCP, Track 01 fraud flow, RESOLVE-AI-main | **Not migrated** | See the feature map |
| Simulations workspace, Reports | **Not built** | |