#!/usr/bin/env python3
"""
Minimal runner to ingest pre-combined Neo4j JSON, or (optionally)
ingest EEC graph from a specified text file.

Edit the config section below, then run:
  PYTHONPATH=. python3 scripts/run_ingest_from_file.py
"""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ---- Config (edit as needed) ----
MODE = "neo4j_json"  # "neo4j_json" or "manual_text"
NODES_JSON = "data/neo4j_nodes.json"
RELATIONSHIPS_JSON = "data/neo4j_relationships.json"
PROGRESS_EVERY = 1000

INPUT_TEXT = "data/input/smile80.txt"
START_CHUNK = 0
WITH_TEMPORAL_SCHEMA = False
SAVE_EVERY = 1
# ---------------------------------


def _sanitize_schema_token(value: str) -> str:
    if not value:
        return ""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value).strip("_")
    if not cleaned:
        return ""
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _load_json_list(path: Path) -> list:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}, got {type(data).__name__}")
    return data


def _print_progress(label: str, current: int, total: int, start_time: float) -> None:
    if total <= 0:
        return
    elapsed = max(0.0001, time.perf_counter() - start_time)
    rate = current / elapsed
    remaining = (total - current) / rate if rate > 0 else 0
    percent = (current / total) * 100
    message = (
        f"{label}: {current}/{total} ({percent:5.1f}%) "
        f"| {rate:,.1f}/s | ETA {remaining/60:,.1f}m"
    )
    print(f"\r{message}   ", end="", flush=True)
    if current >= total:
        print()


def _ingest_neo4j_json(driver: GraphDatabase, database: str | None, nodes_path: Path, rels_path: Path) -> None:
    nodes = _load_json_list(nodes_path)
    relationships = _load_json_list(rels_path)
    progress_every = max(1, PROGRESS_EVERY)

    with driver.session(database=database) as session:
        node_start = time.perf_counter()
        for idx, node in enumerate(nodes, start=1):
            node_id = node.get("id")
            if not node_id:
                continue
            current = idx
            labels = [
                _sanitize_schema_token(label)
                for label in (node.get("labels") or [])
            ]
            labels = [label for label in labels if label]
            label_clause = ":" + ":".join(sorted(set(labels))) if labels else ""

            properties = node.get("properties") or {}
            if not isinstance(properties, dict):
                properties = {}

            query = f"MERGE (n{label_clause} {{id: $id}}) SET n += $properties"
            session.run(query, {"id": node_id, "properties": properties})
            if current % progress_every == 0 or current == len(nodes):
                _print_progress("Nodes", current, len(nodes), node_start)

        rel_start = time.perf_counter()
        for idx, rel in enumerate(relationships, start=1):
            source = rel.get("source")
            target = rel.get("target")
            rel_type = _sanitize_schema_token(rel.get("type"))
            if not source or not target or not rel_type:
                continue
            current = idx

            properties = rel.get("properties") or {}
            if not isinstance(properties, dict):
                properties = {}
            if rel.get("source_labels"):
                properties["source_labels"] = rel.get("source_labels")
            if rel.get("target_labels"):
                properties["target_labels"] = rel.get("target_labels")

            temporal_info = rel.get("temporal_info") or {}
            if not isinstance(temporal_info, dict):
                temporal_info = {}

            query = f"""
            MATCH (a {{id: $source}})
            MATCH (b {{id: $target}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            """
            params = {"source": source, "target": target, "properties": properties}

            if temporal_info:
                query += " SET r.temporal_info = $temporal_info"
                params["temporal_info"] = temporal_info

            session.run(query, params)
            if current % progress_every == 0 or current == len(relationships):
                _print_progress("Relationships", current, len(relationships), rel_start)

    print(f"✅ Neo4j JSON ingest complete: {len(nodes)} nodes, {len(relationships)} relationships")


def main():
    load_dotenv()

    if MODE == "neo4j_json":
        print("🚀 Starting Neo4j JSON ingest")
        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_username = os.getenv("NEO4J_USERNAME")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        if not all([neo4j_uri, neo4j_username, neo4j_password]):
            print("❌ Please set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")
            return

        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_username, neo4j_password)
        )
        database = os.getenv("NEO4J_DATABASE")

        nodes_path = Path(NODES_JSON)
        rels_path = Path(RELATIONSHIPS_JSON)
        if not nodes_path.exists():
            print(f"❌ Nodes file not found: {nodes_path}")
            return
        if not rels_path.exists():
            print(f"❌ Relationships file not found: {rels_path}")
            return

        _ingest_neo4j_json(driver, database, nodes_path, rels_path)
        driver.close()
        return

    if MODE != "manual_text":
        print(f"❌ Unknown MODE: {MODE}")
        return

    print("🚀 Starting EEC ingestion from file")
    print(f"📖 Input: {INPUT_TEXT}")
    if START_CHUNK > 0:
        print(f"📍 Starting from chunk {START_CHUNK}")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Please set ANTHROPIC_API_KEY in .env file")
        return

    from src.graph_builder import ManualGraphBuilder

    builder = ManualGraphBuilder(
        anthropic_api_key=api_key,
        neo4j_uri=os.getenv("NEO4J_URI"),
        neo4j_username=os.getenv("NEO4J_USERNAME"),
        neo4j_password=os.getenv("NEO4J_PASSWORD")
    )

    if not os.path.exists(INPUT_TEXT):
        print(f"❌ Input file not found: {INPUT_TEXT}")
        return

    try:
        result = builder.build_graph_from_manual(
            file_path=INPUT_TEXT,
            start_chunk=START_CHUNK,
            process_temporal_schema=WITH_TEMPORAL_SCHEMA,
            save_every=max(1, SAVE_EVERY)
        )

        print("\n✅ EEC Graph ingestion completed!")
        print("📊 Statistics:")
        print(f"  - Total chunks processed: {result['total_chunks']}")
        print(f"  - EEC documents created: {result['total_eec_documents']}")
        print(f"  - Total entities extracted: {result['total_entities']}")
        print(f"  - Total events extracted: {result['total_events']}")
        print(f"  - Total concepts extracted: {result['total_concepts']}")
        print(f"  - Total relationships: {result['total_relationships']}")

        # Export EEC JSON snapshot
        if result['eec_documents']:
            output_path = os.path.join(builder.output_dir, "e80_eec_knowledge_graph.json")
            builder.export_eec_json(result['eec_documents'], output_path)
            print(f"📄 EEC graph exported to: {output_path}")

        # Optional temporal/schema prints
        if result.get('temporal_patterns') is not None:
            tp = result['temporal_patterns']
            print(f"\n🔄 Temporal Patterns:")
            print(f"  - Diagnostic sequences: {len(tp['diagnostic_sequences'])}")
            print(f"  - Causal chains: {len(tp['causal_chains'])}")
            print(f"  - Prerequisite graphs: {len(tp['prerequisite_graphs'])}")
            print(f"  - Conditional logic: {len(tp['conditional_logic'])}")

        if result.get('schemas') is not None:
            schemas = result['schemas']
            print(f"\n🏗️ Schemas:")
            print(f"  - Entity hierarchies: {len(schemas['entity_hierarchies'])}")
            print(f"  - Event patterns: {len(schemas['event_patterns'])}")
            print(f"  - Concept networks: {len(schemas['concept_networks'])}")
            print(f"  - Domain schemas: {len(schemas['domain_schemas'])}")

    except Exception as e:
        print(f"❌ Error during ingestion: {e}")
        print("Verify .env configuration and dependencies (pip install -r requirements.txt)")


if __name__ == "__main__":
    main()
