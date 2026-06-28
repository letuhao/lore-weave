"""Coarse arc-conformance (D-W10-ARC-CONFORMANCE, §14.4 altitude 3) — a PURE structural
diff of the realized motif bindings (the materialized ledger) against the arc TEMPLATE.

This is the COARSE tier (§R1.5): it compares what the template PLANNED to what actually
got BOUND, using only data that ALREADY exists — the arc `layout` placements, the
`motif_application` rows materialize wrote (carrying `arc_template_id` + `thread` in
annotations), the per-scene `tension`, and the `precedes` graph. It does NOT extract the
realized arc from prose (effects→preconditions over the written text); that deep
extract-diff rides the causal-event graph (F-1) + the `motif_beat` extractor and stays
P4+. So `causal_verified` is always False — the succession dim is a STRUCTURAL precedes
check, not a prose-verified one.

Three coarse dims:
  • thread_progress — per thread, did each placed motif (by code) actually get bound?
  • pacing          — realized per-chapter tension curve vs the template pacing curve.
  • succession      — does the realized per-thread order respect the precedes graph?

Plus `unmaterialized`: template placements that produced NO binding (drop/merge folded
them, §12.6 honesty — never silent). Pure: no DB, no LLM, no clock; the router gathers
the inputs and calls this.
"""

from __future__ import annotations

from typing import Any


def _planned_pacing(pacing: list[Any]) -> list[float] | None:
    """Tolerantly extract a per-chapter planned tension curve from the freeform
    ``arc.pacing`` JSONB. Accepts a list of bare numbers or ``{tension|value|t}`` dicts;
    returns None when any entry has no recoverable numeric tension (→ pacing is reported
    realized-only, ``comparable=false``)."""
    if not pacing:
        return None
    out: list[float] = []
    for entry in pacing:
        v: float | None = None
        if isinstance(entry, (int, float)):
            v = float(entry)
        elif isinstance(entry, dict):
            for k in ("tension", "value", "t"):
                if isinstance(entry.get(k), (int, float)):
                    v = float(entry[k])
                    break
        if v is None:
            return None
        out.append(v)
    return out or None


def build_arc_conformance(
    *, arc: Any, realized: list[dict[str, Any]], precedes_pairs: set[tuple[str, str]],
) -> dict[str, Any]:
    """Compute the coarse arc-conformance report (see module docstring).

    ``realized`` is one normalized row per materialized scene:
    ``{motif_id, motif_code, thread, chapter_index, tension}`` (``chapter_index`` a 1-based
    realized-chapter sequence; ``tension`` may be None). ``precedes_pairs`` is the set of
    ``(from_motif_id, to_motif_id)`` legal-succession edges among the realized motifs."""
    threads = arc.threads or []
    layout = arc.layout or []
    thread_labels = {
        t.get("key"): (t.get("label") or t.get("key"))
        for t in threads if isinstance(t, dict) and t.get("key")
    }

    placements_by_thread: dict[str, list[dict]] = {}
    for p in layout:
        placements_by_thread.setdefault(p.get("thread") or "", []).append(p)

    rows_by_thread: dict[str, list[dict]] = {}
    for r in realized:
        rows_by_thread.setdefault(r.get("thread") or "", []).append(r)
    codes_by_thread = {
        th: {r["motif_code"] for r in rows if r.get("motif_code")}
        for th, rows in rows_by_thread.items()
    }
    all_realized_codes = {r["motif_code"] for r in realized if r.get("motif_code")}

    # ── thread_progress: each placed motif (by CODE — the stable cross-tier key) bound?
    thread_keys = list(thread_labels.keys())
    for th in placements_by_thread:
        if th not in thread_keys:
            thread_keys.append(th)
    thread_progress: list[dict[str, Any]] = []
    for th in thread_keys:
        placed = placements_by_thread.get(th, [])
        realized_codes = codes_by_thread.get(th, set())
        missing: list[dict[str, Any]] = []
        covered = 0
        for p in placed:
            if p.get("motif_code") and p["motif_code"] in realized_codes:
                covered += 1
            else:
                missing.append({"motif_code": p.get("motif_code"),
                                "ord": p.get("ord", 0)})
        thread_progress.append({
            "thread": th, "label": thread_labels.get(th, th),
            "planned": len(placed), "covered": covered, "missing": missing,
        })

    # ── pacing: realized per-chapter tension curve vs the (optional) template curve.
    by_ch: dict[int, list[int]] = {}
    for r in realized:
        if r.get("tension") is not None:
            by_ch.setdefault(r["chapter_index"], []).append(r["tension"])
    realized_curve = [
        {"chapter_index": ci, "avg_tension": round(sum(by_ch[ci]) / len(by_ch[ci]), 1),
         "scenes": len(by_ch[ci])}
        for ci in sorted(by_ch)
    ]
    planned_curve = _planned_pacing(arc.pacing or [])
    comparable = planned_curve is not None and len(realized_curve) > 0
    max_drift: float | None = None
    if comparable:
        drifts = [abs(pt["avg_tension"] - planned_curve[i])
                  for i, pt in enumerate(realized_curve) if i < len(planned_curve)]
        max_drift = round(max(drifts), 1) if drifts else None
    pacing = {"comparable": comparable, "planned": planned_curve or [],
              "realized": realized_curve, "max_drift": max_drift}

    # ── succession: structural precedes-order per thread (NOT prose-verified).
    succession_threads: list[dict[str, Any]] = []
    for th, rows in rows_by_thread.items():
        ordered = sorted(rows, key=lambda r: r["chapter_index"])
        seq: list[str] = []
        for r in ordered:
            mid = r.get("motif_id")
            if mid and (not seq or seq[-1] != mid):
                seq.append(mid)
        legal = unrelated = 0
        violations: list[dict[str, Any]] = []
        for a, b in zip(seq, seq[1:]):
            if (a, b) in precedes_pairs:
                legal += 1
            elif (b, a) in precedes_pairs:
                # a reversed precedes edge → a real ordering violation (b should precede a).
                violations.append({"from_motif_id": a, "to_motif_id": b})
            else:
                unrelated += 1
        succession_threads.append({
            "thread": th, "label": thread_labels.get(th, th),
            "transitions": max(0, len(seq) - 1),
            "legal": legal, "unrelated": unrelated, "violations": violations,
        })

    # ── unmaterialized template placements (drop/merge or never bound) — §12.6 honesty.
    unmaterialized = [
        {"motif_code": p.get("motif_code"), "thread": p.get("thread"), "ord": p.get("ord", 0)}
        for p in layout
        if not p.get("motif_code") or p["motif_code"] not in all_realized_codes
    ]

    chapter_count = len({r["chapter_index"] for r in realized})
    return {
        "scope": "arc",
        "available": True,
        "coarse": True,                 # §R1.5 — structural diff only, no prose extract
        "causal_verified": False,       # succession is precedes-structural, not prose-verified
        "arc_template_id": str(arc.id),
        "arc_name": arc.name,
        "chapter_count": chapter_count,
        "thread_progress": thread_progress,
        "pacing": pacing,
        "succession": {"causal_verified": False, "threads": succession_threads},
        "unmaterialized": unmaterialized,
    }
