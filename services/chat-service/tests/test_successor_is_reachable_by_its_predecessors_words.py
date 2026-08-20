"""R2 — a superseded tool must not out-declare its successor.

MEASURED LIVE 2026-08-14, K=3, real chat path, throwaway book per run. Prompt: "Rename the
chapter called The Ember Codex in my outline to The Ember Codex Opens."

  * `composition_outline_node_update` declares "rename chapter", "edit scene", "update node" —
    the words a person actually types — and is marked `superseded_by:
    composition_outline_node_edit`.
  * `composition_outline_node_edit`, the unified entry point that exists to serve exactly those
    requests, declares "edit outline node", "manage outline node" and a set of CREATE verbs.

So the answerability pass matched the DEPRECATED tool, the successor was surfaced on 0 of 3 runs,
and a request naming its precise job could not reach it. One run renamed the manuscript chapter in
loreweave_book instead of the outline node.

Swept across the live catalogue: 59 of 62 supersession pairs orphan at least one phrasing. That is
not a scatter of per-tool slips — it is what happens every time a tool is split or unified and the
synonyms stay behind on the old name. `scripts/lint_superseded_synonyms.py` makes the DECLARATIONS
converge; this asserts the SURFACE is correct meanwhile, and stays correct for the next pair
somebody adds.

THE INVARIANT: whatever phrasing can reach A must also be able to reach the tool that REPLACED A.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_surface import answerable_tools  # noqa: E402

OLD = "composition_outline_node_update"
NEW = "composition_outline_node_edit"


def _td(name, synonyms, superseded_by=None):
    meta = {"synonyms": synonyms, "tier": "A", "scope": "book"}
    if superseded_by:
        meta["superseded_by"] = superseded_by
    return {"type": "function",
            "function": {"name": name, "description": f"{name} does things.", "_meta": meta}}


#: The two tools exactly as the live catalogue declares them.
CATALOG = [
    _td(OLD, ["edit scene", "update node", "rename chapter", "set status", "edit beat"],
        superseded_by=NEW),
    _td(NEW, ["edit outline node", "create chapter", "create scene", "delete scene",
              "move scene", "reorder outline", "restore scene", "manage outline node"]),
    _td("book_read", ["read chapter", "open book"]),
]

PROMPT = "Rename the chapter called The Ember Codex in my outline to The Ember Codex Opens."


def test_the_deprecated_tool_is_what_the_users_words_actually_match():
    """The premise, asserted rather than assumed — if this ever stops holding, the test below
    would pass for the wrong reason."""
    got = answerable_tools(PROMPT, [CATALOG[0], CATALOG[2]])
    assert OLD in got, "'rename chapter' is the phrasing the deprecated tool claims"


def test_the_successor_is_reachable_by_the_words_its_predecessor_claims():
    """THE FALSIFIER. Original defect = no supersession union; then the successor is absent."""
    got = answerable_tools(PROMPT, CATALOG)
    assert NEW in got, (
        f"{NEW} supersedes {OLD} and exists to serve this request, but only {OLD} declares the "
        "words a user types. Live: the successor was surfaced on 0 of 3 runs and one run renamed "
        "the manuscript chapter instead of the outline node."
    )


def test_the_deprecated_tool_keeps_working():
    """A UNION, not a redirect. Existing callers depend on the old tool, and silently removing it
    from the surface would trade one unreachable tool for another."""
    got = answerable_tools(PROMPT, CATALOG)
    assert OLD in got


def test_a_tool_with_no_successor_is_untouched():
    """The union must not invent a successor, and must not widen a surface that was already
    correct — a broader surface costs schema tokens on every turn."""
    got = answerable_tools("Please read chapter one to me.", CATALOG)
    assert got == {"book_read"}


def test_a_successor_outside_the_catalogue_is_not_added():
    """A dangling `superseded_by` (renamed or retired successor) must not put a name on the
    surface that no tool definition backs — that would advertise a tool the dispatcher cannot
    resolve."""
    dangling = [_td("old_thing", ["frobnicate"], superseded_by="gone_tool")]
    got = answerable_tools("Please frobnicate this.", dangling)
    assert got == {"old_thing"}
