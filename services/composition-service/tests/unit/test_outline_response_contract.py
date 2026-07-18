"""T1 / L1-L2 — composition_list_outline reference-first contract (spec §6b, §14b).

The kit proves `apply_response_contract` generically (loreweave_mcp test_kit). This
pins the composition-SPECIFIC contract: the outline ref-field set must drop the
heavy prose (`goal`/`synopsis` — the 146K-case bloat) at detail=summary and keep
the concurrency token (`version`) + the structural fields needed to navigate the
tree. If someone re-adds a prose field to the refs, this goes red.
"""

from uuid import uuid4

from loreweave_mcp import apply_response_contract

from app.db.models import OutlineNode
from app.mcp.server import _OUTLINE_REF_FIELDS


def _node(**over) -> dict:
    base = dict(
        id=uuid4(), created_by=uuid4(), project_id=uuid4(), book_id=uuid4(), parent_id=None,
        kind="scene", rank="a0", title="A scene", goal="do the thing",
        status="drafting", synopsis="x" * 500, version=4, story_order=1,
    )
    base.update(over)
    return OutlineNode.model_validate(base).model_dump(mode="json")


class TestOutlineRefFields:
    def test_heavy_prose_dropped_at_summary(self):
        rows = [_node()]
        out, meta = apply_response_contract(rows, ref_fields=_OUTLINE_REF_FIELDS, detail="summary")
        assert "synopsis" not in out[0]
        assert "goal" not in out[0]
        assert meta["detail"] == "summary"

    def test_concurrency_token_and_structure_kept_at_summary(self):
        out, _ = apply_response_contract([_node()], ref_fields=_OUTLINE_REF_FIELDS, detail="summary")
        for required in ("id", "kind", "title", "status", "version", "parent_id", "story_order"):
            assert required in out[0], f"summary ref must keep {required}"

    def test_full_detail_keeps_prose(self):
        out, _ = apply_response_contract([_node()], ref_fields=_OUTLINE_REF_FIELDS, detail="full")
        assert out[0]["synopsis"]
        assert out[0]["goal"]

    def test_summary_is_materially_smaller(self):
        rows = [_node() for _ in range(12)]
        summ, _ = apply_response_contract(rows, ref_fields=_OUTLINE_REF_FIELDS, detail="summary")
        full, _ = apply_response_contract(rows, ref_fields=_OUTLINE_REF_FIELDS, detail="full")
        assert len(str(summ)) < len(str(full)) * 0.4

    def test_ref_fields_never_include_prose(self):
        # Belt-and-suspenders: the constant itself must not name a prose field.
        assert "synopsis" not in _OUTLINE_REF_FIELDS
        assert "goal" not in _OUTLINE_REF_FIELDS
