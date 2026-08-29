"""DQ-T59, answered by the owner 2026-08-28.

    "REFUSE a contract question answered from a description-only read — the model must call
     tool_load for arguments. tool_list keeps returning descriptions and does NOT grow
     input_schema, and it keeps listing tools not on the wire."

    BUILD NOTE (the owner's): "'refuse' has to be enforced somewhere real. A line of guidance in
    tool_list's own description is the cheap version … whether a refusal needs a mechanism rather
    than wording is a measurement, and it is owed before this is called done."

🔴 THE MEASUREMENT WAS OWED, WAS RUN, AND THE WORDING LOST.

`_stamp_no_schemas` has put that exact sentence at the TOP of every tool_list payload since
2026-08-23 — added for this defect, never tested. Batch c-toollistoffwire1 (2026-08-30, K=5)
tested it: a tool_list read, then a contract question about `composition_arc_edit`, a tool NOT on
the wire so its description really is all the model holds.

    4 of 5 stated its arguments as FACT from the prose, never calling tool_load
    1 of 5 declined and pointed at tool_load

The stamp was present verbatim every time. So the sentence moves from one line above 29KB of
prose to EVERY entry, beside the description it is about.

🔴 TWO EARLIER ARMS PROVED NOTHING, and they are pinned here so nobody re-runs them believing
they settle it:
  * c-toolload3 — 5/5 went straight to tool_load and called tool_list ZERO times. The stamp never
    fired; 0 failures was the absence of the trigger.
  * c-toollistcontract1 — 5/5 read tool_list, but the tool asked about (composition_arc_apply)
    was ADVERTISED, so its real JSON schema was already in context. The replies recited all five
    arguments WITH TYPES, which tool_list never carried. Correct answers from the wrong source.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_discovery import tool_list_result, visible_tools  # noqa: E402


def _t(name: str, desc: str = "", **meta) -> dict:
    return {"function": {"name": name, "description": desc,
                         "parameters": {"type": "object", "properties": {"project_id": {}}},
                         "_meta": meta}}


CATALOG = [
    _t("composition_arc_apply", "Apply an arc TEMPLATE onto this Work's book.", tier="A"),
    # The neighbour whose PROSE was borrowed in the original failure — it names arguments in
    # running text, which is exactly what makes a description-only read look answerable.
    _t("composition_arc_edit",
       "op=create mints a saga/arc (needs book_id; optional arc_template_id).", tier="A"),
]


class TestEveryEntryCarriesTheRefusal:
    def test_each_entry_says_its_arguments_are_not_shown(self):
        for e in visible_tools(CATALOG):
            assert "arguments" in e, f"{e['name']} carries no arguments marker"
            assert "NOT SHOWN" in e["arguments"]

    def test_it_names_the_tool_to_load_and_that_tool_is_ITSELF(self):
        """🔴 THE POINT OF PER-ENTRY. A top-level line cannot say WHICH tool to load; that is the
        gap the defect fell through, since the borrowed prose belonged to a different tool than
        the question. Each marker names its own entry, so the instruction cannot be mis-applied
        to the neighbour whose description happens to sit beside it."""
        for e in visible_tools(CATALOG):
            assert f"tool_load({e['name']!r})" in e["arguments"], e

    def test_it_is_present_in_the_CATEGORY_payload(self):
        out = tool_list_result(CATALOG, "composition")
        assert out["tools"], out
        assert all("NOT SHOWN" in t["arguments"] for t in out["tools"])

    def test_it_is_present_in_the_ALL_payload(self):
        out = tool_list_result(CATALOG, "all")
        entries = [t for group in out["categories"].values() for t in group]
        assert entries
        assert all("NOT SHOWN" in t["arguments"] for t in entries)


class TestItDoesNotReplaceWhatWasAlreadyThere:
    def test_the_top_level_stamp_still_stands(self):
        """The per-entry marker is an ESCALATION, not a swap. The top-level sentence carries the
        part an entry cannot — that a description may mention ANOTHER tool's arguments in prose —
        and removing it would trade one gap for another."""
        out = tool_list_result(CATALOG, "composition")
        assert "NOT INCLUDED" in out["schemas"]
        assert "call tool_load" in out["schemas"]

    def test_the_description_is_untouched(self):
        """The declaration is the tool author's; this adds a field beside it and never edits it.
        Mutilating descriptions to stop a misread would break every other reader of the payload."""
        e = next(t for t in visible_tools(CATALOG) if t["name"] == "composition_arc_edit")
        assert e["description"] == (
            "op=create mints a saga/arc (needs book_id; optional arc_template_id).")

    def test_a_deprecated_entry_keeps_its_own_labels(self):
        cat = [_t("composition_arc_create", "old", tier="A", visibility="legacy",
                  superseded_by="composition_arc_edit")]
        e = visible_tools(cat)[0]
        assert e["deprecated"] is True
        assert e["superseded_by"] == "composition_arc_edit"
        assert "NOT SHOWN" in e["arguments"]
