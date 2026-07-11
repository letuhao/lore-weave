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
from app.services.workflow_runner import pinned_rail_block

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
