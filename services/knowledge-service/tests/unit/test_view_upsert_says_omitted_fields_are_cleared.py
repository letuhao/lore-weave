"""TOOLV2 LOOP #262 — "optional" fields whose omission silently destroys data.

kg_view_edit is correct on every path measured. The per-op gates are precise ("op=upsert requires
name" as a business rule; a missing `code` caught at schema level because both ops need it), the
create/update distinction is honest (`created: true` then `created: false` with the SAME view_id
on the second upsert — a real upsert, not a duplicate), and delete returns `deleted: true`.

The replace semantics are exactly as advertised, which is the point. Measured in the SSOT:

    upsert code + name + edge_type_codes[knows,owns] + node_kind_codes[character,location]
      + description "first"                      -> {knows,owns} | {character,location} | first
    upsert code + name + edge_type_codes[serves] -> {serves}     | {}                    | (empty)

So node_kind_codes and description were CLEARED by a call that never mentioned them. The tool said
"creates/replaces", and it replaces — the behaviour is right.

The wording was the risk. Listing description/edge_type_codes/node_kind_codes as "optional"
alongside "needs code + name" invites the ordinary reading — optional means leave it alone — and a
caller who tweaks one edge type loses their whole node-kind filter and their description with no
error and no warning. The sibling in this same service goes the other way: kg_arc_template_update
uses `exclude_unset` so an omitted field IS preserved (#155). Two tools, opposite semantics, and
only one of them said which it was.

Nothing was wrong with the code. This pins the description to the measured behaviour so the two
cannot drift apart, in either direction.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _flat(rel: str) -> str:
    body = APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    return re.sub(r'"\s*\n\s*"', "", body)


def _desc(rel: str) -> str:
    flat = _flat(rel)
    start = flat.index("Create, replace, or delete one of YOUR saved views")
    return flat[start: start + 700]


def test_both_copies_warn_that_omitted_fields_are_cleared():
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        desc = _desc(rel)
        assert "is CLEARED" in desc, (
            f"{rel}: the description calls the fields optional without saying that omitting one "
            "destroys its current value"
        )
        assert "send the full lens every time" in desc, (
            f"{rel}: naming the hazard is not enough — say what to do instead"
        )


def test_the_word_optional_is_no_longer_left_to_mean_unchanged():
    """'optional' is true of the ARGUMENT and false of the STORED VALUE. The distinction is the
    whole defect, so the text must draw it rather than drop the word."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        desc = _desc(rel)
        assert "optional to SUPPLY but not preserved" in desc, rel


def test_the_delete_half_is_untouched():
    """delete's wording was already accurate and #261 verified the reverse op really works —
    recreating a deleted code succeeded with a fresh view_id. It must not be swept along."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        desc = _desc(rel)
        assert "reversible — recreate with upsert" in desc, rel


def _legacy_desc(rel: str) -> str:
    flat = _flat(rel)
    start = flat.index("Create or replace one of the caller's saved views")
    return flat[start: start + 700]


def test_the_legacy_tool_carries_the_same_warning():
    """#263. kg_view_edit DELEGATES to `_handle_kg_view_upsert`, so the legacy tool has the
    identical clearing behaviour — proven through it directly: upserting with only code+name
    wiped {knows} | {character} | "keep me" to {} | {} | "". Fixing the unified tool and leaving
    the legacy one is the half-fix this loop has now shipped twice (#253, #260)."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        desc = _legacy_desc(rel)
        assert "is CLEARED, not left alone" in desc, f"{rel}: the legacy tool gives no warning"
        assert "send the full lens every time" in desc, rel


def test_the_legacy_warning_names_the_inverted_consequence():
    """Sharper here than on the unified tool: `edge_type_codes` is documented "(empty = all)", so
    an accidentally-cleared list does not leave an empty view — it leaves one showing
    EVERYTHING. The cleared state is maximal, not neutral."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        desc = _legacy_desc(rel)
        assert "an emptied code list means ALL" in desc.lower() or \
               "emptied code list means ALL" in desc, rel
        assert "widens the view to " in desc, rel


def test_the_empty_means_all_convention_still_holds():
    """The warning above is only true while `(empty = all)` is the convention. If that ever
    flips, the sentence misleads in the opposite direction."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        assert "(empty = all)" in _flat(rel), (
            f"{rel}: the empty=all convention is gone — re-check the widening warning"
        )


def test_the_repo_really_replaces_rather_than_merges():
    """If upsert ever starts merging, this description becomes the false one and these guards
    would be pinning a new lie. Anchor to the write."""
    repo = APP.joinpath("db", "repositories", "graph_views.py").read_text(encoding="utf-8")
    assert "exclude_unset" not in repo, (
        "the view upsert now preserves unset fields — it MERGES, and the 'anything you omit is "
        "CLEARED' warning is now wrong in the opposite direction"
    )
