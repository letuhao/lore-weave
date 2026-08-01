"""E7 — did the scene plan actually LAND on the arc's tension curve?

Pass 4 shapes a per-chapter tension target; pass 6 passes it to the drafter as a prompt directive
(`TENSION TARGET: … peak around N/100 — do not exceed it`) and then never looks again.
`parse_scenes` clamps a scene's tension to 0..100 and defaults a missing one to 50; it is never
told what the chapter was aiming at. So the curve is ADVISORY TO A MODEL, and whether the model
obeyed was, until this module, unobservable — measured once by hand against stored artifacts and
never again.

That is the gap this closes, and it is worth stating why it is a gap and not a nice-to-have:
a chapter that misses its target by 22 points looks exactly like one that hit it. The plan is
well-formed either way. Nothing is missing, nothing errors, and the pacing the author approved at
the blocking beats checkpoint quietly is not the pacing they get.

Deliberately PURE and DETERMINISTIC — no LLM, no I/O. Tension is a number; judging it with a model
(the `motif_conformance` shape) would add cost, latency and non-determinism to a question that
arithmetic answers exactly. This is the `shape_tension_curve` family, not the judge family.

ADVISORY, never a gate: a missed target is information for the author, not a reason to fail a
planning pass. Every entry point degrades to a report that SAYS it could not measure rather than
one that reports zero — "we did not look" and "we looked and found nothing wrong" are different
claims, and this codebase has been burned by conflating them (the motif `absent ≠ zero` rule).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: How far a chapter's realised peak may sit from its target before it is called a miss.
#: Chosen from measured behaviour rather than taste: on the first real 10-chapter arc the local
#: drafter landed 7 chapters EXACTLY on target and missed two by 4 and 22. A tolerance of 10
#: therefore separates "the model is tracking the curve" from "this chapter went its own way"
#: without flagging ordinary rounding.
_DEFAULT_TOLERANCE = 10

ON_TARGET, UNDER, OVER, NO_SCENES = "on_target", "under", "over", "no_scenes"


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):          # bool is an int subclass; a True target is not a target
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return None
    return None


def _peaks_by_chapter(chapters: Any) -> dict[int, int]:
    """chapter_index → the highest scene tension in that chapter.

    PEAK, not mean: the curve's `tension_target` is defined as the chapter's intended peak
    (`shape_tension_curve` ramps base→peak), so comparing against a mean would measure a different
    quantity and read as a systematic undershoot on every multi-scene chapter.

    Chapters are keyed by `chapter.sort_order` — the 1-based ordinal the curve indexes by. Falls
    back to enumeration order only when the field is absent, because a plan whose chapters carry no
    order is one we cannot align to a curve at all, and guessing would silently compare chapter 3
    against chapter 7's target.
    """
    out: dict[int, int] = {}
    if not isinstance(chapters, list):
        return out
    for pos, ch in enumerate(chapters, start=1):
        if not isinstance(ch, dict):
            continue
        idx = _as_int((ch.get("chapter") or {}).get("sort_order") if isinstance(ch.get("chapter"), dict) else None)
        if idx is None:
            idx = pos
        tensions = [
            t for t in (
                _as_int(s.get("tension"))
                for s in (ch.get("scenes") or []) if isinstance(s, dict)
            ) if t is not None
        ]
        if tensions:
            out[idx] = max(tensions)
    return out


def measure(curve: Any, chapters: Any, *, tolerance: int = _DEFAULT_TOLERANCE) -> dict[str, Any]:
    """Compare a scene plan's realised peaks against the arc's tension curve.

    `curve` is pass 4's `tension_curve` (or a prior report's chapters — see `curve_from_report`);
    `chapters` is a `scene_plan` artifact's `chapters` list. Never raises.
    """
    rows: list[dict[str, Any]] = []
    entries = [c for c in curve if isinstance(c, dict)] if isinstance(curve, list) else []
    if not entries:
        # NOT measured ≠ measured-and-clean. A report of "0 misses" here would be a lie about a
        # look that never happened, and it is the lie that renders identically to success.
        return {
            "measured": False,
            "chapters": [],
            "warning": "no tension curve was available — curve conformance was NOT measured",
        }

    peaks = _peaks_by_chapter(chapters)
    counts = {ON_TARGET: 0, UNDER: 0, OVER: 0, NO_SCENES: 0}
    deltas: list[int] = []
    for c in entries:
        idx, target = _as_int(c.get("chapter_index")), _as_int(c.get("tension_target"))
        if idx is None or target is None:
            continue
        peak = peaks.get(idx)
        if peak is None:
            verdict, delta = NO_SCENES, None
        else:
            delta = peak - target
            if abs(delta) <= tolerance:
                verdict = ON_TARGET
            else:
                # OVER is its own verdict, not a signed UNDER: the prompt says "do not exceed",
                # so overshooting is disobedience where undershooting is a shortfall. An author
                # deciding whether to re-run wants to know which of the two happened.
                verdict = OVER if delta > 0 else UNDER
            deltas.append(abs(delta))
        counts[verdict] += 1
        rows.append({
            "chapter_index": idx, "beat_role": c.get("beat_role"),
            "tension_target": target, "peak": peak, "delta": delta, "verdict": verdict,
        })

    if not rows:
        return {
            "measured": False, "chapters": [],
            "warning": "the tension curve carried no usable chapter targets — NOT measured",
        }

    report: dict[str, Any] = {
        "measured": True,
        "tolerance": tolerance,
        "chapters": rows,
        "on_target": counts[ON_TARGET], "under": counts[UNDER],
        "over": counts[OVER], "no_scenes": counts[NO_SCENES],
        "mean_abs_delta": round(sum(deltas) / len(deltas), 1) if deltas else None,
        "degenerate_curve": is_degenerate(entries),
        "warning": "",
    }
    report["warning"] = _warning(report)
    return report


def is_degenerate(curve: Any) -> bool:
    """True when the curve was shaped from NO beat roles at all.

    `shape_tension_curve([None, None, …])` groups every chapter into one neutral run and ramps it
    base→peak — a smooth linear climb that is indistinguishable, by its numbers alone, from a
    deliberately-paced arc. It is not one: it is what a failed L1 beat-mapping degrades to, and it
    is present in this project's stored artifacts (a 10-chapter run reading 50,52,55…72, every
    `beat_role` NULL). Detected on the ROLES rather than on the shape of the numbers, because a
    legitimate single-beat arc is also linear and must not be flagged.
    """
    entries = [c for c in curve if isinstance(c, dict)] if isinstance(curve, list) else []
    if len(entries) < 2:
        return False
    return all(not (c.get("beat_role") or "") for c in entries)


def curve_from_report(report: Any) -> list[dict[str, Any]]:
    """Recover the curve's targets from a conformance report stamped on a `scene_plan`.

    Pass 7 (`self_heal`) depends on `("scenes", "cast")` — NOT on `beats` — so it cannot read the
    curve from pass 4 without widening its dependency set, which would change its input
    fingerprint and stale it (and everything keyed to it) for no functional gain. It does not need
    to: pass 6 stamps the targets onto the artifact that IS pass 7's input, so pass 7 can re-measure
    its healed plan against the same numbers. That is what makes a pass-6 → pass-7 comparison
    possible at all, and pass 7 is the one that can silently flatten what pass 6 achieved: it
    rewrites scenes knowing nothing about the curve.
    """
    rows = (report or {}).get("chapters") if isinstance(report, dict) else None
    if not isinstance(rows, list):
        return []
    return [
        {"chapter_index": r.get("chapter_index"), "beat_role": r.get("beat_role"),
         "tension_target": r.get("tension_target")}
        for r in rows
        if isinstance(r, dict) and r.get("chapter_index") is not None
        and r.get("tension_target") is not None
    ]


def _warning(report: dict[str, Any]) -> str:
    """One human sentence, or "" when there is genuinely nothing to say.

    Empty-when-clean on purpose: a warning that fires on every run is one nobody reads.
    """
    bits: list[str] = []
    if report.get("degenerate_curve"):
        bits.append(
            "the tension curve was shaped from NO beat roles — it is the flat default ramp, not a "
            "planned arc (the beat mapping degraded)"
        )
    missed = int(report.get("under") or 0) + int(report.get("over") or 0)
    if missed:
        worst = max(
            (r for r in report["chapters"] if r.get("delta") is not None),
            key=lambda r: abs(r["delta"]), default=None,
        )
        where = (
            f" (worst: chapter {worst['chapter_index']} aimed at {worst['tension_target']}, "
            f"peaked at {worst['peak']})" if worst else ""
        )
        bits.append(f"{missed} chapter(s) missed their tension target{where}")
    if report.get("no_scenes"):
        bits.append(f"{report['no_scenes']} chapter(s) have no scenes to measure")
    return "; ".join(bits)
