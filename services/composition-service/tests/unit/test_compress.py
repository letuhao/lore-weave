"""S2 — compress primitive tests (degrade-safe; spoiler-safe by construction)."""

from __future__ import annotations

from types import SimpleNamespace

from app.engine import compress as C


def test_cap_recent_prose_keeps_most_recent_within_budget():
    # D-COMP-COMPRESS-INPUT-CAP: keep the newest paragraphs whose total ≤ cap.
    prose = ["A" * 100, "B" * 100, "C" * 100, "D" * 100]  # 400 chars
    assert C.cap_recent_prose(prose, 1000) == prose          # under budget → unchanged
    assert C.cap_recent_prose(prose, 250) == ["C" * 100, "D" * 100]  # newest two fit
    # always keeps ≥1 even if the newest alone exceeds the cap
    assert C.cap_recent_prose(["X" * 500], 100) == ["X" * 500]


async def test_compress_caps_input_to_recent():
    # the older prose is bounded before the LLM call (newest kept).
    llm = FakeLLM(content="summary")
    await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                     prose=["old" * 100, "mid" * 100, "new" * 100], timeline=[],
                     max_input_chars=350)
    user_msg = llm.last_input["messages"][1]["content"]
    assert "new" in user_msg and "old" not in user_msg  # oldest elided


class FakeLLM:
    def __init__(self, content=None, status="completed", raises=False):
        self._content, self._status, self._raises = content, status, raises
        self.calls = 0
        self.last_input = None
        # D-LEDGER-DROPS-CAST-ATTRIBUTES — compress now makes TWO calls (ledger +
        # a mechanical cast extraction), so a single `last_input` cannot tell them apart.
        self.inputs: list = []

    async def submit_and_wait(self, **kw):
        from loreweave_llm.errors import LLMError
        self.calls += 1
        self.last_input = kw["input"]
        self.inputs.append(kw["input"])
        if self._raises:
            raise LLMError("gateway down")
        res = {"messages": [{"content": self._content}]} if self._content is not None else {}
        return SimpleNamespace(status=self._status, result=res)


def test_compress_prompt_is_a_state_ledger_not_a_generic_recap():
    # Root-cause fix (2026-07-26 chapter-quality investigation): the ch5 continuity
    # violations (Silas's dissolution state flipped; a character crossed an "erased
    # void") happened because the running summary was a GENERIC recap that blurred
    # each character's evolving physical/status state. The prompt must instruct an
    # explicit per-entity STATE LEDGER — condition/transformation + location + what
    # changed in the world — so the drafter cannot re-invent it.
    system, _ = C.build_compress_messages(
        prose=["Silas was dissolving into a rain-blurred sketch."],
        timeline=[], plan="", source_language="auto",
    )
    s = system.lower()
    assert "condition" in s          # per-character physical/mental state
    assert "transformation" in s or "status" in s   # ongoing change (the Silas class)
    assert "location" in s or "where" in s          # who/what is where (the void class)
    # continuity intent is explicit, and the anti-hallucination guard is preserved
    assert "ledger" in s or "state record" in s
    assert "not invent" in s or "do not invent" in s


async def test_compress_returns_summary():
    llm = FakeLLM(content="Kael reached the keep; Bryn distrusts him.")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["para one", "para two"], timeline=["Kael arrives"], plan="retake the keep")
    # D-LEDGER-DROPS-CAST-ATTRIBUTES: the ledger is now PRECEDED by a mechanically-extracted
    # cast block when the extraction yields rows. This stub returns prose for BOTH calls, so
    # nothing parses as people and the output is the ledger alone — which is exactly the
    # degrade path: no cast rows ⇒ ledger unchanged.
    assert out == "Kael reached the keep; Bryn distrusts him."
    # all three inputs reached the COMPRESS prompt (prose + timeline + plan). `last_input` is
    # now the cast-state call, so this reads the first recorded one.
    user = llm.inputs[0]["messages"][1]["content"]
    assert "para one" in user and "Kael arrives" in user and "retake the keep" in user


async def test_the_cast_block_is_prepended_and_carries_pronouns():
    """The whole point: the summariser no longer decides whether a character's pronoun
    survives. Measured twice on real runs — a ledger recording the character scene 2 had just
    introduced as `Condition: Unknown`, and a later one omitting the Scribe entirely."""
    llm = FakeLLM(content="LEDGER BODY")
    llm._content = None  # per-call scripting below
    calls = {"n": 0}

    async def submit(**kw):
        calls["n"] += 1
        llm.inputs.append(kw["input"])
        body = ('{"people": [{"who": "The Scribe", "pronoun": "she", "role": "anchor"}, '
                '{"who": "she", "pronoun": "she", "role": ""}]}') if calls["n"] == 2             else "LEDGER BODY"
        return SimpleNamespace(status="completed", result={"messages": [{"content": body}]})

    llm.submit_and_wait = submit
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["The Scribe did not move."], timeline=[], plan="")
    assert out.startswith("WHO IS IN THIS"), out[:80]
    assert "The Scribe — she — anchor" in out
    assert out.rstrip().endswith("LEDGER BODY")
    assert "- she" not in out, "a bare pronoun row names nobody"


async def test_a_failed_cast_extraction_still_returns_the_ledger():
    """Degrade-safe: losing the mechanical guarantee must not lose the summary."""
    from loreweave_llm.errors import LLMError

    llm = FakeLLM(content="LEDGER BODY")
    calls = {"n": 0}

    async def submit(**kw):
        calls["n"] += 1
        llm.inputs.append(kw["input"])
        if calls["n"] == 2:
            raise LLMError("gateway down")
        return SimpleNamespace(status="completed",
                               result={"messages": [{"content": "LEDGER BODY"}]})

    llm.submit_and_wait = submit
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["x"], timeline=[], plan="")
    assert out == "LEDGER BODY"


async def test_compress_llm_error_returns_empty_not_raise():
    llm = FakeLLM(raises=True)
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["x"], timeline=[], plan="")
    assert out == ""  # degrade → caller keeps raw prose


async def test_compress_non_completed_returns_empty():
    llm = FakeLLM(content="ignored", status="failed")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=["x"], timeline=[], plan="")
    assert out == ""


async def test_compress_empty_inputs_is_noop_no_llm_call():
    llm = FakeLLM(content="should not run")
    out = await C.compress(llm, user_id="u", model_source="user_model", model_ref="m",
                           prose=[], timeline=[], plan="")
    assert out == "" and llm.calls == 0  # nothing to compress → no LLM call
