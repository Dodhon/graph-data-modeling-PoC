# Plan: HITL Workflow for LGV Neo4j Troubleshooting Chatbot

## End User Context
- Primary user: non-technical customer reporting LGV (Laser Guided Vehicle) issues.
- Secondary user: operations/reliability operator reviewing uncertain or high-impact recommendations.
- Business need: provide fast, plain-language troubleshooting recommendations while preventing low-confidence automation from being treated as final truth.

## Current Repo State
- Prompt baseline exists and is customer-friendly: `prompts/neo4j_chatbot_prompt_v2.txt`.
- Prompt already enforces read-only Neo4j behavior and schema-first investigation: `prompts/neo4j_chatbot_prompt_v2.txt`.
- Repository currently has no HITL MCP servers or HITL storage layout.
- Existing project is focused on extraction/ingestion scripts and Neo4j data prep, not operator review workflow:
  - `scripts/run_stakeholder_extraction.py`
  - `scripts/reset_and_ingest_stakeholder_output.py`
  - `src/graph_builder.py`
- `dev_plans/` did not previously exist in this repo; this plan initializes it.

## User Requirements
1. Keep the chatbot’s current non-technical customer communication style.
2. Keep Neo4j access read-only.
3. Add HITL so low-confidence/ambiguous/high-impact cases are escalated to a human operator.
4. Produce a deterministic review flow where operator decisions are explicit and auditable.
5. Preserve momentum: chatbot should still provide best effort recommendation when possible.

## Goals
- Add a durable, file-first HITL queue for troubleshooting cases needing human review.
- Separate capture from review so customer chat and operator decisioning remain independent.
- Define a strict record schema so downstream automation can rely on machine-checkable decisions.
- Introduce confidence-based routing rules in prompts so escalation is consistent.

## Non-Goals
- Automatic writes back to Neo4j from chatbot or review flow.
- Full multi-tenant auth system in v1.
- UI buildout beyond MCP tool + prompt driven workflow.
- Migrating HITL persistence to SQL/Neo4j in the first implementation pass.

## Architecture Context and Assumptions
- Runtime model: Claude Desktop + MCP servers.
- Existing Neo4j MCP remains read-only from the chatbot’s perspective.
- HITL services are local MCP Python servers, parallel to existing workflow.
- File-first storage is acceptable for MVP and mirrors the proven VMRS pattern.

Path assumptions:
- `REPO_ROOT` for MCP servers is derived from `Path(__file__).resolve().parents[2]`.
- HITL storage root proposed: `REPO_ROOT / "HitL_local"`.
- Pending queue: `HitL_local/pending/`.
- Reviewed queue: `HitL_local/reviewed/approved/` and `HitL_local/reviewed/rejected/`.

## Proposed Workflow
1. Customer submits LGV issue.
2. Chatbot investigates via read-only Neo4j MCP tools.
3. Chatbot assigns confidence (`high|medium|low`) and impact (`normal|high`).
4. If confidence is high and impact normal, chatbot returns recommendation.
5. If confidence is medium/low, evidence conflicts, or impact high, chatbot submits HITL capture record.
6. Operator reviews queued item and records `approved` or `rejected` with short rationale.
7. Chatbot can reference reviewed outcomes in future follow-up workflows (without writing Neo4j).

## Architecture Diagram
```text
Customer
   |
   v
LGV Troubleshooting Chatbot (prompt-guided)
   |                         \
   | read-only Cypher         \ escalate when uncertain/high-impact
   v                           v
Neo4j MCP (read-only)      HITL Capture MCP
                                |
                                v
                      HitL_local/pending/*.json
                                |
                                v
                        HITL Review MCP (operator)
                           |                |
                           v                v
      HitL_local/reviewed/approved/*.json   HitL_local/reviewed/rejected/*.json
```

## Data Contracts (MVP)

### Pending submission record
- `schema_version: int`
- `id: str` (format `HITL-<uuid4>`)
- `submitted_at_ms: int` (epoch milliseconds UTC)
- `status: "pending"`
- `issue` object:
  - `ticket_id: str | null`
  - `lgv_id: str | null`
  - `site: str | null`
  - `reported_symptom: str`
- `investigation` object:
  - `what_checked: str[]`
  - `evidence: str[]`
  - `candidate_root_cause: str | null`
  - `services_connections_involved: str[]`
  - `confidence: "high"|"medium"|"low"`
  - `impact: "normal"|"high"`
- `recommendation` object:
  - `proposed_next_action: str`
  - `expected_outcome: str`
- `why_escalated: str`
- `missing_information: str[]`
- `submitter` object:
  - `name: str`
  - `role: str`
  - `id?: str`
  - `team?: str`

### Reviewed record additions
- `status: "reviewed"`
- `review` object:
  - `decision: "approved"|"rejected"`
  - `reviewed_at_ms: int`
  - `notes: str`
  - `operator` object with `name`, `role`, optional `id`, optional `team`
- Legacy mirror fields may be included for back-compat if needed:
  - `decision`, `reviewed_at_ms`, `review_notes`, `reviewed_by`

## MCP Tool Surface (MVP)

Capture MCP (`mcp/hitl_get_feedback/server.py`):
- `submit_issue_for_review(...)`
- `get_submission_status(submission_id)`
- `list_submissions(limit=10)`

Review MCP (`mcp/hitl_review/server.py`):
- `list_submissions(limit=10, location="pending|approved|rejected")`
- `get_submission(submission_id)`
- `record_review(submission_id, outcome, reviewed_by, review_notes, operator_name, operator_role, operator_id?, operator_team?)`

## Error and Empty-State Handling (minimum)
- Invalid payload: return `{status:"error", message:"..."}` with first validation failure.
- Missing ID: return `{status:"error", message:"submission_id is required"}`.
- Not found: return `{status:"not_found", id:"..."}`.
- Invalid location filter: return `{status:"error", message:"Invalid location..."}`.
- Duplicate review destination: reject overwrite and return error.
- Empty queue: return success with `count: 0` and empty `submissions`.

## Determinism and Integrity Rules
- Tool call is the only source of truth for persisted decision.
- Enforce enum outcomes at server layer (`approved|rejected`).
- Enforce filename/id match.
- Use atomic move/write for review transitions.
- Prevent path traversal by strict ID validation.
- Bound oversized text fields to avoid unbounded storage growth.

## Prompt Changes Required
- Add a v3 prompt based on `prompts/neo4j_chatbot_prompt_v2.txt` with:
  - explicit confidence assignment step
  - escalation triggers
  - required handoff fields for operator review
  - unchanged read-only Neo4j restrictions

## Core PR (Must-Do Work)
1. Add HITL design plan doc (this PR).
2. Add implementation issue checklist tied to this plan.
3. Confirm naming and storage conventions for LGV-specific HITL records.

## Optional Follow-Ups
1. Implement HITL capture MCP server in this repo.
2. Implement HITL review MCP server in this repo.
3. Add prompt v3 HITL escalation workflow.
4. Add schema validation tests similar to VMRS `tests/test_hitl_schema.py`.
5. Add basic metrics script for queue depth and review throughput.

## Success Metrics
- 100% of medium/low-confidence investigations create a HITL record.
- 100% of reviewed records contain `decision`, `reviewed_at_ms`, and operator identity (`name`, `role`).
- 0 Neo4j write operations initiated by chatbot/review flow.
- Median operator review completion time < 2 business days for pending queue.
- < 1% invalid record write attempts after schema validation is enabled.

## Risks and Mitigations
- Risk: prompt drift causes inconsistent escalation.
  - Mitigation: deterministic trigger rules in prompt + examples.
- Risk: file corruption/partial writes.
  - Mitigation: atomic writes and staging move strategy.
- Risk: operator fatigue from noisy escalations.
  - Mitigation: strict escalation criteria + confidence gating.

## Open Questions
1. Should `skip` be a persisted review state or a non-persisted operator action?
2. Are review notes required for both approve and reject, or reject only?
3. Should identity be mandatory at capture time, or allow `Unknown/unspecified` placeholders in MVP?
4. Do we need tenant/site segregation now (`tenant_id`), or in phase 2?

## References
- MCP specification (tooling patterns): https://modelcontextprotocol.io/specification
- Neo4j Cypher manual: https://neo4j.com/docs/cypher-manual/current/
- Neo4j temporal values guidance: https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/
- Temporal human-in-the-loop durability concepts: https://learn.temporal.io/tutorials/ai/building-durable-ai-applications/human-in-the-loop/
- Letta HITL guide: https://docs.letta.com/guides/agents/human-in-the-loop/
