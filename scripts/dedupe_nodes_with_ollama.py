#!/usr/bin/env python3
"""
Deduplicate nodes using Ollama Llama 3.1 for semantic matching.

Edit the config section below, then run:
  PYTHONPATH=. python3 scripts/dedupe_nodes_with_ollama.py
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import request, error

# ---- Config (edit as needed) ----
NODES_JSON = "data/neo4j_nodes.json"
RELATIONSHIPS_JSON = "data/neo4j_relationships.json"

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b-instruct-q8_0"
OLLAMA_TIMEOUT_SECONDS = 120

SIMILARITY_THRESHOLD = 0.90
CROSS_TYPE_EXACT_MATCH = True
ALLOW_CROSS_TYPE_MERGE = False
CONFIDENCE_THRESHOLD = 0.85

CHECKPOINT_EVERY = 1
RESUME_FROM = ""  # Path to a checkpoint.json to resume from
PROGRESS_EVERY = 1

PREFIX_LEN = 4
MIN_NAME_LEN = 4
MAX_BUCKET_SIZE = 400
MAX_CANDIDATES_PER_NODE = 25
MAX_TOTAL_CANDIDATES = 8000

DRY_RUN = False
RETRY_COUNT = 1
LOG_EACH_CALL = True
LOG_SAMPLE_EVERY = 1  # keep at 1 for full verbosity
# ---------------------------------

LABEL_GROUPS = {"Entity", "Event", "Concept"}


def _normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _label_group(labels: List[str]) -> str:
    for label in labels:
        if label in LABEL_GROUPS:
            return label
    return "Unknown"


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}, got {type(data).__name__}")
    return data


def _ollama_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as resp:
        return json.load(resp)


def _print_progress(label: str, current: int, total: int, start_time: float) -> None:
    if total <= 0:
        return
    elapsed = max(0.0001, time.perf_counter() - start_time)
    rate = current / elapsed
    remaining = (total - current) / rate if rate > 0 else 0
    percent = (current / total) * 100
    message = (
        f"{label}: {current}/{total} ({percent:5.1f}%) "
        f"| {rate:,.2f}/s | ETA {remaining/60:,.1f}m"
    )
    print(f"\r{message}   ", end="", flush=True)
    if current >= total:
        print()


def _evaluate_with_ollama(node_a: Dict[str, Any], node_b: Dict[str, Any]) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {
            "same": {"type": "boolean"},
            "confidence": {"type": "number"},
            "canonical_name": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["same", "confidence", "canonical_name", "reason"],
    }

    prompt = (
        "Decide if these two nodes represent the same real-world thing.\n"
        "If unsure, answer same=false. Use the names, labels, and descriptions.\n\n"
        f"Node A:\n"
        f"- id: {node_a['id']}\n"
        f"- labels: {node_a['labels']}\n"
        f"- name: {node_a['name']}\n"
        f"- description: {node_a['description']}\n"
        f"- domain: {node_a['domain']}\n\n"
        f"Node B:\n"
        f"- id: {node_b['id']}\n"
        f"- labels: {node_b['labels']}\n"
        f"- name: {node_b['name']}\n"
        f"- description: {node_b['description']}\n"
        f"- domain: {node_b['domain']}\n"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "You are a careful entity resolution assistant."},
            {"role": "user", "content": prompt},
        ],
        "format": schema,
        "options": {"temperature": 0},
    }

    last_error = None
    for _ in range(RETRY_COUNT + 1):
        try:
            response = _ollama_chat(payload)
            content = response.get("message", {}).get("content", "")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("Ollama response is not a JSON object")
            return result
        except (error.URLError, error.HTTPError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Ollama call failed: {last_error}")


def _build_candidates(nodes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    records = []
    record_by_id = {}

    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        labels = node.get("labels") or []
        properties = node.get("properties") or {}
        name = str(properties.get("name") or node_id)
        description = str(properties.get("description") or "")
        domain = str(properties.get("domain") or "")

        record = {
            "id": node_id,
            "labels": labels,
            "group": _label_group(labels),
            "name": name,
            "description": description,
            "domain": domain,
            "name_norm": _normalize_text(name) or _normalize_text(node_id),
            "desc_norm": _normalize_text(description),
        }
        records.append(record)
        record_by_id[node_id] = record

    buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        prefix = record["name_norm"][:PREFIX_LEN]
        key = (record["group"], record["domain"], prefix)
        buckets[key].append(record)

    seen = set()
    candidates = []
    per_node = defaultdict(int)

    for bucket_key in sorted(buckets.keys()):
        bucket = buckets[bucket_key]
        if len(bucket) > MAX_BUCKET_SIZE:
            continue
        bucket.sort(key=lambda item: (item["name_norm"], item["id"]))
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                if len(candidates) >= MAX_TOTAL_CANDIDATES:
                    break
                a = bucket[i]
                b = bucket[j]
                if per_node[a["id"]] >= MAX_CANDIDATES_PER_NODE:
                    continue
                if per_node[b["id"]] >= MAX_CANDIDATES_PER_NODE:
                    continue
                if a["id"] == b["id"]:
                    continue
                key = tuple(sorted((a["id"], b["id"])))
                if key in seen:
                    continue
                name_a = a["name_norm"]
                name_b = b["name_norm"]
                if len(name_a) < MIN_NAME_LEN or len(name_b) < MIN_NAME_LEN:
                    continue
                score = _similarity(name_a, name_b)
                if score < SIMILARITY_THRESHOLD:
                    continue
                candidates.append({
                    "node_a": a["id"],
                    "node_b": b["id"],
                    "reason": "same_group_bucket",
                    "name_similarity": round(score, 4),
                })
                seen.add(key)
                per_node[a["id"]] += 1
                per_node[b["id"]] += 1
            if len(candidates) >= MAX_TOTAL_CANDIDATES:
                break
        if len(candidates) >= MAX_TOTAL_CANDIDATES:
            break

    if CROSS_TYPE_EXACT_MATCH:
        name_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for record in records:
            if record["name_norm"]:
                name_map[record["name_norm"]].append(record)

        for name_norm in sorted(name_map.keys()):
            items = name_map[name_norm]
            groups = {item["group"] for item in items}
            if len(groups) <= 1:
                continue
            items.sort(key=lambda item: (item["group"], item["id"]))
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if len(candidates) >= MAX_TOTAL_CANDIDATES:
                        break
                    a = items[i]
                    b = items[j]
                    key = tuple(sorted((a["id"], b["id"])))
                    if key in seen:
                        continue
                    candidates.append({
                        "node_a": a["id"],
                        "node_b": b["id"],
                        "reason": "cross_type_exact_name",
                        "name_similarity": 1.0,
                    })
                    seen.add(key)
                if len(candidates) >= MAX_TOTAL_CANDIDATES:
                    break
            if len(candidates) >= MAX_TOTAL_CANDIDATES:
                break

    return candidates, record_by_id


def _node_score(record: Dict[str, Any]) -> int:
    return len(record.get("name", "")) + len(record.get("description", "")) + len(record.get("labels", []))


def _union_find(edges: List[Tuple[str, str]]) -> Dict[str, str]:
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    for a, b in edges:
        union(a, b)

    return {node: find(node) for node in parent}


def _merge_nodes(nodes: List[Dict[str, Any]], merge_map: Dict[str, str]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        canonical_id = merge_map.get(node_id, node_id)
        labels = node.get("labels") or []
        properties = node.get("properties") or {}

        if canonical_id not in merged:
            merged[canonical_id] = {
                "id": canonical_id,
                "labels": list(labels),
                "properties": dict(properties),
            }
            continue
        existing = merged[canonical_id]
        existing["labels"] = sorted(set(existing["labels"]).union(labels))
        for key, value in properties.items():
            if key not in existing["properties"] or existing["properties"][key] in (None, "", [], {}):
                existing["properties"][key] = value

    return sorted(merged.values(), key=lambda item: item["id"])


def _merge_relationships(
    relationships: List[Dict[str, Any]],
    merge_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for rel in relationships:
        source = merge_map.get(rel.get("source"), rel.get("source"))
        target = merge_map.get(rel.get("target"), rel.get("target"))
        rel_type = rel.get("type")
        if not source or not target or not rel_type:
            continue

        key = (source, rel_type, target)
        props = rel.get("properties") or {}
        temporal = rel.get("temporal_info") or {}

        if key not in merged:
            merged[key] = {
                "source": source,
                "target": target,
                "type": rel_type,
                "properties": dict(props),
                "temporal_info": dict(temporal) if temporal else {},
            }
            if rel.get("source_labels"):
                merged[key]["source_labels"] = rel.get("source_labels")
            if rel.get("target_labels"):
                merged[key]["target_labels"] = rel.get("target_labels")
            continue

        existing = merged[key]
        for k, v in props.items():
            if k not in existing["properties"] or existing["properties"][k] in (None, "", [], {}):
                existing["properties"][k] = v
        if temporal:
            for k, v in temporal.items():
                if k not in existing["temporal_info"] or existing["temporal_info"][k] in (None, "", [], {}):
                    existing["temporal_info"][k] = v

    return sorted(merged.values(), key=lambda item: (item["source"], item["type"], item["target"]))


def _pair_key(a_id: str, b_id: str) -> Tuple[str, str]:
    return tuple(sorted((a_id, b_id)))


def _load_checkpoint(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_checkpoint(run_dir: Path, state: Dict[str, Any]) -> None:
    checkpoint_path = run_dir / "checkpoint.json"
    with checkpoint_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, ensure_ascii=False)

    review_path = run_dir / "review_pairs.json"
    with review_path.open("w", encoding="utf-8") as file:
        json.dump(state["reviewed"], file, indent=2, ensure_ascii=False)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    nodes_path = repo_root / NODES_JSON
    rels_path = repo_root / RELATIONSHIPS_JSON

    if not nodes_path.exists():
        raise SystemExit(f"Nodes file not found: {nodes_path}")
    if not rels_path.exists():
        raise SystemExit(f"Relationships file not found: {rels_path}")

    nodes = _load_json_list(nodes_path)
    relationships = _load_json_list(rels_path)

    print("🔎 Building candidate pairs...")
    candidates, record_by_id = _build_candidates(nodes)
    print(f"✅ Candidates: {len(candidates)}")

    reviewed: List[Dict[str, Any]] = []
    merge_edges: List[Tuple[str, str]] = []
    cross_type_suggestions = 0
    processed_pairs = set()

    run_dir = None
    prior_evaluated = 0
    if RESUME_FROM:
        checkpoint_path = repo_root / RESUME_FROM
        if not checkpoint_path.exists():
            raise SystemExit(f"Checkpoint not found: {checkpoint_path}")
        checkpoint = _load_checkpoint(checkpoint_path)
        reviewed = checkpoint.get("reviewed", [])
        merge_edges = [tuple(edge) for edge in checkpoint.get("merge_edges", [])]
        cross_type_suggestions = int(checkpoint.get("cross_type_suggestions", 0))
        processed_pairs = {_pair_key(item["node_a"], item["node_b"]) for item in reviewed}
        prior_evaluated = int(checkpoint.get("evaluated", len(processed_pairs)))
        run_dir = checkpoint_path.parent
        print(f"↩️ Resuming from checkpoint: {checkpoint_path}")

    if run_dir is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = repo_root / "data" / "dedupe" / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=False)

    checkpoint_every = max(1, CHECKPOINT_EVERY)
    progress_every = max(1, PROGRESS_EVERY)
    evaluated = 0
    total_remaining = max(0, len(candidates) - len(processed_pairs))
    progress_start = time.perf_counter()

    if total_remaining == 0:
        print("✅ No remaining candidates to evaluate.")
    else:
        print(f"🧠 LLM evaluations remaining: {total_remaining}")

    for idx, candidate in enumerate(candidates, start=1):
        pair = _pair_key(candidate["node_a"], candidate["node_b"])
        if pair in processed_pairs:
            continue
        node_a = record_by_id[candidate["node_a"]]
        node_b = record_by_id[candidate["node_b"]]
        result = None
        error_message = None

        if DRY_RUN:
            result = {"same": False, "confidence": 0, "canonical_name": "", "reason": "dry_run"}
        else:
            if LOG_EACH_CALL and (evaluated % LOG_SAMPLE_EVERY == 0):
                print(
                    f"🧠 [{evaluated + 1}/{total_remaining}] Calling Ollama "
                    f"({node_a['id']} ↔ {node_b['id']})"
                )
            call_start = time.perf_counter()
            try:
                result = _evaluate_with_ollama(node_a, node_b)
            except RuntimeError as exc:
                error_message = str(exc)
            call_elapsed = time.perf_counter() - call_start
            if LOG_EACH_CALL and (evaluated % LOG_SAMPLE_EVERY == 0):
                status = "ok" if error_message is None else "error"
                confidence = None if not result else result.get("confidence")
                print(
                    f"✅ [{evaluated + 1}/{total_remaining}] Ollama {status} "
                    f"in {call_elapsed:.2f}s (conf={confidence})"
                )

        reviewed_item = {
            "node_a": node_a["id"],
            "node_b": node_b["id"],
            "labels_a": node_a["labels"],
            "labels_b": node_b["labels"],
            "name_a": node_a["name"],
            "name_b": node_b["name"],
            "reason": candidate["reason"],
            "name_similarity": candidate["name_similarity"],
            "llm": result,
            "error": error_message,
        }
        reviewed.append(reviewed_item)
        processed_pairs.add(pair)
        evaluated += 1

        if not result or error_message:
            continue

        same = bool(result.get("same"))
        confidence = float(result.get("confidence") or 0)
        if not same or confidence < CONFIDENCE_THRESHOLD:
            continue

        if node_a["group"] != node_b["group"] and not ALLOW_CROSS_TYPE_MERGE:
            cross_type_suggestions += 1
            continue

        merge_edges.append((node_a["id"], node_b["id"]))

        if evaluated % progress_every == 0 or evaluated == total_remaining:
            _print_progress("Progress", evaluated, total_remaining, progress_start)

        if evaluated % checkpoint_every == 0:
            checkpoint_state = {
                "reviewed": reviewed,
                "merge_edges": merge_edges,
                "cross_type_suggestions": cross_type_suggestions,
                "candidates_total": len(candidates),
                "evaluated": prior_evaluated + evaluated,
            }
            _write_checkpoint(run_dir, checkpoint_state)
            print(f"💾 Checkpoint saved ({evaluated} evaluated)")

    if evaluated > 0:
        _print_progress("Progress", evaluated, total_remaining, progress_start)
        checkpoint_state = {
            "reviewed": reviewed,
            "merge_edges": merge_edges,
            "cross_type_suggestions": cross_type_suggestions,
            "candidates_total": len(candidates),
            "evaluated": prior_evaluated + evaluated,
        }
        _write_checkpoint(run_dir, checkpoint_state)

    merge_map_root = _union_find(merge_edges)
    groups: Dict[str, List[str]] = defaultdict(list)
    for node_id, root in merge_map_root.items():
        groups[root].append(node_id)

    merge_map = {}
    for members in groups.values():
        canonical = max(members, key=lambda node_id: _node_score(record_by_id[node_id]))
        for member in members:
            if member != canonical:
                merge_map[member] = canonical

    deduped_nodes = _merge_nodes(nodes, merge_map)
    deduped_relationships = _merge_relationships(relationships, merge_map)

    with (run_dir / "review_pairs.json").open("w", encoding="utf-8") as file:
        json.dump(reviewed, file, indent=2, ensure_ascii=False)
    with (run_dir / "merge_map.json").open("w", encoding="utf-8") as file:
        json.dump(merge_map, file, indent=2, ensure_ascii=False)
    with (run_dir / "neo4j_nodes_deduped.json").open("w", encoding="utf-8") as file:
        json.dump(deduped_nodes, file, indent=2, ensure_ascii=False)
    with (run_dir / "neo4j_relationships_deduped.json").open("w", encoding="utf-8") as file:
        json.dump(deduped_relationships, file, indent=2, ensure_ascii=False)
    with (repo_root / "data" / "dedupe" / "latest.json").open("w", encoding="utf-8") as file:
        json.dump({"run_id": run_dir.name.replace("run_", "")}, file, indent=2)

    print(f"✅ Deduped nodes: {len(deduped_nodes)}")
    print(f"✅ Deduped relationships: {len(deduped_relationships)}")
    print(f"✅ Merge map entries: {len(merge_map)}")
    if cross_type_suggestions:
        print(f"ℹ️ Cross-type merge suggestions skipped: {cross_type_suggestions}")
    print(f"📦 Output: {run_dir}")


if __name__ == "__main__":
    main()
