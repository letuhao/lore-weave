"""A refusal from a Tier-A tool executed ON RESUME must reach the re-derived surface.

`discovery_seed_for_surface` already states the rule, for skills:

    "an INJECTED instruction must never name a tool that is not on the wire — the named tools
     of every injected skill ride budget-exempt, exactly like a pinned rail's next-step tools."

A REFUSAL is an injected instruction too — the runtime's own words telling the model what to
call — and it was the only one of the three not riding.

MEASURED 2026-08-24, batch c-override12, K=5, gemma-4-26b-a4b-qat:

    composition_entity_override_edit   advertised 5 of 5
    composition_list_derivatives       withheld 5 of 5, for TWO reasons, per
                                       chat_messages.withheld_tools:
        domain_not_selected | domain not in this turn's hot set (book, glossary, knowledge, story)
        hot_seed            | did not fit the hot_seed token budget (2000 tok)

while the refusal said "Call composition_list_derivatives and pass it THIS SAME project_id".

The union therefore goes AFTER both filters: a budget-only exemption would still have left the
tool out of the hot set. That is the property these tests pin — a fix that only survived the
budget would pass a weaker test and fail the measured case.
"""
from __future__ import annotations

import pytest

from app.services import instrument
from app.services.tool_surface import (
    discovery_seed_for_surface,
    resolve_session_tool_pins,
    skill_named_tools,
)


def _td(name: str, desc: str = "") -> dict:
    return {"type": "function",
            "function": {"name": name, "description": desc or name,
                         "parameters": {"type": "object", "properties": {}}}}


@pytest.fixture(autouse=True)
def _isolated_withheld_sink():
    """🔴 WITHOUT THIS, THESE TESTS BROKE test_cp0_instrument IN THE FULL SUITE — five failures
    that passed in isolation and failed only when run together.

    `discovery_seed_for_surface` records every tool it withholds into
    `instrument.surface_withheld`, a ContextVar. Calling the real seed builder therefore leaves
    rows in whatever sink is current, and cp0's catalogue-outage assertions read that same sink.
    Exercising the real thing is the point of these tests, so the fix is to give each one its own
    sink and put the old one back — not to stop calling it.
    """
    token = instrument.surface_withheld.set([])
    try:
        yield
    finally:
        instrument.surface_withheld.reset(token)


class TestARefusalNamedToolRides:
    """These call the real seed builder with a minimal catalogue. The assertion is only ever
    'the named tool is in the result' — never 'the result is exactly this' — so an unrelated
    change to seeding does not turn into a red here."""

    def _seed(self, **kw):
        catalog = [_td("composition_list_derivatives"), _td("composition_entity_override_edit"),
                   _td("book_read"), _td("glossary_search")]
        pins = resolve_session_tool_pins(None)
        return discovery_seed_for_surface(
            catalog, pins=pins, editor=False, book_scoped=True, studio=False,
            context_length=32000, permission_mode="default", **kw)

    def test_a_named_tool_is_in_the_seed(self):
        got = self._seed(refusal_named_tools={"composition_list_derivatives"})
        assert "composition_list_derivatives" in got

    def test_it_is_absent_without_the_declaration(self):
        """The control that makes the test above mean something: if the tool were seeded
        anyway, the union would be proving nothing."""
        got = self._seed()
        assert "composition_list_derivatives" not in got, (
            "the tool is already seeded without any exemption, so this scenario cannot "
            "demonstrate the fix — pick a tool the seed actually drops"
        )

    def test_a_name_that_is_not_in_the_catalogue_cannot_ride(self):
        """A refusal is model-visible text. Only real catalogue tools may be seeded from it —
        the same restriction skill_named_tools applies."""
        got = self._seed(refusal_named_tools={"composition_invent_a_tool"})
        assert "composition_invent_a_tool" not in got

    def test_an_empty_declaration_changes_nothing(self):
        assert self._seed(refusal_named_tools=set()) == self._seed()

    def test_none_changes_nothing(self):
        assert self._seed(refusal_named_tools=None) == self._seed()


class TestTheRuleItInherits:
    def test_skill_named_tools_still_resolves_against_the_catalogue(self):
        """The precedent this fix copies must keep working — the union was inserted directly
        beside it."""
        catalog = [_td("glossary_propose_entities")]
        assert skill_named_tools([], catalog) == set()


class TestTheResumePathCollectsIt:
    """The half that makes the seed parameter matter. A parameter nobody passes is a mechanism
    that never runs, and this loop has shipped one of those before."""

    @staticmethod
    def _src() -> str:
        import inspect

        from app.services import stream_service

        return inspect.getsource(stream_service)

    def test_the_resume_dispatch_captures_the_refusal(self):
        src = self._src()
        assert "_resume_refused_tool = _tool_name" in src, (
            "the resume path no longer captures which tool refused"
        )

    def test_the_seed_call_passes_the_resolved_names(self):
        src = self._src()
        assert "refusal_named_tools=_resume_refusal_named" in src, (
            "resolved and never passed — the mechanism would never run"
        )

    def test_resolution_happens_AFTER_the_catalogue_is_fetched(self):
        """🔴 THIS IS THE BUG THAT MADE THE FIRST VERSION A NO-OP, AND IT IS WHY THE CHECK IS
        ORDER-BASED RATHER THAN PRESENCE-BASED.

        The names were resolved at the DISPATCH site, which runs before `catalog` is fetched. The
        guard `if _resume_refusal and catalog:` was therefore false every time and the collection
        silently did nothing — measured as three suspended runs of
        composition_entity_override_edit and ZERO carry-forward log lines. Presence of the code
        proved nothing; only its position does."""
        import re

        lines = self._src().splitlines()
        def at(pat):
            return next(i for i, l in enumerate(lines) if pat in l)

        decl = at('_resume_refusal: str = ""')
        cap = at("_resume_refused_tool = _tool_name")
        res = at("_resume_refusal_named = set(_tools_named_in_refusal(")
        use = at("refusal_named_tools=_resume_refusal_named")
        cat = next(i for i, l in enumerate(lines)
                   if decl < i < use and re.match(r"\s*catalog\s*=", l))
        assert decl < cap < cat < res < use, (
            f"declared {decl}, captured {cap}, catalogue {cat}, resolved {res}, used {use} — "
            f"resolution must come AFTER the catalogue exists"
        )
        indent = len(lines[decl]) - len(lines[decl].lstrip())
        assert indent == 4, (
            f"declared at indent {indent}, not function scope — a resume path that skips the "
            f"approval branch would NameError"
        )
