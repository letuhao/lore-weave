"""D-A-LISTING-TOOL-RETURNS-EVERYTHING-WITH-NO-INDEX-TIER — the invariant, guarded.

    "A tool that returns an unbounded COLLECTION must offer an index tier and a way to page it.
     A DISCOVERY listing in particular must be materially cheaper than the thing it defers to,
     or the two-tier design buys nothing."

OWNER 2026-09-01: "my original tool list only return index and short description that agent now
what it tool does and load the tool when it want, but seem like this tool_list design wrong, so
this is a defect need to fix."

🔴 THE REMEDY SHIPPED AND NOTHING GUARDED ITS POINT. `short_description` is built and deployed,
and `test_a_listing_entry_says_its_arguments_are_not_shown` covers the per-entry refusal — but
NO test asserted that the listing is actually an INDEX. Restore the full descriptions and every
existing test stays green while the index silently becomes the thing it replaced.

MEASURED LIVE 2026-09-02, K=5, local model, the corpus prompt that provably reaches the tool
("Call tool_list for the composition category, then tell me exactly what arguments the
composition_arc_edit tool requires"):

    tool_list  5/5 calls, all carrying short_description, 15,803 B for 54 tools (293 B/tool)
    tool_load  5/5 calls                     <- the deferral is REAL, not theoretical
    per tool_load payload: 6,747 B

So loading all 54 would cost ~364 kB against the index's 15.8 kB: 23x. That ratio is the
invariant, and it is what these tests pin.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_discovery import (  # noqa: E402
    SHORT_DESCRIPTION_CHARS, tool_list_result, visible_tools,
)

#: A description of the length the real catalogue carries (mean 303 chars, and the worst are far
#: longer). The index's whole claim is that it does not pay this per row.
LONG = (
    "PROPOSE running the grounded cowrite ENGINE to generate prose — a SCENE (pass "
    "outline_node_id) or a whole CHAPTER (pass chapter_id; persisted to the book draft). This is "
    "DISTINCT from book_chapter_save_draft, which only SAVES text you wrote yourself: this "
    "invokes the canon-grounded drafter+critic engine and SPENDS LLM tokens, so it is cost-gated "
    "— it returns a confirm_token + descriptor and generates NOTHING until the user confirms."
)


def _tool(name: str, desc: str, **meta) -> dict:
    return {"function": {"name": name, "description": desc,
                         "parameters": {"type": "object",
                                        "properties": {"book_id": {"type": "string"},
                                                       "chapter_id": {"type": "string"}}},
                         "_meta": meta}}


CATALOG = [_tool(f"composition_tool_{i}", LONG, tier="W") for i in range(20)]


def test_the_listing_is_MATERIALLY_cheaper_than_the_descriptions_it_replaces():
    """The two-tier design buys nothing if the index costs what the full read costs."""
    listing = json.dumps(visible_tools(CATALOG), ensure_ascii=False)
    full = json.dumps([t["function"]["description"] for t in CATALOG], ensure_ascii=False)
    assert len(listing) < len(full), (
        f"the index ({len(listing)} B) is not smaller than the descriptions alone "
        f"({len(full)} B) — it is not an index, it is the thing it was meant to defer to"
    )


def test_no_entry_carries_a_FULL_description():
    """🔴 THE REGRESSION THIS EXISTS FOR. Restoring `description` would leave every other test
    green: the per-entry refusal still stamps, the names are still right, the count is still
    right. Only the SIZE would change, and nothing was watching it."""
    for entry in visible_tools(CATALOG):
        assert "description" not in entry, (
            f"{entry.get('name')} carries a full `description` — the index tier is gone and "
            "the payload is back to the 303-char-per-row shape the owner called a defect"
        )
        sd = entry.get("short_description") or ""
        assert len(sd) <= SHORT_DESCRIPTION_CHARS + 1, (
            f"{entry.get('name')}'s short_description is {len(sd)} chars, over the "
            f"{SHORT_DESCRIPTION_CHARS} bound — an unbounded 'short' description is the defect "
            "wearing a different key"
        )
        assert sd, f"{entry.get('name')} has an EMPTY short_description — the index says nothing"


def test_no_entry_carries_a_SCHEMA():
    """The deferral's whole subject. A listing that ships inputSchema has nothing left to defer,
    and tool_load becomes a round trip that buys the model nothing."""
    for entry in visible_tools(CATALOG):
        for banned in ("inputSchema", "input_schema", "parameters"):
            assert banned not in entry, (
                f"{entry.get('name')} carries {banned!r} — the index now contains the thing "
                "tool_load exists to fetch"
            )


def test_the_index_still_says_what_each_tool_DOES():
    """🔴 THE TEETH AGAINST OVER-TRIMMING. The measured trade is that the model LISTS 12x more
    often than it LOADS, so it decides FROM these lines. Cut them to bare names and it either
    round-trips far more or picks worse. A shorter index is not automatically a better one."""
    entries = visible_tools(CATALOG)
    for e in entries:
        sd = e["short_description"]
        assert len(sd) >= 20, (
            f"{e['name']}'s short_description is {len(sd)} chars — too little to choose from, "
            "and choosing is what this field is for"
        )
    # ...and the name + tier a caller routes on survive.
    assert all(e.get("name") and e.get("tier") for e in entries)


def test_the_whole_result_keeps_the_header_that_says_schemas_are_absent():
    out = tool_list_result(CATALOG, category="composition")
    blob = json.dumps(out, ensure_ascii=False)
    assert "tool_load" in blob, (
        "the listing never names tool_load — an index that does not say where the rest lives "
        "is a truncation, not a tier"
    )
