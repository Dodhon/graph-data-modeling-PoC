# Ollama Llama 3.1 Node Dedup Plan

## End user context
- Primary user is a developer/data engineer working with the LGV knowledge graph outputs.
- Technical level: comfortable running Python scripts and editing config blocks.
- Goal: reduce duplicate nodes before Neo4j ingestion while keeping an audit trail.

## User requirements
- Detect likely duplicate nodes across `data/neo4j_nodes.json`.
- Use Ollama with Llama 3.1 8B Instruct for semantic matching on shortlisted pairs.
- Produce a merge map and a deduped nodes/relationships output that can be ingested.
- Keep the process reproducible and reviewable (no silent merges without evidence).

## Architecture diagram
```
            +---------------------------+
            | data/neo4j_nodes.json     |
            | data/neo4j_relationships  |
            +-------------+-------------+
                          |
                          v
               +--------------------+
               | Candidate Builder  |
               | (type/domain block |
               | + string similarity)|
               +----------+---------+
                          |
                          v
               +--------------------+        +--------------------+
               | Ollama LLM Judge   |<------>| Ollama server      |
               | llama3.1 8B        |        | /api/chat          |
               +----------+---------+        +--------------------+
                          |
                          v
               +--------------------+
               | Merge Map + Report |
               +----------+---------+
                          |
                          v
               +--------------------+
               | Deduped JSON       |
               | nodes + rels       |
               +--------------------+
```

## Goals
- Provide a minimal, local workflow to evaluate duplicate nodes with Ollama.
- Limit LLM calls by generating candidate pairs via cheap heuristics first.
- Output deduped JSON files and a human-readable audit trail.

## Non-goals
- No automated in-DB dedupe or Neo4j GDS pipeline in this iteration.
- No GUI for review; output JSON/CSV only.
- No cross-document entity resolution beyond the current JSON exports.

## Success metrics
- ≥ 80% of obvious duplicates merged in a small sample review set.
- < 1% false-positive merges in a manually checked sample (e.g., 100 pairs).
- End-to-end run completes within a reasonable time (< 1 hour on local machine).

## Research summary (how to use Ollama)
- Ollama chat API supports JSON-structured output via `format` (JSON schema), which is ideal for consistent dedupe decisions: https://docs.ollama.com/api/chat
- Ollama structured output guidance: https://ollama.com/blog/structured-outputs
- Llama 3.1 8B Instruct models for Ollama (quantized variants):  
  https://ollama.com/library/llama3.1:8b-instruct-q8_0  
  https://ollama.com/library/llama3.1:8b-instruct-q6_K
- Ollama Python client examples (optional): https://github.com/ollama/ollama-python

## Proposed approach
1. **Candidate generation (no LLM)**
   - Primary pass: group by label group (Entity/Event/Concept) and optional `properties.domain`.
   - Secondary pass (cross-type safety net): allow cross-type candidates when names are highly similar
     (e.g., exact normalized match or very high similarity threshold).
   - Normalize `properties.name` and `properties.description` (lowercase, strip punctuation, collapse whitespace).
   - Generate candidate pairs by string similarity (e.g., `difflib.SequenceMatcher`) above a threshold.
   - Cap per-node candidate count to avoid combinatorial explosion.

2. **LLM evaluation with Ollama**
   - For each candidate pair, call `/api/chat` with `model=llama3.1:8b-instruct-q8_0` (or q6_K).
   - Use JSON schema output to force a consistent structure:
     - `same` (bool)
     - `confidence` (0–1)
     - `canonical_name` (string)
     - `reason` (string, short)
   - Only accept merges above a strict confidence threshold (e.g., ≥ 0.85).

3. **Merge application**
   - Build `merge_map.json` mapping `duplicate_id -> canonical_id`.
   - Apply map to nodes: collapse duplicates, merge properties (prefer non-empty).
   - If labels disagree, default to **no merge** and emit a `same_as` suggestion in the review output
     (or require manual override for cross-type merges).
   - Apply map to relationships: rewrite `source/target`, then de-dupe identical triples.

4. **Outputs (no overwrites)**
   - Always write to a new timestamped run directory.
   - `data/dedupe/run_<timestamp>/merge_map.json`
   - `data/dedupe/run_<timestamp>/review_pairs.json`
   - `data/dedupe/run_<timestamp>/neo4j_nodes_deduped.json`
   - `data/dedupe/run_<timestamp>/neo4j_relationships_deduped.json`
   - `data/dedupe/latest.json` points to last run directory

## Path assumptions, schema, IDs
- `REPO_ROOT` derived from `Path(__file__).resolve().parents[1]` in a new script.
- Inputs are read-only: `data/neo4j_nodes.json`, `data/neo4j_relationships.json`.
- Outputs written under `data/dedupe/` and new deduped files in `data/`.
- **Node schema** (current): `{"id": str, "labels": [str], "properties": {...}}`.
- **Relationship schema**: `{"source": str, "target": str, "type": str, "properties": {...}, "temporal_info": {...}}`.
- **Run IDs**: use UTC timestamp `YYYYMMDDTHHMMSSZ` for run folder names; `latest.json` stores that ID.

## Error and empty states
- Missing input files: fail fast with clear message.
- No candidates found: write empty `review_pairs.json` and no merge map.
- Ollama unavailable: log error and keep candidates for manual review.
- LLM response invalid JSON: retry once, then flag as `error` in review output.

## Core PR (must-do)
- Add a new script, e.g. `scripts/dedupe_nodes_with_ollama.py`.
- Implement candidate generation and review queue.
- Add Ollama JSON-schema evaluation via `/api/chat`.
- Apply merge map to nodes/relationships and write outputs.
- Document usage in `README.md` (short, minimal).

## Optional follow-ups
- Add sampling report for manual QA (top-100 pairs).
- Add a dry-run mode that only outputs candidates without LLM calls.
- Add batching and rate controls for Ollama calls.
