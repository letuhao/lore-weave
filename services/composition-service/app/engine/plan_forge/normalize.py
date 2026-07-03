"""D-PF-NORMALIZE — deterministic post-materialize / post-refine fixes."""

from __future__ import annotations

import re
from typing import Any

_ALWAYS_BLOCK_NAMES = frozenset({"Female Protagonist"})
_TBD_PLACEHOLDER_NAMES = frozenset({"[TBD]", "Untitled Project (TBD)"})
_YIN_YANG_NAME_HINTS = ("âm dương hợp hoan", "hợp hoan", "yin yang", "yin_yang")


def _open_questions_name_tbd(spec: dict[str, Any]) -> bool:
    for q in spec.get("meta", {}).get("open_questions") or []:
        ql = q.lower()
        if "tên" in ql or "name" in ql or "tbd" in ql:
            return True
    return False


def _vn_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    vn = len(re.findall(r"[\u00C0-\u1EF9]", text))
    return vn / max(len(text), 1)


def _is_yin_yang_mechanic(mech: dict[str, Any]) -> bool:
    blob = f"{mech.get('id', '')} {mech.get('name', '')}".lower()
    return any(hint in blob for hint in _YIN_YANG_NAME_HINTS)


def post_normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic normalizations after rules/LLM materialize or refine."""
    name_tbd = _open_questions_name_tbd(spec)
    for char in spec.get("layers", {}).get("characters") or []:
        name = char.get("name") or ""
        if name in _ALWAYS_BLOCK_NAMES:
            char["name"] = "Nữ chính"
        elif (
            name_tbd
            and char.get("role") == "protagonist"
            and name in _TBD_PLACEHOLDER_NAMES
        ):
            char["name"] = "Nữ chính"

    for mech in spec.get("layers", {}).get("mechanics") or []:
        rules = mech.get("rules") or []
        if not rules:
            continue
        joined = " ".join(str(r) for r in rules)
        if _vn_char_ratio(joined) < 0.15 and _is_yin_yang_mechanic(mech):
            mech["rules"] = [
                "Âm Dương Hợp Hoan: hấp thụ linh khí qua đối tác; cường độ tỷ lệ thân mật",
                "Không gắn với cảnh giới tu luyện — chỉ theo trải nghiệm và biến số PA/HA",
            ]

    return spec
