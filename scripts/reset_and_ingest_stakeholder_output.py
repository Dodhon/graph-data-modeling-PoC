#!/usr/bin/env python3
"""
Reset the active Neo4j database and ingest stakeholder output JSON.

Default input files:
  - data/stakeholder/output/stakeholder_nodes.json
  - data/stakeholder/output/stakeholder_relationships.json

Safety:
  - Requires --confirm-reset to run destructive reset.

Usage:
  PYTHONPATH=. python3 scripts/reset_and_ingest_stakeholder_output.py --confirm-reset
  PYTHONPATH=. python3 scripts/reset_and_ingest_stakeholder_output.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


DEFAULT_NODES_FILE = "data/stakeholder/output/stakeholder_nodes.json"
DEFAULT_RELS_FILE = "data/stakeholder/output/stakeholder_relationships.json"


def sanitize_schema_token(value: str) -> str:
    if not value:
        return ""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value).strip("_")
    if not cleaned:
        return ""
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def load_json_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}, got {type(data).__name__}")
    return data


def print_progress(label: str, current: int, total: int, started: float) -> None:
    if total <= 0:
        return
    elapsed = max(0.0001, time.perf_counter() - started)
    rate = current / elapsed
    eta = (total - current) / rate if rate > 0 else 0
    pct = (current / total) * 100
    print(
        f"\r{label}: {current}/{total} ({pct:5.1f}%) | {rate:,.1f}/s | ETA {eta/60:,.1f}m",
        end="",
        flush=True,
    )
    if current >= total:
        print()


def _is_primitive(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def sanitize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Return Neo4j-safe properties (primitive or arrays of primitive only)."""
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        if _is_primitive(value):
            safe[key] = value
            continue

        if isinstance(value, list):
            if all(_is_primitive(item) for item in value):
                safe[key] = value
            else:
                # Preserve information deterministically for nested structures.
                safe[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            continue

        if isinstance(value, dict):
            if not value:
                # Drop empty maps (common with temporal_info: {}).
                continue
            safe[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            continue

        safe[key] = str(value)
    return safe


def count_graph(session) -> tuple[int, int]:
    nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return nodes, relationships


def reset_graph(session, batch_size: int) -> int:
    total_deleted = 0
    while True:
        deleted = session.run(
            """
            MATCH (n)
            WITH n LIMIT $limit
            DETACH DELETE n
            RETURN count(*) AS deleted
            """,
            {"limit": batch_size},
        ).single()["deleted"]
        total_deleted += int(deleted)
        if deleted == 0:
            break
    return total_deleted


def ingest_nodes(session, nodes: list[dict[str, Any]], progress_every: int) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    started = time.perf_counter()
    for idx, node in enumerate(nodes, start=1):
        node_id = node.get("id")
        if not node_id:
            skipped += 1
            continue

        labels = [sanitize_schema_token(str(label)) for label in (node.get("labels") or [])]
        labels = [label for label in labels if label]
        label_clause = ":" + ":".join(sorted(set(labels))) if labels else ""

        properties = node.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        properties = sanitize_properties(properties)

        query = f"MERGE (n{label_clause} {{id: $id}}) SET n += $properties"
        session.run(query, {"id": node_id, "properties": properties})
        inserted += 1

        if idx % progress_every == 0 or idx == len(nodes):
            print_progress("Nodes", idx, len(nodes), started)

    return inserted, skipped


def ingest_relationships(session, relationships: list[dict[str, Any]], progress_every: int) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    started = time.perf_counter()
    for idx, rel in enumerate(relationships, start=1):
        source = rel.get("source")
        target = rel.get("target")
        rel_type = sanitize_schema_token(str(rel.get("type", "")))
        if not source or not target or not rel_type:
            skipped += 1
            continue

        properties = rel.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        properties = sanitize_properties(properties)

        # Retain optional metadata if present in export format.
        if rel.get("source_labels"):
            properties["source_labels"] = rel.get("source_labels")
        if rel.get("target_labels"):
            properties["target_labels"] = rel.get("target_labels")

        query = f"""
        MATCH (a {{id: $source}})
        MATCH (b {{id: $target}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $properties
        """
        result = session.run(query, {"source": source, "target": target, "properties": properties}).consume()
        if result.counters.relationships_created == 0 and result.counters.properties_set == 0:
            # Most likely missing endpoints; count as skipped for visibility.
            skipped += 1
        else:
            inserted += 1

        if idx % progress_every == 0 or idx == len(relationships):
            print_progress("Relationships", idx, len(relationships), started)

    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset active Neo4j database and ingest stakeholder output JSON")
    parser.add_argument("--nodes-file", default=DEFAULT_NODES_FILE, help=f"Nodes JSON path (default: {DEFAULT_NODES_FILE})")
    parser.add_argument(
        "--relationships-file",
        default=DEFAULT_RELS_FILE,
        help=f"Relationships JSON path (default: {DEFAULT_RELS_FILE})",
    )
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size used when clearing graph (default: 5000)")
    parser.add_argument("--progress-every", type=int, default=200, help="Progress update interval (default: 200)")
    parser.add_argument("--skip-reset", action="store_true", help="Ingest without clearing the database first")
    parser.add_argument("--confirm-reset", action="store_true", help="Required to perform destructive reset")
    parser.add_argument("--dry-run", action="store_true", help="Show plan and file stats only; do not connect/write")
    args = parser.parse_args()

    nodes_path = Path(args.nodes_file)
    rels_path = Path(args.relationships_file)
    if not nodes_path.exists():
        raise SystemExit(f"Nodes file not found: {nodes_path}")
    if not rels_path.exists():
        raise SystemExit(f"Relationships file not found: {rels_path}")

    nodes = load_json_list(nodes_path)
    relationships = load_json_list(rels_path)
    unique_node_ids = {node.get("id") for node in nodes if node.get("id")}
    unique_rel_triples = {
        (rel.get("source"), rel.get("target"), sanitize_schema_token(str(rel.get("type", ""))))
        for rel in relationships
        if rel.get("source") and rel.get("target") and rel.get("type")
    }

    print("Planned ingest")
    print(f"  Nodes file: {nodes_path}")
    print(f"  Relationships file: {rels_path}")
    print(f"  Node records: {len(nodes)} (unique IDs: {len(unique_node_ids)})")
    print(f"  Relationship records: {len(relationships)} (unique triples: {len(unique_rel_triples)})")
    print(f"  Reset database first: {not args.skip_reset}")
    print(f"  Dry run: {args.dry_run}")

    if args.dry_run:
        return

    if not args.skip_reset and not args.confirm_reset:
        raise SystemExit("Refusing to reset database without --confirm-reset")

    load_dotenv()
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")
    if not uri or not username or not password:
        raise SystemExit("Missing Neo4j config. Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")

    driver = GraphDatabase.driver(uri, auth=(username, password))
    progress_every = max(1, int(args.progress_every))
    batch_size = max(100, int(args.batch_size))

    try:
        with driver.session(database=database) as session:
            before_nodes, before_relationships = count_graph(session)
            print("\nCurrent database counts")
            print(f"  Nodes: {before_nodes}")
            print(f"  Relationships: {before_relationships}")

            deleted_nodes = 0
            if not args.skip_reset:
                print("\nResetting database...")
                deleted_nodes = reset_graph(session, batch_size=batch_size)
                after_reset_nodes, after_reset_relationships = count_graph(session)
                print(f"  Deleted node rows: {deleted_nodes}")
                print(f"  After reset - Nodes: {after_reset_nodes}, Relationships: {after_reset_relationships}")

            print("\nIngesting nodes...")
            inserted_nodes, skipped_nodes = ingest_nodes(session, nodes, progress_every=progress_every)
            print("Ingesting relationships...")
            inserted_relationships, skipped_relationships = ingest_relationships(
                session, relationships, progress_every=progress_every
            )

            final_nodes, final_relationships = count_graph(session)
    finally:
        driver.close()

    print("\nDone")
    print(f"  Nodes ingested attempts: {inserted_nodes} (skipped: {skipped_nodes})")
    print(f"  Relationships ingested attempts: {inserted_relationships} (skipped: {skipped_relationships})")
    print(f"  Final database counts - Nodes: {final_nodes}, Relationships: {final_relationships}")


if __name__ == "__main__":
    main()
