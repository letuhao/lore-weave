"""Cycle 73c — simulate pass2_writer cascade on a variant's filter dump
and emit a 'realized' actual.json that the ensemble can re-judge.

Mirrors the writer cascade rule from
`services/knowledge-service/app/extraction/pass2_writer.py:204`:
relations whose subject or object NAME isn't in the entity name set
get skipped at write time. Per cycle 73c c73c_cascade_analysis.md:
this is a name-based UPPER BOUND on cascade (writer uses canonical
IDs and may merge surface forms the simulator treats as distinct).

For events: cycle 73c finds that participants are free-text strings
(no FK), so events do NOT cascade. Events pass through unchanged.

For facts: not filtered in cycle 72/73b; pass through unchanged.

Usage:
    python simulate_realized_dump.py <source-variant-dir> <out-variant-dir>

Example:
    python simulate_realized_dump.py \\
        eval_runs/c72c eval_runs/c72c-realized
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def realize_actual(actual: dict) -> tuple[dict, int]:
    """Apply writer cascade to actual.json. Returns (realized_actual, n_cascade_dropped)."""
    entity_names = {e.get("name", "") for e in actual.get("entities", [])}
    realized_relations = []
    cascade_dropped = 0
    for r in actual.get("relations", []):
        if r.get("subject", "") in entity_names and r.get("object", "") in entity_names:
            realized_relations.append(r)
        else:
            cascade_dropped += 1
    return (
        {
            "entities": actual.get("entities", []),
            "relations": realized_relations,
            "events": actual.get("events", []),
            "facts": actual.get("facts", []),
        },
        cascade_dropped,
    )


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    chapter_dirs = sorted(
        p for p in src.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )
    if not chapter_dirs:
        print(f"ERROR: no chapter dumps under {src}", file=sys.stderr)
        return 1

    total_orig = 0
    total_realized = 0
    total_dropped = 0
    per_chapter = []
    for cd in chapter_dirs:
        actual = json.loads((cd / "actual.json").read_text(encoding="utf-8"))
        realized, dropped = realize_actual(actual)
        out_cd = out / cd.name
        out_cd.mkdir(parents=True, exist_ok=True)
        (out_cd / "actual.json").write_text(
            json.dumps(realized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        for sidecar in ("expected.json", "attribution.json"):
            sp = cd / sidecar
            if sp.is_file():
                shutil.copyfile(sp, out_cd / sidecar)
        n_orig = len(actual.get("relations", []))
        n_realized = len(realized["relations"])
        total_orig += n_orig
        total_realized += n_realized
        total_dropped += dropped
        per_chapter.append((cd.name, n_orig, n_realized, dropped))
        print(f"{cd.name}: relations {n_orig} → {n_realized} ({dropped} cascade-dropped)")

    print()
    print(f"TOTAL: relations {total_orig} → {total_realized} ({total_dropped} dropped, "
          f"{total_dropped/total_orig*100:.1f}%)")
    print(f"Output: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
