"""D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — the pure binding-assembler (no DB/glossary).

_assemble_motif_bindings joins committed scenes × motif_application × motif × cast into
the {node_id: BoundMotif | null} map the FE MotifBindingCard consumes. These cover the
join-correctness surface without a stack: every scene present (null = free-form), the
BoundMotif shape (name/source/role_bindings{entity_id,entity_name}/match_reason/beat_key),
and the three degrade-to-null paths (unbound, cleared, archived-not-visible).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.db.models import MotifApplication
from app.routers.plan import _assemble_motif_bindings, _assemble_succession


def _scene(node_id):
    return SimpleNamespace(id=node_id)


def _app(node_id, *, motif_id, role_bindings=None, annotations=None):
    return MotifApplication(
        id=uuid.uuid4(), created_by=uuid.uuid4(), project_id=uuid.uuid4(),
        book_id=uuid.uuid4(), motif_id=motif_id, motif_version=1,
        outline_node_id=node_id, role_bindings=role_bindings or {},
        annotations=annotations or {},
    )


def _motif(name="Planted Evidence", source="authored"):
    return SimpleNamespace(name=name, source=source)


def test_bound_scene_assembles_full_boundmotif():
    n1, mid, eid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid, role_bindings={"schemer": str(eid)},
               annotations={"beat_key": "bait",
                            "match_reason": {"tension": 0.9, "cosine": 0.7}})
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, cast_names={str(eid): "Lady Wu"},
    )
    b = out[str(n1)]
    assert b["motif_id"] == str(mid)
    assert b["motif_name"] == "Planted Evidence"
    assert b["motif_source"] == "authored"
    assert b["beat_key"] == "bait"
    assert b["match_reason"] == {"tension": 0.9, "cosine": 0.7}
    # role binding resolved to {entity_id, entity_name} via the cast.
    assert b["role_bindings"]["schemer"] == {"entity_id": str(eid), "entity_name": "Lady Wu"}


def test_unresolved_cast_member_gets_empty_name():
    n1, mid, eid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid, role_bindings={"schemer": str(eid)})
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, cast_names={},  # eid not in the cast
    )
    assert out[str(n1)]["role_bindings"]["schemer"] == {"entity_id": str(eid), "entity_name": ""}


def test_unbound_scene_is_null():
    n1 = uuid.uuid4()
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={}, motif_by_id={}, cast_names={})
    assert out[str(n1)] is None


def test_cleared_application_is_null():
    n1 = uuid.uuid4()
    app = _app(n1, motif_id=None)  # a clear-motif row (swap to free-form)
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={n1: app}, motif_by_id={}, cast_names={})
    assert out[str(n1)] is None


def test_archived_motif_not_visible_is_null():
    # bound row, but get_visible returned None (archived/foreign) → motif_by_id misses it.
    n1, mid = uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid)
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={n1: app}, motif_by_id={}, cast_names={})
    assert out[str(n1)] is None


def test_missing_match_reason_degrades_to_empty():
    # a pre-GAP-1 binding (no persisted match_reason) → {} not a crash.
    n1, mid = uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid, annotations={"beat_key": "bait"})
    out = _assemble_motif_bindings(
        scenes=[_scene(n1)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, cast_names={})
    assert out[str(n1)]["match_reason"] == {}
    assert out[str(n1)]["beat_key"] == "bait"


def test_every_scene_present_in_map():
    n1, n2, n3, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid, annotations={"beat_key": "b"})
    out = _assemble_motif_bindings(
        scenes=[_scene(n1), _scene(n2), _scene(n3)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, cast_names={})
    assert set(out.keys()) == {str(n1), str(n2), str(n3)}
    assert out[str(n1)] is not None and out[str(n2)] is None and out[str(n3)] is None


# ── _assemble_succession (D-MOTIF-CHAIN-SUCCESSION-HINT) ──────────────────────────

def test_succession_hint_points_at_the_free_form_next_scene():
    n1, n2, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid)
    succ = {str(mid): [{"code": "revenge.face_slap", "name": "Face Slap", "ord": 0}]}
    out = _assemble_succession(
        scenes=[_scene(n1), _scene(n2)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, successors=succ)
    # the hint shows on scene 1's card and pre-seeds the (unbound) scene 2.
    assert out[str(n1)] == {
        "from_motif_id": str(mid), "to_motif_code": "revenge.face_slap",
        "to_motif_name": "Face Slap", "for_node_id": str(n2)}
    assert out[str(n2)] is None  # last scene → no next to pre-seed


def test_succession_first_successor_wins_by_ord():
    n1, n2, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid)
    succ = {str(mid): [{"code": "a.first", "name": "First", "ord": 0},
                       {"code": "b.second", "name": "Second", "ord": 1}]}
    out = _assemble_succession(
        scenes=[_scene(n1), _scene(n2)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, successors=succ)
    assert out[str(n1)]["to_motif_code"] == "a.first"


def test_succession_suppressed_when_next_scene_already_bound():
    # never suggest chaining OVER a deliberate binding on the next scene.
    n1, n2, mid, mid2 = (uuid.uuid4() for _ in range(4))
    a1 = _app(n1, motif_id=mid)
    a2 = _app(n2, motif_id=mid2)
    succ = {str(mid): [{"code": "x", "name": "X", "ord": 0}]}
    out = _assemble_succession(
        scenes=[_scene(n1), _scene(n2)], apps_by_node={n1: a1, n2: a2},
        motif_by_id={mid: _motif(), mid2: _motif()}, successors=succ)
    assert out[str(n1)] is None


def test_succession_null_when_motif_has_no_successor():
    n1, n2, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    app = _app(n1, motif_id=mid)
    out = _assemble_succession(
        scenes=[_scene(n1), _scene(n2)], apps_by_node={n1: app},
        motif_by_id={mid: _motif()}, successors={})  # no precedes edge
    assert out[str(n1)] is None


def test_succession_null_for_unbound_or_invisible_scene():
    n1, n2, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # scene 1 bound but its motif isn't visible (archived/foreign) → no hint.
    app = _app(n1, motif_id=mid)
    succ = {str(mid): [{"code": "x", "name": "X", "ord": 0}]}
    out = _assemble_succession(
        scenes=[_scene(n1), _scene(n2)], apps_by_node={n1: app},
        motif_by_id={}, successors=succ)  # motif_by_id misses mid
    assert out[str(n1)] is None and out[str(n2)] is None
