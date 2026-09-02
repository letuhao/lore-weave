"""DQ-T88 (a) WITH A CEILING — prior turns' tool results replay, bounded.

OWNER 2026-09-01: "try claude code idea" — replay tool results across turns, in the shape the
Messages API uses, where a result is a content block in the transcript and survives to the next
turn by construction.

🔴 THEN THE OWNER CORRECTED THE BUILD, and the correction is the reason every assertion here is
about a BOUND: "i don't think problem only come from resent or store but the tool return so much
data and it cause context bloated, that why the tool result is not store".

That is causal in the opposite direction to the framing I had. Results are not stored BECAUSE
they are large, so replaying them unbounded relocates the problem into every turn. Measured over
5,182 sessions that made a tool call: median 3,270 bytes, p95 38,369, MAX 890,805 — against 1,759
bytes of everything the author and assistant actually SAID. The replay is ~6x the conversation
and its tail is nearly a megabyte.

So the ceiling is not a refinement of the ruling. It is the only affordable form of it.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.db.tool_call_history import (  # noqa: E402
    REPLAY_RESULT_CAP, REPLAY_SESSION_BUDGET, project_result,
)

ID = "01a04107-5b4a-789c-8b22-30f17c8abb{:02x}"


def _big(n: int = 60) -> dict:
    return {"items": [{"entity_id": ID.format(i), "text": "y" * 200} for i in range(n)]}


def test_a_result_that_FITS_is_untouched():
    """The common case must cost nothing: the per-session MEDIAN is 3,270 bytes across ALL of a
    session's calls, so a typical result is nowhere near the cap."""
    small = {"ok": True, "entity_id": ID.format(0)}
    assert project_result("glossary_get_entity", small) == json.dumps(small)


def test_an_OVERSIZED_result_is_held_to_the_cap():
    """🔴 THE FALSIFIER ON THE CEILING ITSELF, and it caught a real overshoot.

    The first implementation reserved a fixed 240 bytes for its note and appended afterwards,
    which exceeded the cap whenever a result carried many ids — measured at 2,416 bytes against a
    2,048 cap, on an ontology-read shape, which is exactly the payload class that made the cap
    necessary. A ceiling the worst case walks through is not a ceiling.
    """
    out = project_result("glossary_book_ontology_read", _big())
    assert len(json.dumps(_big())) > REPLAY_RESULT_CAP, "the fixture is not actually oversized"
    assert len(out) <= REPLAY_RESULT_CAP, (
        f"projection returned {len(out)} bytes against a cap of {REPLAY_RESULT_CAP} — the caller "
        f"cannot trust the budget arithmetic if the cap does not bind")


def test_the_IDS_survive_the_trim():
    """🔴 WHAT IS PRESERVED IS NOT THE PREFIX. Truncating to the first N bytes keeps the opening
    brace and loses the ids — and an id is the one thing a later turn cannot re-derive. That is
    the entire subject of the fabricated-id work this replay sits beside."""
    out = project_result("glossary_book_ontology_read", _big())
    assert ID.format(0) in out
    assert "id(s) returned" in out
    assert "trimmed to fit" in out, "the model is not told the result was cut"
    assert "Call glossary_book_ontology_read again" in out, "no route to the rest"


def test_a_PATHOLOGICAL_id_count_still_respects_the_cap():
    """More ids than the cap can hold. The ids matter more than the body, so the note wins — but
    the cap must STILL bind, which is the property a naive 'note always wins' would break."""
    many = {"ids": [ID.format(i % 256) for i in range(400)]}
    out = project_result("kg_triage_list", many, cap=200)
    assert len(out) <= 200


def test_the_caps_come_from_the_MEASURED_distribution():
    """Not taste. 2 kB per result leaves a median session (3,270 bytes across all its calls)
    untouched; 16 kB per turn admits the great majority (p95 of a whole session is 38 kB) and
    bounds the 890 kB worst case at roughly 2% of itself."""
    assert REPLAY_RESULT_CAP == 2_048
    assert REPLAY_SESSION_BUDGET == 16_384
    # The budget must admit several capped results, or the ceiling degenerates to "one result".
    assert REPLAY_SESSION_BUDGET // REPLAY_RESULT_CAP >= 8


def test_a_projected_result_is_still_VALID_TEXT_for_a_transcript():
    """It is replayed as a content block, so it must be a string a model can read — not a
    half-closed JSON object presented as if it parsed."""
    out = project_result("tool_list", _big())
    assert isinstance(out, str) and out
    # It must NOT claim to be complete JSON: a trimmed body that still looks parseable is how a
    # consumer downstream starts trusting it.
    assert out.rstrip().endswith("]"), "the trim marker is not the last thing in the block"


def test_the_replay_is_WIRED_and_DEFAULT_OFF():
    """🔴 THE HALF THAT IS EASY TO GET WRONG. A projection helper nobody calls is a mechanism
    that exists and is empty — this loop has found several. And a context change of this size
    shipping ON by default would assert the result of a measurement nobody has run.

    The platform's own precedent is DQ-T90: a flag, an A/B against the shipped path, adoption
    only if it wins. arm (b) was adopted that way and its numbers are recorded at the flag.
    """
    from app.config import settings

    assert settings.replay_prior_tool_results is False, (
        "the replay is ON by default — the owner's correction says results are not stored "
        "BECAUSE they are large, so turning this on without an A/B asserts the trade is worth "
        "making when nobody has measured it")

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
    assert "settings.replay_prior_tool_results" in src, "the flag is declared and never read"
    assert "results_for_replay" in src, "the projection helper is never called"
    # 🔴 RE-AIMED 2026-09-02, AND THIS ASSERTION USED TO ENFORCE THE DEFECT. It required
    # `not _continuing` in the condition, on the reasoning that "the server already holds that
    # history there". That is true of the TRANSCRIPT and false of the TOOL RESULTS — and the
    # results are the whole subject. On a stateful chain the provider holds what it was sent,
    # and what it was sent never contained the results either, because a result lives on the
    # assistant row rather than as its own turn. So the exclusion removed exactly the case the
    # feature exists for.
    #
    # MEASURED: the 2026-09-02 A/B ran both arms with the flag verified True inside the running
    # service and logged ZERO replays in either — 5/5 vs 5/5, a result that says nothing because
    # the mechanism never executed. This assertion is what had protected the cause.
    i = src.index("settings.replay_prior_tool_results")
    assert "not _continuing" not in src[i:i + 120], (
        "the replay is excluded from stateful CONTINUE passes again — that is exactly the case "
        "it exists for, and excluding it makes the feature unobservable rather than off")
