"""TOOLV2 LOOP #258 — a second tool whose required input its own named producer never emitted.

`kg_triage_place_edge` requires `triage_id`, "The proposed_edge triage item id to place (from
kg_triage_list)". Its refusal repeats the route: "no pending proposed edge with that id (use
kg_triage_list to find one)".

Measured, kg_triage_list at detail="full" returned:

    {"signature": "propose_edge:member_of:110a…->2222…", "item_type": "proposed_edge",
     "count": 1, "status": "pending", "sample_payload": {…},
     "suggested_actions": ["dismiss", "place_edge"]}

Six fields, no id — and `suggested_actions` names `place_edge` outright. So the listing told the
agent to place the edge and gave it nothing to place. The tool itself works: handed an id read
straight out of `kg_triage_items`, it minted a token and rendered a card ("Place edge 'member_of'"
with source, predicate and target rows). Only the addressability was missing.

The sibling settles what the right currency is. `kg_triage_resolve` takes `signature` — "from
kg_triage_list" — which the listing does emit, and that pairing works. `place_edge` is the odd one
out.

A grouped view has no single id, so the listing now emits the SAMPLE's id, from the same
`array_agg(… ORDER BY created_at DESC)[1]` the sample_payload already uses. That is deliberate:
the id and the payload describe the same item, so an agent acts on the thing it just read rather
than on an arbitrary member of the group.

This is #256's defect in another tool, found two iterations later — there `base_source_hash` was
dropped from a hand-written projection, here `triage_id` was never in the grouped row at all.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _read(rel: str) -> str:
    return APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_listing_emits_an_id_the_place_tool_can_use():
    fn = _read("tools/graph_schema_tools.py")
    assert '"sample_triage_id": g.sample_triage_id,' in fn, (
        "kg_triage_list no longer hands back a placeable id; kg_triage_place_edge names this "
        "tool as the source and cannot be reached without one"
    )


def test_the_id_survives_the_default_detail():
    """`summary` is the DEFAULT. An id is a reference, not a heavy body — the reference-first
    contract exists to hand back cheap ids the agent can act on. Dropping this one at the
    default would leave the tool as unreachable as it was before it was emitted."""
    fn = _read("tools/graph_schema_tools.py")
    start = fn.index("TRIAGE_GROUP_REF_FIELDS = ")
    ref_set = fn[start: fn.index(")", start)]
    assert '"sample_triage_id"' in ref_set


def test_the_id_and_the_payload_describe_the_same_item():
    """Two different array_agg orderings would pair an id with someone else's payload, and the
    agent would place an edge it never saw."""
    repo = _read("db/repositories/triage.py")
    assert "(array_agg(payload ORDER BY created_at DESC))[1] AS sample_payload" in repo
    assert "(array_agg(triage_id ORDER BY created_at DESC))[1] AS sample_triage_id" in repo


def test_the_repo_object_carries_it():
    repo = _read("db/repositories/triage.py")
    assert '"sample_triage_id",' in repo, "the __slots__ entry is gone; assignment would raise"
    assert "sample_triage_id=str(r[\"sample_triage_id\"]) if r[\"sample_triage_id\"] else None," in repo


def test_the_constructor_stays_additive():
    """One non-repo call site exists (a unit-test fixture). A required keyword would break it,
    and the loop's own rule is to audit every call site when adding a kwarg."""
    repo = _read("db/repositories/triage.py")
    assert "sample_triage_id: str | None = None," in repo


def test_the_rest_surface_did_not_get_left_behind():
    """The MCP tool and the REST route render the same groups. Fixing one and not the other is
    how the two surfaces drift — the shape #257 had to correct on sync_available."""
    rest = _read("routers/public/triage.py")
    assert "sample_triage_id: str | None = None" in rest


def test_the_place_tool_still_validates_the_item_before_minting():
    """The id is now easy to obtain, which makes the pre-mint check matter more, not less: a
    stale or wrong-type id must not produce a token a human is then asked to confirm."""
    fn = _read("tools/graph_schema_tools.py")
    assert 'item is None or item.item_type != "proposed_edge" or item.status != "pending"' in fn
