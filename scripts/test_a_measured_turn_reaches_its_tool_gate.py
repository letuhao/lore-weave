"""A tool must declare the words the author actually typed at it.

🔴 THE INVARIANT: for every turn this loop has MEASURED against a tool, that tool's own declared
vocabulary must make it answerable. If the request cannot reach the tool, nothing downstream can
save it — and the measured consequence is not a missing answer, it is a FALSE one.

MEASURED 2026-08-22, cycle 1 of the resolution loop, offline against the real `answerable_tools`
and the cached 315-tool catalogue: of the 25 tools blocked on `P1-SURFACE`, **23 were never matched
on their own measured turn**. `stream_service`'s R1 block states the platform's guarantee outright —
"if the user's words match a tool's own vocabulary, it is on the wire, whatever the budget, the
domain selection or the rail decided" — and `discovery_catalog` is the near-full turn catalogue, so
that check sees almost everything. The guarantee held. The words never matched.

The correlation runs both ways, which is what makes this the right bar rather than a plausible one:
tools that SURFACED N/N matched answerability 89 of 96; tools that surfaced 0/N matched 7 of 33.

WHY A GATE AND NOT 27 EDITS. Widening a declaration is correct the day it is made and silent the
next time a tool is added or split — which is exactly how these 27 accumulated. This asserts the
property at ONE place, over every scenario on disk, so a new scenario whose wording cannot reach
its own tool fails here instead of costing five live runs to discover.

WHAT IT DOES NOT COVER, stated so its green is never over-read:
  * Answerability is the DOMINANT reach path, not the only one. `ALWAYS_ON_CORE` tools and
    frontend/consumer-local tools are advertised regardless, and are exempt below BY NAME.
  * A match does not promise the tool was advertised — `filter_intent_gated_setup_tools` removes
    five world-setup tools from the catalogue BEFORE answerability runs (DQ-T31), and
    `glossary_book_sync_apply` is one of them.
  * It says nothing about whether the model then CHOOSES the tool. That is P5's problem.
  * It reads the CACHED catalogue. After a synonym change: rebuild, restart ai-gateway (it caches
    the federated tool list), and `python scripts/toolloop/catalog.py --refresh`.

BASELINE, NOT A HARD FAILURE. The gaps are real and are cycle 1's work-list, but failing the suite
on all of them would block every unrelated change. This asserts the set does not GROW, and that a
FIXED entry leaves the file — so the count stays a work-list rather than a monument.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

BASELINE = ROOT / "contracts" / "unreachable-measured-turns-baseline.json"
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"

try:
    from app.services.tool_discovery import ALWAYS_ON_CORE_NAMES
    from app.services.tool_surface import answerable_tools
except Exception as e:  # chat-service not importable here
    pytest.skip(f"chat-service not importable: {e}", allow_module_level=True)

# Advertised by a path that is not answerability. Each is exempt BY NAME with the reason, because
# an exemption without one becomes a place to hide a real failure.
EXEMPT = {
    **{n: "ALWAYS_ON_CORE — advertised on every turn" for n in ALWAYS_ON_CORE_NAMES},
    # 🔴 `propose_edit` WAS EXEMPT ON A REASON THE CATALOGUE CONTRADICTS, and the exemption is
    # REMOVED rather than reworded. It read: "declares NO synonyms by design, so answerability
    # cannot reach it and is not meant to". Measured 2026-09-03 against the live catalogue: it
    # declares SIX synonyms ('show me the change', 'suggest an edit', 'rewrite this', ...), it has
    # a measured turn, and answerable_tools reaches it on that turn. An exemption whose stated
    # reason is false is a place a real failure can hide — this file's own comment says an
    # exemption without a reason becomes exactly that, and a WRONG reason is worse than none
    # because it survives review. The tool passes the gate on its own merits; nothing is lost.
    "workflow_list": "consumer-local meta-tool, advertised when the turn has curated workflows",
    "workflow_load": "consumer-local meta-tool, same",
    "load_skill": "consumer-local control, advertised when lazy skill bodies are on",
    "find_tools": "consumer-local, not federated",
}


def _catalog() -> list[dict]:
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]


def measured_turns() -> dict[str, str]:
    """{tool: the turn it was actually CONCLUDED on}.

    Two rules matter here and both were learned by getting them wrong.

    THE TURN IS THE LAST ONE. Reading the first gave "List my worlds." for three four-turn
    world-map scenarios — a turn that says nothing about the tool under test.

    🔴 THE SCENARIO IS THE ONE ITS LEDGER ROW CITES, not whichever file sorts last. This used to
    take the last file alphabetically, and `scripts/toolloop/answerability_probe.py` takes the one
    matching `evidence_file`. For `translation_update_settings` those are different files, so the
    two instruments read different sentences and disagreed about whether it was reachable — the
    gate said 0 unreachable while the probe said 1. An instrument that disagrees with its own
    sibling is measuring something neither of us named. One rule now, and it is the ledger's.

    🔴 AND WHEN THE CITED FILE IS NOT ON DISK, READ THE EVIDENCE — DO NOT GUESS. The rule above
    was stated and then quietly broken: matching on `evidence_file` fell back to `cands[-1]`, the
    last scenario file alphabetically, whenever no scenario file carried that name. Measured
    2026-08-25: `translation_job_control` is concluded on `c-tjc-jobsupplier`, for which there is
    NO scenario file, so the gate was reporting a sentence out of `rebaseline` — a file the
    ledger does not cite — and calling it the measured turn.

    The evidence records the exact sentence — but ONLY in its newer shape, and reading it blindly
    is a trap this nearly fell into. THE BATCH SCHEMA DRIFTED: 72 rows carry `scenario_prompt`
    (the scenario's opening) alongside `prompt` (the turn actually measured), and 58 older rows
    carry `prompt` alone, holding the OPENING. Reading `prompt` unconditionally reported seven
    world_* tools as measured on "List my worlds." — which is the very sentence this docstring
    already says means nothing about them, arriving by a new route. `scenario_prompt`'s presence
    is the discriminator, so it is the discriminator here.

    That also fixes what the fallback was hiding — `c-tjc-jobsupplier`'s real sequence is a
    SUPPLIER turn ("What is the status of the translation job for this book?") followed by an
    anaphoric "Cancel that job.", which no scenario file on disk describes.
    """
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"tools": {}}

    # What was actually SENT, straight off the evidence the conclusion cites.
    from_evidence: dict[str, str] = {}
    for tool, row in ledger["tools"].items():
        ev = row.get("evidence_file")
        if not ev:
            continue
        p = ROOT / ev
        if not p.exists():
            continue
        try:
            batch = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        er = next((x for x in batch.get("tools", []) if x.get("tool") == tool), None)
        runs = (er or {}).get("runs") or []
        if not runs:
            continue
        last = runs[-1]
        # Only the newer shape distinguishes the opening from the measured turn. Without
        # `scenario_prompt`, `prompt` IS the opening and says nothing about a later turn.
        if "scenario_prompt" in last and last.get("prompt"):
            from_evidence[tool] = last["prompt"]

    by_tool: dict[str, list[tuple[str, str]]] = {}
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            t = [x for x in [s.get("prompt")] + list(s.get("follow_ups") or []) if x]
            if t and s.get("tool_under_test"):
                by_tool.setdefault(s["tool_under_test"], []).append(
                    (f.stem.replace("scenarios-", ""), t[-1]))
    out: dict[str, str] = dict(from_evidence)
    for tool, cands in by_tool.items():
        if tool in out:  # the measurement itself always wins over a scenario file
            continue
        ev = (ledger["tools"].get(tool) or {}).get("evidence_file") or ""
        want = pathlib.Path(ev).stem
        # No evidence prompt AND a cited file that names no scenario: there is nothing here to
        # read, so take the file the ledger cites if it exists and otherwise the last candidate —
        # but only for pre-gate rows, which is the only case that now reaches this line.
        out[tool] = next((turn for name, turn in cands if name == want), cands[-1][1])
    return out


def _legacy_names() -> set[str]:
    """Tools `drop_superseded_tools` removes from EVERY turn.

    🔴 REQUIRING A DROPPED TOOL TO BE REACHABLE IS A CONTRADICTION, and the gate held one.
    Since 2026-08-25 the superseded gate drops every `visibility: legacy` tool from the wire --
    with or without a declared replacement -- so no declaration can put one in front of a model.
    The gate nonetheless demanded that `book_get` be answerable on its measured turn and failed
    when it was not. Widening its synonyms would have been busywork with a green light at the
    end: the tool would still never be advertised, and the next reader would have inherited a
    declaration written to satisfy a check rather than to describe a capability.

    This is the same shape as the day's other findings -- a rule outliving the state it was
    written against. The measured turns for these tools stay on file; they simply cannot be
    reachability failures.
    """
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return {n for n, t in raw.items()
            if (t.get("meta") or {}).get("visibility", "live") == "legacy"}


def unreachable() -> dict[str, str]:
    """{tool: the turn that could not reach it} for every non-exempt LIVE tool in the catalogue."""
    defs = _catalog()
    names = {td["function"]["name"] for td in defs}
    legacy = _legacy_names()
    bad = {}
    for tool, text in sorted(measured_turns().items()):
        if tool in EXEMPT or tool not in names or tool in legacy:
            continue
        if tool not in answerable_tools(text, defs):
            bad[tool] = text
    return bad


def _baseline() -> dict:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))["unreachable"]


def test_no_new_measured_turn_fails_to_reach_its_own_tool():
    now = unreachable()
    new = {k: v for k, v in now.items() if k not in _baseline()}
    assert not new, (
        "a scenario's measured turn cannot reach the tool it tests — the tool will surface 0/N "
        "before a single run is spent:\n"
        + "\n".join(f"  {k}\n    said: {v}" for k, v in sorted(new.items()))
        + "\n\nWiden the tool's declared synonyms, or fix the scenario's wording. If the tool is "
          "reached by another path, add it to EXEMPT with the reason."
    )


def test_a_tool_that_became_reachable_leaves_the_baseline():
    """A baseline that only ever grows stops meaning anything."""
    now = unreachable()
    stale = sorted(k for k in _baseline() if k not in now)
    assert not stale, (
        f"{stale} are now reachable but still in the baseline — regenerate it:\n"
        "  python scripts/toolloop/answerability_probe.py --write-unreachable-baseline"
    )


def test_the_exemptions_are_named_and_real():
    """An exemption is a place to hide a failure unless it carries a reason and the tool exists."""
    for name, why in EXEMPT.items():
        assert why and len(why) > 20, f"{name} is exempt without a reason"


def test_the_gate_is_red_able_on_the_original_instance():
    """world_map_update_region declares `rename region`; the author said "Rename the AREA called
    The North". Kept as a live assertion: if the detector stops seeing this, the gate is inert."""
    defs = _catalog()
    said = "Rename the area called The North to The Frozen North."
    assert "world_map_update_region" not in answerable_tools(said, defs) or \
        "world_map_update_region" not in _baseline(), (
        "either the declaration was widened (remove it from the baseline) or the gate went inert"
    )


# ── PER SCENARIO, not per tool ───────────────────────────────────────────────────────────
#
# 🔴 THE GATE ABOVE READS ONE TURN PER TOOL, and a tool is measured by SEVERAL scenarios with
# different wordings. `measured_turns()` picks the turn the tool was CONCLUDED on and never
# looks at the others, so a tool that reaches its own vocabulary in the batch that concluded it
# and misses in five other scenarios passes — and those five will surface 0/N whenever they are
# run. Measured 2026-08-27: the per-tool baseline holds ONE entry, while 25 scenario turns
# cannot reach their own tool, across 5 tools of which 4 are not in that baseline at all.
#
# THIS IS ALSO WHERE D-A-FIFTH-OF-SCENARIOS-DO-NOT-ASK-FOR-THEIR-OWN-TOOL ENDS UP, and the
# re-derivation reverses that row. Judged on the turn fe_runner actually measures rather than on
# `prompt`:
#
#     108  scenarios cannot reach their tool from the FIRST turn   <- what the row measured
#      25  from the MEASURED turn                                  <- what is real
#
# and the split of those 25 is not what the row claimed either:
#
#      22  SYNONYM gap on a Tier A/W tool     ("Attach the pattern called …" -> motif_bind_edit)
#       2  a Tier R read tool
#       1  a tool the offline tier scan does not know
#       0  read-verb prompt on a write tool   <- the 84 the row was closed on
#
# Every one of the 25 is a DECLARATION gap: the sentence asks for exactly what the tool does and
# the tool has not declared those words. Rewriting the prompts would be fixing the wrong half,
# which is the mistake that row already made once.

SCENARIO_BASELINE = ROOT / "contracts" / "unreachable-scenario-turns-baseline.json"


def unreachable_scenarios() -> set[str]:
    """{file::id} for every scenario whose MEASURED turn cannot reach its own tool."""
    # From fe_runner, which OWNS the rule (its turn loop asserts against it). An earlier draft
    # imported it out of a TEST module by path — and a falsifier that edited that module was a
    # SILENT NO-OP, because the function had already moved. Import from the home, not from a
    # neighbour that re-exports it.
    sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
    from fe_runner import measured_turn  # noqa: PLC0415
    defs = _catalog()
    names = {td["function"]["name"] for td in defs}
    # Same legacy exclusion as the per-tool scan: a tool the superseded gate drops from every
    # turn cannot be made reachable by any declaration, so it is not a reachability failure.
    # Both scans must agree — two answers to one question is how this file's own docstring says
    # the earlier falsifier became a silent no-op.
    legacy = _legacy_names()
    out = set()
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            tool = s.get("tool_under_test")
            if not tool or tool in EXEMPT or tool not in names or tool in legacy:
                continue
            if tool not in answerable_tools(measured_turn(s), defs):
                out.add(f"{f.name}::{s.get('id')}")
    return out


def _scenario_contract() -> dict:
    if not SCENARIO_BASELINE.exists():
        return {"scenarios": [], "by_design": {}, "overridden_by_live_evidence": {}}
    return json.loads(SCENARIO_BASELINE.read_text(encoding="utf-8"))


def _scenario_baseline() -> set[str]:
    """Everything the GATE tolerates — three categories with three different rules.

    🔴 SPLIT 2026-08-30, and the split was overdue rather than occasioned. This was one flat
    shrink-only list, and five of its twenty-five entries were already "Yes, go ahead and do it."
    confirmation turns. A confirmation carries no tool vocabulary AND MUST NOT — so those entries
    could never leave the list, while `test_a_scenario_that_became_reachable_leaves_the_baseline`
    stood ready to demand their removal the moment they did, which would have been a regression
    dressed as progress.

      scenarios   DECLARATION DEBT — shrink-only; becoming reachable is progress
      by_design   the measured turn MUST NOT reach its tool; becoming reachable is a REGRESSION
      overridden  the gate was WRONG here, and a live run on disk proves it
    """
    c = _scenario_contract()
    return (set(c.get("scenarios") or [])
            | set(c.get("by_design") or {})
            | set(c.get("overridden_by_live_evidence") or {}))


def test_the_per_scenario_scan_sees_more_than_the_per_tool_one():
    """ANTI-VACUITY, and the reason this exists beside the gate above rather than inside it. If
    the two ever agreed, one of them would be dead weight."""
    per_tool = set(_baseline())
    tools_here = {s.split("::")[0] for s in unreachable_scenarios()}
    assert len(unreachable_scenarios()) > len(per_tool), (
        "the per-scenario scan no longer finds more than the per-tool baseline — re-derive "
        "whether it is still needed"
    )
    assert tools_here, "the scan found nothing at all"


def test_no_NEW_scenario_turn_fails_to_reach_its_own_tool():
    """THE GATE. Shrink-only, like its per-tool sibling."""
    new = sorted(unreachable_scenarios() - _scenario_baseline())
    assert not new, (
        "these scenarios' MEASURED turn cannot reach the tool they test, so the tool will "
        "surface 0/N before a run is spent:\n  " + "\n  ".join(new)
        + "\n\nThis is a DECLARATION gap in almost every case measured so far: widen the tool's "
          "synonyms. Rewriting the prompt is fixing the wrong half unless the prompt genuinely "
          "asks for something else."
    )


def test_a_scenario_that_became_reachable_leaves_the_baseline():
    """Scoped to the DEBT list alone. Applying it to `by_design` would demand the removal of an
    entry whose becoming reachable is the thing we most want to hear about."""
    debt = set(_scenario_contract().get("scenarios") or [])
    stale = sorted(debt - unreachable_scenarios())
    assert not stale, f"no longer unreachable, remove from {SCENARIO_BASELINE.name}: {stale}"


def test_a_BY_DESIGN_turn_has_not_started_reaching_its_tool():
    """🔴 THE INVERTED RULE, and the reason the split had to happen.

    These measured turns are confirmations — "Yes, go ahead and do it." — and a confirmation that
    could name its tool through `answerable_tools` would mean some tool had declared assent itself
    as vocabulary. That is a bug in the declaration, and it would silently make every
    confirmation-turn measurement in this loop mean something different."""
    by_design = _scenario_contract().get("by_design") or {}
    assert by_design, "the by-design category is empty — the split has been undone"
    regressed = sorted(set(by_design) - unreachable_scenarios())
    assert not regressed, (
        "these turns are supposed to be UNABLE to name their tool, and now can — a tool has "
        "declared confirmation vocabulary: " + ", ".join(regressed))


def test_every_OVERRIDE_is_backed_by_a_run_that_called_the_tool():
    """🔴 THE ESCAPE HATCH, HELD SHUT. An override says "the gate is wrong here", which is exactly
    the sentence someone reaches for when the gate is right and inconvenient. So it is not taken on
    trust: the cited raw batch is re-read and the calls RE-COUNTED from the wire records. An
    override whose evidence stops supporting it fails, and one whose file is gone fails."""
    overrides = _scenario_contract().get("overridden_by_live_evidence") or {}
    assert overrides, "the override category is empty — the split has been undone"
    for key, o in sorted(overrides.items()):
        ev = ROOT / o["evidence"]
        assert ev.exists(), f"{key}: evidence file is gone: {o['evidence']}"
        d = json.loads(ev.read_text(encoding="utf-8"))
        runs = d if isinstance(d, list) else d.get("runs", [])
        called = sum(1 for r in runs
                     if o["tool"] in {c.get("toolCallName") for c in r.get("tool_calls", [])
                                      if c.get("type") == "TOOL_CALL_START"})
        assert runs and called, (
            f"{key}: the override claims {o['tool']} was called {o['called']}, but the cited "
            f"batch shows {called} of {len(runs)} — the gate was NOT refuted here"
        )
