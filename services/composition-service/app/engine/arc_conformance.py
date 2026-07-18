"""Coarse arc-conformance (D-W10-ARC-CONFORMANCE, §14.4 altitude 3) — a PURE structural
diff of the realized motif bindings (the materialized ledger) against a planned arc.

BA4 (23_book_architecture) RETARGET: the primary arc axis is now the durable SPEC
(`structure_node`) — "did the prose realize *my plan*". The builders are tolerant of the
arc object (spec `structure_node` OR `arc_template`) via the `arc_threads`/`arc_layout`/
`arc_pacing`/`arc_name` accessors, so the split-out `composition_arc_template_drift` path
(realized-vs-the-template-it-came-from) reuses the same join-correctness surface.

This is the COARSE tier (§R1.5): it compares what was PLANNED to what actually
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

# BA4 retarget — the coarse builder is shared by TWO arc objects: the durable spec
# (`structure_node`, the new `scope='arc'` axis, keyed by `structure_node_id`) and the
# `arc_template` (the split-out `composition_arc_template_drift` path). They carry the
# same *shape* under different names (`tracks`↔`threads`, `title`↔`name`), and the spec
# has NO `layout`/`pacing` (BA5: `motif_application` IS the realized layout; BA3: pacing
# is derived from member-scene tension). These tolerant accessors let ONE builder serve
# both without a hard `isinstance` branch.
_UNSET = object()


def arc_threads(arc: Any) -> list[dict[str, Any]]:
    """The arc's declared tracks/threads ([{key,label}]). An `arc_template` exposes
    `.threads`; a `structure_node` exposes `.tracks` (BA10 vocabulary) — same shape."""
    t = getattr(arc, "threads", None)
    if t is None:
        t = getattr(arc, "tracks", None)
    return t or []


def arc_layout(arc: Any) -> list[dict[str, Any]]:
    """The arc's planned placements. An `arc_template` carries `layout`; a `structure_node`
    has NONE (BA5 — `motif_application` IS the realized layout), so the spec path has no
    separately-planned placements and coverage/unmaterialized degrade to empty (honest)."""
    return getattr(arc, "layout", None) or []


def arc_pacing(arc: Any) -> list[Any]:
    """The arc's template pacing curve. A `structure_node` has none (BA3 — pacing is derived
    from member-scene `tension`), so the spec path reports pacing realized-only."""
    return getattr(arc, "pacing", None) or []


def arc_name(arc: Any) -> str:
    """`arc_template.name` or `structure_node.title`."""
    return getattr(arc, "name", None) or getattr(arc, "title", None) or ""


def arc_provenance_template_id(arc: Any) -> Any:
    """The template this arc is measured *from*. An `arc_template` IS its own template
    (its `.id`); a `structure_node` carries a nullable `.arc_template_id` (BA13 — an arc
    authored from conversation has none)."""
    tid = getattr(arc, "arc_template_id", _UNSET)
    if tid is _UNSET:
        return getattr(arc, "id", None)
    return tid


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


def _deep_thread_progression(
    sequences: list[list[dict[str, Any]]], chapter_index_by_id: dict[str, int],
    arc_threads: list[dict[str, Any]],
) -> dict[str, Any]:
    """The realized-from-PROSE thread-presence diff (unblocked by THREAD-TAG). Reads each
    step's ``narrative_thread`` (the classifier label) → which planned threads actually show
    up in the written prose, and in how many chapters. ``available:false`` (with a reason)
    until events are tagged — never faked. Also surfaces threads the prose introduced that
    the arc never planned (``unplanned``)."""
    # A thread counts as realized ONLY in the arc's materialized chapters (the dim asks
    # "did the thread advance WHERE PLACED"). The motif_beat sequences span the whole book,
    # so a tagged event in a chapter outside this arc (idx None) is irrelevant here — gating
    # the setdefault on idx keeps `realized=True` ⟺ `realized_chapters ≥ 1` (no 0-chapter
    # "realized" verdict) and keeps `unplanned` to threads the prose delivered IN-arc.
    realized: dict[str, set[int]] = {}
    for seq in sequences:
        for step in seq:
            nt = step.get("narrative_thread")
            if not nt:
                continue
            idx = chapter_index_by_id.get(str(step.get("thread") or ""))
            if idx is not None:
                realized.setdefault(nt, set()).add(idx)
    planned = {t["key"]: (t.get("label") or t["key"])
               for t in (arc_threads or []) if t.get("key")}
    rows = [{"thread": k, "label": label, "realized": k in realized,
             "realized_chapters": len(realized.get(k, set()))}
            for k, label in planned.items()]
    if not realized:
        return {"available": False,
                "reason": "no narrative_thread tags yet — run tag-threads (pass model_ref)",
                "threads": rows, "unplanned": []}
    return {"available": True, "threads": rows,
            "unplanned": sorted(t for t in realized if t not in planned)}


def _deep_succession(
    sequences: list[list[dict[str, Any]]],
    precedes_code_pairs: set[tuple[str, str]],
    causal_code_pairs: set[tuple[str, str]] | None = None,
    entailed_code_pairs: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """The realized-from-PROSE legal-succession diff (unblocked by the motif-tag classifier).
    Flattens the realized motif order (``realized_motif_code`` per step, event-order-ordered,
    consecutive dups collapsed) and checks each transition against the ``precedes`` graph:
    ``legal`` (a forward precedes edge), ``reversed`` (a precedes edge the WRONG way → a
    violation), or ``unrelated`` (no edge). ``available:false`` until events are motif-tagged.

    F2: when ``causal_code_pairs`` is given (realized ``(:Event)-[:CAUSES]`` between the two
    motifs), a legal transition that is ALSO causally backed sets ``caused:true`` and the dim's
    ``causal_verified:true`` — structural-only otherwise.

    D-SUCCESSION-ENTAILMENT-JUDGE: when ``entailed_code_pairs`` is given (the LLM judged A's
    effects entail B's preconditions), a legal transition that is ALSO entailed sets the dim's
    ``entailment_verified:true`` + an ``entailed`` count — the deepest signal (a legal, caused
    transition can still be a non-sequitur if A's outcome doesn't establish B's premises)."""
    # FIRST-OCCURRENCE order, each motif once: "did the motifs first appear in legal order".
    # (Consecutive-only dedup would let a legitimately RECURRING motif — e.g. humiliation,
    # face_slap, humiliation — manufacture a face_slap→humiliation "reversed" false violation.)
    seen: set[str] = set()
    seq: list[str] = []
    for s in sequences:
        for step in s:
            c = step.get("realized_motif_code")
            if c and c not in seen:
                seen.add(c)
                seq.append(c)
    if not seq:
        return {"available": False, "causal_verified": False,
                "reason": "no realized-motif tags yet — run tag-motifs (pass model_ref)",
                "transitions": 0, "legal": 0, "unrelated": 0, "violations": []}
    causal = causal_code_pairs or set()
    entailed = entailed_code_pairs or set()
    legal = unrelated = 0
    violations: list[dict[str, Any]] = []
    caused_total = 0
    entailed_total = 0
    for a, b in zip(seq, seq[1:]):
        if (a, b) in precedes_code_pairs:
            legal += 1
            if (a, b) in causal:
                caused_total += 1
            if (a, b) in entailed:
                entailed_total += 1
        elif (b, a) in precedes_code_pairs:
            violations.append({"from_motif_code": a, "to_motif_code": b})
        else:
            unrelated += 1
    return {"available": True, "causal_verified": caused_total > 0,
            "entailment_verified": entailed_total > 0,
            "transitions": len(seq) - 1, "legal": legal, "unrelated": unrelated,
            "caused": caused_total, "entailed": entailed_total, "violations": violations}


def build_deep_report(
    *, sequences: list[list[dict[str, Any]]],
    chapter_index_by_id: dict[str, int],
    planned_by_index: dict[int, float],
    arc_threads: list[dict[str, Any]] | None = None,
    precedes_code_pairs: set[tuple[str, str]] | None = None,
    causal_code_pairs: set[tuple[str, str]] | None = None,
    entailed_code_pairs: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """The DEEP (realized-from-PROSE) overlay (D-W10-ARC-CONFORMANCE-DEEP).

    The coarse diff reads the planned ledger; this reads what the PROSE actually delivered
    via the `motif_beat` extractor (Option A), which projects the realized `:Event` timeline
    into `{beat, thread, tension}` steps. But that extractor's `thread` is the event's
    CHAPTER (not a narrative thread) and `beat` is the event TITLE (not a motif beat key),
    so ONLY pacing is realizable from prose today: the realized per-chapter tension curve.
    This is the FIRST real prose-drift measure — the coarse `pacing.realized` is actually the
    PLANNED `outline_node.tension`, never the prose. thread-progression + legal-succession
    from prose need the narrative-thread / motif tagging extractor (a knowledge-service
    follow-up) + causal edges — surfaced as `available:false` with a reason, NEVER faked.

    `sequences`: motif_beat steps (thread = chapter_id, tension a 1..5 band).
    `chapter_index_by_id`: chapter_id → the 1-based realized index (from the materialized
    ledger). `planned_by_index`: index → planned avg tension (0..100, the outline plan).
    Realized tension (1..5) is normalized ×20 → 0..100 for a like-for-like drift vs the plan."""
    by_idx: dict[int, list[float]] = {}
    for seq in sequences:
        for step in seq:
            if not isinstance(step, dict):
                continue
            idx = chapter_index_by_id.get(str(step.get("thread") or ""))
            t = step.get("tension")
            if idx is None or not isinstance(t, (int, float)):
                continue
            by_idx.setdefault(idx, []).append(float(t) * 20.0)   # 1..5 band → 0..100
    realized = [
        {"chapter_index": i, "avg_tension": round(sum(by_idx[i]) / len(by_idx[i]), 1),
         "events": len(by_idx[i])}
        for i in sorted(by_idx)
    ]
    planned = [{"chapter_index": r["chapter_index"],
                "avg_tension": round(planned_by_index.get(r["chapter_index"], 0.0), 1)}
               for r in realized]
    drifts = [abs(r["avg_tension"] - p["avg_tension"])
              for r, p in zip(realized, planned) if r["chapter_index"] in planned_by_index]
    max_drift = round(max(drifts), 1) if drifts else None
    return {
        "available": len(realized) > 0,
        "source": "motif_beat_extractor",
        "pacing": {
            "comparable": len(realized) > 0 and bool(drifts),
            "planned": planned, "realized": realized, "max_drift": max_drift,
            "scale_note": "realized tension from extracted :Event salience (1..5 band → ×20)",
        },
        "thread_progression": _deep_thread_progression(
            sequences, chapter_index_by_id, arc_threads or []),
        "succession": _deep_succession(
            sequences, precedes_code_pairs or set(), causal_code_pairs, entailed_code_pairs),
    }


def build_arc_conformance(
    *, arc: Any, realized: list[dict[str, Any]], precedes_pairs: set[tuple[str, str]],
) -> dict[str, Any]:
    """Compute the coarse arc-conformance report (see module docstring).

    ``realized`` is one normalized row per materialized scene:
    ``{motif_id, motif_code, thread, chapter_index, tension}`` (``chapter_index`` a 1-based
    realized-chapter sequence; ``tension`` may be None). ``precedes_pairs`` is the set of
    ``(from_motif_id, to_motif_id)`` legal-succession edges among the realized motifs."""
    threads = arc_threads(arc)
    layout = arc_layout(arc)
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
    planned_curve = _planned_pacing(arc_pacing(arc))
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
    tid = arc_provenance_template_id(arc)
    return {
        "scope": "arc",
        "available": True,
        "coarse": True,                 # §R1.5 — structural diff only, no prose extract
        "causal_verified": False,       # succession is precedes-structural, not prose-verified
        # BA4: `arc_id` is the axis identity (structure_node.id on the spec path;
        # arc_template.id on the template-drift path). `arc_template_id` is now PROVENANCE
        # — the template the arc was measured from (nullable for a conversation-authored arc).
        "arc_id": str(arc.id),
        "arc_template_id": str(tid) if tid else None,
        "arc_name": arc_name(arc),
        "chapter_count": chapter_count,
        "thread_progress": thread_progress,
        "pacing": pacing,
        "succession": {"causal_verified": False, "threads": succession_threads},
        "unmaterialized": unmaterialized,
    }
