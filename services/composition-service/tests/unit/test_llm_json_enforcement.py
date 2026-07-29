"""Schema enforcement — the primitive, and the drift it is most likely to grow.

Enforcing a closed set at the DECODER (`response_format` → provider-registry → llama.cpp's grammar
layer) is only an improvement while the enum in the schema and the set the parser filters on are the
SAME set. The moment someone adds a world kind, a verdict, or a motif kind and updates only one of
them, the grammar silently forbids a value the parser would happily have accepted — and the failure
looks like the model refusing to produce it.

That is a worse bug than the one enforcement fixes, because it is invisible from the outside. So the
sync is machine-checked here rather than trusted.

Measured basis for doing any of this at all (`docs/specs/2026-07-28-poc-material-read.md` §6d):
parse failures 2 → 0, quality unchanged, fixed-seed determinism 18/18, and a ranking arm that had
been dismissed TWICE as a model failure recovered to 3/4 once the output shape was enforced.
"""
from __future__ import annotations

import pytest

from app.engine import llm_json


# ── the closed sets must not drift from the schemas that enforce them ────────────────────────────

def test_world_plan_enum_matches_WORLD_KINDS():
    from app.engine.world_plan import _WORLD_SCHEMA, WORLD_KINDS

    enum = _WORLD_SCHEMA["properties"]["items"]["items"]["properties"]["kind"]["enum"]
    assert sorted(enum) == sorted(WORLD_KINDS), (
        "the grammar and the parser disagree about world kinds — the grammar would forbid a kind "
        "the parser accepts, and it would look like the model refusing to say it"
    )


def test_promise_audit_enum_matches_the_verdict_set():
    from app.engine.promise_audit import _AUDIT_SCHEMA, _VERDICTS

    enum = _AUDIT_SCHEMA["properties"]["promises"]["items"]["properties"]["verdict"]["enum"]
    assert sorted(enum) == sorted(_VERDICTS)


def test_motif_mine_enums_match_their_valid_sets():
    from app.engine.motif_mine import _ABSTRACTION_SCHEMA, _VALID_ACTANTS, _VALID_KINDS

    props = _ABSTRACTION_SCHEMA["properties"]
    assert sorted(props["kind"]["enum"]) == sorted(_VALID_KINDS)
    assert sorted(props["actants"]["items"]["enum"]) == sorted(_VALID_ACTANTS)


def test_the_beat_schema_carries_the_BOOKS_OWN_vocabulary():
    """`beat_role` has no global vocabulary — the book's structure template is it. A hardcoded enum
    here would be the exact fixture-binding this whole line of work is undoing."""
    from app.engine.plan import chapter_map_schema

    schema = chapter_map_schema({"hook", "midpoint", "climax"}, 4)
    beat = schema["properties"]["chapters"]["items"]["properties"]["beat"]
    assert sorted(beat["enum"]) == ["climax", "hook", "midpoint"]
    assert schema["properties"]["chapters"]["maxItems"] == 4


def test_an_EMPTY_beat_vocabulary_yields_no_schema_at_all():
    """A closed set with nothing in it is not a constraint, it is an unsatisfiable grammar — the
    model would be forbidden from emitting ANY beat. The empty-vocabulary case already has its own
    loud warning in `parse_chapter_map`; this must degrade to free-form, not to a wall."""
    from app.engine.plan import chapter_map_schema

    assert chapter_map_schema(set(), 4) is None


# ── the primitive ────────────────────────────────────────────────────────────────────────────────

def test_enum_of_keeps_integers_INTEGER():
    """A `tension` enum of 1..5 emitted as the string "3" would still need coercion — which is the
    post-hoc repair this change exists to remove."""
    assert llm_json.enum_of([1, 2, 3]) == {"type": "integer", "enum": [1, 2, 3]}
    assert llm_json.enum_of(["hook", "climax"]) == {"type": "string", "enum": ["hook", "climax"]}
    # bools are ints in Python and would silently become an integer enum
    assert llm_json.enum_of([True, False])["type"] == "string"


class _Job:
    def __init__(self, text="{}"):
        self.status = "completed"
        self.result = {"messages": [{"content": text}]}


class _LLM:
    """Records every `response_format` it was handed, so the fallback is asserted on the CALLS."""

    def __init__(self, *, reject_schema=False, status="completed"):
        self.formats: list = []
        self._reject = reject_schema
        self._status = status

    async def submit_and_wait(self, **kw):
        fmt = kw["input"]["response_format"]
        self.formats.append(fmt)
        if self._reject and fmt.get("type") == "json_schema":
            from loreweave_llm.errors import LLMError
            raise LLMError("400 unsupported response_format")
        job = _Job('{"ok": true}')
        job.status = self._status
        return job


_ARGS = dict(user_id="u", model_source="user_model", model_ref="m",
             messages=[{"role": "user", "content": "hi"}], max_tokens=100,
             job_meta={"extractor": "t"})


@pytest.mark.asyncio
async def test_the_schema_is_sent_when_the_provider_takes_it():
    llm = _LLM()
    out = await llm_json.call_json(llm, schema={"type": "object"}, schema_name="x", **_ARGS)
    assert out == '{"ok": true}'
    assert llm.formats == [{"type": "json_schema",
                            "json_schema": {"name": "x", "schema": {"type": "object"}}}]


@pytest.mark.asyncio
async def test_a_provider_that_REJECTS_the_schema_degrades_to_todays_behaviour():
    """`response_format` support is not a platform requirement. A 400 here must cost the constraint,
    never the call — the worst case has to equal the status quo, or this change is a regression for
    anyone on a provider that does not implement it."""
    llm = _LLM(reject_schema=True)
    out = await llm_json.call_json(llm, schema={"type": "object"}, **_ARGS)
    assert out == '{"ok": true}'
    assert [f["type"] for f in llm.formats] == ["json_schema", "text"]


@pytest.mark.asyncio
async def test_no_schema_means_one_plain_call_not_two():
    llm = _LLM()
    await llm_json.call_json(llm, **_ARGS)
    assert [f["type"] for f in llm.formats] == ["text"]


@pytest.mark.asyncio
async def test_a_non_completed_job_returns_None_rather_than_raising():
    """Every caller here already degrades on a failed job — the planning passes are individually
    skippable. Raising would turn a degradation into an outage."""
    llm = _LLM(status="failed")
    assert await llm_json.call_json(llm, **_ARGS) is None


@pytest.mark.asyncio
async def test_a_hard_LLM_error_on_the_fallback_returns_None():
    from loreweave_llm.errors import LLMError

    class _Dead:
        async def submit_and_wait(self, **kw):
            raise LLMError("connection refused")

    assert await llm_json.call_json(_Dead(), schema={"type": "object"}, **_ARGS) is None


# ── the sites that must NEVER be constrained ─────────────────────────────────────────────────────

def test_the_PROSE_paths_are_left_unconstrained():
    """`compress` and `stitch` return narrative. Wrapping generated prose in a JSON grammar would
    constrain the writing itself, which is the opposite of the point — pinned so a later sweep
    cannot "finish the job" by including them."""
    import inspect

    from app.engine import compress, stitch

    for mod in (compress, stitch):
        src = inspect.getsource(mod)
        assert "json_schema" not in src, f"{mod.__name__} generates prose — it must stay free-form"
