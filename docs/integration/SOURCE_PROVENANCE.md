# Source Provenance & Attribution Ledger

**Last Updated:** 2026-10-18T06:45:00+05:30 (IST)
**Status:** ACTIVE - Provenance tracking established

---

## Purpose

This document tracks audited source candidates, behavior adaptations, and source code integrated into Kairos. It ensures:

1. **Attribution**: Every incorporated capability acknowledges its source
2. **License Compliance**: All licenses are respected and requirements met
3. **Provenance**: Exact commit and file locations are recorded
4. **Audit Trail**: Who integrated what, when, and why

---

## Master Provenance Statement

### Kairos (Host Repository)
- **Copyright Holder**: Krishna Somani
- **License**: Proprietary - All Rights Reserved
- **Copyright Year**: 2026
- **Permission Status**: USER_ATTESTED_OWNER_PERMISSION
- **Attestation**: User attested as copyright holder (Krishna Somani)
- **Integration Authority**: Full modification rights for commercial development

### ResolveAI (Contributed Repository)
- **Copyright Holder**: vsrupeshkumar (user's GitHub handle)
- **License**: Proprietary (frontend/LICENSE_PROPRIETARY.md states all rights reserved)
- **Copyright Year**: 2026
- **Permission Status**: USER_ATTESTED_OWNER_PERMISSION
- **Attestation**: User is owner/creator
- **Integration Authority**: Full modification rights for commercial development
- **Frontend License File**: LICENSE_PROPRIETARY.md (all rights reserved, prohibits copying/modification without permission)

### Track 01 (Integration Repository)
- **Copyright Holder**: Track1 Developer (user's GitHub handle)
- **License**: Not specified (open for integration)
- **Permission Status**: USER_ATTESTED_OWNER_PERMISSION
- **Attestation**: User is owner/creator
- **Integration Authority**: Full modification rights
- **Note**: Already contains Interdict integration with MIT license (Yash Soni)

---

## Integrated Third-Party Code

### 1. Interdict (Min-Cost Cut Algorithm)

**Upstream Repository**: https://github.com/YashSoni998265/interdict
**Upstream Author**: Yash Soni
**Commit**: 829f1dd63fab80f56c019c4a0a40d761c822ea2a
**License**: MIT
**Permission Status**: USER_ATTESTED_OWNER_PERMISSION
**Attestation Date**: 2026-10-17

**Files Adapted:**
- `backend/src/interdict/engine/planner.py` (`solve`, `_minimal`, `objective`)
- `backend/src/interdict/engine/attackgraph.py` (`Chain` type)

**Adapted Into:**
- Track 01: `backend/app/capabilities/adapters/interdict_cut.py`
- Track 01: `backend/app/capabilities/remedy_conflicts.py`

**Modifications:**
- Objective fields replaced by caller-supplied cost
- Strict-mode unknown-impact filtering removed
- Deny-all hard-isolation plan removed
- Local dataclasses replace Interdict's types
- Input guards added

**License Compliance:**
- MIT license preserved
- Copyright notice retained in Track 01 THIRD_PARTY_NOTICES.md
- File headers include original authorship attribution

**Verification:**
- Track 01 tests pass (59 tests including Interdict integration)
- Functionality verified in `test_falkordb_removal_gives_no_decision` (Track 01 test evidence)

---

## 98-Repository Integration Provenance

### Attribution Model

All 98 repository identities are inventoried; they are not all integrated. The source ledger tracks current audit and integration state. The present Kairos source-backed implementation adapts one audited decision-revision behavior, with no upstream source lines copied. The Beyondions root-cause candidate is reference-only. Other capabilities remain queued until actual implementations, dependencies, licenses and tests are reviewed.

The user attests that owners granted permission for all 98 identities. Record this as `USER_ATTESTED_OWNER_PERMISSION`; it is not independently verified and does not establish the scope of a commercial grant.

### Permission Status Summary

| Source state | Count | Handling |
|---|---:|---|
| MIT license identified in source ledger | 26 | Review terms and notices for each adaptation |
| `NO_LICENSE_FILE` among audited sources | 44 | Local adaptation may proceed under user attestation; document actual commercial grant scope before distribution |
| Not audited; source license unknown | 27 | Inspect checkout and actual license before choosing an integration strategy |
| Empty upstream source | 1 | Mark `NO_UPSTREAM_IMPLEMENTATION`; do not count as a capability |

Permission evidence remains the user's attestation in the master engineering directive. No independent owner records or commercial grant scope are linked in this workspace.

### Provenance Tracking Format

For each integrated capability, record:

```yaml
capability: "short_name"
source_repository: "owner/name"
commit_sha: "full_40_char_sha"
source_file: "path/in/repo"
source_function: "function_or_class_name"
adapted_file: "path/in/kairos"
adapted_function: "new_name_or_same"
integration_strategy: "NATIVE_MERGE|SHARED_ENGINE|DOMAIN_CAPABILITY_PACK|..."
license: "MIT|Apache-2.0|...|NO_LICENSE_FILE"
copyright_holder: "name_or_organization"
permission_status: "USER_ATTESTED_OWNER_PERMISSION|WRITTEN_GRANT_LINKED|BLOCKED"
attribution_location: "file:line_where_credit_appears"
```

### Current Kairos Integration Ledger

**As of 2026-10-18:**

1. **Interdict Min-Cost Cut** ? present in the separate Track 01 project under MIT attribution; not counted as integrated into Kairos in this report.
2. **Evidence Drift Cascade** ? Kairos-native implementation. It is not counted as an external source contribution.
3. **First Domino decision-revision behavior** - adapted into Kairos from `AjaySingh-a/firstdomino` commit `9f266603f6bb21f0c9f2e1ae1b3c24cc21907245`. The adapted behavior is immutable decision revision lineage and review pinned to the revision/hash it approved. Exact source/destination paths and local test proof are recorded in this file's adaptation note and the master ledger. No source lines, clinical rules, frontend or dependency were copied.
4. **ResolveAI synthetic workflow** ? Kairos-native route and demo. This is not evidence that the standalone ResolveAI specialist runtime has been integrated.
5. **Beyondions root-cause agent** - inspected at `0adc20ff29642e35389a644ad38a58aa38cc9871`, classified `REFERENCE_ONLY`; no code, graph queries or dependencies were copied. Its trace-based answer-repair mechanism should be reconsidered after Kairos has a bounded tool-trace adapter. The source has no license file, uses an unbounded service graph, and its surrounding agent requires Groq/Streamlit.

Upstream First Domino has no license file. The user-attested permission is recorded, but the actual grant scope is not independently verified.

## Attribution in Code

### File-Level Attribution

All adapted files MUST include attribution in one of these locations:

1. **File Header Comment** (preferred for adapted code):
```python
"""
Adapted from: https://github.com/owner/repo
Commit: abc123...
Original File: path/to/file.py
Original Function: function_name
License: MIT (see LICENSE file)
Copyright: Original Author
"""
```

2. **Module Docstring**:
```python
"""Module implementing X.

Adapted from [owner/repo](https://github.com/owner/repo) @ commitabc123
by Original Author. MIT licensed.
"""
```

3. **Separate NOTICES File** (for third-party with many files):
- Create `THIRD_PARTY_NOTICES.md` or `NOTICES.txt`
- List each third-party component with license text
- Include in distribution

### Function-Level Attribution

For individual functions adapted from external sources:

```python
def adapted_function(...):
    """Function description.

    Adapted from owner/repo@commit (path/to/file.py:function_name)
    Original License: MIT
    """
    ...
```

---

## License Compliance Matrix

### Permissive Licenses (Can Integrate)

| License | Requirements | Kairos Compliance |
|---------|-------------|-------------------|
| MIT | Include copyright notice | ✅ Include in file headers |
| Apache 2.0 | Include NOTICE file | ✅ Include in NOTICES |
| BSD-2-Clause | Include copyright notice | ✅ Include in file headers |
| BSD-3-Clause | Include copyright notice | ✅ Include in file headers |
| ISC | Include copyright notice | ✅ Include in file headers |

### Copyleft Licenses (Need Review)

| License | Requirements | Kairos Compliance |
|---------|-------------|-------------------|
| GPL-3.0 | Source must be GPL-3.0 | ❌ Kairos is Proprietary - BLOCK |
| LGPL-3.0 | Dynamic linking OK, static needs compliance | ⚠️ Review per use case |
| AGPL-3.0 | Network use triggers source release | ❌ BLOCK for SaaS |
| MPL-2.0 | File-level copyleft | ⚠️ Review per use case |

### No License File

A missing upstream license is not itself a new license. For this workspace, the owner-permission status is `USER_ATTESTED_OWNER_PERMISSION`; local source adaptation may proceed under the user's explicit directive. Record the exact source and attribution. Before commercial publication or distribution of affected code, document the actual grant scope, including commercial use, modifications, distribution and restrictions. The user attestation is not independent verification.

## Verification Procedures

### Before Integration

1. **License Check**:
   - [ ] License file exists in upstream
   - [ ] License is OSI-approved or clearly stated
   - [ ] License allows commercial use (if applicable)
   - [ ] License allows modification
   - [ ] License allows redistribution

2. **Permission Check**:
   - [ ] Written permission obtained OR
   - [ ] USER_ATTESTED_OWNER_PERMISSION recorded
   - [ ] Permission scope documented (commercial use, modification, etc.)

3. **Code Review**:
   - [ ] Security audit completed
   - [ ] Dependency conflicts identified
   - [ ] Integration strategy selected

### During Integration

1. **Provenance Tracking**:
   - [ ] Exact commit SHA recorded
   - [ ] Exact source file recorded
   - [ ] Exact source function/class recorded
   - [ ] Adapted file recorded
   - [ ] All modifications documented

2. **Attribution**:
   - [ ] Original authorship preserved in comments
   - [ ] License notice included
   - [ ] Copyright notices preserved

3. **Testing**:
   - [ ] Original tests adapted and passing
   - [ ] New integration tests added
   - [ ] Regression tests pass

### After Integration

1. **Documentation**:
   - [ ] Entry added to 98_SOURCE_MASTER_LEDGER.csv
   - [ ] Entry added to this SOURCE_PROVENANCE.md
   - [ ] Changes committed with clear message

2. **Verification**:
   - [ ] Functionality works end-to-end
   - [ ] No regressions in existing tests
   - [ ] Security scan passes

---

## Current Status by Repository

- **1 source behavior adapted and tested in Kairos:** `AjaySingh-a/firstdomino` decision revision/review lineage. No upstream source code was copied.
- **1 source reviewed as reference-only:** `beyondions/rootcause-agent`.
- **68 other audited identities** await integration review.
- **27 nonempty identities** remain unaudited.
- **1 identity** has a verified empty upstream tree and is excluded from capability counts.
- **0 direct third-party source lines** were copied into the current Kairos slice.
- **44 audited identities** have no license file; this does not block authorized local adaptation under the user's attestation, but commercial grant scope is not documented.

An audit classification or behavior adaptation is not a complete repository integration. Use the per-repository queue and ledger for exact status.

## Maintenance Procedures

### Adding a New Integration

1. Create entry in 98_SOURCE_MASTER_LEDGER.csv
2. Create audit JSON in source_audit/
3. Add provenance entry to this file
4. Add attribution to code
5. Add integration tests
6. Commit with clear message

### Updating Attribution

If source code is modified after integration:
1. Update the adaptation notes in this file
2. Update any version-specific attribution in code
3. Commit the changes

### Handling License Changes

If upstream license changes:
1. Review new license for compatibility
2. Update this file
3. If incompatible, remove adapted code and find alternative

---

## Compliance Verification

### Required for Commercial Distribution

Before any commercial publication or distribution:

1. **Written Grants**: Obtain written permission for all NO_LICENSE_FILE repositories
2. **License Review**: Confirm all integrated licenses allow commercial use
3. **Attribution Complete**: Verify all attributions are present
4. **Source Available**: Ensure all source code with copyleft licenses has source available
5. **Notices File**: Create comprehensive NOTICES file with all licenses

### Commercial Distribution Review

Before distributing affected source-derived code commercially, verify grant scope and license obligations for each included repository. Current evidence is a user attestation only; no independent grant documents are linked. The 44 audited repositories with `NO_LICENSE_FILE` remain a commercial-scope review item, not a reason to stop authorized local development.

## Contact & References

- **Kairos License**: `kairos-main/LICENSE` (Proprietary)
- **ResolveAI License**: `RESOLVE-AI-main/frontend/LICENSE_PROPRIETARY.md` (Proprietary)
- **Track 01 Notices**: `track1-agent/THIRD_PARTY_NOTICES.md`
- **98-Repository Ledger**: `docs/integration/98_SOURCE_MASTER_LEDGER.csv`
- **Audit Reports**: `docs/integration/source_audit/*.json`

---

**Note**: This document is a work in progress. It will be updated as integrations continue and provenance information is verified.
