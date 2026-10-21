# Catalyst inside AIDtrace

AIDtrace is the product (this repository, Kairos). Catalyst, the electrode-material batch QC from FIB-SEM images, now lives in
`integrations/catalyst` and is reached through AIDtrace's API. The supply-chain physics layer is part of AIDtrace itself.

**Verified against:** the Kairos backend and the Catalyst code as they stand after this merge, with the worker running live.
**Not verified:** a real batch run (see "Not verified" below).

## What changed

| Piece | Where | Notes |
|---|---|---|
| Catalyst folder | `integrations/catalyst/` | Moved from `GRAPH HACKS/catalyst-main`. Changed only as listed under "Catalyst code changes" |
| Catalyst worker launcher | `scripts/start_catalyst_worker.py` | Starts `qc.api:app` on 127.0.0.1:8300 from Catalyst's own virtualenv |
| Catalyst gateway | `backend/api/routers/catalyst_platform.py`, mounted at `/catalyst` | Staff only, demo closed, allow-listed routes |
| Physics and mathematics | `backend/domains/physics/` (`cold_chain`, `thermal`, `flow`), `backend/api/routers/physics.py`, mounted at `/physics` | Pure formulas, no stored data, no model call |
| Dev harness | `scripts/dev_harness.py` | Also reads the Catalyst gateway secret |
| Kairos frontend | unchanged | `git status -- frontend` is empty |

## Why a separate worker and not an in-process import

Kairos and Catalyst pin different versions of the same core packages. Merging them into one environment would mean upgrading
Kairos's whole stack, which is the main product:

| Package | Kairos (`backend/requirements.txt`) | Catalyst (`integrations/catalyst`, `uv.lock`) |
|---|---|---|
| pydantic | 2.7.4 | 2.13.5 |
| numpy | 1.26.4 | 2.5.3 |
| pandas | 2.2.2 | 3.0.6 |
| scikit-learn | 1.5.0 | 1.9.1 |
| fastapi | 0.135.1 | 0.141.1 |
| torch | not installed | required (DINOv2 features) |

ResolveAI has the same problem and uses the same pattern (`scripts/start_resolveai_worker.py`, `resolveai_platform.py`).
Catalyst follows it. The cost is two virtualenvs and one more process to start.

## Run it

```powershell
# 1. Catalyst's own environment, once. Its .python-version pins 3.11; this machine used 3.13 (see "Setup notes").
cd integrations\catalyst
uv sync
cd ..\..

# 2. The private worker (generates var\catalyst\gateway.secret on first start)
.venv\Scripts\python.exe scripts\start_catalyst_worker.py          # 127.0.0.1:8300

# 3. The Kairos API (reads the same secret)
.venv\Scripts\python.exe scripts\dev_harness.py                    # 127.0.0.1:8100

# 4. Check it end to end
curl http://127.0.0.1:8100/catalyst/status
```

Batches go in `integrations/catalyst/data/<batch>/` (see that folder's README). Catalyst reads and writes relative to its own
folder, so the worker is started with that folder as its working directory.

## Gateway

Every Catalyst route is under `/catalyst`, and the path after it is the worker's own path: the browser's
`/catalyst/api/evidence/Batch_1` reaches the worker as `/api/evidence/Batch_1`.

- **Who:** roles `engineer`, `reliability`, `admin`. The `demo` account is refused before any call is made.
- **What:** only the 25 routes in `ALLOWED`: reads, uploads, measurement and comparison runs, mask images. The one config write,
  `PUT /api/settings/baseline`, is deliberately not exposed (405).
- **How it stays closed:** every forwarded call carries `X-Kairos-Gateway-Secret`, and the worker checks it on every request.
  The browser's bearer token is never forwarded.
- **Paths:** `.` and `..` segments, literal or percent-encoded, are refused with 400 before anything is forwarded.
- **Streams:** the NDJSON progress for measure, compare and attribution is relayed as it arrives. PNGs pass through unchanged.
- **Uploads:** re-sent as multipart. Limited to `CATALYST_MAX_UPLOAD_MB` (default 500) and held in memory while forwarded.
- **Failures:** worker unreachable gives 503 `NOT_CONNECTED`. A worker 5xx gives 502 without the worker's text.

## Physics and mathematics (supply chain)

Each route returns the formula it used and the assumptions the number rests on.

| Route | Physics or maths | Used for |
|---|---|---|
| `POST /physics/cold-chain/exposure` | Arrhenius rate ratio, time-temperature integration, mean kinetic temperature (USP <1079> definition) | Shelf life used up by a temperature history, MKT, expiry |
| `POST /physics/thermal/time-to-limit` | Lumped-capacitance heat transfer, tau = m c / UA | How long a payload takes to reach a limit temperature |
| `POST /physics/flow/queue` | Kingman's G/G/1 wait, Little's law | Expected delay and queue size at a handling stage |
| `POST /physics/inventory/policy` | Economic order quantity, safety stock with the normal quantile, reorder point | Order size, buffer and reorder point for one item |

Defaults chosen here, to change if the domain says otherwise: activation energy 83.144 kJ/mol for cold-chain kinetics (the value
conventionally used for MKT) and reference storage at 5 C. The formulas are standard. The defaults are not validated for any
product.

`backend/tests/test_physics_models.py` checks each formula against a value that can be derived by hand: the M/M/1 limit of
Kingman's formula, the 1/e point of the heating curve, MKT of a constant temperature equal to that temperature, and so on.

## Catalyst code changes

Two kinds of change to Catalyst's own code. Nothing in its QC logic or its verdict changed.

1. **Gateway guard** (`qc/api.py`). If `CATALYST_GATEWAY_SECRET` is set, every request must carry the matching header. Mask images
   moved from a static mount to a route, so the guard covers them too.
2. **Windows text encoding.** On Windows, Catalyst's tests failed with `UnicodeEncodeError: 'charmap' codec` (for example on `≥` and
   `→` in the evidence text), and the fixture CSV compare failed on CRLF line endings. Every text read and write in `qc/` and
   `tests/` now passes `encoding="utf-8"`, and the fixture is written with LF. Without this, Windows could not save an evidence
   file that contained those characters, and reading one back would have mis-decoded it silently.

## Verified

- **Catalyst test suite, moved code:** before the encoding fix, 142 passed and 9 failed, all 9 from the Windows issue above. After
  it, **154 passed, 0 failed** (run with `.venv\Scripts\python.exe -m pytest` in `integrations/catalyst`, Python 3.13).
- **Kairos gateway and physics, targeted:** `test_catalyst_platform.py` (secret forwarding, allow-list, demo block, streaming,
  uploads, oversized upload, dot segments, unreachable worker, 502 without leaking), `test_physics_models.py`,
  `test_physics_api.py`, plus `test_resolveai_platform.py` and `test_hub_capabilities.py`: **63 passed**.
- **Kairos full backend suite, final code:** **323 passed, 69 skipped, 0 failed.**
- **Live, through the gateway, with the real worker:**
  - the worker starts from the launcher, generates the secret, and returns **403 to an unsigned request**;
  - `GET /catalyst/status` returns `connected: true` with the worker's real health;
  - `GET /catalyst/api/batches` returns `[]` with HTTP 200 (the data folder is empty here);
  - `PUT /catalyst/api/settings/baseline` returns **405**;
  - a `..` segment, sent without client normalisation (`curl --path-as-is`), returns **400**;
  - an NDJSON run on a missing batch streams the worker's own error event through the gateway;
  - the physics routes return the expected numbers. 100 h at the reference leaves 900 h of 1000 h. A saturated queue returns 422
    rather than a finite wait. The warming payload crosses 25 C after 23.1 min, which is 2000·ln 2 seconds.

## Not verified

- **A real batch run.** No FIB-SEM batches are in this folder, so `/catalyst/api/runs/…` was exercised only with a missing batch.
- **Identify and the attribution model.** The worker reports `dinov2_cached: false`, so Identify is not ready. The DINOv2 weights
  download from Hugging Face. On this machine that download fails with a certificate error (`UnknownIssuer`), and uv's own
  downloads failed the same way until `--native-tls` was used. On a machine with network access, run the one-line download in the
  Catalyst README.
- **The Claude guide.** The worker reads `ANTHROPIC_API_KEY` from its own environment, and nothing passes the Kairos key to it.
  The gateway restricts it to staff, but it has not been called with a key.
- **The Catalyst web UI.** It still runs as its own app (`integrations/catalyst/web`, port 5173, `/api` on :8000). It is not wired
  into the Kairos frontend, because the frontend is not to change. Its `npm run build` was not re-run after the move.
- **Deployment.** Catalyst is not in `backend/Dockerfile` or `render.yaml`. The worker runs on a local machine only.
- **Physics against real data.** The formulas are verified against their own derivations. They have not been fitted to, or
  checked against, a product's stability study, a logger trace, or a carrier's lead-time history.

## Setup notes (this machine)

- uv downloads failed with `invalid peer certificate: UnknownIssuer` because this machine's network inserts its own root
  certificate, which uv's bundled CA list does not include. `UV_NATIVE_TLS=1 uv sync --native-tls` fixes it by using the Windows
  certificate store.
- `uv run` reads `.python-version` (3.11) and tries to download that interpreter, which fails on this network. Running the venv's
  Python directly (`.venv\Scripts\python.exe -m pytest`) avoids it. `uv sync --python <3.13 path>` built the venv.

## Known limits

- **One shared Catalyst data folder,** not partitioned by site, so the gateway is restricted to the staff roles. Per-site folders
  would need one worker per site, or a data-root parameter in Catalyst. Decide this before a second site uses it.
- **Uploads are buffered in memory** by the gateway before they are forwarded.
- **The gateway is a catch-all route** and is hidden from the OpenAPI schema. The allow-list in `catalyst_platform.py` is the only
  record of what is reachable, so keep it in step with the worker.
