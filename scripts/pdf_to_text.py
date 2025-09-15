#!/usr/bin/env python3
"""
Minimal PDF to text extractor (pdfminer.six).
Usage:
  PYTHONPATH=. python3 scripts/pdf_to_text.py --pdf "/Users/thuptenwangpo/Documents/GitHub/graph-data-modeling-PoC/E80 Software (SMILE80) Manual - Full (1).pdf" \
    --out /Users/thuptenwangpo/Documents/GitHub/graph-data-modeling-PoC/data/input/smile80.txt

Extracts raw text only. Inserts a form-feed (\f) between pages when provided by the engine.
"""

import argparse
from pathlib import Path
import sys

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    print("❌ Missing dependency 'pdfminer.six'. Please add it to requirements.txt and install.")
    sys.exit(1)


def extract_text(pdf_path: Path) -> str:
    # pdfminer.six tends to be more robust for complex PDFs
    text = pdfminer_extract_text(str(pdf_path))
    return text or ""


def main():
    parser = argparse.ArgumentParser(description="Extract plain text from a PDF (pdfminer.six)")
    parser.add_argument("--pdf", required=True, help="Absolute path to PDF file")
    parser.add_argument("--out", required=True, help="Output .txt path under data/input/")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"📖 Reading: {pdf_path}")
    text = extract_text(pdf_path)

    print(f"💾 Writing: {out_path}")
    out_path.write_text(text, encoding="utf-8")
    print("✅ Done")


if __name__ == "__main__":
    main()
