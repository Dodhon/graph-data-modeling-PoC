#!/usr/bin/env python3
"""
Extract a separate knowledge graph from stakeholder documents (tickets, procedures, templates).
Outputs to data/stakeholder/output/ — independent from the handbook graph.
"""

import os
import glob
import json
import time
import argparse
import sys
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from langchain.schema import Document
from langchain_anthropic import ChatAnthropic


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.eec_graph_transformer import EECGraphTransformer


def read_file(path: str) -> str:
    """Read an input file (markdown or csv) as plain text."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks. Larger chunks than handbook
    since stakeholder docs are shorter and more self-contained."""
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def source_kind(path: str) -> str:
    return "csv" if path.lower().endswith(".csv") else "markdown"


def gather_input_files(input_dir: str) -> list[str]:
    """Gather files while avoiding duplicate ticket ingestion.

    Preference for ticket CSVs:
    1. stakeholder_tickets_canonical.csv
    2. Ticket Report Day 1 thru 6-25-25 (5).csv
    3. any first CSV fallback

    Return CSV-first ordering so structured files seed canonical entities
    before markdown extraction expands context.
    """
    md_files = sorted(glob.glob(os.path.join(input_dir, "*.md")))
    csv_files = sorted(glob.glob(os.path.join(input_dir, "*.csv")))

    selected_csv: list[str] = []
    if csv_files:
        canonical = os.path.join(input_dir, "stakeholder_tickets_canonical.csv")
        preferred = os.path.join(input_dir, "Ticket Report Day 1 thru 6-25-25 (5).csv")
        if canonical in csv_files:
            selected_csv = [canonical]
        elif preferred in csv_files:
            selected_csv = [preferred]
        else:
            selected_csv = [csv_files[0]]

    return selected_csv + md_files


LABEL_ALIASES = {
    "COMPONENTS": "COMPONENT",
    "TOOLS": "TOOL",
    "PEOPLE": "PERSON",
    "LOCATIONS": "LOCATION",
    "SYMPTOMS": "SYMPTOM",
    "MEASUREMENTS": "MEASUREMENT",
}

DOMAIN_ALIASES = {
    "warehouse_management_systems": "warehouse_management_system",
    "warehouse_management_system": "warehouse_management_system",
    "warehouse_management": "warehouse_management_system",
    "system_diagnostics": "system_diagnostics",
    "system_diagnostic": "system_diagnostics",
    "troubleshooting_methodology": "troubleshooting_methodology",
    "incident_management": "incident_management",
    "system_integration": "system_integration",
}

CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def normalize_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", token)


def canonicalize_id(value: str) -> str:
    normalized = normalize_token(value or "")
    return normalized or "unknown"


def normalize_label(label: str) -> str:
    if not label:
        return label
    normalized = normalize_token(label).upper()
    return LABEL_ALIASES.get(normalized, normalized)


def normalize_domain(domain: Any) -> Any:
    if not isinstance(domain, str):
        return domain
    normalized = normalize_token(domain)
    return DOMAIN_ALIASES.get(normalized, normalized)


def normalize_relationship_type(rel_type: str) -> str:
    return normalize_token(rel_type or "related_to").upper()


def display_name_fingerprint(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        return ""

    acronym_match = re.match(r"^\s*([A-Za-z0-9]{2,10})\s*\(", name)
    if acronym_match:
        acronym = normalize_token(acronym_match.group(1))
        if acronym:
            return acronym

    lowered = name.lower()
    lowered = re.sub(r"\([^)]*\)", " ", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    stopwords = {
        "a",
        "an",
        "the",
        "system",
        "systems",
        "process",
        "procedure",
        "protocol",
        "workflow",
        "module",
        "platform",
    }
    tokens = [t for t in lowered.split() if t and t not in stopwords]
    if not tokens:
        return ""
    return "_".join(tokens[:6])


def merge_lists(left: Any, right: Any) -> list[Any]:
    merged: list[Any] = []
    for value in [left, right]:
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                if item not in merged:
                    merged.append(item)
        else:
            if value not in merged:
                merged.append(value)
    return merged


class CanonicalGraphBuilder:
    """Canonical graph accumulator with incremental upserts + final reconcile."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.aliases: dict[str, str] = {}
        self.stats = {
            "raw_node_records": 0,
            "raw_relationship_records": 0,
            "node_upserts": 0,
            "node_merges": 0,
            "relationship_upserts": 0,
            "relationship_deduped": 0,
            "final_name_merges": 0,
            "final_relationship_deduped": 0,
            "dropped_relationships_missing_endpoints": 0,
        }

    def _source_priority(self, kind: str) -> int:
        return 2 if kind == "csv" else 1

    def _coarse_domain(self, node: dict[str, Any]) -> str:
        domain = node["properties"].get("domain")
        if domain in {"hardware", "software", "environmental", "human"}:
            return domain
        return ""

    def _canonical_node_id(self, node: dict[str, Any], source_kind_value: str) -> str:
        raw_id = canonicalize_id(str(node.get("id", "")))
        properties = node.get("properties") or {}
        name = properties.get("name", "")
        name_id = canonicalize_id(str(name)) if name else ""
        node_type = properties.get("node_type", "").lower()

        for candidate in [raw_id, name_id]:
            if candidate and candidate in self.aliases:
                return self.aliases[candidate]

        if node_type == "entity" and name_id:
            if raw_id.endswith("_system") or raw_id.endswith("_module"):
                return name_id
            if len(name_id) <= len(raw_id):
                return name_id

        if source_kind_value == "csv" and name_id:
            return name_id

        if raw_id:
            return raw_id
        if name_id:
            return name_id
        return "unknown_node"

    def _choose_property_value(
        self,
        key: str,
        existing_value: Any,
        incoming_value: Any,
        existing_priority: int,
        incoming_priority: int,
    ) -> Any:
        if incoming_value in (None, "", [], {}):
            return existing_value
        if existing_value in (None, "", [], {}):
            return incoming_value

        if isinstance(existing_value, list) or isinstance(incoming_value, list):
            return merge_lists(existing_value, incoming_value)

        if key == "description" and isinstance(existing_value, str) and isinstance(incoming_value, str):
            return incoming_value if len(incoming_value) > len(existing_value) else existing_value

        if key == "domain":
            existing_domain = normalize_domain(existing_value)
            incoming_domain = normalize_domain(incoming_value)
            if incoming_priority > existing_priority:
                return incoming_domain
            return existing_domain

        if isinstance(existing_value, str) and isinstance(incoming_value, str):
            if incoming_priority > existing_priority:
                return incoming_value
            return existing_value if len(existing_value) >= len(incoming_value) else incoming_value

        return incoming_value if incoming_priority >= existing_priority else existing_value

    def _normalize_node(self, node: dict[str, Any], source_file: str, source_kind_value: str) -> dict[str, Any]:
        labels = node.get("labels", [])
        if not isinstance(labels, list):
            labels = [labels] if labels else []
        normalized_labels = [normalize_label(str(label)) for label in labels if label]
        if not normalized_labels:
            normalized_labels = ["ENTITY"]

        properties = dict(node.get("properties", {}) or {})
        properties["domain"] = normalize_domain(properties.get("domain"))
        if "node_type" in properties and isinstance(properties["node_type"], str):
            properties["node_type"] = normalize_token(properties["node_type"])
        else:
            properties["node_type"] = normalized_labels[0].lower()

        return {
            "id": self._canonical_node_id(node, source_kind_value),
            "labels": normalized_labels,
            "properties": properties,
            "_source_priority": self._source_priority(source_kind_value),
            "_source_files": [source_file],
            "_aliases": [canonicalize_id(str(node.get("id", "")))],
        }

    def _merge_node_records(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "id": existing["id"],
            "labels": merge_lists(existing.get("labels"), incoming.get("labels")),
            "properties": dict(existing.get("properties", {})),
            "_source_priority": max(existing.get("_source_priority", 0), incoming.get("_source_priority", 0)),
            "_source_files": merge_lists(existing.get("_source_files"), incoming.get("_source_files")),
            "_aliases": merge_lists(existing.get("_aliases"), incoming.get("_aliases")),
        }

        existing_priority = existing.get("_source_priority", 0)
        incoming_priority = incoming.get("_source_priority", 0)
        all_keys = set(existing.get("properties", {}).keys()) | set(incoming.get("properties", {}).keys())
        for key in all_keys:
            merged["properties"][key] = self._choose_property_value(
                key,
                existing.get("properties", {}).get(key),
                incoming.get("properties", {}).get(key),
                existing_priority,
                incoming_priority,
            )

        merged["properties"]["source_files"] = merged["_source_files"]
        merged["properties"]["alias_ids"] = merged["_aliases"]
        return merged

    def ingest_batch(
        self,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        source_file: str,
        source_kind_value: str,
    ) -> None:
        self.stats["raw_node_records"] += len(nodes)
        self.stats["raw_relationship_records"] += len(relationships)

        for node in nodes:
            normalized_node = self._normalize_node(node, source_file, source_kind_value)
            canonical_id = normalized_node["id"]
            original_id = canonicalize_id(str(node.get("id", "")))

            if canonical_id in self.nodes:
                self.nodes[canonical_id] = self._merge_node_records(self.nodes[canonical_id], normalized_node)
                self.stats["node_merges"] += 1
            else:
                normalized_node["properties"]["source_files"] = normalized_node["_source_files"]
                normalized_node["properties"]["alias_ids"] = normalized_node["_aliases"]
                self.nodes[canonical_id] = normalized_node

            self.aliases[canonical_id] = canonical_id
            if original_id:
                self.aliases[original_id] = canonical_id
            for alias in self.nodes[canonical_id].get("_aliases", []):
                self.aliases[alias] = canonical_id
            self.stats["node_upserts"] += 1

        for relationship in relationships:
            source_id = canonicalize_id(str(relationship.get("source", "")))
            target_id = canonicalize_id(str(relationship.get("target", "")))
            source_id = self.aliases.get(source_id, source_id)
            target_id = self.aliases.get(target_id, target_id)
            rel_type = normalize_relationship_type(str(relationship.get("type", "")))
            key = (source_id, target_id, rel_type)

            rel_properties = dict(relationship.get("properties", {}) or {})
            rel_properties["domain"] = normalize_domain(rel_properties.get("domain"))
            rel_properties["source_files"] = merge_lists(rel_properties.get("source_files"), [source_file])
            rel_properties["occurrences"] = 1

            if key in self.relationships:
                existing_rel = self.relationships[key]
                existing_props = existing_rel["properties"]
                self.stats["relationship_deduped"] += 1
                existing_props["source_files"] = merge_lists(existing_props.get("source_files"), rel_properties.get("source_files"))
                existing_props["occurrences"] = int(existing_props.get("occurrences", 1)) + 1

                existing_conf = str(existing_props.get("confidence", "low")).lower()
                incoming_conf = str(rel_properties.get("confidence", "low")).lower()
                if CONFIDENCE_RANK.get(incoming_conf, 0) > CONFIDENCE_RANK.get(existing_conf, 0):
                    existing_props["confidence"] = incoming_conf

                existing_context = str(existing_props.get("context", ""))
                incoming_context = str(rel_properties.get("context", ""))
                if len(incoming_context) > len(existing_context):
                    existing_props["context"] = incoming_context

                if rel_properties.get("domain") and not existing_props.get("domain"):
                    existing_props["domain"] = rel_properties["domain"]
            else:
                self.relationships[key] = {
                    "source": source_id,
                    "target": target_id,
                    "type": rel_type,
                    "properties": rel_properties,
                }
            self.stats["relationship_upserts"] += 1

    def _choose_primary_id(self, node_ids: list[str], fingerprint: str) -> str:
        if fingerprint in node_ids:
            return fingerprint
        sorted_ids = sorted(
            node_ids,
            key=lambda node_id: (
                len(node_id),
                -len(self.nodes[node_id].get("properties", {}).get("source_files", [])),
                node_id,
            ),
        )
        return sorted_ids[0]

    def _can_merge_nodes(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_domain = self._coarse_domain(left)
        right_domain = self._coarse_domain(right)
        if left_domain and right_domain and left_domain != right_domain:
            return False
        return True

    def _final_name_based_reconcile(self) -> dict[str, str]:
        groups: dict[tuple[str, str], list[str]] = defaultdict(list)
        for node_id, node in self.nodes.items():
            node_type = str(node.get("properties", {}).get("node_type", ""))
            name = str(node.get("properties", {}).get("name", ""))
            fingerprint = display_name_fingerprint(name) or display_name_fingerprint(node_id)
            if not fingerprint:
                continue
            groups[(node_type, fingerprint)].append(node_id)

        remap: dict[str, str] = {}
        for (node_type, fingerprint), group in groups.items():
            if len(group) < 2:
                continue
            primary = self._choose_primary_id(group, fingerprint)
            for candidate in group:
                if candidate == primary:
                    continue
                if candidate not in self.nodes or primary not in self.nodes:
                    continue
                if not self._can_merge_nodes(self.nodes[primary], self.nodes[candidate]):
                    continue
                merged = self._merge_node_records(self.nodes[primary], self.nodes[candidate])
                merged["id"] = primary
                self.nodes[primary] = merged
                del self.nodes[candidate]
                remap[candidate] = primary
                self.aliases[candidate] = primary
                self.stats["final_name_merges"] += 1
        return remap

    def _remap_relationships(self, remap: dict[str, str]) -> None:
        if not remap:
            remap = {}

        new_relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
        for relationship in self.relationships.values():
            source_id = remap.get(relationship["source"], relationship["source"])
            target_id = remap.get(relationship["target"], relationship["target"])
            rel_type = relationship["type"]

            if source_id not in self.nodes or target_id not in self.nodes:
                self.stats["dropped_relationships_missing_endpoints"] += 1
                continue

            key = (source_id, target_id, rel_type)
            rel_props = dict(relationship.get("properties", {}) or {})

            if key in new_relationships:
                existing = new_relationships[key]["properties"]
                self.stats["final_relationship_deduped"] += 1
                existing["source_files"] = merge_lists(existing.get("source_files"), rel_props.get("source_files"))
                existing["occurrences"] = int(existing.get("occurrences", 1)) + int(rel_props.get("occurrences", 1))
                existing_context = str(existing.get("context", ""))
                incoming_context = str(rel_props.get("context", ""))
                if len(incoming_context) > len(existing_context):
                    existing["context"] = incoming_context
            else:
                new_relationships[key] = {
                    "source": source_id,
                    "target": target_id,
                    "type": rel_type,
                    "properties": rel_props,
                }

        self.relationships = new_relationships

    def finalize(self) -> dict[str, Any]:
        remap = self._final_name_based_reconcile()
        self._remap_relationships(remap)

        duplicate_aliases = {alias: canonical for alias, canonical in self.aliases.items() if alias != canonical}
        return {
            "raw_counts": {
                "nodes": self.stats["raw_node_records"],
                "relationships": self.stats["raw_relationship_records"],
            },
            "final_counts": {
                "nodes": len(self.nodes),
                "relationships": len(self.relationships),
            },
            "stats": self.stats,
            "alias_count": len(duplicate_aliases),
            "alias_sample": dict(list(sorted(duplicate_aliases.items()))[:30]),
        }

    def export(self) -> dict[str, list[dict[str, Any]]]:
        final_nodes = []
        for node_id, node in sorted(self.nodes.items()):
            final_nodes.append(
                {
                    "id": node_id,
                    "labels": sorted(node.get("labels", [])),
                    "properties": node.get("properties", {}),
                }
            )

        final_relationships = []
        for key in sorted(self.relationships.keys()):
            rel = self.relationships[key]
            final_relationships.append(
                {
                    "source": rel["source"],
                    "target": rel["target"],
                    "type": rel["type"],
                    "properties": rel.get("properties", {}),
                }
            )
        return {"nodes": final_nodes, "relationships": final_relationships}


def main():
    parser = argparse.ArgumentParser(description="Extract KG from stakeholder docs")
    parser.add_argument("--dry-run", action="store_true", help="List files without calling LLM")
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Anthropic model to use (default: claude-haiku-4-5-20251001).",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Optional input directory override. Defaults to cleaned data if present, else processed.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/stakeholder/output",
        help="Output directory for graph JSON files.",
    )
    parser.add_argument(
        "--canonical-report",
        default="canonicalization_report.json",
        help="File name for canonicalization report in output directory.",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY in .env")
        return

    if args.input_dir:
        input_dir = args.input_dir
    elif os.path.isdir("data/stakeholder/cleaned"):
        input_dir = "data/stakeholder/cleaned"
    else:
        input_dir = "data/stakeholder/processed"

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    files = gather_input_files(input_dir)

    if not files:
        print(f"No files found in {input_dir}")
        return

    print(f"Input directory: {input_dir}")
    print(f"Model: {args.model}")
    print(f"Found {len(files)} files:")
    for f in files:
        print(f"  {os.path.basename(f)} ({source_kind(f)})")

    if args.dry_run:
        return

    # Initialize LLM + transformer
    llm = ChatAnthropic(
        api_key=api_key,
        model=args.model,
        temperature=0,
        timeout=90,
        max_retries=3,
        max_tokens=8192,
    )
    transformer = EECGraphTransformer(llm=llm)
    canonical_graph = CanonicalGraphBuilder()
    n_entities = 0
    n_events = 0
    n_concepts = 0
    n_rels = 0

    for filepath in files:
        filename = os.path.basename(filepath)
        kind = source_kind(filepath)
        print(f"\n{'='*60}")
        print(f"Processing: {filename} [{kind}]")
        print(f"{'='*60}")

        text = read_file(filepath)
        if not text.strip():
            print(f"  Skipping empty file")
            continue

        chunks = chunk_text(text)
        print(f"  {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            print(f"  Chunk {i+1}/{len(chunks)}")
            try:
                doc = Document(
                    page_content=chunk,
                    metadata={"source": filename, "chunk_id": i},
                )
                eec_docs = transformer.convert_to_eec_documents([doc])
                for eec_doc in eec_docs:
                    n_entities += len(eec_doc.entities)
                    n_events += len(eec_doc.events)
                    n_concepts += len(eec_doc.concepts)
                    n_rels += len(eec_doc.relationships)

                neo4j_chunk = transformer.export_to_neo4j_format(eec_docs)
                canonical_graph.ingest_batch(
                    nodes=neo4j_chunk["nodes"],
                    relationships=neo4j_chunk["relationships"],
                    source_file=filename,
                    source_kind_value=kind,
                )
            except Exception as e:
                print(f"    Error: {e}")
                continue

            # Rate-limit courtesy
            if i > 0 and i % 10 == 0:
                time.sleep(2)

    canonical_report = canonical_graph.finalize()
    neo4j_data = canonical_graph.export()

    # Save nodes and relationships as separate files
    nodes_path = os.path.join(output_dir, "stakeholder_nodes.json")
    rels_path = os.path.join(output_dir, "stakeholder_relationships.json")
    report_path = os.path.join(output_dir, args.canonical_report)

    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(neo4j_data["nodes"], f, indent=2, ensure_ascii=False)

    with open(rels_path, "w", encoding="utf-8") as f:
        json.dump(neo4j_data["relationships"], f, indent=2, ensure_ascii=False)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(canonical_report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Done. Stakeholder graph extracted:")
    print(f"  Entities:      {n_entities}")
    print(f"  Events:        {n_events}")
    print(f"  Concepts:      {n_concepts}")
    print(f"  Relationships: {n_rels}")
    print(f"  Total nodes:   {len(neo4j_data['nodes'])}")
    print(f"  Total rels:    {len(neo4j_data['relationships'])}")
    print(f"  Aliases:       {canonical_report['alias_count']}")
    print(f"\nOutput:")
    print(f"  {nodes_path}")
    print(f"  {rels_path}")
    print(f"  {report_path}")


if __name__ == "__main__":
    main()
