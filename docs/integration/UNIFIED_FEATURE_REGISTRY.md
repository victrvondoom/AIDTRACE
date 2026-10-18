# Unified feature registry

Frontend registry: `frontend/src/features/feature-host.tsx` (`FEATURES`). Backend capability list: `GET /graphlab/algorithms`, `GET /sources/ledger`, and `COMPLETE_MERGER_LEDGER.csv` (stage flags per feature). Statuses: OPERATIONAL, VERIFIED_DEMO, EXPERIMENTAL, NOT_CONNECTED, PLANNED.

Workspaces in `/hub`: Overview (clickable capability graph), GreenChain, ResolveAI (consumer engine + platform panel), Fraud Intelligence, Cybersecurity, Evidence Drift & Memory, Graph Explorer, Capability Workbench. A workspace is listed here only if its code executes and produces a meaningful result; unconnected pieces are shown inside their workspace with the reason.