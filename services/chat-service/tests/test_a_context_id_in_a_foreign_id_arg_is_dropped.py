"""D-XWIRE-FOREIGN-ID-ARG — a context id in an argument NOT called book/chapter/project.

`_inject_context_ids` iterated over exactly three argument names, so a cross-wire into any
other id argument was never examined. Measured 2026-08-24 on composition_authoring_run_manage:
the model sent `plan_run_id` = the turn's CHAPTER id, the runtime forwarded it untouched, a
durable gate task was minted, and approving it produced a bare 400 `action_error` —
LookupError("plan run not found"). Approve-then-fail on a cost-bearing tool.

These tests pin the RULE, not the tool: drop only on an exact match against an id this turn
published under another name, only for an `*_id` argument the tool declares, and only where the
tool declares an EMITTER so the refusal can say where to get the real value.
"""
import pytest

from app.services.stream_service import _inject_context_ids

BOOK = "01a03219-a175-73c8-a15d-cbd214491abd"
CHAPTER = "01a03219-a210-7aa5-b995-77b001111e7f"
PROJECT = "01a03219-a2d4-7299-9765-6de810ed9b09"
REAL_PLAN_RUN = "01a03219-a35a-7645-a916-05d6cc6990b9"


def _tool(name, props, meta=None):
    return {"function": {"name": name, "_meta": meta or {},
                         "parameters": {"type": "object", "properties": props}}}


MANAGE = _tool("composition_authoring_run_manage", {
    "op": {"type": "string"}, "book_id": {"type": "string"},
    "plan_run_id": {"type": "string"}, "run_id": {"type": "string"},
})


def _inject(args, tool=MANAGE, **kw):
    kw.setdefault("book_id", BOOK)
    kw.setdefault("chapter_id", CHAPTER)
    kw.setdefault("project_id", PROJECT)
    return _inject_context_ids(dict(args), tool, **kw)


class TestTheMeasuredDefect:
    def test_the_chapter_id_sent_as_plan_run_id_is_dropped(self):
        """The exact payload recovered from mcp_gate_tasks, on both measured runs."""
        out = _inject({"op": "create", "book_id": BOOK, "plan_run_id": CHAPTER})
        assert "plan_run_id" not in out, (
            "the runtime forwarded an id it had the evidence to know was a chapter — a card is "
            "minted and approving it fails with a bare 400"
        )

    def test_the_book_id_beside_it_is_left_correct(self):
        out = _inject({"op": "create", "book_id": BOOK, "plan_run_id": CHAPTER})
        assert out["book_id"] == BOOK

    def test_the_project_id_sent_as_plan_run_id_is_dropped_too(self):
        """Any of the turn's ids in the wrong slot, not just the chapter."""
        out = _inject({"op": "create", "book_id": BOOK, "plan_run_id": PROJECT})
        assert "plan_run_id" not in out


class TestItDoesNotFireOnALegitimateCall:
    """The precision half. Dropping a REAL id would break calls that work today."""

    def test_a_real_plan_run_id_is_untouched(self):
        out = _inject({"op": "create", "book_id": BOOK, "plan_run_id": REAL_PLAN_RUN})
        assert out["plan_run_id"] == REAL_PLAN_RUN

    def test_an_unrelated_uuid_is_untouched(self):
        """Only an id THIS TURN published is evidence. An unknown UUID is not a cross-wire —
        it may be a perfectly good id from a tool result the server never saw."""
        other = "01a03219-ffff-7000-8000-000000000000"
        out = _inject({"op": "create", "book_id": BOOK, "plan_run_id": other})
        assert out["plan_run_id"] == other

    def test_an_arg_with_no_declared_emitter_is_forwarded(self):
        """🔴 THE NARROWING THAT WAS PAID FOR IN A MEASURED REGRESSION (c-override11): a drop
        whose refusal names nowhere to go blank-retries into the repeat-breaker, which is worse
        than the opaque failure it replaced. `run_id` declares no emitter, so it is forwarded."""
        out = _inject({"op": "start", "book_id": BOOK, "run_id": CHAPTER})
        assert out.get("run_id") == CHAPTER

    def test_a_non_id_field_holding_the_same_value_is_untouched(self):
        """Name-scoped on purpose: a prose field that happens to carry a UUID is not an id slot."""
        t = _tool("composition_authoring_run_manage",
                  {"book_id": {"type": "string"}, "note": {"type": "string"}})
        out = _inject({"book_id": BOOK, "note": CHAPTER}, tool=t)
        assert out["note"] == CHAPTER

    def test_an_undeclared_arg_is_untouched(self):
        """Only arguments the tool declares are in scope, same as the loop above."""
        out = _inject({"op": "create", "book_id": BOOK, "widget_id": CHAPTER})
        assert out["widget_id"] == CHAPTER

    def test_no_context_fill_is_respected(self):
        """A tool that declares an argument mode-selecting owns it entirely — the runtime must
        neither supply nor correct it."""
        t = _tool("composition_authoring_run_manage",
                  {"book_id": {"type": "string"}, "plan_run_id": {"type": "string"}},
                  meta={"no_context_fill": ["plan_run_id"]})
        out = _inject({"book_id": BOOK, "plan_run_id": CHAPTER}, tool=t)
        assert out["plan_run_id"] == CHAPTER
