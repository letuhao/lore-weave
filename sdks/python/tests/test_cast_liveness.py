"""S2 — one cast-liveness SSOT, per ENTITY.

The bug: `gone_entities_referenced` answers "which of these is marked gone and named in the
text?", and everything it omits is treated by every caller as fine. So an entity the knowledge
graph has NEVER HEARD OF takes the identical path to an entity the graph positively knows is
alive. Those are different facts, and the second one is the interesting one — a reference to an
undeclared identifier, which PF-1 named as *"anonymous characters were uses of undeclared
identifiers"*.

⚠ THE FIXTURE. The spec is explicit and it is the whole reason these tests exist: the case that
matters is a **NON-EMPTY snapshot with no status row for the subject**, not an empty snapshot.
An empty one is indistinguishable from an outage and every implementation passes it — v1's
fixture would have gone green while the bug survived. Both are tested below and they mean
different things.
"""
from __future__ import annotations

from loreweave_canon_check import (
    LIVENESS_SOURCE_KG,
    LIVENESS_SOURCE_NONE,
    LIVENESS_SOURCE_PLAN,
    LIVENESS_UNKNOWN,
    resolve_cast_liveness,
    unresolved_cast_refs,
)


def _snap(*rows) -> dict:
    return {"entities": [dict(r) for r in rows]}


# ── the fixture the spec names ────────────────────────────────────────────────────────────

def test_a_NONEMPTY_snapshot_with_no_row_for_the_subject_is_unknown_not_alive():
    """THE test. The graph is populated and healthy — it simply has never heard of `ghost`."""
    snap = _snap({"entity_id": "elara", "status": "alive"},
                 {"entity_id": "cassius", "status": "gone"})
    out = resolve_cast_liveness(["elara", "cassius", "ghost"], snap)
    assert out["elara"] == {"status": "alive", "source": LIVENESS_SOURCE_KG}
    assert out["cassius"] == {"status": "gone", "source": LIVENESS_SOURCE_KG}
    assert out["ghost"] == {"status": LIVENESS_UNKNOWN, "source": LIVENESS_SOURCE_NONE}


def test_CONTROL_an_EMPTY_snapshot_also_yields_unknown_and_that_proves_less():
    """Kept deliberately, and labelled: this is the fixture that would have passed against the
    broken implementation too. It is a control for the test above, not a substitute for it."""
    out = resolve_cast_liveness(["elara"], {"entities": []})
    assert out["elara"]["source"] == LIVENESS_SOURCE_NONE


def test_an_OUTAGE_is_unknown_for_everyone_and_must_not_read_as_gone():
    """`snapshot=None` is a knowledge outage. Every entity is unknown/none — which is why a
    caller must never treat `unknown` as `gone` and block a generate on it (F1)."""
    out = resolve_cast_liveness(["elara", "cassius"], None)
    assert {v["status"] for v in out.values()} == {LIVENESS_UNKNOWN}
    assert {v["source"] for v in out.values()} == {LIVENESS_SOURCE_NONE}


# ── the cascade ───────────────────────────────────────────────────────────────────────────

def test_the_plan_speaks_only_where_the_GRAPH_is_silent():
    snap = _snap({"entity_id": "elara", "status": "alive"})
    out = resolve_cast_liveness(["elara", "cassius"], snap,
                                plan_status={"elara": "gone", "cassius": "gone"})
    assert out["elara"] == {"status": "alive", "source": LIVENESS_SOURCE_KG}, \
        "a plan status must not override the graph's"
    assert out["cassius"] == {"status": "gone", "source": LIVENESS_SOURCE_PLAN}


def test_a_row_with_NO_status_has_no_opinion_and_does_not_shadow_the_plan():
    """A snapshot row can exist with an empty/absent status — the entity is known to the graph
    but nothing has been asserted about its liveness. Letting that shadow the plan layer would
    turn "the graph mentions them" into "the graph vouches for them"."""
    snap = _snap({"entity_id": "cassius"}, {"entity_id": "elara", "status": ""})
    out = resolve_cast_liveness(["cassius", "elara"], snap,
                                plan_status={"cassius": "gone", "elara": "gone"})
    assert out["cassius"]["source"] == LIVENESS_SOURCE_PLAN
    assert out["elara"]["source"] == LIVENESS_SOURCE_PLAN


def test_a_malformed_row_does_not_crash_the_resolution():
    out = resolve_cast_liveness(["elara"], {"entities": ["not a dict", None,
                                                         {"entity_id": "elara", "status": "gone"}]})
    assert out["elara"]["status"] == "gone"


def test_ids_are_compared_as_strings_so_a_UUID_object_still_matches():
    """asyncpg hands back UUID objects; the snapshot carries strings. A type mismatch here
    would silently make every entity `unknown` — the exact serialization-boundary class this
    repo has already paid for."""
    import uuid
    eid = uuid.uuid4()
    out = resolve_cast_liveness([eid], _snap({"entity_id": str(eid), "status": "gone"}))
    assert out[str(eid)]["status"] == "gone"


# ── the eval signal ───────────────────────────────────────────────────────────────────────

def test_unresolved_refs_counts_only_what_NO_layer_could_speak_to():
    snap = _snap({"entity_id": "elara", "status": "alive"})
    live = resolve_cast_liveness(["elara", "ghost", "phantom"], snap,
                                 plan_status={"phantom": "alive"})
    assert unresolved_cast_refs(live) == ["ghost"]


def test_unresolved_refs_is_a_COUNT_OF_FACTS_not_of_failures():
    """A book early in its life legitimately has a cast the graph has not caught up with. The
    signal must be readable without implying something is broken — otherwise it becomes the
    permanent-amber banner S1 exists to prevent."""
    live = resolve_cast_liveness(["a", "b", "c"], {"entities": []})
    assert unresolved_cast_refs(live) == ["a", "b", "c"]


def test_an_empty_cast_resolves_to_nothing_rather_than_erroring():
    assert resolve_cast_liveness([], _snap({"entity_id": "elara", "status": "alive"})) == {}
    assert unresolved_cast_refs({}) == []
