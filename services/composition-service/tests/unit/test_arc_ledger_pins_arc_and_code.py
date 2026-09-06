"""TOOLV2 LOOP #146 — the BA5 arc-ledger mechanism had never run in production.

`arc_apply()` in app/engine/arc_apply.py sets two things on every motif_application row: the
first-class `structure_node_id` (its comment says arc conformance reads `WHERE structure_node_id =
$arc`) and `annotations.motif_code` (its comment says the code "lets extract rebuild `layout`
without re-resolving motifs").

Nothing in app/ calls that function. Both production entry points — the MCP tool
composition_arc_apply and the REST route POST /works/{id}/arc/materialize — go through
`apply_arc_to_spec()`, which assembled its ledger rows as `{**row, "outline_node_id": ...}` and
wrote neither field. Only tests/integration/db/test_arc_apply_roundtrip.py calls the other
function, so the suite stayed green over a mechanism with a 100% miss rate.

Measured before the fix: 0 of 47 motif_application rows in the whole table carried
structure_node_id, and 0 carried annotations.motif_code — including the four rows a successful
composition_arc_apply had just written.

The visible damage was in the round trip. composition_arc_extract_template read the code back with
`ann.get("motif_code") or app.motif_id`, so with the annotation missing it emitted the motif's
UUID in a field named `motif_code`. A library arc template exists to be applied to ANOTHER book,
where that uuid resolves to nothing — so every extracted template was silently unportable. Live,
extracting from an applied arc produced placements with motif_code == motif_id ==
"019ff005-9674-…" where the real codes were "duel" and "meet".
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "engine" / "arc_apply.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _live_apply() -> str:
    """The function production actually calls — NOT arc_apply(), which is the dead one."""
    start = BODY.index("async def apply_arc_to_spec(")
    nxt = BODY.find("\nasync def ", start + 10)
    return BODY[start: nxt if nxt != -1 else len(BODY)]


def test_the_live_apply_pins_the_arc_on_every_ledger_row():
    live = _live_apply()
    assert '"structure_node_id": arc_id_str' in live, (
        "apply_arc_to_spec writes ledger rows without the first-class arc link again — "
        "arc conformance's `WHERE structure_node_id = $arc` matches nothing"
    )
    assert 'arc_id_str = str(created["arc_id"])' in live


def test_the_live_apply_writes_the_motif_code_annotation():
    live = _live_apply()
    assert "code_by_id = {str(m.id): m.code for m in resolved if m is not None}" in live
    assert 'ann["motif_code"] = code_by_id[str(mid)]' in live, (
        "without the code annotation, extract cannot rebuild a portable layout"
    )
    # And the old shape, which silently wrote neither, must not come back.
    assert '[{**row, "outline_node_id": str(node_id)}' not in live


def test_extract_never_emits_a_uuid_as_a_motif_code():
    """The fallback may stay — rows written before the fix carry no code — but it must not
    disguise an id as a code, because that is what made every extracted template unportable
    while looking perfectly well-formed."""
    assert 'motif_code = str(ann.get("motif_code") or (app.motif_id or ""))' not in BODY, (
        "the extract fallback puts the motif UUID back into the motif_code field"
    )
    assert 'motif_code = str(ann.get("motif_code") or "")' in BODY
    # Distinct motifs sharing a thread must still land in distinct groups: an empty code as the
    # grouping key would merge them into one placement.
    assert 'key = (motif_code or f"id:{app.motif_id}", thread)' in BODY
