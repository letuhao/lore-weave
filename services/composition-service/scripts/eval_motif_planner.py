"""W2 eval-gate — motif planner select+bind (3-way A/B/C) + the CI structural gate.

Two modes:

  CI (default, no live stack — `python eval_motif_planner.py`):
    Drives engine.plan.decompose directly with a FakeRetriever + a FakeLLM (no
    network), asserting the W2 doc §6.3/§6.4 STRUCTURAL guarantees that do not need
    the real W3 retrieve or the R2.1 labeled seed:
      - reproducibility (§6.4): two runs with the same scripted candidates bind the
        SAME motif_ids (the §5 tie-break total order).
      - fallback non-regression (§6.3): a genre with NO seed motifs (FakeRetriever
        returns []) ⇒ every chapter falls back to invent, output identical-in-shape
        to motifs-off (arm B), and motif_coverage records the fallbacks.
      - the bound path is LLM-free (no L2 call when a motif binds) — the latency win.
    This is the gate W2 ships behind; exit non-zero on any assertion failure.

  LIVE (`python eval_motif_planner.py --live`): the full 3-way plot-density compare
    (A motif-planner vs B A3-invent vs C A3-invent+plot-nudge) against the running
    stack + the W5-owned R2.1 labeled seed + W3's real retrieve. DEFERRED to
    R-NODE-P1 (master §6): it needs W3 (real retrieve) + a seed pack + the gold seed,
    none bootable from W2 alone. Prints the deferral note + exits 0 (advisory) so CI
    never blocks on an unavailable dependency (the C16 "never wall on an optional
    dependency" lesson).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from types import SimpleNamespace


# ── ensure the service package imports (env that Settings needs) ────────────
os.environ.setdefault("COMPOSITION_DB_URL", "postgresql://u:p@h:5432/composition")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)
os.environ.setdefault("CONFIRM_TOKEN_SIGNING_SECRET", "c" * 32)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Motif, MotifCandidate  # noqa: E402
from app.engine.plan import ChapterPlan, decompose  # noqa: E402


_BEATS = [{"key": "climax", "purpose": "payoff"}, {"key": "setup", "purpose": "establish"}]
_L1 = json.dumps({"chapters": [
    {"index": 1, "beat": "climax", "intent": "the confrontation"},
    {"index": 2, "beat": "setup", "intent": "the calm before"},
], "unmapped_beats": []})
_L2 = json.dumps({"scenes": [{"title": "X", "intent": "an invented scene", "tension": 55, "present": []}]})


class _FakeLLM:
    def __init__(self):
        self.l2_calls = 0

    async def submit_and_wait(self, **kw):
        user = kw["input"]["messages"][1]["content"]
        if "STRUCTURE BEATS" in user:
            return SimpleNamespace(status="completed", result={"messages": [{"content": _L1}]})
        self.l2_calls += 1
        return SimpleNamespace(status="completed", result={"messages": [{"content": _L2}]})


class _FakeRetriever:
    def __init__(self, candidates):
        self._c = candidates

    async def retrieve(self, caller_id, **kw):
        return list(self._c)


def _motif(code, name, tension_target=4):
    return Motif.model_validate({
        "id": uuid.uuid4(), "owner_user_id": None, "code": code, "language": "en",
        "visibility": "unlisted", "kind": "scheme", "name": name, "summary": "s",
        "genre_tags": ["xianxia"],
        "roles": [{"key": "hero", "actant": "subject", "label": "Lin", "constraints": []}],
        "beats": [
            {"key": "b1", "label": "Beat 1", "intent": "{hero} acts", "tension_target": 3, "order": 1},
            {"key": "b2", "label": "Beat 2", "intent": "{hero} prevails", "tension_target": 5, "order": 2},
        ],
        "effects": [{"text": "e"}], "annotations": {},
        "tension_target": tension_target, "status": "active", "version": 1,
    })


def _candidate(m, score):
    return MotifCandidate(motif=m, score=score, match_reason={"cosine": score})


def _chapters(n=2):
    return [ChapterPlan(chapter_id=str(uuid.uuid4()), title=f"Ch{i}", sort_order=i,
                        beat_role=None, intent="") for i in range(n)]


_BASE = dict(
    user_id=str(uuid.uuid4()), model_source="local", model_ref="m",
    premise="p", arc_title="Arc", beats=_BEATS,
    cast=[{"entity_id": "ent-lin", "name": "Lin"}],
    k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6, source_language="en",
)


async def _run_motif(retriever):
    return await decompose(
        _FakeLLM(), chapters=_chapters(), motifs_enabled=True, retriever=retriever,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        motif_min_score=0.30, **_BASE,
    )


async def _ci_gate() -> int:
    failures: list[str] = []

    # ── reproducibility (§6.4): same scripted candidates → same bound motif_ids ──
    cands = [_candidate(_motif("m.a", "A"), 0.9), _candidate(_motif("m.b", "B"), 0.9)]
    r1 = await _run_motif(_FakeRetriever(cands))
    r2 = await _run_motif(_FakeRetriever(cands))
    ids1 = [cs.motif.motif.id for cs in r1.chapters if cs.motif]
    ids2 = [cs.motif.motif.id for cs in r2.chapters if cs.motif]
    if ids1 != ids2:
        failures.append(f"reproducibility: {ids1} != {ids2}")
    if not ids1:
        failures.append("reproducibility: nothing bound (expected the tie-break to pick one)")

    # ── the bound path is LLM-free ──
    llm = _FakeLLM()
    bound = await decompose(
        llm, chapters=_chapters(2), motifs_enabled=True,
        retriever=_FakeRetriever([_candidate(_motif("m.x", "X"), 0.95)]),
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        motif_min_score=0.30, **_BASE,
    )
    n_bound = sum(1 for cs in bound.chapters if cs.motif)
    if llm.l2_calls != (len(bound.chapters) - n_bound):
        failures.append(f"bound path not LLM-free: l2_calls={llm.l2_calls}, bound={n_bound}")

    # ── fallback non-regression (§6.3): no seed motifs ⇒ all invent, == arm B ──
    arm_a_empty = await _run_motif(_FakeRetriever([]))   # arm A, no motifs available
    arm_b = await decompose(_FakeLLM(), chapters=_chapters(), **_BASE)  # motifs OFF
    a_bound = sum(1 for cs in arm_a_empty.chapters if cs.motif)
    if a_bound != 0:
        failures.append(f"fallback: arm A bound {a_bound} with an empty library (expected 0)")
    if len(arm_a_empty.chapters) != len(arm_b.chapters):
        failures.append("fallback: arm A and arm B chapter counts differ")
    if arm_a_empty.motif_coverage.get("fallbacks", {}).get("no_motif_match") != len(arm_a_empty.chapters):
        failures.append("fallback: motif_coverage did not record no_motif_match per chapter")

    print("── W2 motif-planner CI structural gate ──")
    print(f"  reproducibility:        {'PASS' if ids1 == ids2 and ids1 else 'FAIL'}")
    print(f"  bound-path LLM-free:    {'PASS' if not any('LLM-free' in f for f in failures) else 'FAIL'}")
    print(f"  fallback non-regress:   {'PASS' if not any('fallback' in f for f in failures) else 'FAIL'}")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nALL STRUCTURAL GATES PASS (live 3-way plot-density compare deferred to R-NODE-P1).")
    return 0


def _live_note() -> int:
    print(
        "LIVE 3-way eval (A motif vs B invent vs C invent+plot-nudge) on plot-density\n"
        "is DEFERRED to R-NODE-P1 — it needs W3's real retrieve + a seed pack + the\n"
        "W5-owned R2.1 gold seed, none of which are bootable from W2 alone. Run the CI\n"
        "structural gate (no flag) until then; it asserts reproducibility + fallback\n"
        "non-regression + the LLM-free bound path against the FakeRetriever."
    )
    return 0


def main() -> int:
    if "--live" in sys.argv:
        return _live_note()
    return asyncio.run(_ci_gate())


if __name__ == "__main__":
    raise SystemExit(main())
