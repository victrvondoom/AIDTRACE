# Standalone to native feature map

| Standalone feature | Native Kairos destination | State |
|---|---|---|
| track1 consumer console (`frontend/app/consumer`) | Hub, ResolveAI workspace | Ported with its backend; 19 tests |
| track1 consumer engine (`backend/app/consumer`, `remedy_conflicts`, `interdict_cut`) | `backend/api/services/consumer` | Ported; tests live against FalkorDB |
| track1 capabilities page | Hub, Capability Workbench and `/sources` | Replaced by the 98-repo library and engine registry |
| 98 research READMEs | `backend/api/services/sources/readmes` (95 of 98; 3 had none) | Collected byte-for-byte |
| README mechanisms | `services/graphlab` (10 engines covering ~60 repos) | Clean-room implementations |
| track1 fraud workflow, agent runtime, MCP server | none | **Not migrated** |
| RESOLVE-AI-main platform | none | **Not migrated** |