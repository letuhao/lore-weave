"""D-A-NEVER-APPROVE-SCENARIO-MEASURES-REACH-BEFORE-ANY-CARD.

    THE INVARIANT. "called 0/N" is a fact about the tool only if the turn reached it.

A scenario with approve=None ends at the FIRST Tier-A card, whatever raised it. When that card
belongs to some OTHER tool, the tool under test never gets its turn — and the batch records
`called 0/5` as though the model had considered and rejected it.

THE PROOF THAT THOSE ARE DIFFERENT SENTENCES: glossary_create_evidence read "surfaced 5/5,
called 0/5, suspended 5/5" and looked like a model that would not use it. Once the harness was
allowed to click, the tool was called 4/5 and failed on its ACTUAL defect — a required id with
no supplier. The first reading would have sent the fix at the model.

MEASURED over every raw record on disk 2026-08-27: 24 scenario-batches recorded `called 0/N`
where EVERY run ended on a card belonging to a different tool. The blockers are a short list —
glossary_propose_entities 21, kg_add_nodes 20, book_chapter_save_draft 20, kg_project_create
18, glossary_adopt_standards 16.

THE RECORD ALREADY NAMED THE OWNER. `pending_approval.tool` is present on all 482 suspended
runs on disk; nothing read it. That is the same shape as the two sibling fixes this week — the
mechanism existed and was merely unread.

WHAT THIS DOES NOT SAY. It does not make approve=None wrong: a never-approve arm is the only
way to see the Tier-A gate work, and it is one of the two user states this loop must run in.
And it does not license approving on a READ-intent scenario — that tool_load's read-only
question raises a kg_project_create card on 5 of 5 runs is a finding about the product, not an
obstacle to clear.
"""
from __future__ import annotations

import collections
import io
import json
import pathlib
import sys
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SC = [{"id": "s", "expect_tool": "tool_load"}]
NEEDLE = "NOT REACHED, NOT DECLINED"


def _render(runs, sc=None) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fr.report(runs, sc or SC, len(runs))
    return buf.getvalue()


def _run(called=(), card=None, **kw):
    r = {"scenario": "s", "surfaces": [], "results": [], "store_diff": {},
         "tool_calls": [{"type": "TOOL_CALL_START", "toolCallName": c} for c in called], **kw}
    if card:
        r["pending_approval"] = {"tool": card, "kind": "tool_approval", "tier": "A"}
    return r


def test_every_run_stopped_by_ANOTHER_tools_card_is_annotated():
    out = _render([_run(called=("kg_project_create",), card="kg_project_create")
                   for _ in range(5)])
    assert NEEDLE in out
    assert "kg_project_create (5)" in out
    assert "not that the model rejected it" in out


def test_it_names_EVERY_blocker_not_just_the_first():
    """The recorded instances are mixed — composition_entity_override_edit was stopped by
    glossary_entity_set_attributes on 3 runs and kg_project_create on 2. Naming one would send
    the reader at the wrong tool for the other two."""
    runs = [_run(card="glossary_entity_set_attributes") for _ in range(3)]
    runs += [_run(card="kg_project_create") for _ in range(2)]
    out = _render(runs)
    assert "glossary_entity_set_attributes (3)" in out and "kg_project_create (2)" in out


def test_a_card_belonging_to_the_TOOL_ITSELF_is_not_this_shape():
    """PRECISION. If the tool under test raised the card, the turn REACHED it — that is the
    store bar's problem (D-A-TIER-A-SCENARIO-THAT-NEVER-APPROVES...), not this one."""
    out = _render([_run(called=("tool_load",), card="tool_load") for _ in range(5)])
    assert NEEDLE not in out


def test_its_OWN_card_with_no_recorded_call_is_still_not_this_shape():
    """🔴 THIS CASE ISOLATES THE `!= want` CLAUSE, AND THE FIRST VERSION DID NOT. Dropping it
    left all nine guards green, because the case above is already excluded by `called 0`.

    The shape is real, not hypothetical: a call deferred at the gate is recorded as an APPROVAL
    ENVELOPE, and `called_names` reads TOOL_CALL_START — so a tool can sit pending on its OWN
    card with no call recorded. The turn REACHED it; saying "not reached" would be the new wrong
    answer, and it is exactly the misreading this annotation exists to prevent, inverted."""
    out = _render([_run(card="tool_load") for _ in range(5)])
    assert NEEDLE not in out, (
        "the tool's OWN pending card was counted as another tool blocking it"
    )


def test_one_run_that_ended_WITHOUT_a_card_silences_it():
    """The boundary. A run that finished cleanly and still did not call the tool IS evidence
    the model passed it over, however weak — `called 0/N` is then partly informative and must
    not be explained away."""
    runs = [_run(card="kg_project_create") for _ in range(4)]
    runs.append(_run())
    assert NEEDLE not in _render(runs)


def test_a_tool_that_WAS_called_is_not_annotated():
    runs = [_run(called=("tool_load",), card="kg_project_create") for _ in range(5)]
    assert NEEDLE not in _render(runs)


def test_the_SUSPENDED_line_is_still_printed():
    out = _render([_run(card="kg_project_create") for _ in range(5)])
    assert "left SUSPENDED on a Tier-A approval card in 5/5" in out


def test_the_RECORDED_instance_renders_it():
    """ANTI-VACUITY against the real corpus — the tool_load batch the row was written from."""
    raw = ROOT / "docs" / "eval" / "toolloop"
    hits = []
    for f in sorted(raw.rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        rs = [r for r in d if isinstance(r, dict) and r.get("scenario") == "tool-load"]
        if len(rs) >= 3 and all("tool_load" not in fr.called_names(r) for r in rs):
            hits.append(rs)
    if not hits:
        import pytest
        pytest.skip("no recorded tool-load batch of that shape")
    out = _render(hits[0], [{"id": "tool-load", "expect_tool": "tool_load"}])
    assert NEEDLE in out and "kg_project_create" in out


def test_the_population_is_worth_a_guard():
    """ANTI-VACUITY on the size, under the rule that shipped."""
    scen = {}
    for f in (ROOT / "scripts" / "toolloop").glob("scenarios-*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            scen.setdefault(s["id"], s.get("expect_tool"))
    by = collections.defaultdict(list)
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if isinstance(r, dict) and r.get("scenario"):
                by[(f.name, r["scenario"])].append(r)
    hit = 0
    for (_, sid), rs in by.items():
        want = scen.get(sid)
        if not want or len(rs) < 3:
            continue
        if any(want in fr.called_names(r) for r in rs):
            continue
        blocked = [r for r in rs if isinstance(r.get("pending_approval"), dict)
                   and (r["pending_approval"].get("tool") or "") != want]
        if len(blocked) == len(rs):
            hit += 1
    assert hit >= 10, f"only {hit} batches on disk match the shipped rule — re-derive the row"


def test_the_owner_field_is_actually_recorded():
    """The whole fix rests on `pending_approval.tool`. If the harness stopped writing it, the
    annotation would silently never fire again."""
    seen = 0
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            pa = r.get("pending_approval") if isinstance(r, dict) else None
            if isinstance(pa, dict):
                assert "tool" in pa, f"a suspended run with no card owner: {f.name}"
                seen += 1
    assert seen >= 100, f"only {seen} suspended runs on disk — re-derive"
