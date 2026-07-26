"""T1 / L1-L2 — motif + arc reference-first contract (spec §6b, §14b).

The kit proves `apply_response_contract` generically (loreweave_mcp test_kit). This
pins the composition-SPECIFIC motif/arc contracts: the ref-field sets must DROP the
heavy structural lists (roles/beats/preconditions/effects for a motif;
threads/layout/pacing/arc_roster for an arc) at detail=summary and KEEP the ≤1-line
`summary` + the concurrency token (`version`) + the fields the model needs to pick a
pattern. If someone re-adds a heavy list to the refs, this goes red.

Mirrors test_outline_response_contract.py.
"""

from uuid import uuid4

from loreweave_mcp import apply_response_contract

from app.db.models import ArcTemplate, Motif
from app.mcp.server import (
    _ARC_REF_FIELDS,
    _MOTIF_BOOK_REF_FIELDS,
    _MOTIF_REF_FIELDS,
)

# The heavy structural lists a summary must never carry.
_MOTIF_HEAVY = ("roles", "beats", "preconditions", "effects", "examples")
_ARC_HEAVY = ("threads", "layout", "pacing", "arc_roster")


def _motif(**over) -> dict:
    base = dict(
        id=uuid4(), owner_user_id=uuid4(), code="cultivation.face_slap",
        name="Face Slap", language="en", visibility="private", kind="sequence",
        summary="humiliate the arrogant", genre_tags=["xianxia"],
        roles=[{"id": "r1", "name": "protagonist"}] * 4,
        beats=[{"id": "b1", "text": "x" * 200}] * 6,
        preconditions=[{"id": "p1", "text": "y" * 200}] * 3,
        effects=[{"id": "e1", "text": "z" * 200}] * 3,
        examples=[{"id": "ex1", "text": "w" * 500}] * 2,
        status="active", version=4,
    )
    base.update(over)
    return Motif(**base).model_dump(mode="json")


def _arc(**over) -> dict:
    base = dict(
        id=uuid4(), owner_user_id=uuid4(), code="revenge.rise", name="Rise to Power",
        language="en", visibility="private", summary="fall then climb",
        genre_tags=["xianxia"], chapter_span=30,
        threads=[{"id": "t1", "name": "revenge"}] * 4,
        layout=[{"motif_code": "m1", "span_start": 1, "span_end": 5}] * 8,
        pacing=[{"chapter": i, "tension": 5} for i in range(10)],
        arc_roster=[{"role": "villain", "name": "x" * 200}] * 4,
        status="active", version=3,
    )
    base.update(over)
    return ArcTemplate(**base).model_dump(mode="json")


class TestMotifRefFields:
    def test_heavy_lists_dropped_at_summary(self):
        out, meta = apply_response_contract([_motif()], ref_fields=_MOTIF_REF_FIELDS, detail="summary")
        for heavy in _MOTIF_HEAVY:
            assert heavy not in out[0], f"summary must drop {heavy}"
        assert meta["detail"] == "summary"

    def test_ref_fields_kept_at_summary(self):
        out, _ = apply_response_contract([_motif()], ref_fields=_MOTIF_REF_FIELDS, detail="summary")
        for required in ("id", "code", "name", "kind", "summary", "status", "version"):
            assert required in out[0], f"summary ref must keep {required}"

    def test_full_detail_keeps_heavy(self):
        out, _ = apply_response_contract([_motif()], ref_fields=_MOTIF_REF_FIELDS, detail="full")
        assert out[0]["roles"] and out[0]["beats"]

    def test_summary_is_materially_smaller(self):
        rows = [_motif() for _ in range(12)]
        summ, _ = apply_response_contract(rows, ref_fields=_MOTIF_REF_FIELDS, detail="summary")
        full, _ = apply_response_contract(rows, ref_fields=_MOTIF_REF_FIELDS, detail="full")
        assert len(str(summ)) < len(str(full)) * 0.4

    def test_ref_fields_never_include_heavy(self):
        # Belt-and-suspenders: the constants themselves must not name a heavy list.
        for heavy in _MOTIF_HEAVY:
            assert heavy not in _MOTIF_REF_FIELDS
            assert heavy not in _MOTIF_BOOK_REF_FIELDS


class TestMotifBookRefFields:
    def test_book_badges_kept_at_summary(self):
        # The book-library summary must still tell the model which rows are shared-tier.
        row = _motif(book_id=uuid4(), book_shared=True)
        out, _ = apply_response_contract([row], ref_fields=_MOTIF_BOOK_REF_FIELDS, detail="summary")
        assert out[0]["book_shared"] is True
        assert "book_id" in out[0]
        for heavy in _MOTIF_HEAVY:
            assert heavy not in out[0]


class TestArcRefFields:
    def test_heavy_lists_dropped_at_summary(self):
        out, meta = apply_response_contract([_arc()], ref_fields=_ARC_REF_FIELDS, detail="summary")
        for heavy in _ARC_HEAVY:
            assert heavy not in out[0], f"summary must drop {heavy}"
        assert meta["detail"] == "summary"

    def test_ref_fields_kept_at_summary(self):
        out, _ = apply_response_contract([_arc()], ref_fields=_ARC_REF_FIELDS, detail="summary")
        for required in ("id", "code", "name", "summary", "chapter_span", "status", "version"):
            assert required in out[0], f"summary ref must keep {required}"

    def test_full_detail_keeps_heavy(self):
        out, _ = apply_response_contract([_arc()], ref_fields=_ARC_REF_FIELDS, detail="full")
        assert out[0]["threads"] and out[0]["layout"]

    def test_ref_fields_never_include_heavy(self):
        for heavy in _ARC_HEAVY:
            assert heavy not in _ARC_REF_FIELDS
