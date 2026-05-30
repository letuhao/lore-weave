"""Cycle 73c — simulate pass2_writer's relation-cascade-skip on saved filter dumps.

Mirrors `services/knowledge-service/app/extraction/pass2_writer.py:204`:
a relation is skipped when its subject_name OR object_name is NOT
present in the merged entity set. The writer matches on canonical IDs,
but since saved eval dumps only have minimal `{name, kind}` /
`{subject, predicate, object}` fields (no IDs), we use NAME-based
matching here. This over-counts conservatively for cases where the
writer's canonicalization would normalize two surface forms to the
same canonical entity (e.g. 'Holmes' + 'Sherlock Holmes' → both
canonicalize to 'sherlock_holmes'), but it gives a clean upper bound
on cascade impact.

Per cycle 73c CLARIFY: D-PASS2-FILTER-NEO4J-REALIZED-F1 follow-up.

Usage:
    python compute_neo4j_realized_cascade.py <variant-dir> [<variant-label>]

Example:
    python compute_neo4j_realized_cascade.py eval_runs/c72c c72c-drop
    python compute_neo4j_realized_cascade.py eval_runs/c73b-drop c73b-drop

Reports per chapter + aggregate:
    - relations kept by filter
    - relations writer would cascade-skip
    - of cascade-skipped relations, how many were marked SUPPORTED by majority of judges
    - implied F1 impact: lost precision if any "supported" relations cascade
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def _load_chapter_actual(chapter_dir: Path) -> dict:
    return json.loads((chapter_dir / "actual.json").read_text(encoding="utf-8"))


def _cascade_skip_count(actual: dict) -> tuple[int, int, list[dict]]:
    """Return (n_relations_kept, n_cascade_skip, cascade_skipped_rel_indices_with_data).

    A relation is cascade-skipped when its subject or object name is not
    in the entity name set of the same dump. Mirrors pass2_writer.py:204
    on a name-basis (writer uses canonical IDs; this conservatively
    over-counts when surface forms differ but canonicalize to the same
    entity).
    """
    entity_names = {e.get("name", "") for e in actual.get("entities", [])}
    relations = actual.get("relations", [])
    n_kept = len(relations)
    cascade = []
    for idx, r in enumerate(relations):
        subj = r.get("subject", "")
        obj = r.get("object", "")
        if subj not in entity_names or obj not in entity_names:
            cascade.append({
                "idx": idx,
                "subject": subj, "predicate": r.get("predicate", ""),
                "object": obj,
                "missing": [n for n in (subj, obj) if n not in entity_names],
            })
    return n_kept, len(cascade), cascade


def _load_judge_verdicts(variant_dir: Path) -> dict[str, dict]:
    """Load all per-judge verdict files; return {judge_label: data}."""
    judges = {
        "gemma": "judge_verdicts_gemma.json",
        "qwen-30b": "judge_verdicts_qwen-30b.json",
        "claude-4.7-opus": "judge_verdicts_claude-4_7-opus.json",
    }
    out = {}
    for label, fn in judges.items():
        p = variant_dir / fn
        if p.is_file():
            out[label] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _supported_majority_for_relation(
    chapter: str, idx: int, verdicts_by_judge: dict[str, dict],
) -> bool:
    """Was relation `idx` in `chapter` marked 'supported' by ≥2/3 judges?

    Reads each judge's verdict list looking for (chapter, category=relation,
    kind=precision, idx). 'supported' verdict counts; partial/unsupported/
    unjudged do not.
    """
    supported_count = 0
    judged_count = 0
    for label, data in verdicts_by_judge.items():
        for v in data.get("verdicts", []):
            if (v.get("chapter") == chapter
                and v.get("category") == "relation"
                and v.get("kind") == "precision"
                and int(v.get("idx", -1)) == idx):
                judged_count += 1
                if v.get("verdict") == "supported":
                    supported_count += 1
                break  # one verdict per (chapter, cat, kind, idx) per judge
    return judged_count >= 2 and supported_count >= 2


def analyze(variant_dir: Path, variant_label: str) -> dict:
    chapter_dirs = sorted(
        p for p in variant_dir.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )
    verdicts_by_judge = _load_judge_verdicts(variant_dir)

    print(f"\n## Cascade analysis — {variant_label}\n")
    print(f"Source: `{variant_dir.relative_to(variant_dir.parents[3]) if len(variant_dir.parents) > 3 else variant_dir}`")
    print(f"Judges loaded: {sorted(verdicts_by_judge.keys()) if verdicts_by_judge else '(none — cannot compute supported-cascade)'}")
    print()
    print("| Chapter | Rel kept | Cascade skip | % skip | Supported cascade | Missing names sample |")
    print("|---|---:|---:|---:|---:|---|")

    agg_kept = 0
    agg_cascade = 0
    agg_supported_cascade = 0
    for cd in chapter_dirs:
        chapter = cd.name
        actual = _load_chapter_actual(cd)
        n_kept, n_cascade, cascade_data = _cascade_skip_count(actual)
        agg_kept += n_kept
        agg_cascade += n_cascade
        sup_count = 0
        for r in cascade_data:
            if verdicts_by_judge and _supported_majority_for_relation(
                chapter, r["idx"], verdicts_by_judge,
            ):
                sup_count += 1
        agg_supported_cascade += sup_count
        sample = ", ".join(
            sorted({m for r in cascade_data for m in r["missing"]})[:3]
        )
        pct_skip = (n_cascade / n_kept * 100) if n_kept else 0
        print(
            f"| {chapter} | {n_kept} | {n_cascade} | {pct_skip:.1f}% | "
            f"{sup_count} | {sample or '—'} |"
        )

    pct_total = (agg_cascade / agg_kept * 100) if agg_kept else 0
    pct_supported = (agg_supported_cascade / agg_kept * 100) if agg_kept else 0
    print()
    print(f"**Aggregate**: {agg_cascade}/{agg_kept} relations cascade-skip "
          f"({pct_total:.1f}%); of those, **{agg_supported_cascade} were judged 'supported' "
          f"by ≥2/3 judges** ({pct_supported:.1f}% of kept relations).")
    print()
    if pct_supported < 5.0:
        verdict = "**NEGLIGIBLE** — filter-output F1 stands; realized F1 within noise."
    elif pct_supported < 10.0:
        verdict = "**MEDIUM** — re-judge cycle recommended to confirm realized F1."
    else:
        verdict = "**LARGE** — re-judge cycle REQUIRED; filter-output F1 over-states realized F1."
    print(f"Cascade impact verdict: {verdict}")
    print()

    return {
        "variant": variant_label,
        "agg_relations_kept": agg_kept,
        "agg_cascade_skip": agg_cascade,
        "agg_cascade_skip_pct": pct_total,
        "agg_supported_cascade": agg_supported_cascade,
        "agg_supported_cascade_pct": pct_supported,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    variant_dir = Path(sys.argv[1])
    variant_label = sys.argv[2] if len(sys.argv) >= 3 else variant_dir.name
    analyze(variant_dir, variant_label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
