# Dependency Conflicts & Resolution Strategies

**Last Updated:** 2026-10-18T06:45:00+05:30 (IST)
**Status:** ACTIVE - Core Kairos/FalkorDB path implemented locally; 98-source integration remains in progress

---

## Executive Summary

This document catalogs all identified dependency conflicts between Kairos, ResolveAI, Track 01, and the 98 source repositories. Each conflict has a documented resolution strategy to maintain compatibility without destructive changes.

---

## Critical Conflicts

### 1. falkordb / redis Version Incompatibility

**Conflict:**
- Kairos pins `redis==5.0.6` (required by Celery/kombu)
- falkordb 1.2.0+ requires `redis>=6.0.0,<7.0.0`
- falkordb 1.4.0+ requires `redis>=7.1.0,<8.0.0`
- falkordb 1.6.0+ requires `redis>=7.1.0` (no upper bound)

**Impact:** Cannot use latest falkordb client with Kairos's pinned redis version

**Resolution:**
- Use `falkordb==1.0.10` which requires `redis>=5.0.1,<6.0.0`
- This version is compatible with Kairos's `redis==5.0.6`
- Trade-off: Older client, but fully functional with current FalkorDB server (4.22.1)

**Verification:**
```python
# falkordb 1.0.10 pyproject.toml
[tool.poetry.dependencies]
redis = "^5.0.1"
```

**File Changes:**
- `backend/requirements.txt`: Added `falkordb==1.0.10`

**Future Consideration:**
- If Kairos upgrades redis to 6.x or 7.x, can upgrade falkordb to latest
- Track in requirements-compatibility matrix

---

### 2. Neo4j vs FalkorDB Graph Operations

**Conflict:**
- Kairos uses Neo4j (Aura cloud) for asset/document knowledge graph
- Evidence Drift Cascade uses FalkorDB for decision-dependency graph
- Different query dialects and capabilities

**Impact:** Cannot directly migrate existing Neo4j queries to FalkorDB

**Resolution:**
- **Separate stores**: Keep Neo4j for asset/document graph, FalkorDB for drift graph
- **No migration**: Do not attempt to move Kairos's Neo4j data to FalkorDB
- **Clear separation**: Evidence Drift operates on its own graph namespace
- **Site isolation**: Each Kairos site gets its own FalkorDB graph (`kairos_drift__<site_id>`)

**File Changes:**
- `backend/api/config.py`: Added separate FalkorDB configuration
- `backend/api/services/drift/store.py`: Uses FalkorDB only
- Existing Neo4j services unchanged

**Future Consideration:**
- Evaluate FalkorDB compatibility with existing Neo4j queries if migration is ever needed
- Document query translation patterns

---

### 3. Python Version Compatibility

**Status:** NO CONFLICT

**Kairos:** Python 3.12 (pinned in Dockerfile)
**ResolveAI:** Python 3.12 (compatible)
**Track 01:** Python 3.12 (compatible)
**falkordb 1.0.10:** Supports Python 3.8+ (compatible)

**Resolution:** All components compatible with Python 3.12

---

## Framework-Level Conflicts

### FastAPI Version

**Kairos:** fastapi==0.135.1 (pinned, capped to keep pydantic 2.7.4)
**ResolveAI:** FastAPI (version not pinned in audit yet)

**Resolution:** Use Kairos's pinned version for all FastAPI components

### Pydantic Version

**Kairos:** pydantic==2.7.4
**falkordb 1.0.10:** No direct pydantic dependency

**Resolution:** Compatible

---

## Database-Level Conflicts

### 1. Neo4j APOC Procedures

**Issue:** Kairos may use Neo4j APOC procedures
**FalkorDB Compatibility:** APOC not supported in FalkorDB

**Resolution:**
- Evidence Drift graph does NOT use APOC procedures
- All FalkorDB queries use standard Cypher supported by FalkorDB 4.22.1
- If Kairos's Neo4j queries use APOC, they remain in Neo4j (separate store)

**Verified:**
- `store.py` uses only: MERGE, MATCH, CREATE, SET, RETURN, COUNT, IN, WHERE, LIMIT
- All queries parameterized
- No APOC functions called

---

### 2. Neo4j GDS Library

**Issue:** Some source repositories may use Neo4j Graph Data Science library
**FalkorDB Compatibility:** GDS not supported

**Resolution:**
- Do NOT integrate repositories requiring GDS into FalkorDB
- Either:
  - Use Neo4j for those capabilities (keep separate)
  - Reimplement algorithm in pure Python
  - Use alternative graph algorithm library

**Tracking:** Will be identified during source audit and recorded in 98_SOURCE_MASTER_LEDGER.csv

---

## Runtime Conflicts

### Celery Worker Dependencies

**Kairos:** Uses Celery workers with redis==5.0.6
**falkordb 1.0.10:** Uses redis>=5.0.1,<6.0.0

**Resolution:** Compatible - same redis client can be used

**Note:** Celery uses redis for message queue, FalkorDB uses redis for graph storage. These are different connections and different data models. No conflict.

---

## Application-Level Conflicts

### 1. Authentication Systems

**Kairos:** Supabase-based auth with role model (field_worker, engineer, reliability, admin)
**ResolveAI:** Has its own auth (per audit: "separate case persistence and authentication/configuration")

**Resolution:**
- Use Kairos's auth as canonical
- Do NOT create second authentication system
- Map ResolveAI capabilities to Kairos roles
- ResolveAI becomes native subsystem, not separate app

**File Changes:**
- `backend/api/routers/resolveai.py`: Uses `get_current_user` dependency
- `backend/api/routers/resolveai.py`: Uses `require_role("*STAFF")` for demo endpoints

---

### 2. Tenant/Organization Model

**Kairos:** site_id based tenant isolation
**ResolveAI:** May have different tenant model (per audit: "independent app auth and user scope")

**Resolution:**
- Use Kairos's site_id for all tenant isolation
- FalkorDB graphs are site-scoped: `kairos_drift__<site_id>`
- All drift operations require site_id from authenticated user

---

### 3. Domain Models

**Kairos:** Industrial assets, documents, maintenance, P&IDs, work orders
**ResolveAI:** Consumer justice, cases, institutions, regulatory domains (per audit)

**Resolution:**
- Keep domain models bounded
- Evidence Drift graph uses generic labels (Document, SourceVersion, Claim, etc.)
- Domain-specific nodes can be added as needed
- No forcing of one model into the other's namespace

---

## Frontend Conflicts

### 1. Design System

**Kairos:** Tailwind CSS v4, Next.js 16, React 19
**ResolveAI:** Separate frontend (per audit)

**Resolution:**
- Do NOT duplicate ResolveAI frontend
- ResolveAI capabilities exposed through Kairos routes
- Use Kairos's design system for any new UI components
- Preserve Kairos's visual identity

**Directive Compliance:** "Do not overwrite Kairos with the Track 01 frontend" - extended to ResolveAI

---

### 2. React Component Conflicts

**Status:** NOT YET AUDITED

**Action:** During source audit, identify:
- React component libraries used
- CSS frameworks
- Build tool configurations

**Resolution Strategy:**
- Prefer Kairos's existing components
- Adapt ResolveAI components to Kairos design system
- Isolate incompatible components or rewrite

---

## Testing Conflicts

### pytest Configuration

**Kairos:** Has pytest.ini with specific configurations
**New Tests:** Must respect Kairos's testing conventions

**Resolution:**
- All drift tests placed in `tests/` directory
- Use Kairos's pytest.ini (already configured for async, timeout=90, etc.)
- Service-free tests marked appropriately
- DB-required tests skip if DB not available

**Implemented:**
- `tests/test_evidence_drift_contracts.py`: Pure computation, no DB
- `tests/test_evidence_drift_engine.py`: Pure computation, no DB
- `tests/test_drift_store.py`: Requires FalkorDB, uses pytest.skip if not available

---

## Security Conflicts

### 1. Graph Query Parameterization

**Requirement:** All Cypher queries must be parameterized to prevent injection

**Status:** COMPLIANT

**Verification:**
- `store.py`: All queries use `$param` syntax
- No string formatting in query construction
- No f-strings embedding user input in queries

---

### 2. Tenant Isolation

**Requirement:** No cross-tenant evidence leakage

**Status:** IMPLEMENTED

**Implementation:**
- Graph names include site_id: `graph_prefix__site_id`
- ResolveAI and drift API operations require staff roles and resolve site scope from the authenticated user; demo graph writes are fenced to showcase scope
- No cross-graph queries
- Site validation in `check_site()` contract function
- Local authz/tenant validation: 136 passed; production identity-provider behavior has not been exercised in this pass

### Current local integration boundary

- `POST /resolveai/drift/demo` runs the synthetic revision-bound review flow; `GET` reads the caller's site-scoped graph state.
- `/drift` has one canonical route prefix, staff role checks, site scoping, an OPA read action, and guarded demo writes.
- First Domino's revision/review behavior was adapted without importing its application, medical rules or dependencies. See `SOURCE_PROVENANCE.md`.
- The graph/API slice uses the existing pinned FalkorDB client. Live multimodal parsers, a ResolveAI model runtime and production graph operations are not connected.

---

## Integration Conflict Matrix

| Component | Kairos | ResolveAI | Track 01 | Resolution |
|-----------|--------|-----------|----------|------------|
| Auth System | Supabase | Independent | FalkorDB | Use Kairos |
| Graph Store | Neo4j | Neo4j | FalkorDB | Separate stores |
| Python Version | 3.12 | 3.12 | 3.12 | Compatible |
| redis Version | 5.0.6 | 5.0.6 | 5.0.6 | Use falkordb 1.0.10 |
| FastAPI | 0.135.1 | Latest | Latest | Use Kairos pin |
| Frontend | Next.js 16 | Separate | Separate | Use Kairos |

---

## Open Conflicts (To Be Resolved During Audit)

The following conflicts will be identified and resolved during the 98-repository audit:

1. **Framework Incompatibilities**: Node.js vs Python, React vs Vue, etc.
2. **Dependency Version Conflicts**: Different requirement pins
3. **License Incompatibilities**: GPL, AGPL, or copyleft licenses
4. **Runtime Incompatibilities**: Java, Go, Rust dependencies
5. **Database Incompatibilities**: PostgreSQL, MySQL, MongoDB requirements
6. **Cloud Service Dependencies**: AWS, GCP, Azure SDKs

**Tracking:** Will be recorded in 98_SOURCE_MASTER_LEDGER.csv under:
- `dependency_requirements`
- `integration_strategy`
- `blockers`

---

## Resolution Patterns Reference

### Pattern 1: Separate Stores
**Use When:** Different databases for different purposes
**Example:** Neo4j for assets, FalkorDB for drift
**Benefit:** No migration needed, clear boundaries

### Pattern 2: Version Pinning
**Use When:** Dependency version conflicts
**Example:** falkordb==1.0.10 with redis==5.0.6
**Benefit:** Maintains compatibility without code changes

### Pattern 3: Adapter Layer
**Use When:** Different interfaces for same capability
**Example:** FalkorDriftStore adapts FalkorDB client to Kairos contracts
**Benefit:** Isolates database-specific code

### Pattern 4: Native Merge
**Use When:** Compatible implementations
**Example:** Integrating pure Python algorithms
**Benefit:** Single codebase, no duplication

### Pattern 5: Isolated Service
**Use When:** Incompatible runtimes
**Example:** Java service for specific capability
**Benefit:** Keeps incompatible dependencies separate

---

## Verification Checklist

- [x] falkordb/redis conflict identified and resolved
- [x] Neo4j/FalkorDB separation documented
- [x] Python version compatibility confirmed
- [x] Authentication integration strategy defined
- [x] Tenant isolation strategy implemented
- [x] Query parameterization verified
- [ ] All 98 repositories audited for conflicts (70/98 complete)
- [ ] All identified conflicts documented

---

## Maintenance

This document is a living file. As new conflicts are discovered during integration:

1. Add conflict to appropriate section
2. Document resolution strategy
3. Record file changes
4. Update verification status
5. Link to relevant entries in 98_SOURCE_MASTER_LEDGER.csv

**Next Review:** After completing source audits (currently 70/98)
