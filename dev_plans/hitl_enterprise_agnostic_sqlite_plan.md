# Plan: Enterprise-Agnostic HITL MCP with SQLite (and LGV PoC Integration)

## End User Context
- Primary operators: domain teams across the enterprise who review AI recommendations before action.
- Secondary users: chatbot agents (LGV now, other use cases later) that escalate uncertain/high-impact outputs.
- Core need: one reusable HITL platform that is data-agnostic, deterministic, auditable, and easy to plug into different domains.

## Current Repo State
- LGV chatbot prompt exists and is domain-specific: `prompts/neo4j_chatbot_prompt_v2.txt`.
- Existing HITL plan is LGV-focused and file-first: `dev_plans/hitl_lgv_chatbot_plan.md`.
- No HITL MCP servers currently exist in this repo.
- No SQLite persistence layer currently exists for HITL in this repo.

## Evaluation Summary
Recommendation: move to a **hybrid schema** in SQLite:
- **Canonical HITL envelope** (domain-agnostic case metadata and workflow state).
- **Domain payload JSON** (adapter-specific details validated by schema registry).
- **Append-only event log + state projection** for deterministic follow-up and auditability.

Key contract:
- Terminal review outcomes are only `approved|rejected`.
- Follow-up is modeled as non-terminal `needs_clarification` state/event.
- `Skip` maps to `needs_clarification`, not `rejected`.

Why this is the best fit:
1. Keeps workflow/audit behavior consistent enterprise-wide.
2. Avoids forcing every domain into one rigid table shape.
3. Supports deterministic server-side validation and approval semantics.
4. Supports follow-up loops without weakening terminal decision integrity.
5. Allows LGV PoC integration now, with minimum rework later.

## User Requirements
1. HITL MCP tools must be data-agnostic as much as possible.
2. SQLite must be the default persistence layer.
3. Domain-specific details must not be hardcoded into HITL core workflow.
4. All decisions must be explicit and machine-checkable.
5. Follow-up must be first-class and queryable (not hidden in free text only).
6. Existing LGV PoC should adopt this without rewriting Neo4j logic.

## Goals
- Build a reusable HITL core usable by any enterprise chatbot/workflow.
- Introduce SQLite-backed queue and lifecycle with strong integrity guarantees.
- Support `needs_clarification` follow-up as non-terminal state.
- Keep domain specificity at the adapter/schema layer.
- Integrate LGV troubleshooting as the first adapter.

## Non-Goals
- Replacing domain systems of record (Neo4j/CRM/ITSM) with SQLite.
- Solving enterprise IAM/SSO in v1 (but provide clean auth seam).
- Building full UI product in this repo.
- Automatic Neo4j writes from HITL decisions.

## Decision Contract
- Terminal outcomes enum: `approved|rejected`.
- Non-terminal workflow state: `needs_clarification`.
- `Skip` semantics: create a `needs_clarification` event and move case state to `needs_clarification`.
- First terminal decision wins for a case; later terminal attempts return existing terminal decision.
- Corrections/supersedes are append-only events; no in-place mutation of prior decision events.

## Architecture

### Core model
- `hitl_cases`: immutable case envelope + payload pointer and provenance baseline.
- `hitl_events`: append-only workflow/audit truth.
- `hitl_state`: current-state projection for queue operations.
- `hitl_schema_registry`: adapter payload schemas (JSON Schema or equivalent).
- `hitl_case_refs`: optional references to external entities (Neo4j nodes, tickets, services).

### Domain adapter model
- `adapter_id` identifies domain pack (for example `lgv_troubleshooting`, `payments_risk`, `it_ops`).
- Adapter provides:
  - payload validation schema
  - optional normalization hook
  - optional reviewer summary formatter

### ASCII architecture
```text
Domain Agent (LGV today, others later)
            |
            | submit_case(adapter_id, payload)
            v
      HITL MCP Core (data-agnostic)
            |
            | validate envelope + adapter schema
            v
         SQLite Store
     +-------------------------+
     | hitl_cases              |
     | hitl_events             |
     | hitl_state              |
     | hitl_schema_registry    |
     | hitl_case_refs          |
     +-------------------------+
            |
            v
      Review/Follow-up MCP tools
            |
            v
      Operator decision flow
```

## SQLite Schema (proposed)

### `hitl_cases`
- `case_id TEXT PRIMARY KEY` (`HITL-<uuid4>`)
- `schema_version INTEGER NOT NULL`
- `adapter_id TEXT NOT NULL`
- `case_type TEXT NOT NULL` (for example `question|correction|incident`)
- `title TEXT NOT NULL`
- `summary TEXT NOT NULL`
- `payload_json TEXT NOT NULL` (adapter-specific)
- `payload_hash_sha256 TEXT NOT NULL`
- `submitter_name TEXT NOT NULL`
- `submitter_role TEXT NOT NULL`
- `submitter_id TEXT`
- `submitter_team TEXT`
- `priority TEXT NOT NULL DEFAULT 'normal'` (`low|normal|high|critical`)
- `confidence TEXT` (`high|medium|low`)
- `created_at_ms INTEGER NOT NULL`
- `updated_at_ms INTEGER NOT NULL`

Indexes:
- `idx_hitl_cases_adapter_created` on `(adapter_id, created_at_ms DESC)`
- `idx_hitl_cases_priority_created` on `(priority, created_at_ms DESC)`

### `hitl_events` (append-only truth)
- `event_id TEXT PRIMARY KEY` (`HEV-<uuid4>`)
- `case_id TEXT NOT NULL` (FK -> `hitl_cases.case_id`)
- `event_type TEXT NOT NULL`
  - allowed: `submitted|needs_clarification|clarification_provided|decision_recorded|decision_superseded`
- `decision_outcome TEXT`
  - allowed when `event_type=decision_recorded`: `approved|rejected`
- `notes TEXT NOT NULL`
- `question TEXT` (required for `needs_clarification`)
- `answer TEXT` (required for `clarification_provided`)
- `actor_kind TEXT NOT NULL` (`operator|agent|system`)
- `actor_name TEXT NOT NULL`
- `actor_role TEXT NOT NULL`
- `actor_id TEXT`
- `actor_team TEXT`
- `supersedes_event_id TEXT`
- `request_id TEXT` (idempotency key)
- `event_json TEXT NOT NULL` (canonical serialized event)
- `created_at_ms INTEGER NOT NULL`

Indexes:
- `idx_hitl_events_case_created` on `(case_id, created_at_ms DESC)`
- `idx_hitl_events_type_created` on `(event_type, created_at_ms DESC)`
- `idx_hitl_events_decision_created` on `(decision_outcome, created_at_ms DESC)`
- `idx_hitl_events_request_id` on `(request_id)`

### `hitl_state` (queue projection)
- `case_id TEXT PRIMARY KEY` (FK -> `hitl_cases.case_id`)
- `current_state TEXT NOT NULL`
  - allowed: `pending|needs_clarification|approved|rejected`
- `active_terminal_event_id TEXT`
- `active_decision_outcome TEXT`
- `needs_clarification_since_ms INTEGER`
- `escalation_due_at_ms INTEGER`
- `escalated_at_ms INTEGER`
- `escalation_target TEXT`
- `updated_at_ms INTEGER NOT NULL`

Indexes:
- `idx_hitl_state_current_updated` on `(current_state, updated_at_ms DESC)`
- `idx_hitl_state_escalation_due` on `(escalation_due_at_ms)`

### `hitl_schema_registry`
- `adapter_id TEXT PRIMARY KEY`
- `schema_version INTEGER NOT NULL`
- `schema_json TEXT NOT NULL`
- `is_active INTEGER NOT NULL` (`0|1`)
- `updated_at_ms INTEGER NOT NULL`

### `hitl_case_refs`
- `case_id TEXT NOT NULL`
- `ref_type TEXT NOT NULL` (for example `neo4j_node`, `ticket`, `service`)
- `ref_key TEXT NOT NULL`
- `ref_value TEXT NOT NULL`
- PK `(case_id, ref_type, ref_key, ref_value)`

## Minimum Query Requirements
1. List pending cases (latest N).
2. Get case by `case_id`.
3. List reviewed cases by terminal decision/date range.
4. Filter by operator/principal and date range.
5. Filter by adapter/domain keys via refs or payload fields.
6. Report throughput and approval/rejection rates over time.
7. Answer audit query: who decided what and when.
8. List `needs_clarification` backlog and age.
9. List cases with escalation due/overdue.
10. Support read-time interpretation of older schema versions.

## MCP Tool Surface (data-agnostic)

Capture:
- `submit_case(adapter_id, case_type, title, summary, payload, submitter, priority?, confidence?, refs?)`
- `get_case(case_id)`
- `list_cases(state?, adapter_id?, priority?, limit?, cursor?)`

Review/follow-up:
- `list_review_queue(adapter_id?, priority?, state?, limit?)`
- `request_clarification(case_id, question, notes, actor)`
- `provide_clarification(case_id, answer, notes, actor)`
- `record_decision(case_id, decision, notes, actor)`
  - `decision` enum: `approved|rejected` only
- `get_case_history(case_id)`

Admin (optional for v1.1):
- `register_adapter_schema(adapter_id, schema_version, schema_json)`
- `activate_adapter_schema(adapter_id, schema_version)`

## Determinism and Safety Requirements
1. Case/event persistence only through MCP tools.
2. Validate envelope + adapter payload before writes.
3. Use SQLite transactions (`BEGIN IMMEDIATE`) for write paths that touch events/state.
4. Enforce first-terminal-wins for each case.
5. Add `request_id` idempotency key for retry-safe writes.
6. Add bounds on payload/text sizes.
7. Keep all timestamps in epoch millis UTC.
8. Use append-only events; never rewrite history.
9. Keep state projection derived from events in the same transaction.

## Schema Evolution Strategy
- Every case/event stores `schema_version` (directly or through canonical envelope).
- Prefer read-time upcasting for older records.
- Use write-time migrations only for index/performance/storage changes.
- Keep canonical schema definitions in one module and generate prompt-safe excerpts from it.

## Path and Runtime Assumptions
- `REPO_ROOT` derived from server location (`Path(__file__).resolve().parents[2]` if under `mcp/.../server.py`).
- SQLite DB default path: `REPO_ROOT / "data" / "hitl" / "hitl.db"`.
- Migrations path: `REPO_ROOT / "mcp" / "hitl_core" / "migrations"`.
- WAL mode enabled for concurrent read-heavy review queues.

## Error and Empty States (minimum)
- Invalid adapter: `{status:"error", code:"ADAPTER_NOT_FOUND"}`.
- Schema validation failure: `{status:"error", code:"PAYLOAD_INVALID", details:[...]}`.
- Case not found: `{status:"not_found", case_id:"..."}`.
- Queue empty: `{status:"success", count:0, items:[]}`.
- Duplicate terminal attempt: `{status:"error", code:"ALREADY_TERMINAL"}` (or return existing terminal event).
- Clarification required but missing question: `{status:"error", code:"QUESTION_REQUIRED"}`.
- Clarification answer missing: `{status:"error", code:"ANSWER_REQUIRED"}`.
- Invalid transition: `{status:"error", code:"INVALID_STATE_TRANSITION"}`.

## Follow-up and Escalation Policy (MVP)
- `needs_clarification` is non-terminal and remains queue-visible.
- `provide_clarification` returns case to `pending`.
- If state remains `needs_clarification` past SLA (example 30 days), mark escalation fields in `hitl_state` and notify escalation target.
- Escalation policy is configurable per adapter/team.

## LGV PoC Integration Strategy
1. Keep `prompts/neo4j_chatbot_prompt_v2.txt` behavior intact (read-only Neo4j).
2. Add a v3 prompt that calls `submit_case(...)` when confidence is medium/low or impact is high.
3. On missing context, call `request_clarification(...)` and surface plain-language follow-up question.
4. Define adapter `lgv_troubleshooting` payload schema:
   - symptom, site, lgv_id, services_checked, connection_path, evidence, missing_data, proposed_next_action.
5. Do not store raw Cypher or full transcripts by default; store summarized evidence + refs.

## Rollout Phases

### Phase 1: Platform foundation
- Create SQLite schema + migration runner for:
  - `hitl_cases`, `hitl_events`, `hitl_state`, `hitl_schema_registry`, `hitl_case_refs`
- Implement core MCP tools (`submit_case`, `get_case`, `list_cases`, `record_decision`, clarification tools).
- Add deterministic validation, idempotency, and transaction guards.

### Phase 2: LGV adapter integration
- Add `lgv_troubleshooting` schema in registry.
- Add prompt v3 escalation/follow-up contract for LGV chatbot.
- Validate end-to-end queue flow: submit -> needs_clarification -> clarification_provided -> pending -> terminal decision.

### Phase 3: Enterprise hardening
- Add auth principal seam (server-derived caller identity).
- Add pagination/cursor support and analytics endpoints.
- Add export pipeline for approved/rejected datasets + manifests.
- Add optional outbox for downstream sync.

## Core PR (Must-do next)
1. Add `mcp/hitl_core/` SQLite-backed server skeleton.
2. Add migration SQL for `hitl_cases`, `hitl_events`, `hitl_state`, `hitl_schema_registry`, `hitl_case_refs`.
3. Add adapter registry loader with `lgv_troubleshooting` seed schema.
4. Add tests for validation, idempotency, transitions, and first-terminal-wins behavior.

## Optional Follow-ups
1. Add web reviewer UI over MCP endpoints.
2. Add export jobs (CSV/JSON) for audit and BI.
3. Add multi-tenant partitioning (`tenant_id`) once org boundaries are finalized.
4. Add claim/lease queue model if reviewer concurrency increases.

## Success Metrics
- 100% of cases persisted through canonical envelope (no adapter bypass).
- 100% of terminal decisions captured via `record_decision` with actor identity.
- 100% of follow-up requests captured as explicit events (not notes-only).
- <1% validation failures in production submissions after initial tuning.
- Median review latency and clarification turnaround visible from SQLite queries.
- Zero Neo4j write operations from HITL core by design.

## Key Risks and Mitigations
- Risk: over-generic model loses domain fidelity.
  - Mitigation: adapter schema registry + required adapter validation.
- Risk: SQLite lock contention under load.
  - Mitigation: WAL mode, short transactions, idempotency keys; migrate to server DB when needed.
- Risk: inconsistent escalation criteria across agents.
  - Mitigation: enforce confidence/impact and follow-up contract in prompt templates and tool wrappers.

## Decision
Proceed with **data-agnostic HITL core + adapter schemas on SQLite + event/state split**. This gives enterprise reuse while keeping this LGV PoC a strong first consumer.

## References
- SQLite docs (WAL, transactions): https://www.sqlite.org/docs.html
- MCP specification: https://modelcontextprotocol.io/specification
- JSON Schema core guidance: https://json-schema.org/specification
- Neo4j Cypher manual (read/query behavior context): https://neo4j.com/docs/cypher-manual/current/
