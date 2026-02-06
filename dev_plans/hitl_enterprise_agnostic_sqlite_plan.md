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
- **Canonical HITL envelope** (domain-agnostic columns for workflow, identity, timestamps, decision, status).
- **Domain payload JSON** (use-case-specific details validated against a schema registry).

Why this is the best fit:
1. Keeps review workflow and audit behavior consistent enterprise-wide.
2. Avoids forcing every domain into one rigid table shape.
3. Supports deterministic server-side validation and approval semantics.
4. Allows LGV PoC integration now, with minimum rework later.

## User Requirements
1. HITL MCP tools must be data-agnostic as much as possible.
2. SQLite must be the default persistence layer.
3. Domain-specific details must not be hardcoded into HITL core workflow.
4. All decisions must be explicit and machine-checkable.
5. Existing LGV PoC should be able to adopt this without rewriting Neo4j logic.

## Goals
- Build a reusable HITL core usable by any enterprise chatbot/workflow.
- Introduce SQLite-backed queue and review lifecycle with strong integrity guarantees.
- Keep domain specificity at the adapter/schema layer.
- Integrate LGV troubleshooting as the first adapter.

## Non-Goals
- Replacing domain systems of record (Neo4j/CRM/ITSM) with SQLite.
- Solving enterprise IAM/SSO in v1 (but provide clean auth seam).
- Building full UI product in this repo.

## Architecture

### Core model
- `hitl_cases`: one row per submission (canonical envelope + payload JSON).
- `hitl_reviews`: append-only review decisions/events.
- `hitl_schema_registry`: domain payload schemas (JSON Schema or equivalent).
- `hitl_case_refs`: optional references to external entities (e.g., Neo4j node ids, ticket ids).

### Domain adapter model
- `adapter_id` identifies domain pack (e.g., `lgv_troubleshooting`, `payments_risk`, `it_ops`).
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
     +---------------------+
     | hitl_cases          |
     | hitl_reviews        |
     | hitl_schema_registry|
     | hitl_case_refs      |
     +---------------------+
            |
            v
      Review MCP/Core Tools
            |
            v
      Operator decision flow
```

## SQLite Schema (proposed)

### `hitl_cases`
- `case_id TEXT PRIMARY KEY` (`HITL-<uuid4>`)
- `schema_version INTEGER NOT NULL`
- `adapter_id TEXT NOT NULL`
- `case_type TEXT NOT NULL` (e.g., `question|correction|incident`)
- `status TEXT NOT NULL` (`pending|reviewed|closed`)
- `priority TEXT NOT NULL DEFAULT 'normal'` (`low|normal|high|critical`)
- `confidence TEXT` (`high|medium|low`)
- `title TEXT NOT NULL`
- `summary TEXT NOT NULL`
- `payload_json TEXT NOT NULL` (adapter-specific)
- `submitter_name TEXT NOT NULL`
- `submitter_role TEXT NOT NULL`
- `submitter_id TEXT`
- `submitter_team TEXT`
- `created_at_ms INTEGER NOT NULL`
- `updated_at_ms INTEGER NOT NULL`

Indexes:
- `(status, priority, created_at_ms DESC)`
- `(adapter_id, status, created_at_ms DESC)`

### `hitl_reviews` (append-only)
- `review_id TEXT PRIMARY KEY` (`HRV-<uuid4>`)
- `case_id TEXT NOT NULL` (FK to `hitl_cases.case_id`)
- `decision TEXT NOT NULL` (`approved|rejected|needs_info`)
- `notes TEXT NOT NULL`
- `operator_name TEXT NOT NULL`
- `operator_role TEXT NOT NULL`
- `operator_id TEXT`
- `operator_team TEXT`
- `reviewed_at_ms INTEGER NOT NULL`

Indexes:
- `(case_id, reviewed_at_ms DESC)`
- `(decision, reviewed_at_ms DESC)`

### `hitl_schema_registry`
- `adapter_id TEXT PRIMARY KEY`
- `schema_version INTEGER NOT NULL`
- `schema_json TEXT NOT NULL`
- `is_active INTEGER NOT NULL` (`0|1`)
- `updated_at_ms INTEGER NOT NULL`

### `hitl_case_refs`
- `case_id TEXT NOT NULL`
- `ref_type TEXT NOT NULL` (e.g., `neo4j_node`, `ticket`, `service`)
- `ref_key TEXT NOT NULL`
- `ref_value TEXT NOT NULL`
- PK `(case_id, ref_type, ref_key, ref_value)`

## MCP Tool Surface (data-agnostic)

Capture:
- `submit_case(adapter_id, case_type, title, summary, payload, submitter, priority?, confidence?, refs?)`
- `get_case(case_id)`
- `list_cases(status?, adapter_id?, priority?, limit?, cursor?)`

Review:
- `list_review_queue(adapter_id?, priority?, limit?)`
- `record_decision(case_id, decision, notes, operator_name, operator_role, operator_id?, operator_team?)`
- `get_case_history(case_id)`

Admin (optional for v1.1):
- `register_adapter_schema(adapter_id, schema_version, schema_json)`
- `activate_adapter_schema(adapter_id, schema_version)`

## Determinism and Safety Requirements
1. Decision persistence only through `record_decision` tool.
2. Validate envelope + adapter payload before write.
3. Use SQLite transactions (`BEGIN IMMEDIATE`) for review writes.
4. Enforce single active terminal decision policy per case (or formal multi-review policy).
5. Add idempotency key support for retry-safe writes.
6. Keep all timestamps in epoch millis UTC.

## Path and Runtime Assumptions
- `REPO_ROOT` derived from server location (`Path(__file__).resolve().parents[2]` if under `mcp/.../server.py`).
- SQLite DB default path: `REPO_ROOT / "data" / "hitl" / "hitl.db"`.
- Migrations path: `REPO_ROOT / "mcp" / "hitl_core" / "migrations"`.
- WAL mode enabled for better concurrent reads during review operations.

## Error and Empty States (minimum)
- Invalid adapter: `{status:"error", code:"ADAPTER_NOT_FOUND"}`.
- Schema validation failure: `{status:"error", code:"PAYLOAD_INVALID", details:[...]}`.
- Case not found: `{status:"not_found", case_id:"..."}`.
- Queue empty: `{status:"success", count:0, items:[]}`.
- Duplicate decision attempt: `{status:"error", code:"ALREADY_DECIDED"}` (or return existing decision based on policy).

## LGV PoC Integration Strategy
1. Keep `prompts/neo4j_chatbot_prompt_v2.txt` behavior intact (read-only Neo4j).
2. Add a v3 prompt that calls data-agnostic `submit_case(...)` when confidence is medium/low or impact high.
3. Define adapter `lgv_troubleshooting` with payload schema:
   - symptom, site, lgv_id, services_checked, connection_path, evidence, missing_data, proposed_next_action.
4. Do not store raw Cypher or full transcripts by default; store summarized evidence + refs.

## Rollout Phases

### Phase 1: Platform foundation
- Create SQLite schema + migration runner.
- Implement core MCP tools (`submit_case`, `get_case`, `list_cases`, `record_decision`).
- Add deterministic validation and transaction guards.

### Phase 2: LGV adapter integration
- Add `lgv_troubleshooting` schema in registry.
- Add prompt v3 escalation contract for LGV chatbot.
- Validate end-to-end queue from chatbot to review decision.

### Phase 3: Enterprise hardening
- Add auth principal seam (caller identity abstraction).
- Add pagination/cursor support and basic analytics endpoints.
- Add optional event outbox for downstream sync.

## Core PR (Must-do next)
1. Add `mcp/hitl_core/` SQLite-backed server skeleton.
2. Add migration SQL for four core tables.
3. Add adapter registry loader with `lgv_troubleshooting` seed schema.
4. Add tests for validation, idempotency, and review transitions.

## Optional Follow-ups
1. Add web reviewer UI over MCP endpoints.
2. Add export jobs (CSV/JSON) for audit and BI.
3. Add multi-tenant partitioning (`tenant_id`) once org boundaries are finalized.

## Success Metrics
- 100% of cases persisted through canonical envelope (no adapter bypass).
- 100% of decisions captured via `record_decision` with operator identity.
- <1% validation failures in production submissions after initial tuning.
- Median review latency by adapter visible from SQLite query metrics.
- Zero Neo4j write operations from HITL core by design.

## Key Risks and Mitigations
- Risk: over-generic model loses domain fidelity.
  - Mitigation: adapter schema registry + required adapter validation.
- Risk: SQLite lock contention under load.
  - Mitigation: WAL mode, short transactions, batched readers; migrate to server DB only when needed.
- Risk: inconsistent escalation criteria across agents.
  - Mitigation: enforce confidence/impact contract in prompt templates and tool wrappers.

## Decision
Proceed with **data-agnostic HITL core + adapter schemas on SQLite**. This gives enterprise reuse while keeping this LGV PoC a strong first consumer.

## References
- SQLite docs (WAL, transactions): https://www.sqlite.org/docs.html
- MCP specification: https://modelcontextprotocol.io/specification
- JSON Schema core guidance: https://json-schema.org/specification
- Neo4j Cypher manual (read/query behavior context): https://neo4j.com/docs/cypher-manual/current/
