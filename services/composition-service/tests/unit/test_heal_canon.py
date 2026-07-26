"""Unit tests for engine/heal_canon.py — rendering a self-heal STORY BIBLE from the
planning pipeline's designed cast (so heal needs no hand-written bible for any book)."""

from app.engine.cast_plan import ProposedChar
from app.engine.heal_canon import (
    DEFAULT_VI_TIENHIEP_CONVENTION,
    canon_from_proposed,
    convention_for,
    render_canon,
)


def test_render_canon_builds_bible_from_cast():
    cast = [{
        "name": "Tô Yến", "role": "antagonist",
        "personality": "Thủ đoạn; Khắt khe",
        "relationships": "mẫu thân của Lâm Uyển",
        "description": "luôn khinh miệt đứa con gái phế vật",
    }]
    out = render_canon(cast, convention="CONV-BLOCK")
    assert "CONV-BLOCK" in out
    assert "CANON NHÂN VẬT" in out
    assert "Tô Yến (antagonist):" in out
    assert "luôn khinh miệt đứa con gái phế vật" in out          # description (the key fact)
    assert "Quan hệ: mẫu thân của Lâm Uyển" in out               # relationship (vai-vế)
    assert "Tính cách" not in out                                # personality dropped (terse — anti-burial)


def test_render_canon_empty_yields_empty():
    assert render_canon([], convention="") == ""
    assert render_canon([{"name": ""}], convention="") == ""


def test_render_canon_skips_blank_fields():
    out = render_canon([{"name": "X"}], convention="")
    assert out.strip() == "CANON NHÂN VẬT (chỉ nêu sự thật cốt lõi):\n- X:"


def test_convention_for_selects_tienhiep_for_vi_or_genre():
    assert convention_for(["tiên hiệp"], "auto") == DEFAULT_VI_TIENHIEP_CONVENTION
    assert convention_for(["xianxia"], "en") == DEFAULT_VI_TIENHIEP_CONVENTION
    assert convention_for([], "vi") == DEFAULT_VI_TIENHIEP_CONVENTION
    assert convention_for(["fantasy"], "en") == ""
    assert convention_for(None, "auto") == ""


def test_canon_from_proposed_maps_attributes():
    c = ProposedChar(
        name="Lâm Uyển", role="protagonist", traits=["Kiên cường"],
        archetype="nghịch thiên", relationships="đích nữ Lâm gia",
        summary="phế vật thành ma tu")
    out = canon_from_proposed([c], convention=DEFAULT_VI_TIENHIEP_CONVENTION)
    assert "QUY ƯỚC XƯNG HÔ" in out                       # convention block present
    assert "Lâm Uyển (protagonist):" in out
    assert "phế vật thành ma tu" in out                   # summary → description (the key fact)
    assert "đích nữ Lâm gia" in out                       # relationships (vai-vế)
    assert "Kiên cường" not in out                        # personality dropped (terse render)
