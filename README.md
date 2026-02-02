# LGV Troubleshooting Knowledge Graph

Entity-Event-Concept (EEC) knowledge graph extraction from technical documentation for LGV (forklift) troubleshooting and maintenance support.

## Overview

Transforms manuals into a troubleshooting-ready knowledge graph. Supports optional Neo4j updates during ingestion and can also export JSON snapshots.

## Prerequisites

- Python 3.8+
- Anthropic API key (Claude 3.5 Sonnet access)
- Neo4j (optional): if you want live graph updates

## Install

```bash
git clone https://github.com/yourusername/graph-data-modeling-PoC.git
cd graph-data-modeling-PoC
pip install -r requirements.txt
```

## Configure environment

Create a `.env` file in the repo root:

```bash
# Required
ANTHROPIC_API_KEY=your_key

# Optional Neo4j (to write while ingesting)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
# Optional database name
# NEO4J_DATABASE=neo4j
```

## Quick example

```bash
PYTHONPATH=. python3 scripts/run_ingest_from_file.py --input data/input/smile80.txt --save-every 10
```

## Ingest data

### Option A: Use included E80 manual

```bash
PYTHONPATH=. python3 scripts/run_graph_extraction.py \
  --start-chunk 0 \
  --save-every 1
```

Defaults read `data/input/E80_manual_text.txt` and export `data/output/e80_eec_knowledge_graph.json`. Add `--with-temporal-schema` to also export `data/output/e80_temporal_patterns.json` and `data/output/e80_schemas.json`.

### Option B: Ingest your own file (TXT)

```bash
PYTHONPATH=. python3 scripts/run_ingest_from_file.py \
  --input data/input/smile80.txt \
  --start-chunk 0 \
  --save-every 1
```

### Convert a PDF to TXT first (if needed)

```bash
PYTHONPATH=. python3 scripts/pdf_to_text.py \
  --pdf "/absolute/path/to/manual.pdf" \
  --out data/input/my_manual.txt
```

## CLI options

- `--start-chunk <int>`: resume from chunk index (default 0)
- `--with-temporal-schema`: also compute temporal patterns and schemas
- `--save-every <int>`: save progress every N chunks (default 1)

## Outputs

- `data/output/e80_eec_knowledge_graph.json`: current EEC snapshot (entities, events, concepts, relationships)
- Progress files during run: `data/output/e80_eec_knowledge_graph_progress_<processed>of<total>.json`
- Progress stats: `data/output/e80_eec_knowledge_graph_progress_<...>_stats.json`
- Final EEC save at end: `data/output/e80_eec_knowledge_graph_final.json` (+ `_stats.json`)
- When `--with-temporal-schema` is used:
  - `data/output/e80_temporal_patterns.json`
  - `data/output/e80_schemas.json`

## How it works (brief)

1. Reads and preprocesses text (removes page markers/line numbers, normalizes whitespace)
2. Splits into 800-character chunks with 100-character overlap
3. Extracts EEC elements per chunk using Claude 3.5 Sonnet
4. Optionally writes to Neo4j after each chunk
5. Periodically saves JSON progress and stats; writes final files at completion

## Project structure

```
graph-data-modeling-PoC/
├── src/
│   ├── eec_graph_transformer.py    # Entity-Event-Concept extraction
│   ├── temporal_extractor.py       # Temporal pattern analysis
│   ├── schema_inducer.py           # Hierarchical schema creation
│   └── graph_builder.py            # Orchestrates ingestion & exports
├── scripts/
│   ├── run_graph_extraction.py     # Ingest default E80 input
│   ├── run_ingest_from_file.py     # Ingest arbitrary TXT input
│   └── pdf_to_text.py              # Utility to convert PDF -> TXT
├── data/
│   ├── input/                      # Place your .txt manuals here
│   │   └── E80_manual_text.txt     # Included example
│   └── output/                     # default export location
└── requirements.txt                # Python dependencies
```

## Notes

- Neo4j is optional: without it, the pipeline still exports JSON files.
- To limit processing to a subset, use `--start-chunk` to resume; chunk size/overlap are fixed in `src/graph_builder.py`.
- Ensure `.env` has `ANTHROPIC_API_KEY` set before running.
- To move existing root-level JSONs into `data/output/`, run `PYTHONPATH=. python3 scripts/move_root_jsons_to_output.py`.