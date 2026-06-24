"""KG-ML M5 (C5 / DD7) — predicate (relation edge) localization.

Predicates are an OPEN vocabulary: the seed graph schema defines common edge
types (``ALLY_OF``, ``KILLED``, …) but extraction can emit any snake_case
predicate. So there is no exhaustive table — labels resolve as:

    curated map[code][language]  →  else  humanize(code)   (the snake→words fallback)

The curated map carries translations only for languages where the humanized
English code isn't already the answer (English needs no curation — ``humanize``
reproduces the seed labels: ``ALLY_OF`` → "ally of"). Unknown / open-vocab
predicates always degrade gracefully to ``humanize`` rather than a raw code.
"""
from __future__ import annotations

import re

__all__ = [
    "PREDICATE_LABELS",
    "humanize_predicate",
    "resolve_predicate_label",
    "predicate_catalog",
]

# Curated labels keyed by the normalized UPPER_SNAKE predicate code → {language:
# label}. Covers the seed_graph_schemas edge types (the common KG predicates).
# English is intentionally absent — humanize() yields the seed English label.
PREDICATE_LABELS: dict[str, dict[str, str]] = {
    "MASTER_OF": {"vi": "sư phụ của"},
    "DISCIPLE_OF": {"vi": "đệ tử của"},
    "FAMILY_OF": {"vi": "người thân của"},
    "LOVER_OF": {"vi": "người yêu của"},
    "BETROTHED_TO": {"vi": "đính hôn với"},
    "DAO_COMPANION_OF": {"vi": "đạo lữ của"},
    "RIVAL_OF": {"vi": "đối thủ của"},
    "ENEMY_OF": {"vi": "kẻ thù của"},
    "ALLY_OF": {"vi": "đồng minh của"},
    "KILLED": {"vi": "đã giết"},
    "BETRAYED": {"vi": "đã phản bội"},
    "SAVED": {"vi": "đã cứu"},
    "MEMBER_OF": {"vi": "thành viên của"},
    "COMPREHENDS": {"vi": "lĩnh ngộ"},
    "PRACTICES": {"vi": "tu luyện"},
    "WIELDS": {"vi": "sử dụng"},
    "PARTICIPATED_IN": {"vi": "tham gia"},
    "FROM": {"vi": "đến từ"},
    "PURSUES": {"vi": "theo đuổi"},
    "SUBORDINATE_OF": {"vi": "cấp dưới của"},
    "ALLIED_WITH": {"vi": "liên minh với"},
    "AT_WAR_WITH": {"vi": "giao chiến với"},
    "PART_OF": {"vi": "một phần của"},
    "INVOLVES": {"vi": "liên quan đến"},
}


def humanize_predicate(code: str) -> str:
    """``ALLY_OF`` / ``ally_of`` / ``ally-of`` → "ally of" — the language-neutral
    (English) fallback for any predicate, curated or not."""
    return re.sub(r"[_\-]+", " ", str(code or "").strip()).strip().lower()


def _norm(code: str) -> str:
    """Normalize a predicate code to the curated-map key (UPPER_SNAKE)."""
    return re.sub(r"[_\-]+", "_", str(code or "").strip()).upper()


def _primary(language: str | None) -> str:
    """ISO-639-1 primary subtag, lowercased (``zh-Hant`` → ``zh``)."""
    return re.split(r"[-_]", str(language or "").strip().lower(), maxsplit=1)[0]


def resolve_predicate_label(code: str, language: str | None) -> str:
    """Localized label for one predicate. Curated ``[code][language]`` when
    present, else ``humanize(code)`` (covers English + every uncurated language +
    open-vocab predicates)."""
    lang = _primary(language)
    entry = PREDICATE_LABELS.get(_norm(code))
    if entry and lang and lang in entry:
        return entry[lang]
    return humanize_predicate(code)


def predicate_catalog(language: str | None) -> dict[str, str]:
    """The full curated catalog resolved for one language: ``{code: label}``.
    A client can preload this and humanize any open-vocab predicate it later
    meets that isn't in the catalog."""
    return {code: resolve_predicate_label(code, language) for code in PREDICATE_LABELS}
