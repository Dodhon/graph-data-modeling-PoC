#!/usr/bin/env python3
"""
Combine EEC JSON exports into Neo4j-ready node/relationship files.

Default behavior:
  - Reads data/output/*eec_knowledge_graph*.json (excluding *_stats.json)
  - Writes data/neo4j_nodes.json and data/neo4j_relationships.json

Usage:
  PYTHONPATH=. python3 scripts/combine_eec_json_for_neo4j.py
  PYTHONPATH=. python3 scripts/combine_eec_json_for_neo4j.py --input-dir data/output --output-dir data
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _is_empty(value: Any) -> bool:
    return value is None or value == {} or value == []


def _clean_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if not _is_empty(v)}


def _merge_properties(base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    for key, value in incoming.items():
        if key not in base or _is_empty(base[key]):
            base[key] = value


def _add_node(
    nodes: Dict[str, Dict[str, Any]],
    node_id: str,
    labels: Iterable[str],
    properties: Dict[str, Any],
) -> None:
    if not node_id:
        return
    label_list = sorted({label for label in labels if label})
    if node_id not in nodes:
        nodes[node_id] = {
            "id": node_id,
            "labels": label_list,
            "properties": properties,
        }
        return
    existing = nodes[node_id]
    existing["labels"] = sorted(set(existing["labels"]).union(label_list))
    _merge_properties(existing["properties"], properties)


def _add_relationship(
    relationships: Dict[Tuple[str, str, str], Dict[str, Any]],
    source: str,
    target: str,
    rel_type: str,
    properties: Dict[str, Any],
    temporal_info: Dict[str, Any],
) -> None:
    if not source or not target or not rel_type:
        return
    key = (source, rel_type, target)
    if key not in relationships:
        relationships[key] = {
            "source": source,
            "target": target,
            "type": rel_type,
            "properties": properties,
            "temporal_info": temporal_info,
        }
        return
    existing = relationships[key]
    _merge_properties(existing["properties"], properties)
    if temporal_info:
        if existing["temporal_info"]:
            _merge_properties(existing["temporal_info"], temporal_info)
        else:
            existing["temporal_info"] = temporal_info


def _find_eec_files(input_dir: Path) -> List[Path]:
    candidates = sorted(input_dir.glob("*eec_knowledge_graph*.json"))
    return [path for path in candidates if not path.name.endswith("_stats.json")]


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _combine_eec_files(paths: List[Path]) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    relationships: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    combined_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for path in paths:
        data = _load_json(path)

        for entity in data.get("entities", []):
            properties = _clean_dict(dict(entity.get("properties") or {}))
            extras = _clean_dict({
                "concepts": entity.get("concepts"),
                "source_chunk": entity.get("source_chunk"),
            })
            _merge_properties(properties, extras)
            _merge_properties(properties, {"combined_at": combined_at})
            _add_node(
                nodes,
                entity.get("id"),
                ["Entity", entity.get("type")],
                properties,
            )

        for event in data.get("events", []):
            properties = _clean_dict(dict(event.get("properties") or {}))
            extras = _clean_dict({
                "actor": event.get("actor"),
                "target": event.get("target"),
                "temporal_order": event.get("temporal_order"),
                "prerequisites": event.get("prerequisites"),
                "concepts": event.get("concepts"),
                "source_chunk": event.get("source_chunk"),
            })
            _merge_properties(properties, extras)
            _merge_properties(properties, {"combined_at": combined_at})
            _add_node(
                nodes,
                event.get("id"),
                ["Event", event.get("type")],
                properties,
            )

        for concept in data.get("concepts", []):
            properties = _clean_dict(dict(concept.get("properties") or {}))
            extras = _clean_dict({
                "applies_to": concept.get("applies_to"),
                "domain": concept.get("domain"),
                "source_chunk": concept.get("source_chunk"),
            })
            _merge_properties(properties, extras)
            _merge_properties(properties, {"combined_at": combined_at})
            _add_node(
                nodes,
                concept.get("id"),
                ["Concept", concept.get("type")],
                properties,
            )

        for rel in data.get("relationships", []):
            properties = _clean_dict(dict(rel.get("properties") or {}))
            temporal_info = _clean_dict(dict(rel.get("temporal_info") or {}))
            _merge_properties(properties, {"combined_at": combined_at})
            _add_relationship(
                relationships,
                rel.get("source"),
                rel.get("target"),
                rel.get("type"),
                properties,
                temporal_info,
            )

    for rel in relationships.values():
        source_node = nodes.get(rel["source"])
        if source_node:
            rel["source_labels"] = source_node["labels"]
        target_node = nodes.get(rel["target"])
        if target_node:
            rel["target_labels"] = target_node["labels"]

    node_list = sorted(nodes.values(), key=lambda item: item["id"])
    rel_list = sorted(relationships.values(), key=lambda item: (item["source"], item["type"], item["target"]))

    return {
        "nodes": node_list,
        "relationships": rel_list,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Combine EEC JSON exports into Neo4j-ready nodes/relationships JSON files."
    )
    parser.add_argument("--input-dir", default=str(repo_root / "data" / "output"))
    parser.add_argument("--output-dir", default=str(repo_root / "data"))
    parser.add_argument("--nodes-file", default="neo4j_nodes.json")
    parser.add_argument("--relationships-file", default="neo4j_relationships.json")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    eec_files = _find_eec_files(input_dir)
    if not eec_files:
        raise SystemExit(f"No EEC JSON files found in {input_dir}")

    combined = _combine_eec_files(eec_files)

    nodes_path = Path(args.nodes_file)
    if not nodes_path.is_absolute():
        nodes_path = output_dir / nodes_path
    rels_path = Path(args.relationships_file)
    if not rels_path.is_absolute():
        rels_path = output_dir / rels_path

    with nodes_path.open("w", encoding="utf-8") as file:
        json.dump(combined["nodes"], file, indent=2, ensure_ascii=False)
    with rels_path.open("w", encoding="utf-8") as file:
        json.dump(combined["relationships"], file, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {len(combined['nodes'])} nodes to {nodes_path}")
    print(f"✅ Wrote {len(combined['relationships'])} relationships to {rels_path}")
    print(f"📦 Combined {len(eec_files)} EEC file(s)")


if __name__ == "__main__":
    main()
