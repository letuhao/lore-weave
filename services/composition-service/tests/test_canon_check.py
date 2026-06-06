"""A2-S3 — SCORE symbolic canon guard (pure units)."""

from __future__ import annotations

from app.engine.canon_check import (
    EVENT_ORDER_CHAPTER_STRIDE,
    CanonViolation,
    gone_cast_in_draft,
    scene_at_order,
)


def _snap(*entities):
    return {"at_order": 5_000_000, "entities": list(entities)}


def _ent(entity_id, name, status, **extra):
    return {"entity_id": entity_id, "name": name, "canonical_name": name.lower(),
            "status": status, **extra}


# ── scene_at_order ────────────────────────────────────────────────────

def test_scene_at_order_scales_by_stride():
    assert scene_at_order(3) == 3 * EVENT_ORDER_CHAPTER_STRIDE
    assert scene_at_order(0) == 0
    assert scene_at_order(None) is None


# ── gone_cast_in_draft ────────────────────────────────────────────────

def test_flags_gone_entity_present_in_draft():
    snap = _snap(_ent("e-kai", "Kai", "gone", glossary_entity_id="g-kai"))
    out = gone_cast_in_draft("Kai drew his sword and charged.", snap)
    assert len(out) == 1
    assert out[0].entity_id == "e-kai"
    assert out[0].glossary_entity_id == "g-kai"
    assert out[0].status == "gone"
    assert out[0].source == "score_symbolic"
    assert "Kai" in out[0].span


def test_active_entity_not_flagged():
    snap = _snap(_ent("e-bob", "Bob", "active"))
    assert gone_cast_in_draft("Bob walked to town.", snap) == []


def test_gone_entity_absent_from_draft_not_flagged():
    snap = _snap(_ent("e-kai", "Kai", "gone"))
    assert gone_cast_in_draft("Bob walked alone through the empty hall.", snap) == []


def test_ascii_word_boundary_avoids_substring_false_positive():
    # 'Al' (gone) must NOT match inside 'Always'.
    snap = _snap(_ent("e-al", "Al", "gone"))
    assert gone_cast_in_draft("Always the wind blew cold.", snap) == []
    # but a real word-boundary mention IS flagged.
    assert len(gone_cast_in_draft("Al stood in the doorway.", snap)) == 1


def test_cjk_name_substring_match():
    # CJK has no \b word boundary → plain containment.
    snap = _snap(_ent("e-z", "卡斯托", "gone"))
    out = gone_cast_in_draft("城门倒下，卡斯托举起了剑。", snap)
    assert len(out) == 1 and out[0].entity_id == "e-z"


def test_dedup_per_entity():
    snap = _snap(_ent("e-kai", "Kai", "gone"))
    out = gone_cast_in_draft("Kai spoke. Kai laughed. Kai left.", snap)
    assert len(out) == 1  # one violation per entity, not per occurrence


def test_absent_snapshot_degrades_to_empty():
    assert gone_cast_in_draft("Kai acted.", None) == []
    assert gone_cast_in_draft("", _snap(_ent("e", "Kai", "gone"))) == []


def test_canonical_name_match_when_display_name_differs():
    # name 'The Phoenix' absent, canonical 'phoenix' present.
    snap = _snap({"entity_id": "e-p", "name": "The Phoenix",
                  "canonical_name": "phoenix", "status": "gone"})
    out = gone_cast_in_draft("A phoenix rose from the ash.", snap)
    assert len(out) == 1 and out[0].matched == "phoenix"


def test_violation_model_shape():
    v = CanonViolation(entity_id="e1", span="x")
    assert v.kind == "gone_entity_present" and v.confirmed is None
