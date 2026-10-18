# Track 01 migration

| Capability | Destination | State |
|---|---|---|
| Consumer remedy engine, verifier, intake, simulation | `backend/api/services/consumer` | Ported, 19 tests, browser-verified |
| Interdict min-cost cut (MIT, Yash Soni) | `consumer/interdict_cut.py` | Ported with notice in `THIRD_PARTY_NOTICES.md` |
| Fraud graph tools, freeze policy, investigator, actions, seed | `backend/domains/fraud` | Ported; the original 11 tests pass; 4 Kairos integration tests |
| Agent runtime trace + native UI | `FraudWorkspace.tsx` | Browser-verified (32-event run, approval with receipt) |
| Added in Kairos | `routers/fraud.py` | Tenant graphs, approver = signed-in user, approval refused and proposal INVALIDATED if the ring changed since proposal |
| MCP server | `domains/fraud/mcp_server.py` | Ported; transport blocked by pydantic pin; run as a private process |
| Claude planner | investigator | Needs `ANTHROPIC_API_KEY` |
| Capability registry and 98-repo audit | `backend/api/services/sources`, Capability Workbench | README library and ledger done; 60+ README mechanisms not implemented |