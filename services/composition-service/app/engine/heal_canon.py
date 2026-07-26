"""Render a self-heal CANON (story bible) from the planning pipeline's designed cast.

The cheap-stack self-heal (`engine/self_heal.py`) is far more accurate when GROUNDED in a
story bible (convention + per-character canon) — it catches xưng-hô / canon errors and
stops confabulating. This module builds that bible from the SAME cast the planning
pipeline designed (and drafting grounded on), so heal needs no hand-written bible for any
book: `render_canon` from the persisted cast attributes + a genre/address `convention`.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

# The Vietnamese xianxia (tiên hiệp) address/honorific convention — the genre-knowledge half
# of the bible that the per-character cast attributes don't carry. Selected by `convention_for`.
DEFAULT_VI_TIENHIEP_CONVENTION = (
    "THỂ LOẠI: Tiên hiệp — trọng tu luyện/chiến đấu, văn phong cổ trang.\n\n"
    "QUY ƯỚC XƯNG HÔ (tiên hiệp):\n"
    "- Ngôi kể dùng: hắn / y / nàng / lão / thị / người nọ. TUYỆT ĐỐI KHÔNG dùng đại từ HIỆN ĐẠI "
    'làm ngôi kể: "ông", "bà", "ông ta", "bà ta", "cô ấy", "anh ấy".\n'
    '- Con nói với cha mẹ tự xưng "hài nhi" / "nữ nhi", KHÔNG tự gọi mình bằng tên riêng.\n'
    '- Người đang TRỰC TIẾP nói không được tự xưng ngôi ba (mẫu thân nói "lệnh của mẫu thân ngươi" '
    'là SAI, phải là "lệnh của ta").\n'
    "- Xưng hô tu tiên: gia chủ, trưởng lão, công tử, tiểu thư, đạo hữu, tiền bối, tông chủ. "
    'TRÁNH cách gọi hiện đại ("ông Lâm", "bà Tô").\n'
    # A NEGATIVE example — so a verifier/judge doesn't confab these valid pronouns into "errors"
    # (the 'lão → Y' false-positive the smart-judge POC caught).
    "- HỢP LỆ (KHÔNG phải lỗi): hắn / y (nam), nàng / thị (nữ), lão (bậc cao niên), người nọ."
)

_TIENHIEP_TAGS = frozenset({
    "tiên hiệp", "tien hiep", "xianxia", "xuanhuan", "cultivation", "tu tiên", "tu tien", "wuxia",
})


def convention_for(genre_tags: Sequence[str] | None, source_language: str = "auto") -> str:
    """Pick a genre/language address convention for the heal canon. Vietnamese or an
    explicitly xianxia genre → the tiên-hiệp block; otherwise "" (the per-character canon
    still grounds heal — only the address-convention axis is genre-specific)."""
    tags = {t.strip().lower() for t in (genre_tags or [])}
    if source_language == "vi" or (tags & _TIENHIEP_TAGS):
        return DEFAULT_VI_TIENHIEP_CONVENTION
    return ""


def render_canon(cast: Sequence[Mapping], *, convention: str = "") -> str:
    """Build a self-heal STORY BIBLE from the designed cast (the same attributes persisted
    to the glossary: `name` + `role`/`personality`/`relationships`/`description`) plus an
    optional genre/address `convention`. Empty cast + empty convention → "" (heal stays
    ungrounded ⇒ legacy behavior).

    TERSE by design — one line per character (role + the key `description` fact, + a short
    relationship). The POC found a verbose bible BURIED the convention rule a verifier needed
    (it refuted 'mẫu thân ngươi' when the rule was drowned; confirmed it when surfaced), so we
    keep the per-character noise low and let the convention rules stand out."""
    lines: list[str] = []
    for c in cast:
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        role = str(c.get("role", "")).strip()
        head = f"- {name}" + (f" ({role})" if role else "") + ":"
        parts: list[str] = []
        if (desc := str(c.get("description", "")).strip()):
            parts.append(desc)
        if (rel := str(c.get("relationships", "")).strip()):   # vai-vế matters; personality dropped (bloat)
            parts.append("Quan hệ: " + rel)
        lines.append(head + " " + " · ".join(parts) if parts else head)
    body = ("CANON NHÂN VẬT (chỉ nêu sự thật cốt lõi):\n" + "\n".join(lines)) if lines else ""
    return "\n\n".join(b for b in (convention.strip(), body) if b)


def canon_from_proposed(cast_objs: Sequence, *, convention: str = "") -> str:
    """Render canon straight from `propose_cast`'s `ProposedChar` objects (in-pipeline use):
    maps each via `cast_attributes` so the bible carries the same DEPTH that was seeded to
    the glossary."""
    from app.engine.cast_plan import cast_attributes
    return render_canon(
        [{**cast_attributes(c), "name": c.name} for c in cast_objs], convention=convention)
