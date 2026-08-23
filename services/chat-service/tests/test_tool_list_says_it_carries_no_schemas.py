"""P10-TOOL-LOAD — a listing that is silent about what it is gets read as an answer.

🔴 THE DEFECT. Measured 2026-08-23, batch c-toolload2, K=5. Asked "What arguments does the
composition_arc_apply tool require? Read its real schema and list them", four runs called tool_load
and answered correctly. The fifth called `tool_list` and replied "arc_template_id + book_id".

composition_arc_apply's input_schema is {project_id, arc_template_id, roster_bindings, replace,
idempotency_key}. There is NO book_id. tool_list carries no input_schema at all — 29KB of 53
DESCRIPTIONS — so the words that run answered with came from a DIFFERENT tool's prose:
composition_arc_edit's description reads "op=create mints a saga/arc (needs book_id; optional ...
arc_template_id ...)". One tool's requirements were attributed to another, confidently, with no
error and no store change. That is a false statement to the author about the platform's own
contract, and tool_load is now recorded in P10's `false_statement_tools`.

The payload was not WRONG — it was SILENT about what it is, and a large authoritative-looking
listing reads like an answer to "what does this tool need". This file already makes the opposite
move twice: `always_available` names what the always-on exclusion withheld ("a caller cannot tell a
withheld tool from an absent one") and an unknown `category` gets a `reason` rather than an empty
list. A missing SCHEMA is the same class of silence.

WHAT THIS DOES NOT DO: it cannot stop a model reading a description as a schema — nothing in a
payload can. It removes the platform's part of the confusion, which is being quiet about it.
"""
from __future__ import annotations

from app.services.tool_discovery import tool_list_result


def _td(name: str, description: str) -> dict:
    return {"type": "function",
            "function": {"name": name, "description": description, "parameters": {}}}


CATALOG = [
    _td("composition_arc_apply", "Apply an arc TEMPLATE onto this Work's book as durable SPEC."),
    _td("composition_arc_edit",
        "op=create mints a saga/arc (needs book_id; optional arc_template_id)."),
]


def test_a_category_listing_says_it_carries_no_schemas():
    """🔴 THE DEFECT, on the shape the failing run actually called: tool_list(category=...)."""
    payload = tool_list_result(CATALOG, "composition")
    assert payload["tools"], "the listing is empty — re-anchor this test"
    note = payload.get("schemas", "")
    assert "NOT INCLUDED" in note, (
        "a category listing carries names and descriptions and says nothing about the absence of "
        "schemas, so a contract question answered from it looks answered"
    )
    assert "tool_load" in note, "the note must name the tool that DOES carry arguments"


def test_the_all_listing_says_it_too():
    """The grouped listing is the same payload with a different shape, and a caller that asked for
    everything is if anything more likely to treat it as complete."""
    payload = tool_list_result(CATALOG, "all")
    assert payload.get("categories"), "the grouped listing is empty — re-anchor"
    assert "NOT INCLUDED" in payload.get("schemas", "")


def test_it_warns_that_a_DESCRIPTION_may_mention_another_tools_arguments():
    """THE PRECISE FAILURE, not a general disclaimer. The bad answer did not invent book_id out of
    nothing — it read it in a NEIGHBOURING tool's description. A note that only said 'no schemas
    here' would leave the model's actual mistake unaddressed."""
    note = tool_list_result(CATALOG, "composition").get("schemas", "")
    assert "description" in note.lower() and "not this tool's schema" in note.lower(), (
        "the note does not warn that prose in one tool's description is not another's schema, "
        "which is exactly how the measured wrong answer was assembled"
    )


def test_an_unknown_category_still_gets_its_reason_and_not_this_note():
    """THE CONTROL. The unknown-category branch returns before any tool is listed, so stamping it
    would tell a caller about absent schemas when its real problem is a mistyped domain — burying
    the message that helps under one that does not."""
    payload = tool_list_result(CATALOG, "definitely-not-a-domain")
    assert "unknown category" in payload.get("reason", "")
    assert "schemas" not in payload, (
        "the no-schemas note was stamped on a listing that has no tools to describe"
    )
