# Source archive manifest (2026-10-18)

Nothing was deleted or moved. Originals stay where they were; Kairos holds copies. Archives exclude `.git`, `node_modules`, `.next`, caches, `.env*` files and files over 3 MB.

| Project | Original location | Git HEAD (dirty files) | Copy inside Kairos | Verified |
|---|---|---|---|---|
| RESOLVE-AI-main | `GRAPH HACKS/RESOLVE-AI-main` | 74eabae (0) | `source-archives/RESOLVE-AI-main` (code archive); `integrations/resolveai/` (runtime copy + frontend source) | 1,577 of 1,577 files copied |
| track1-agent | `GRAPH HACKS/track1-agent` | 4745f78 (1) | `source-archives/track1-agent` (excludes `EXTERNAL_REPOS`) | 11,334 of 11,334 files copied |
| GreenChain | `GREENCHAIN-main` already sat inside kairos-main; same tree as `Downloads/greenchain/GREENCHAIN-main` and a 260 MB copy under `payment at critical situation/` | not a git repo | archived in place at `GREENCHAIN-main/`; runtime copy `backend/domains/greenchain`; datasets in `backend/domains/greenchain/data` and `integrations/greenchain/data` | 54 original tests pass in the new location |
| Kairos | `GRAPH HACKS/kairos-main` | cd041d1 (62 uncommitted before this session) | n/a | n/a |

Not copied: 14 files over 3 MB in RESOLVE-AI-main (insurer PDFs; the 512 MB `knowledge/` corpus stays in the original), the 98 `EXTERNAL_REPOS` clones (README text is in `backend/api/services/sources`), all `.env` files. `source-archives/`, `GREENCHAIN-main/` and the duplicate dataset copy are in `.gitignore` so they cannot become nested repositories or bloat commits. Normal startup and builds never read them.