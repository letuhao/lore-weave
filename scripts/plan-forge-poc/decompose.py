#!/usr/bin/env python3
"""CLI: decompose NovelSystemSpec → plan graph."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.decompose import build_graph


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge decompose")
    p.add_argument("input", type=Path, help="novel_system_spec.json")
    p.add_argument("-o", "--output", type=Path, required=True)
    args = p.parse_args()
    spec = json.loads(args.input.read_text(encoding="utf-8"))
    graph = build_graph(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    stats = graph["stats"]
    print(f"graph: {stats['node_count']} nodes, {stats['edge_count']} edges, link_ratio={stats['planner_notes_linked_ratio']} → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
