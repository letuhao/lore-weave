"""WS-3 (C6) — mode → capability binding: the pinned rail, the seed, the skills.

The bug this mechanism exists to kill (measured, S06 2026-07-11): the agent had the
right workflow ADVERTISED and a directive telling it to load one, and still improvised —
because the user never ASKED for the job, they only ASSENTED to the agent's own offer
("yeah do it"). A pin puts the rail IN CONTEXT, removing the recognition step entirely.

So the tests here assert the properties that make a pin real:
  - the rail's tools are actually ADVERTISED (a rail naming invisible tools is a silent
    no-op — the worst shape, because it looks like it should work),
  - the rail text names the steps IN ORDER and carries the assent language,
  - and the whole thing DEGRADES to pre-WS-3 behavior when the registry is down.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.client.registry_workflows_client import WorkflowsClient
from app.services.skill_registry import resolve_skills_to_inject
from app.services.tool_surface import (
    SessionToolPins,
    _tool_tokens,
    budget_rail_tools,
    discovery_seed_for_surface,
)
from app.services.workflow_runner import (
    NOTES_CHAR_CAP,
    TOTAL_CHAR_CAP,
    pinned_rail_block,
)

WF = {
    "slug": "vision-to-book",
    "title": "Turn a story idea into a real book foundation",
    "description": "Build the world, cast, connections and plan.",
    "tier": "system",
    "surfaces": ["book", "editor"],
    "inputs": {},
    "steps": [
        {"id": "see-standards", "tool": "glossary_list_system_standards", "gate": "none"},
        {"id": "adopt", "tool": "glossary_adopt_standards", "gate": "none"},
        {"id": "apply", "tool": "glossary_confirm_action", "gate": "confirm"},
        {"id": "arc-plan", "tool": "plan_propose_spec", "gate": "none", "async_job": True},
    ],
    "notes_md": "Use this when the user is building their book. Speak plainly.",
}


def _catalog(*names: str, size: int = 200) -> list[dict]:
    return [
        {"type": "function", "function": {"name": n, "description": "x" * size}}
        for n in names
    ]


def _pins(**kw) -> SessionToolPins:
    base = dict(
        effective_enabled=[], effective_skills=[], curated_mode=False,
        activation_state={"activated_tools": [], "dirty": False}, pinned_legacy=[],
    )
    base.update(kw)
    return SessionToolPins(**base)


# ── the rail block ────────────────────────────────────────────────────────────

def test_pinned_rail_renders_steps_in_order_and_returns_step_tools():
    text, tools = pinned_rail_block([WF], ["vision-to-book"])
    assert text is not None
    # Step ORDER is the whole point — the S01 failure was the model reconstructing the
    # sequence wrong (entities before categories existed).
    assert text.index("see-standards") < text.index("adopt") < text.index("arc-plan")
    assert tools == [
        "glossary_list_system_standards", "glossary_adopt_standards",
        "glossary_confirm_action", "plan_propose_spec",
    ]
    # gates + async must survive into the rail the agent reads
    assert "confirm" in text
    assert "background job" in text


def test_pinned_rail_carries_the_assent_language():
    # The measured S06 root cause: the user says only "yeah do it". If the rail does not
    # tell the agent that an assent to its OWN offer counts, the pin does not fix the bug
    # it exists to fix.
    text, _ = pinned_rail_block([WF], ["vision-to-book"])
    low = text.lower()
    assert "agrees" in low or "agree" in low
    assert "do it" in low


def test_pinned_rail_skips_a_slug_that_is_not_visible():
    text, tools = pinned_rail_block([WF], ["no-such-workflow"])
    assert text is None and tools == []


def test_pinned_rail_skips_missing_but_keeps_the_visible_one():
    text, tools = pinned_rail_block([WF], ["no-such-workflow", "vision-to-book"])
    assert text is not None and "vision-to-book" in text
    assert "glossary_adopt_standards" in tools


def test_pinned_rail_caps_the_notes_prose():
    # An ALWAYS-ON block needs a ceiling (Context Budget Law).
    big = dict(WF, notes_md="n" * 9000)
    text, _ = pinned_rail_block([big], ["vision-to-book"], notes_char_cap=100)
    assert "n" * 101 not in text
    assert "…" in text


def test_truncating_a_rail_is_LOUD(caplog):
    # Measured 2026-07-11: the flagship rail's notes were 3218 chars against a 3000 cap, so the tail was
    # dropped — and the tail was the SPEAK-PLAINLY block, i.e. the exact rules that stop
    # the agent leaking the machinery to the user. The leak they were written to fix
    # therefore survived, and the truncation said NOTHING. A cap that silently eats the
    # end of a prompt is worse than no cap: the block still LOOKS complete.
    big = dict(WF, notes_md="n" * 9000)
    with caplog.at_level(logging.WARNING):
        pinned_rail_block([big], ["vision-to-book"], notes_char_cap=100)
    assert any("truncated" in r.message for r in caplog.records), (
        "a truncated rail must WARN — a silent cut removes the rail's vocabulary rules"
    )


def test_the_real_w6_notes_would_not_be_truncated():
    # The authored rail must fit the ceiling with room to spare. The registry side asserts
    # the same thing on the seed (migrate_lint_test.go) — this is the consumer half, so the
    # two constants cannot drift apart unnoticed.
    assert NOTES_CHAR_CAP >= 5000


def test_pinned_rail_forbids_leaking_its_own_name_to_the_user():
    # Measured on the first WS-3 live run: the agent told the novelist "we can use the
    # vision-to-book workflow" (×6). The rail is the agent's PRIVATE recipe — putting it
    # in context must not put it in the user's face. This is the jargon-leak class §1
    # calls an automatic scenario failure.
    text, _ = pinned_rail_block([WF], ["vision-to-book"])
    low = text.lower()
    assert "private" in low
    assert "never mention" in low
    assert "workflow" in low  # ...specifically, as a word it must NOT say to the user


def test_pinned_rail_says_call_the_tools_not_narrate_them():
    # Same run: the agent DESCRIBED the steps ("first I'll look at the categories, then
    # I'll…") instead of calling them, so 17 turns produced one adopted category set and
    # nothing else. Narration is not execution.
    text, _ = pinned_rail_block([WF], ["vision-to-book"])
    low = text.lower()
    assert "do not narrate" in low
    assert "call" in low


# ── the tools actually reach the wire ─────────────────────────────────────────

def test_pinned_step_tools_are_advertised_in_auto_mode():
    # Without this, the agent reads a recipe naming tools it cannot call.
    cat = _catalog(
        "glossary_list_system_standards", "glossary_adopt_standards",
        "glossary_confirm_action", "plan_propose_spec", "unrelated_tool",
    )
    names = discovery_seed_for_surface(
        cat, pins=_pins(), editor=False, book_scoped=True,
        pinned_step_tools=[
            "glossary_list_system_standards", "glossary_adopt_standards",
            "glossary_confirm_action", "plan_propose_spec",
        ],
    )
    assert {"glossary_adopt_standards", "glossary_confirm_action", "plan_propose_spec"} <= names


def test_pinned_step_tools_are_advertised_in_curated_mode_too():
    # A curated session (the user pinned a tool) must still get the rail's tools — the
    # binding is the platform's decision, not one of the user's ad-hoc pins.
    cat = _catalog("glossary_adopt_standards", "plan_propose_spec", "some_pinned_tool")
    names = discovery_seed_for_surface(
        cat,
        pins=_pins(effective_enabled=["some_pinned_tool"], curated_mode=True),
        editor=False, book_scoped=True,
        pinned_step_tools=["glossary_adopt_standards", "plan_propose_spec"],
    )
    assert {"glossary_adopt_standards", "plan_propose_spec"} <= names
    assert "some_pinned_tool" in names


def test_rail_budget_keeps_step_order_not_reads_first():
    # budget_names_by_tokens orders reads first — for a RAIL that would drop exactly the
    # write steps that persist anything. The rail budget must honor the author's order.
    cat = (
        _catalog("glossary_list_system_standards", size=100)   # a READ, step 1
        + _catalog("glossary_adopt_standards", size=100)       # a WRITE, step 2
        + _catalog("glossary_list_more_stuff", size=100)       # a READ, step 3
    )
    per = _tool_tokens(cat[0])
    kept, dropped = budget_rail_tools(
        cat,
        ["glossary_list_system_standards", "glossary_adopt_standards", "glossary_list_more_stuff"],
        token_budget=int(per * 2.5),  # room for exactly 2 of the 3
    )
    assert "glossary_adopt_standards" in kept, "the step-2 WRITE must not lose to a later read"
    assert dropped == ["glossary_list_more_stuff"]


def test_rail_budget_reports_drops():
    cat = _catalog("a_tool", "b_tool", size=4000)
    kept, dropped = budget_rail_tools(cat, ["a_tool", "b_tool"], token_budget=10)
    assert kept == {"a_tool"}          # at least the first step survives
    assert dropped == ["b_tool"]       # and the loss is REPORTED, never silent


def test_binding_categories_union_into_the_hot_seed():
    cat = _catalog("translation_start_job", "glossary_search")
    without = discovery_seed_for_surface(cat, pins=_pins(), editor=False, book_scoped=True)
    assert "translation_start_job" not in without
    with_cat = discovery_seed_for_surface(
        cat, pins=_pins(), editor=False, book_scoped=True,
        binding_categories=["translation"],
    )
    assert "translation_start_job" in with_cat


def test_a_sync_tool_is_not_mislabelled_async_when_the_step_says_so():
    # Measured 2026-07-11 (the S06 stall): the flagship rail's capture-cast step calls
    # glossary_extract_entities_from_doc, whose NAME matches the async heuristic
    # ("extract_entities") — so the rail told the agent "background job, watch it before
    # continuing" for a tool that returns synchronously. It stalled waiting for a job that
    # never existed, and the cast was never saved. An AUTHORED async_job must win over the
    # name heuristic.
    wf = dict(WF, steps=[
        {"id": "capture-cast", "tool": "glossary_extract_entities_from_doc",
         "gate": "none", "async_job": False},
    ])
    text, _ = pinned_rail_block([wf], ["vision-to-book"])
    assert "background job" not in text


def test_the_name_heuristic_still_fires_without_an_authored_flag():
    # Negative control — the fix above must not disable async honesty generally.
    wf = dict(WF, steps=[
        {"id": "capture-cast", "tool": "glossary_extract_entities_from_doc", "gate": "none"},
    ])
    text, _ = pinned_rail_block([wf], ["vision-to-book"])
    assert "background job" in text


def test_the_catalog_async_flag_reaches_a_PINNED_rail():
    # workflow_load passes the catalog's _meta.async set; the pin must too, or a pinned
    # rail and a loaded rail disagree about which steps start a job — the pin/load drift
    # that reusing workflow_load_result was supposed to make impossible.
    wf = dict(WF, steps=[{"id": "s", "tool": "some_quiet_tool", "gate": "none"}])
    plain, _ = pinned_rail_block([wf], ["vision-to-book"])
    assert "background job" not in plain
    flagged, _ = pinned_rail_block([wf], ["vision-to-book"], frozenset({"some_quiet_tool"}))
    assert "background job" in flagged


def test_the_pinned_block_has_a_TOTAL_ceiling_not_just_a_per_rail_one():
    # A binding may pin up to 32 workflows; notes_char_cap bounds ONE rail's prose, so
    # without a block-level ceiling the always-on block is unbounded.
    many = [dict(WF, slug=f"wf-{i}", notes_md="n" * 4000) for i in range(20)]
    text, _ = pinned_rail_block(many, [w["slug"] for w in many])
    assert len(text) < TOTAL_CHAR_CAP + 8000, "the pinned block must stop at its total ceiling"


def test_a_resumed_turn_still_advertises_the_pinned_rails_tools():
    """The HIGH bug: the rail's TEXT survives a confirm-gate suspend for free (it lives in
    the system message inside `working`), but its TOOLS did not — the resume re-derives the
    tool surface from scratch and has no book_id to re-fetch the binding with. So the
    resumed turn read an ordered recipe naming tools it could not call. the flagship rail's FIRST confirm
    gate is step 3 of 12, so the flagship rail broke at its very first gate.

    The fix carries `pinned_step_tools` on the SuspendedRun; this asserts the seam that
    consumes it — a resume-shaped seed call (which passes no binding) still advertises them.
    """
    cat = _catalog("glossary_adopt_standards", "glossary_confirm_action", "plan_propose_spec")
    resumed = discovery_seed_for_surface(
        cat,
        pins=_pins(),
        editor=True, book_scoped=True, studio=True,   # the resume superset
        permission_mode="write",
        pinned_step_tools=["glossary_adopt_standards", "glossary_confirm_action", "plan_propose_spec"],
    )
    assert {"glossary_adopt_standards", "glossary_confirm_action", "plan_propose_spec"} <= resumed


def test_a_resume_with_no_pin_is_unchanged():
    # A pre-WS-3 suspended row has NULL here; it must behave exactly as before.
    cat = _catalog("glossary_search")
    before = discovery_seed_for_surface(cat, pins=_pins(), editor=True, book_scoped=True, studio=True)
    after = discovery_seed_for_surface(
        cat, pins=_pins(), editor=True, book_scoped=True, studio=True, pinned_step_tools=None,
    )
    assert before == after


# ── skills ────────────────────────────────────────────────────────────────────

def _skills(**kw) -> list[str]:
    base = dict(
        enabled_skills=[], stream_format="agui", disable_tools=False,
        tool_calling_enabled=True, editor=False, book_scoped=True, admin=False,
    )
    base.update(kw)
    return resolve_skills_to_inject(**base)


def test_binding_skills_are_additive():
    base = _skills()
    out = _skills(binding_skills=["plan_forge"])
    assert set(base) <= set(out), "a binding may only ADD — never remove a static default"
    assert "plan_forge" in out


def test_binding_skills_are_surface_filtered():
    # plan_forge is not visible on the plain chat surface; a binding must not smuggle it
    # in (a skill whose tools aren't hot there is a prompt pointing at nothing).
    out = _skills(book_scoped=False, binding_skills=["plan_forge"])
    assert "plan_forge" not in out


def test_no_binding_is_byte_identical_to_before():
    assert _skills(binding_skills=None) == _skills()


# ── degrade ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_client_parses_the_binding():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("mode") == "write"
        return httpx.Response(200, json={
            "catalog_version": 1,
            "workflows": [WF],
            "mode_binding": {
                "mode": "write",
                "inject_skills": ["plan_forge", ""],
                "inject_workflows": ["vision-to-book"],
                "seed_tool_categories": [],
                "disable_workflows": [],
            },
        })

    c = WorkflowsClient("http://reg", "tok", transport=httpx.MockTransport(handler))
    got = await c.get_workflows("u1", book_id="b1", surface="book", mode="write")
    assert got.mode_binding is not None
    assert got.mode_binding.inject_workflows == ["vision-to-book"]
    assert got.mode_binding.inject_skills == ["plan_forge"]  # the blank is dropped
    await c.aclose()


@pytest.mark.asyncio
async def test_registry_down_means_no_binding_not_a_crash():
    # Degrade is the contract: a registry outage must leave the turn exactly as it was
    # before WS-3 (no pin, no binding skills), never raise into the chat turn.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("registry down")

    c = WorkflowsClient("http://reg", "tok", transport=httpx.MockTransport(handler))
    got = await c.get_workflows("u1", mode="write")
    assert got.workflows == [] and got.mode_binding is None
    await c.aclose()


@pytest.mark.asyncio
async def test_absent_binding_field_is_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"catalog_version": 1, "workflows": [WF]})

    c = WorkflowsClient("http://reg", "tok", transport=httpx.MockTransport(handler))
    got = await c.get_workflows("u1", mode="write")
    assert got.mode_binding is None and len(got.workflows) == 1
    await c.aclose()


@pytest.mark.asyncio
async def test_an_all_empty_binding_is_treated_as_no_binding():
    # An empty record must not flip any behavior on — otherwise seeding a blank row
    # would silently change every turn of that mode.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "catalog_version": 1, "workflows": [],
            "mode_binding": {
                "mode": "ask", "inject_skills": [], "inject_workflows": [],
                "seed_tool_categories": [], "disable_workflows": [],
            },
        })

    c = WorkflowsClient("http://reg", "tok", transport=httpx.MockTransport(handler))
    got = await c.get_workflows("u1", mode="ask")
    assert got.mode_binding is None
    await c.aclose()


# ── the model cannot transcribe a UUID ────────────────────────────────────────

def test_a_mistranscribed_book_id_is_corrected_not_400d():
    """Measured 2026-07-11 (S06): gemma called glossary_propose_entities with the turn's
    real book_id plus one extra character ("…056e6") and the tool 400'd "book_id must be a
    UUID" — twice. A mid-tier model cannot reliably copy a 36-char UUID. A MALFORMED value
    cannot be a deliberate cross-book call, so the server's known id must win."""
    from app.services.stream_service import _inject_context_ids

    real = "019f5239-3f0d-7ad7-8fff-edd7176d056e"
    td = {"function": {"parameters": {"properties": {"book_id": {"type": "string"}}}}}
    args = _inject_context_ids(
        {"book_id": real + "6"}, td, book_id=real, chapter_id=None, project_id=None,
    )
    assert args["book_id"] == real


def test_a_valid_but_different_book_id_is_STILL_honored():
    """The negative control: a well-formed id that differs IS a deliberate cross-book call.
    Correcting a typo must not become silently redirecting an intentional one."""
    from app.services.stream_service import _inject_context_ids

    other = "019f0000-0000-7000-8000-000000000000"
    td = {"function": {"parameters": {"properties": {"book_id": {"type": "string"}}}}}
    args = _inject_context_ids(
        {"book_id": other}, td,
        book_id="019f5239-3f0d-7ad7-8fff-edd7176d056e", chapter_id=None, project_id=None,
    )
    assert args["book_id"] == other


def test_a_missing_book_id_is_still_filled():
    from app.services.stream_service import _inject_context_ids

    real = "019f5239-3f0d-7ad7-8fff-edd7176d056e"
    td = {"function": {"parameters": {"properties": {"book_id": {"type": "string"}}}}}
    assert _inject_context_ids({}, td, book_id=real, chapter_id=None, project_id=None)["book_id"] == real
