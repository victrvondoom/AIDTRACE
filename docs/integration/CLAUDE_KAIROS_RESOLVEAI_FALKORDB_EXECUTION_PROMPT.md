# Claude Code Execution Prompt: Kairos + ResolveAI + FalkorDB

> **Use:** Open Claude Code at the Graph Hacks workspace root and paste this prompt. It is designed to reduce repeated discovery, protect existing work, and drive one narrow feature to a real, reviewable end-to-end result before expanding scope.

---

## ROLE AND OUTCOME

Act as the principal product architect and implementation engineer for one integrated product. Inspect the actual workspace, then make the smallest sequence of code changes that delivers the first complete, verifiable vertical slice described below. Continue through implementation and verification; do not stop after proposing architecture or producing a plan.

The final product is **Kairos**. Preserve its identity, existing interface, navigation, authentication, governance, routes, and working operations. **ResolveAI** is Kairos's native investigative intelligence subsystem. **FalkorDB** is the graph store for ResolveAI's evidence-linked agent memory and decision-dependency reasoning. ResolveAI is an ongoing, incomplete project: integrate working capabilities, label incomplete ones honestly, and do not present it as finished.

The user wants a main Kairos dashboard and a first-class **RDS (Reasoning and Decision System)** area for inspecting the real agent graph, configured models, curated evidence, and decisions affected by changing evidence. The new CyberFlow brief adds a focused cyber-defense capability profile, including agent-memory-backed fraud investigation. Treat CYBERFLOW OS as the supplied architecture reference, not a product rename: Kairos remains the product and ResolveAI remains its in-progress intelligence subsystem. Keep existing industrial operations intact; do not claim Kairos already delivers the full enterprise cyber-defense vision.

### Product hierarchy

```text
Workspace/
|-- Kairos/       # canonical product, interface, API, identity, governance
`-- ResolveAI/    # preserved in-progress source product; capabilities integrated natively
```

The current checkout names may be `kairos-main` and `RESOLVE-AI-main`. Verify before any move. The intended end state has two product roots named `Kairos/` and `ResolveAI/`. Preserve both Git histories, branches, uncommitted work, source provenance, and references. Do not flatten one project into the other, copy both frontends into one UI, or delete supporting research. If Track 1 or repository research material must remain, keep it clearly labeled as reference material under the existing integration/research area; it is not a third product.

## PRODUCT THESIS AND NARROW PROBLEM

Kairos observes and governs industrial operational evidence. ResolveAI investigates conflicts and dependencies in that evidence. FalkorDB connects source revisions, claims, agent memories, conclusions, decisions, recommendations, models, and approvals. Kairos retains human authority over consequential decisions.

### First workflow: Evidence Drift Cascade for suspected payment-diversion fraud

Solve exactly this cyber-defense problem first:

> **Can the system connect suspicious identity activity, a payment-destination change, a monitoring gap, and relevant adjudicated agent memory into a defensible suspected-fraud case, then show which conclusions or response recommendations are unsafe because their evidence changed?**

Build the end-to-end path:

1. Generate an isolated synthetic case with a suspicious cloud sign-in, a new OAuth/service-account permission, a changed vendor payment destination, and an expected endpoint/security heartbeat that has gone stale. Include benign counter-evidence (such as an authorized maintenance window) so detection is not a one-rule demo.
2. ResolveAI retrieves only authorized, tenant-scoped, source-backed memories from prior adjudicated synthetic cases. Memory records include what was observed, supporting evidence, time scope, confidence/status (`CONFIRMED`, `DISPROVED`, or `UNVERIFIED`), curator/analyst provenance, and retention policy. Do not treat an LLM summary or an unreviewed case as a confirmed fact.
3. FalkorDB traverses identity -> session/device -> permission change -> asset/service -> vendor/payee change -> transaction request, and joins relevant prior case memories plus security obligations (for example, required telemetry freshness). Every link must have its own evidence and time boundary. A missing heartbeat means coverage is `UNKNOWN`, not proof of compromise or proof of safety.
4. ResolveAI creates a suspected-fraud hypothesis with supporting evidence, counter-evidence, confidence, alternative explanations, memory matches, and what evidence would distinguish them. Use deterministic, inspectable scoring/policy for risk and eligibility; the LLM can investigate and explain but cannot promote suspicion to confirmed fraud.
5. Demonstrate the agent-memory contribution with the same synthetic case run twice: memory disabled and memory enabled. Show which prior validated memory changes retrieval, the graph path, or the investigation hypothesis. Do not claim improved detection unless the evaluation proves it; memory must never override contradictory current evidence.
6. If evidence or a security assumption changed after a saved conclusion/approval, run bounded impact traversal and classify the dependent conclusion/recommendation as `UNAFFECTED`, `REVIEW_REQUIRED`, or `BLOCKED_STALE_EVIDENCE`. Show exact affected paths and do not invalidate unrelated graph branches.
7. Simulate the least-privilege response options (for example, revoke a suspicious session, remove a newly granted permission, or hold a synthetic payment request). Require policy evaluation and authorized human approval before any action. Keep the entire showcase synthetic; never call a real bank, cloud IAM, EDR, firewall, or production connector.
8. Verify the postcondition independently using fresh synthetic evidence (revocation observed, suspicious permission absent, telemetry restored, and payee change reviewed). An action API success is not containment proof. Append the evidence, decision, approvals, verification, and audit receipt.

Use only isolated synthetic data and local graph namespaces. A suspected-fraud finding is not a factual accusation or final determination. Do not execute real payments, production security remediation, physical plant control, clinical recommendations, or other consequential actions. State clearly that this is decision support.

## NON-NEGOTIABLES

1. **Inspect before changing.** Read root and nested `AGENTS.md`, `CLAUDE.md`, project READMEs, current progress checkpoint, architecture, manifests, Git status, and the call paths relevant to this workflow. Trace existing implementations; do not rely on marketing copy.
2. **Keep Kairos canonical.** Reuse its shell, design tokens, components, auth, tenant/site scope, policy checks, API patterns, database conventions, audit trail, and existing routes. Add an integrated RDS destination to Kairos navigation. ResolveAI must not become a separately branded app, iframe, duplicate sign-in, or second source of truth.
3. **Preserve all existing work.** No `git reset`, `git clean`, destructive checkout, force operation, broad formatting, unrelated refactors, or overwriting user changes. Before relocating the two product roots, prove destination paths are safe, preserve `.git`, check open processes/path references, and make the move reversible. Never delete originals or source audits.
4. **FalkorDB must do real work.** The graph traversal must affect which conclusions and pending recommendations are shown as stale or eligible. A health badge, decorative graph, hard-coded result, or disconnected adapter does not satisfy this requirement.
5. **Fail closed on uncertainty.** Missing, contradictory, inaccessible, or unverified evidence means `UNKNOWN`/`REVIEW_REQUIRED`; it never becomes evidence that an action is safe. Keep evidence valid-time and observed-time distinct where existing contracts support it.
6. **Bound and secure graph operations.** Scope every query by the authenticated organization/site derived server-side, parameterize values, cap traversal depth/edges/time, validate IDs and revision transitions, make writes idempotent, and fail closed on overflow, timeout, policy outage, or graph outage. Do not let callers select another tenant's graph.
7. **Protect approval integrity.** An approval is bound to the exact decision and evidence revision. Any relevant revision change makes that approval ineligible until re-reviewed. No model or agent may approve its own consequential recommendation.
8. **No fabricated capabilities.** Keep configured models, fine-tuned model checkpoints, deployed models, agents, agent roles, and training jobs as distinct states. Discover them from actual code, provider configuration, and durable registries. Never label a base model fine-tuned; never invent training metrics, agents, data counts, integrations, or successful outcomes.
9. **No cloud writes or secrets.** Do not print, copy, commit, or transmit secrets. Do not write/delete/migrate Supabase, Neo4j Aura, Qdrant Cloud, hosted FalkorDB, or other production/shared data. Use isolated local services and synthetic data. Do not run a suite whose fixtures or cleanup may mutate cloud data; inspect fixtures before selecting commands.
10. **Source and license integrity.** Preserve ResolveAI and Track 1 source trees. Record origin, commit, relevant code paths, license status, and user-attested permission accurately. No root license in a source tree is not proof of an open-source license. Do not distribute copied code until attribution and commercial grant scope are documented. Prefer adapting compatible, clearly authorized components; otherwise implement a clean interface and defer the source.
11. **One vertical slice beats broad scaffolding.** Do not implement 98 shallow adapters, speculative microservices, fake provider connections, empty CRUD screens, or a generic agent marketplace. Keep the source ledger accurate and continue source audits separately from verified product capability.
12. Follow the repository-specific instructions unless they conflict with this prompt or the user's authorization. This prompt authorizes ordinary reversible local engineering only; it does not authorize destructive data operations, public releases, paid services, or production actions.

## FIRST INSPECTION: USE WHAT EXISTS

The workspace checkpoint currently reports the following; verify it against files before relying on it:

- Kairos already has a Plant Overview and a partial “Reasoning infrastructure / Data curation / Models and evaluation” workspace in `frontend/src/app/(app)/overview/_components/reasoning-workspace.tsx`.
- Kairos has FalkorDB drift contracts, bounded traversal, a store adapter, lazy dependency wiring, a read-only graph readiness route, and a credential-free model catalog under `backend/api/services/drift/` and `backend/api/routers/health.py`.
- Kairos's current UI reports that the fine-tuned model registry/training jobs are not connected. Do not relabel that as implemented.
- The current progress checkpoint says the graph is not yet exposed as a governed evidence/decision workflow: persistence, revision supersession, cascade writes, approval receipts, and a complete user review screen remain outstanding.
- ResolveAI source includes a LangGraph investigation workflow, model-routing code/tests, domain routing/fan-out, case and agent-run persistence, evidence/knowledge curation assets and tests. Verify exact entry points and behavior. Its current domain/data model may not directly fit Kairos's industrial workflows.
- ResolveAI has no root `LICENSE` in the inspected checkout. Record the user's permission as `USER_ATTESTED_OWNER_PERMISSION`; retain attribution and do not represent it as independently verified or a distribution-ready grant.
- The Kairos worktree contains uncommitted user-owned changes and generated local artifacts. Do not reset, clean, or overwrite them.

Use existing artifacts instead of creating duplicates. Update the current integration checkpoint and ledgers in place only when this repository's instructions permit it; create new files only when the destination does not already exist. Preserve prior prompt files, including `GraphHacks98_CLAUDE_CODE_MASTER_PROMPT.md`.

## RDS: USER-FACING BUILD REQUIREMENTS

Make the main Kairos dashboard the coherent entry point for this capability. Preserve the supplied Kairos dashboard reference: dark left navigation, high-contrast white operational canvas, compact KPI strip, restrained orange/red accents, clear operational signals, and dense but readable evidence-first layouts. Do not copy another product's branding or replace Kairos's existing shell.

Implement the RDS as an integrated, navigable workspace, not only a card. Its first screen must answer: **what changed, what agent reasoning depends on it, what is blocked, why, and who owns the next review?**

Required sections, implemented through actual APIs and existing design primitives:

- **Impact queue:** source revision, affected decision/recommendation, severity/status, site, evidence age, owner, due/review state, and count of dependent graph nodes. Every row opens a traceable detail view.
- **Agent map:** render the actual ResolveAI/Kairos workflow graph from a server-owned registry or graph definition. Show agent purpose, upstream/downstream dependencies, allowed tools/data scope, live/idle/blocked status, last run, and actual model binding. Clicking a node opens its inputs/evidence, output, guardrails, and run trace. Never infer a running state from a static diagram.
- **Model registry:** show provider, model identifier, role, version, configured/deployed/trained status, evaluation status, data lineage, and last verified time. Never show credentials. When checkpoints or fine-tuned models are absent, show “not registered/not connected” and explain the missing prerequisite rather than inventing them.
- **Evidence graph:** explain each changed-source → claim → memory/conclusion → decision/recommendation → approval path. Provide a useful table/detail view if an interactive graph would be decorative or inaccessible; retain keyboard access and text alternatives.
- **Curation team workspace:** source review, claim labels/corrections, deduplication and quality flags, provenance/licensing, dataset snapshot/version, reviewer/assignee, comments, and audit history. Require human acceptance before curated material enters a training/evaluation snapshot.
- **Evaluation and fine-tuning lifecycle:** connect real validation/evaluation APIs first. Implement dataset/version selection, role/model target, split/leakage checks, evaluation gate, job states, ownership, review, and artifact lineage. Use an existing supported trainer/provider only if one is actually present and configured. If none exists, implement truthful job specification/blocked prerequisite state and do not claim training occurred. A job can become “trained” only after a real artifact is stored, versioned, evaluated, and registered.
- **Governance:** site/tenant access checks, role-gated curation and approvals, revision-bound approvals, explicit dry-run/synthetic labels, and audit evidence. Keep the default view useful when registries or graph services are unavailable.

The agent map must reflect real workflows and run records, not an aspirational roster. A reasonable display could include extraction, retrieval, investigation/planning, graph analysis, contradiction review, impact evaluation, and human review **only if these roles exist in or are implemented by the actual runtime**. Show ResolveAI as the source of investigative intelligence; Kairos owns orchestration boundaries, experience, authorization, and approvals.

## CYBER DEFENSE CAPABILITY PROFILE AND MEMORY-BASED FRAUD

Use the supplied CyberFlow brief to design a future-capable cyber-defense architecture under the Kairos identity. Separate `implemented now`, `first demonstrable slice`, and `future architecture` in the UI/docs/demo materials. Do not imply that the eight-layer enterprise vision or every specialist engine already exists. Code scanning is one application-security engine, never the whole product.

Keep these eight logical layers visible in the architecture map, adapting names and boundaries to the real codebase:

1. **User experience:** Kairos SOC/operations dashboard, RDS, voice/text copilot, executive view, and API.
2. **Kairos control plane:** identity, tenant/site scope, gateway, durable workflows, roles, policies, and audit context.
3. **Security data fabric:** cloud/IAM, endpoint, network, firewall, SIEM, application and threat-intelligence inputs; connector -> validation -> normalization -> timestamps -> provenance.
4. **Evidence-Obligation-Decision Graph:** assets, identities, permissions, attack paths, controls, incidents, evidence, memories, decisions and outcomes. FalkorDB must materially drive a graph query in the demo; do not add a second authoritative graph store without evidence and a migration plan.
5. **Specialist engines:** asset/exposure; identity/attack path; vulnerability/threat context; detection/correlation; hidden-problem discovery; incident investigation; digital forensics (NetForensiq only if its real adapter exists); response analysis/simulation; application-security checks; posture/governance.
6. **Zero-trust decision gate:** evidence sufficiency, policy, blast radius, service impact, authorization and human approval.
7. **Response orchestration:** simulation, notification, ticketing and tightly scoped connectors. Production-changing actions require explicit, authenticated authorization and must be disabled in the synthetic showcase.
8. **Independent verification:** containment evidence, recovery tests, control revalidation, compliance evidence and audit receipt. Feed new evidence back to the graph and reopen conclusions whose assumptions no longer hold.

Map Govern, Identify, Protect, Detect, Respond and Recover as continuous product views, not a mandatory linear lifecycle. Treat STIX, OCSF, MITRE D3FEND, OPA, LiveKit, Temporal, NetForensiq, and every named provider as proposed interoperability/technology choices until the existing source and license/configuration checks confirm an actual usable implementation. Never claim compliance because a label or schema was added.

### Fraud and security memory contract

- Persist structured, evidence-linked episodic case memory and reviewed entity/control facts in the authorized tenant/site graph. Memory is a retrieval aid, not an authority source by itself.
- Every recalled memory must return provenance, source IDs/revisions, original case status, review actor/time, temporal validity, access scope, and why it matched. Keep confirmed, disproved, unverified, expired and contradicted memories distinct.
- Prevent cross-tenant recall. Exclude secrets and unnecessary personal data. Honor retention/deletion obligations using the existing governance model; keep immutable audit references without retaining prohibited content.
- Do not auto-promote model-generated answers to durable memory. Promotion requires evidence validation and a human or deterministic policy approval. Correcting a memory creates an auditable new state; it does not erase the historical record.
- Evaluate false positives as seriously as detection misses. Include benign authorized travel/device changes, maintenance windows, shared infrastructure, unrelated payee changes, stale memory, contradictory memory, duplicate events, missing telemetry, graph outage and cross-tenant access attempts.
- Report memory-on versus memory-off evidence: relevant recall precision, citation/provenance coverage, suspected-case ranking changes, false-positive/false-negative counts, and the actual synthetic records/query used. Never state that agent memory “detected fraud” when it only generated an unsupported suspicion.

The RDS must show the suspected case, current evidence, missing obligations/telemetry, recalled prior memories and why they are relevant, competing hypotheses, graph path, affected decisions, response approval state, independent verification, and assigned analyst/reviewer. The analyst can mark a finding `CONFIRMED`, `DISPROVED`, or `INCONCLUSIVE` with evidence and comments; that adjudication becomes eligible for future memory retrieval only after the configured validation gate.

## IMPLEMENTATION SEQUENCE AND GATES

### Gate 0 — Establish state

- Confirm the workspace root, exact Kairos and ResolveAI roots, `.git` identity/remotes/branches, dirty files, active processes, applicable agent instructions, and current baseline.
- Inspect only relevant source paths, dependencies, schemas, policies, graph queries, agent workflows, frontend shell, existing tests, fixture cleanup, and data backends.
- Create or update a concise integration map: ownership, source-derived component, destination, status (`PRESENT`, `ADAPT`, `DEFER`, `UNSAFE/UNKNOWN`), license/provenance note, dependency conflicts, and verification command.
- Before a folder rename, build a path reference map and prove the target names do not exist. Keep the rename reversible and preserve independent Git histories. If any reference or process makes relocation unsafe, keep current paths and continue implementation; do not block the product work.

### Gate 1 — Specify the vertical slice

- Define typed source revision, claim, agent run, memory/conclusion, decision/recommendation, impact, review, and audit contracts based on existing schemas.
- Define graph uniqueness/idempotency keys, valid-time and recorded-time behavior, allowed transitions, tenant/site partitioning, traversal limits, and policy decisions.
- Provide a concise sequence diagram and threat/failure matrix in Kairos integration docs. Record explicit decisions and the smallest planned file set.
- Define what counts as affected: a changed or superseded claim reaches a decision through a supported dependency path, or a contradiction is unresolved. Preserve “possibly affected” as review state rather than overstate certainty.

### Gate 2 — Implement the graph and decision service

- Extend the existing FalkorDB adapter, typed contracts, dependency injection, and lifecycle; do not add a parallel client or hard-coded tenant graph.
- Implement validated, parameterized, idempotent operations for registering immutable source/claim revisions, recording dependency edges, querying impact paths, transitioning review state, and writing audit receipts. Do not create a site graph merely to report health.
- Keep decision and policy logic deterministic/testable and separate from routers. Agent output proposes; policy evaluates; a human approves. If FalkorDB or policy is unavailable, return an explicit unavailable/review state and prevent approval/eligibility.
- Add/adjust API routes under Kairos conventions. Enforce auth, role, tenant/site scoping, request size, rate, query depth/time/edge caps, and safe error responses. Do not expose raw Cypher or cross-site identifiers.

### Gate 3 — Integrate ResolveAI without importing a second product

- Adapt one verified ResolveAI investigation capability: prefer its source-backed evidence/citation verification, actual LangGraph agent-run trace, and/or parallel domain/workstream investigation mechanism where compatible with Kairos. Do not import its consumer-facing application wholesale into industrial Kairos.
- Wrap the chosen capability behind Kairos contracts and identity/policy controls. Persist agent run/model versions and evidence dependencies. Preserve source attribution.
- Keep unadapted modules in ResolveAI and record them as `DEFER`; do not copy the whole source tree into Kairos.

### Gate 4 — Build the Kairos dashboard and RDS

- Extend the current dashboard and routing with an RDS route/detail flow using the existing Kairos component system, icons, responsive behavior, keyboard support, and reduced-motion preferences.
- Connect live values to actual backend responses. Add loading, empty, partial, unavailable, and permission-denied states. Distinguish live operational records from synthetic walkthrough data visibly.
- Implement impact list → graph path/detail → investigator replay → human review → audit receipt end-to-end. Make decisions and graph paths explorable and understandable without relying solely on a visualization.
- Add team curation and honest model/training registry surfaces. Do not add a button that claims to train or deploy unless it invokes a real, authorized implementation with tracked artifacts and evaluation.

### Gate 5 — Prove it

Inspect fixture and test cleanup behavior before running tests. Use only isolated local FalkorDB names/containers and synthetic inputs; do not run cloud-mutating tests or seed scripts. Run the narrowest relevant checks first, then broader non-destructive checks if safe and requested by repository instructions.

Required evidence for this slice:

1. A graph contract test for revisions, provenance, tenant/site isolation, idempotency, and invalid transitions.
2. A FalkorDB-backed test proving bounded traversal identifies the correct dependent decision/recommendation, ignores an unrelated branch, and fails closed on overflow/outage.
3. Tests proving a changed evidence revision invalidates a prior approval and prevents eligibility until a newly authorized review.
4. API tests for auth/role/site scoping and safe behavior on missing graph/policy services.
5. Frontend tests or equivalent browser verification for loading/empty/error states, impact detail, agent/model trace, curation review, and approval status.
6. A synthetic end-to-end walkthrough through the actual Kairos UI and API, capturing the exact run commands, output, and screenshots/artifacts.
7. Typecheck, lint, production build, diff check, and relevant test summary. Report every skipped or blocked check and why.

Never count a mocked unit test as the end-to-end proof. Label any synthetic data and demo-only services. No benchmark, novelty, model-tuning, or “production-ready” claim without reproducible evidence.

## SOURCE INTEGRATION AND TWO-REPO ACCOUNTING

Keep the source queue bounded and evidence-based. The 98 repository list is a set of candidates, not a success target. Continue the existing source audit and queue in batches, but the flagship work is complete only when the end-to-end slice above runs.

For each source actually used, record repository URL, commit, exact source path/symbol, behavior observed, license/permission status, dependency/security review, adaptation made, Kairos destination, tests, and runtime proof. Keep separate counts for sources audited, sources adapted, services connected, and capabilities verified. Treat README claims, demo JSONL, placeholder outputs, and “fine-tuned” model names as unverified until actual source/runtime evidence confirms them.

Keep the two product roots clear:

- `Kairos/` owns the app, user interface, APIs, auth, workflow policy, and graph integration.
- `ResolveAI/` retains its independent source/history and its unfinished original product capabilities. Kairos imports only selected, reviewed domain capabilities behind native boundaries.

Do not report “merged everything” because directories were moved or files copied. Report what is actually integrated and what remains in ResolveAI.

## REQUIRED DELIVERABLES

Update existing documents rather than creating duplicates. Produce or maintain:

- `Kairos/docs/integration/RESOLVEAI_INVENTORY.md` — accurate capability map and integration disposition.
- `Kairos/docs/integration/DEPENDENCY_CONFLICTS.md` — current conflicts and decisions.
- `Kairos/docs/integration/INTEGRATION_QUEUE.json` and `98_SOURCE_MASTER_LEDGER.csv` — truthful source statuses.
- `Kairos/docs/integration/EVIDENCE_DRIFT_ARCHITECTURE.md` — contracts, graph, temporal/provenance model, policy, limits, failure modes.
- `Kairos/docs/integration/TEST_EVIDENCE.md` — commands, exact outcomes, fixture/data safety, runtime proof.
- `Kairos/docs/integration/PROGRESS_CHECKPOINT.md` — updated phase, changed paths, verified behavior, gaps, exact next action.
- Working Kairos code for the API/service/graph/user flow; do not substitute documentation for implementation.

Do not modify this prompt or the older prompt unless asked. Do not commit or publish unless the user separately asks.

## DEFINITION OF DONE FOR THE FIRST RELEASE SLICE

Declare the slice done only if all are true:

- Kairos remains the clearly visible product and original routes/workflows still work.
- ResolveAI contributes a verified investigation capability through Kairos-owned auth and contracts; its unfinished status is visible in the integration record.
- A real local FalkorDB graph records versioned evidence dependencies and a real bounded query determines which synthetic decision/recommendation is affected.
- One synthetic suspected-fraud investigation demonstrates what authorized, adjudicated agent memory adds versus the same run without memory; findings stay provisional until evidence-backed human review.
- Stale or ambiguous evidence blocks eligibility; approval is revision-bound and requires an authorized human.
- Missing telemetry is represented as an obligation/coverage gap and `UNKNOWN`; it is investigated as negative-space evidence, never silently interpreted as healthy or automatically malicious.
- The RDS shows actual agents and model registrations/traces, impact paths, curation states, and training/checkpoint availability truthfully.
- Data curation is actionable, team-attributed, versioned, and audited. Model training is only claimed when a real artifact completed evaluation and registration.
- Synthetic end-to-end run, relevant checks, screenshots, and API outputs are reproducible; no production/shared cloud store was changed.
- Ledger/checkpoint accurately separate implemented, verified, blocked, and deferred work.

## FINAL RESPONSE FORMAT

Be concise and evidence-based. Report:

1. **Built:** actual user-visible and backend behavior, with file links.
2. **Product structure:** whether the two roots were moved/renamed and how Git history was preserved.
3. **ResolveAI contribution:** exact capability/source symbol integrated and what remains unfinished.
4. **FalkorDB proof:** graph records, query behavior, scope/limits, affected synthetic decision, and memory-on/off investigation evidence.
5. **RDS:** working agent map, model registry status, curation/team workflow, fine-tune status, and cyber-defense capability maturity labels.
6. **Verification:** commands and exact results; distinguish unit, integration, browser, and live-provider evidence.
7. **Limitations and next action:** precise blockers, never generic “more work needed.”

Start with Gate 0 now. Do not ask the user to repeat permission for reversible local work already authorized. Ask only if a newly discovered action would delete/overwrite user data, mutate production/cloud data, incur cost, publish externally, or exceed the stated scope; otherwise use the safest evidence-based implementation choice and continue.
