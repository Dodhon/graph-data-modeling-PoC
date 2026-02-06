#!/usr/bin/env python3
"""
Clean stakeholder source data into a model-friendly canonical layer.

Input:
  data/stakeholder/processed/

Output:
  data/stakeholder/cleaned/
    - cleaned markdown files (base64/image noise removed)
    - cleaned CSV files (orphan rows removed, whitespace normalized)
    - stakeholder_tickets_canonical.csv (preferred richer ticket export)
    - clean_report.json (summary metrics)
"""

import argparse
import csv
import glob
import json
import os
import re
from dataclasses import dataclass, asdict


DEFAULT_INPUT_DIR = "data/stakeholder/processed"
DEFAULT_OUTPUT_DIR = "data/stakeholder/cleaned"
PREFERRED_TICKET_FILE = "Ticket Report Day 1 thru 6-25-25 (5).csv"


@dataclass
class MarkdownReport:
    file: str
    bytes_before: int
    bytes_after: int
    images_removed: int
    ai_warning_lines_removed: int
    base64_tokens_removed: int


@dataclass
class CsvReport:
    file: str
    rows_before: int
    rows_after: int
    dropped_empty_ticket_rows: int
    normalized_empty_issue_type: int


def clean_markdown(text: str) -> tuple[str, int, int, int]:
    # Remove markdown image links that embed data URI blobs.
    data_image_pattern = re.compile(r"!\[[^\]]*]\(data:image/[^)]*\)")
    text, images_removed = data_image_pattern.subn("[IMAGE_REMOVED]", text)

    # Remove residual raw base64 URI segments if any remain.
    raw_base64_pattern = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")
    text, base64_tokens_removed = raw_base64_pattern.subn("", text)

    # Drop OCR/editor noise lines.
    ai_warning_lines_removed = 0
    cleaned_lines = []
    for line in text.splitlines():
        if "AI-generated content may be incorrect." in line:
            ai_warning_lines_removed += 1
            continue
        cleaned_lines.append(line.rstrip())

    # Collapse repeated blank lines.
    collapsed = []
    prev_blank = False
    for line in cleaned_lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    output = "\n".join(collapsed).strip() + "\n"
    return output, images_removed, ai_warning_lines_removed, base64_tokens_removed


def clean_csv(path: str) -> tuple[list[dict[str, str]], list[str], int, int]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    cleaned_rows: list[dict[str, str]] = []
    dropped_empty_ticket_rows = 0
    normalized_empty_issue_type = 0

    for row in rows:
        row_norm = {k: (v or "").strip() for k, v in row.items()}
        ticket_number = row_norm.get("Ticket Number", "")
        if ticket_number == "":
            dropped_empty_ticket_rows += 1
            continue

        if "Issue Type" in row_norm and row_norm["Issue Type"] == "":
            row_norm["Issue Type"] = "Unknown"
            normalized_empty_issue_type += 1

        cleaned_rows.append(row_norm)

    return cleaned_rows, fieldnames, dropped_empty_ticket_rows, normalized_empty_issue_type


def write_csv(path: str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean stakeholder data into data/stakeholder/cleaned")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help=f"Input directory (default: {DEFAULT_INPUT_DIR})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    md_reports: list[MarkdownReport] = []
    csv_reports: list[CsvReport] = []
    canonical_rows: list[dict[str, str]] = []
    canonical_fieldnames: list[str] = []

    md_files = sorted(glob.glob(os.path.join(input_dir, "*.md")))
    csv_files = sorted(glob.glob(os.path.join(input_dir, "*.csv")))

    for path in md_files:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
        cleaned, images_removed, ai_removed, base64_removed = clean_markdown(original)
        out_path = os.path.join(output_dir, os.path.basename(path))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        md_reports.append(
            MarkdownReport(
                file=os.path.basename(path),
                bytes_before=len(original.encode("utf-8")),
                bytes_after=len(cleaned.encode("utf-8")),
                images_removed=images_removed,
                ai_warning_lines_removed=ai_removed,
                base64_tokens_removed=base64_removed,
            )
        )

    for path in csv_files:
        rows, fieldnames, dropped, normalized = clean_csv(path)
        out_path = os.path.join(output_dir, os.path.basename(path))
        write_csv(out_path, fieldnames, rows)

        csv_reports.append(
            CsvReport(
                file=os.path.basename(path),
                rows_before=(len(rows) + dropped),
                rows_after=len(rows),
                dropped_empty_ticket_rows=dropped,
                normalized_empty_issue_type=normalized,
            )
        )

        if os.path.basename(path) == PREFERRED_TICKET_FILE:
            canonical_rows = rows
            canonical_fieldnames = fieldnames

    # Build canonical ticket file from richer preferred source.
    if canonical_rows and canonical_fieldnames:
        canonical_path = os.path.join(output_dir, "stakeholder_tickets_canonical.csv")
        write_csv(canonical_path, canonical_fieldnames, canonical_rows)

    report_path = os.path.join(output_dir, "clean_report.json")
    report = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "markdown_files": [asdict(x) for x in md_reports],
        "csv_files": [asdict(x) for x in csv_reports],
        "canonical_ticket_file": "stakeholder_tickets_canonical.csv" if canonical_rows else None,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Cleaned markdown files: {len(md_reports)}")
    print(f"Cleaned csv files: {len(csv_reports)}")
    if canonical_rows:
        print(f"Canonical tickets: {len(canonical_rows)} rows")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
