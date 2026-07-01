#!/usr/bin/env python3
"""CLI: ingest markdown → PlanDocument."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.ingest import ingest_file


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge ingest")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    args = p.parse_args()
    doc = ingest_file(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ingested {len(doc['sections'])} sections → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
