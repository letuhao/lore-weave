"""TOOLV2 LOOP #144 — composition_arc_delete described a mechanism it does not use.

The description said member chapters' "structure_node_id simply points at an archived node".
Measured live across a full delete/restore round trip on a real arc with two member chapters:

    before delete   structure_node_id = <arc>            : 2   archived_from = <arc> : 0
    after  delete   structure_node_id = <arc>            : 0   archived_from = <arc> : 2
    after  restore  structure_node_id = <arc>            : 2

So membership is CLEARED into the recovery slot (`archived_from_structure_node_id`) and moved back
on restore — the opposite of what the sentence claimed.

This is a factual correction, not a rewording. A caller who believed the old sentence would query
the outline by structure_node_id after archiving, find nothing, and conclude the chapters had been
lost — which is exactly the reassurance the sentence was trying to give. The true mechanism is both
correct and more reassuring, because it names what brings them back.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _delete_description() -> str:
    start = BODY.index('name="composition_arc_delete"')
    return BODY[start:BODY.index(")", BODY.index("meta=require_meta", start))]


def test_the_description_does_not_claim_membership_survives_the_archive():
    desc = _delete_description()
    assert "structure_node_id simply points at an archived node" not in desc, (
        "the false mechanism is back — measured, membership is cleared into the recovery slot"
    )


def test_the_description_states_the_measured_mechanism_and_its_reversal():
    desc = _delete_description()
    # Chapters survive — the reassurance the original was for, and it is true.
    assert "NOT deleted" in desc
    # ...but they DO leave the arc, which is the part a caller plans around.
    assert "recovery slot" in desc
    # ...and the way back, so "unplanned" does not read as "lost".
    assert "composition_arc_restore" in desc
