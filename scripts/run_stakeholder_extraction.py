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
from pathlib import Path
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


def gather_input_files(input_dir: str) -> list[str]:
    """Gather files while avoiding duplicate ticket ingestion.

    Preference for ticket CSVs:
    1. stakeholder_tickets_canonical.csv
    2. Ticket Report Day 1 thru 6-25-25 (5).csv
    3. any first CSV fallback
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

    return md_files + selected_csv


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
        print(f"  {os.path.basename(f)}")

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

    all_eec_docs = []

    for filepath in files:
        filename = os.path.basename(filepath)
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
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
                all_eec_docs.extend(eec_docs)
            except Exception as e:
                print(f"    Error: {e}")
                continue

            # Rate-limit courtesy
            if i > 0 and i % 10 == 0:
                time.sleep(2)

    # Export using the transformer's own neo4j format
    neo4j_data = transformer.export_to_neo4j_format(all_eec_docs)

    # Save nodes and relationships as separate files
    nodes_path = os.path.join(output_dir, "stakeholder_nodes.json")
    rels_path = os.path.join(output_dir, "stakeholder_relationships.json")

    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(neo4j_data["nodes"], f, indent=2, ensure_ascii=False)

    with open(rels_path, "w", encoding="utf-8") as f:
        json.dump(neo4j_data["relationships"], f, indent=2, ensure_ascii=False)

    # Summary
    n_entities = sum(len(d.entities) for d in all_eec_docs)
    n_events = sum(len(d.events) for d in all_eec_docs)
    n_concepts = sum(len(d.concepts) for d in all_eec_docs)
    n_rels = sum(len(d.relationships) for d in all_eec_docs)

    print(f"\n{'='*60}")
    print(f"Done. Stakeholder graph extracted:")
    print(f"  Entities:      {n_entities}")
    print(f"  Events:        {n_events}")
    print(f"  Concepts:      {n_concepts}")
    print(f"  Relationships: {n_rels}")
    print(f"  Total nodes:   {len(neo4j_data['nodes'])}")
    print(f"\nOutput:")
    print(f"  {nodes_path}")
    print(f"  {rels_path}")


if __name__ == "__main__":
    main()
