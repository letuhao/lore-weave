"""Cycle 73e — simulate pass2_writer cascade WITH Tier A + Tier B autocreate
on a variant filter dump and emit a realized actual.json the ensemble
can re-judge.

Mirrors the writer logic from
``services/knowledge-service/app/extraction/pass2_writer.py`` Step 3
WITHOUT Neo4j writes. For each relation:

  1. **Tier A.1** — chapter-local canonical-name map. If unique
     kind match → repair endpoint, relation kept.
  2. **Tier A.1 ambiguous** — multi-kind match → skip BOTH Tier A.1
     and Tier B (would pollute graph).
  3. **Tier A.2** — anchor pre-check. Not simulated here (anchors
     live in glossary DB, not the dump). Set ``--anchors-json`` to
     pass a list of canonical names if needed.
  4. **Tier B** — env-gated autocreate; mints synthetic entity with
     ``auto_created=true``, ``kind="concept"``,
     ``confidence=min(rel.confidence, 0.3)``. Cap enforced per-chapter.

For events / facts: pass through unchanged (no cascade in writer).

Usage:
    KNOWLEDGE_C73E_VARIANT=c73e-autocreate-off \\
        python -m tests.quality.run_c73e_writer_autocreate \\
        services/knowledge-service/tests/quality/eval_runs/c73b-drop \\
        services/knowledge-service/tests/quality/eval_runs/c73e-autocreate-off

    KNOWLEDGE_C73E_VARIANT=c73e-autocreate-on \\
    KNOWLEDGE_C73E_AUTOCREATE_MAX=20 \\
        python -m tests.quality.run_c73e_writer_autocreate \\
        services/knowledge-service/tests/quality/eval_runs/c73b-drop \\
        services/knowledge-service/tests/quality/eval_runs/c73e-autocreate-on
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# /review-impl r2 M1 fold: import production canonicalize so eval driver
# folds match what pass2_writer Step 2 stores in the chapter map.
# Previously a local NFKC+casefold-only impl missed honorific stripping
# ("Master Phoenix" → "phoenix" in production, "master phoenix" in eval)
# and over-counted cascade drops.
from loreweave_extraction.canonical import canonicalize_entity_name as _real_canonicalize

# Mirror writer's noise heuristic exactly.
_NOISE_CHAR_BUDGET = 60
_NOISE_WORD_BUDGET = 3
_NOISE_STRIP_CHARS = "，。、？！,.?!:;()[]{}\"' \t\n"


def _is_noise_subject(name: str) -> bool:
    stripped = name.strip(_NOISE_STRIP_CHARS)
    if not stripped:
        return True
    if len(stripped) > _NOISE_CHAR_BUDGET:
        return True
    if len(stripped.split()) > _NOISE_WORD_BUDGET:
        return True
    return False


def _fold_name(name: str) -> str:
    """Mirror app.extraction.entity_resolver._fold using the REAL
    production canonicalize (M1 fold). Without this, the eval driver
    would over-count cascades by missing honorific-stripped Tier A.1
    hits (e.g. "Master Phoenix" → "phoenix" in production)."""
    return _real_canonicalize(name).strip().casefold()


def realize_actual_c73e(
    actual: dict,
    *,
    autocreate_enabled: bool,
    autocreate_max: int | None,
) -> tuple[dict, dict]:
    """Apply cycle 73e writer logic to ``actual.json``. Returns
    (realized_actual, stats_dict).

    Stats dict per-chapter:
      ``tier_a_name_repair`` — endpoint resolved via chapter map
      ``kind_ambiguous`` — Tier A skipped, cascade-skipped
      ``tier_b_autocreated`` — endpoint resolved via Tier B autocreate
      ``noise_skipped`` — Tier B skipped due to noise heuristic
      ``cap_exhausted`` — Tier B skipped due to budget exhaustion
      ``cap_exhausted_high_conf`` — subset of cap_exhausted, conf>0.8
      ``invalid_name`` — canonicalize returned empty
      ``cascade_dropped`` — still cascade-skipped (all tiers exhausted)
      ``relations_kept`` — final kept count
    """
    entities = list(actual.get("entities", []))
    relations = list(actual.get("relations", []))

    # Build chapter-local fold-keyed map mirroring writer's
    # `chapter_entity_by_canonical_name` (pass2_writer.py Step 2).
    # Stores (kind, name) since simulation has no real IDs. /review-impl
    # r3 H1 fold: removed the parallel raw-name `entity_names_set`
    # shortcut — it diverged from writer semantics by short-circuiting
    # Tier A.1 on exact-string match without bumping `tier_a_name_repair`.
    # Now the simulation routes every unresolved endpoint through the
    # same fold-lookup the writer does.
    chapter_map: dict[str, list[tuple[str, str]]] = {}
    for e in entities:
        ename = e.get("name", "")
        ekind = e.get("kind", "concept")
        fold = _fold_name(ename)
        if fold:
            chapter_map.setdefault(fold, []).append((ekind, ename))

    stats = {
        "tier_a_name_repair": 0,
        "kind_ambiguous": 0,
        "tier_a_anchor_repair": 0,  # not simulated; always 0 here
        "tier_b_autocreated": 0,
        "noise_skipped": 0,
        "cap_exhausted": 0,
        "cap_exhausted_high_conf": 0,
        "invalid_name": 0,
        "error": 0,  # not simulated; always 0
        "cascade_dropped": 0,
        "relations_kept": 0,
    }
    realized_relations: list[dict] = []
    autocreated_entities: list[dict] = []
    budget = autocreate_max  # None = unlimited (when enabled)

    for rel in relations:
        rel_kept = True
        for endpoint_key in ("subject", "object"):
            endpoint_name = rel.get(endpoint_key, "") or ""
            if not endpoint_name:
                stats["invalid_name"] += 1
                rel_kept = False
                break

            fold = _fold_name(endpoint_name)
            if not fold:
                stats["invalid_name"] += 1
                rel_kept = False
                break

            # Tier A.1 — chapter map (single-kind match → repair).
            # If the endpoint name already folds to a chapter-merged
            # entity, treat as resolved without bumping any "new write"
            # counter. Matches writer's tier_a_name_repair semantic.
            candidates = chapter_map.get(fold, [])
            if len(candidates) == 1:
                stats["tier_a_name_repair"] += 1
                continue
            if len(candidates) > 1:
                stats["kind_ambiguous"] += 1
                rel_kept = False
                break

            # Tier A.2 — anchor pre-check (NOT simulated)
            # Skip; fall through to Tier B.

            # Tier B — autocreate
            if not autocreate_enabled:
                rel_kept = False
                break
            if budget is not None and budget <= 0:
                # /review-impl r3 + r2 M4 fold: cap_exhausted bumps
                # always; cap_exhausted_high_conf additionally bumps
                # when conf > 0.8 (tuning signal).
                stats["cap_exhausted"] += 1
                conf = rel.get("confidence", 0.0) or 0.0
                if conf > 0.8:
                    stats["cap_exhausted_high_conf"] += 1
                rel_kept = False
                break
            if _is_noise_subject(endpoint_name):
                stats["noise_skipped"] += 1
                rel_kept = False
                break

            # Auto-create — synthetic entity. Mark with auto_created=true
            # so downstream consumers (judge ensemble doesn't care; but
            # future dashboards do) can distinguish.
            autocreated_entities.append({
                "name": endpoint_name,
                "kind": "concept",
                "confidence": min(rel.get("confidence", 0.0) or 0.0, 0.3),
                "auto_created": True,
            })
            chapter_map.setdefault(fold, []).append(("concept", endpoint_name))
            stats["tier_b_autocreated"] += 1
            if budget is not None:
                budget -= 1

        if rel_kept:
            realized_relations.append(rel)

    stats["relations_kept"] = len(realized_relations)
    # cascade_dropped = relations dropped for reasons OTHER than the
    # accounted-for outcomes. Matches writer's "fell through all tiers
    # with autocreate disabled" semantic.
    stats["cascade_dropped"] = len(relations) - len(realized_relations) - (
        stats["kind_ambiguous"]
        + stats["noise_skipped"]
        + stats["cap_exhausted"]
        + stats["invalid_name"]
    )

    return (
        {
            "entities": entities + autocreated_entities,
            "relations": realized_relations,
            "events": actual.get("events", []),
            "facts": actual.get("facts", []),
        },
        stats,
    )


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    variant = os.environ.get("KNOWLEDGE_C73E_VARIANT", "c73e-autocreate-off").strip()
    autocreate_enabled = variant.endswith("-on")
    max_env = os.environ.get("KNOWLEDGE_C73E_AUTOCREATE_MAX", "20").strip()
    try:
        autocreate_max: int | None = max(1, int(max_env))
    except ValueError:
        autocreate_max = 20

    chapter_dirs = sorted(
        p for p in src.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )
    if not chapter_dirs:
        print(f"ERROR: no chapter dumps under {src}", file=sys.stderr)
        return 1

    print(f"variant={variant} autocreate_enabled={autocreate_enabled} cap={autocreate_max}")
    print(f"src={src} out={out}")
    print()

    total_kept = 0
    total_orig = 0
    aggregate_stats: dict[str, int] = {
        "tier_a_name_repair": 0,
        "kind_ambiguous": 0,
        "tier_b_autocreated": 0,
        "noise_skipped": 0,
        "cap_exhausted": 0,
        "cap_exhausted_high_conf": 0,
        "invalid_name": 0,
        "cascade_dropped": 0,
    }
    per_chapter_stats: list[dict] = []

    for cd in chapter_dirs:
        actual = json.loads((cd / "actual.json").read_text(encoding="utf-8"))
        realized, stats = realize_actual_c73e(
            actual,
            autocreate_enabled=autocreate_enabled,
            autocreate_max=autocreate_max,
        )
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
        n_kept = stats["relations_kept"]
        total_orig += n_orig
        total_kept += n_kept
        for k in aggregate_stats:
            aggregate_stats[k] += stats[k]
        stats_summary = ", ".join(
            f"{k}={v}" for k, v in stats.items() if v > 0
        )
        per_chapter_stats.append({"chapter": cd.name, **stats})
        print(f"{cd.name}: rel {n_orig} → {n_kept}  ({stats_summary})")

    summary = {
        "variant": variant,
        "autocreate_enabled": autocreate_enabled,
        "autocreate_max": autocreate_max,
        "total_relations_orig": total_orig,
        "total_relations_kept": total_kept,
        "cascade_skip_pct": round(
            (total_orig - total_kept) / max(total_orig, 1) * 100, 2,
        ),
        "aggregate_stats": aggregate_stats,
        "per_chapter": per_chapter_stats,
    }
    (out / "c73e_run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(f"TOTAL: relations {total_orig} → {total_kept} "
          f"(cascade {total_orig - total_kept}, "
          f"{(total_orig - total_kept) / max(total_orig, 1) * 100:.1f}%)")
    print("Aggregate stats:")
    for k, v in aggregate_stats.items():
        if v:
            print(f"  {k}: {v}")
    print(f"Output: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
