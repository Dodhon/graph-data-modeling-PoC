#!/usr/bin/env python3
"""
Move JSON files from repo root into data/output.

Usage:
  PYTHONPATH=. python3 scripts/move_root_jsons_to_output.py
"""

from pathlib import Path
import shutil


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    skipped = 0
    for src in repo_root.glob("*.json"):
        dest = output_dir / src.name
        if dest.exists():
            skipped += 1
            print(f"⚠️  Skipping {src.name} (already in data/output)")
            continue
        shutil.move(str(src), str(dest))
        moved += 1

    print(f"✅ Moved {moved} JSON file(s) to {output_dir}")
    if skipped:
        print(f"ℹ️  Skipped {skipped} existing file(s)")


if __name__ == "__main__":
    main()
