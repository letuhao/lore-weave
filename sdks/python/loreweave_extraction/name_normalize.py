"""Multi-language entity-name normalization (D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP).

Phase 1 — PURE functions, no I/O, fully deterministic. NOT yet wired into the live
``canonicalize_entity_name`` id derivation (that cutover lands WITH the dedup
migration, Phase 2 — see docs/specs/2026-06-26-multilang-entity-normalization-dedup.md).

Folds *equivalence* (same identity, different encoding/script) so variant spellings
of one entity dedup to a single canonical form, WITHOUT folding *similarity*
(distinct names that merely look close). The folds, in order:

  1. **NFKC** — Unicode compatibility composition: full-width↔half-width (Ｋ→K),
     composed↔decomposed accents (e+◌́ → é), ligatures, compatibility chars.
     Language-agnostic; stdlib.
  2. **casefold** — Unicode-correct lowercasing for every script (ß→ss, İ→i̇),
     stronger + more correct than ``str.lower()``.
  3. **Han simplified fold** — traditional→simplified per the vendored frozen table
     (張→张), so CJK simplified/traditional variants of a name collapse. Gated on the
     presence of any Han character (cheap no-op for non-CJK text).

Deliberately NOT done: diacritic/accent stripping — it would over-merge distinct
names (vi ``ma``≠``má``; ``Müller``≠``Muller``). Accents are preserved.
"""

from __future__ import annotations

import unicodedata

from ._han_simplified_table import T2S

__all__ = [
    "nfkc_casefold",
    "fold_han_simplified",
    "normalize_entity_name",
    "has_han",
]

# Han (CJK ideograph) blocks — used only as a cheap GATE so the simplified fold is
# skipped entirely for non-CJK text (the common case). Covers the main + extension-A
# + compatibility ideograph ranges that real entity names land in.
_HAN_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),   # CJK Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF), # CJK Extension B
)


def has_han(s: str) -> bool:
    """True if *s* contains any Han ideograph (the simplified-fold gate)."""
    for ch in s:
        cp = ord(ch)
        for lo, hi in _HAN_RANGES:
            if lo <= cp <= hi:
                return True
    return False


def nfkc_casefold(s: str) -> str:
    """NFKC-normalize then Unicode-casefold. Language-agnostic; idempotent."""
    return unicodedata.normalize("NFKC", s).casefold()


def fold_han_simplified(s: str) -> str:
    """Map each traditional Han char to its simplified form (vendored table).

    No-op when *s* has no Han character (cheap guard) and for any character absent
    from the curated table (Phase-1 incompleteness → a residual duplicate, never a
    wrong fold). Non-Han characters always pass through unchanged.
    """
    if not has_han(s):
        return s
    return "".join(T2S.get(ch, ch) for ch in s)


def normalize_entity_name(name: str) -> str:
    """Phase-1 v2 entity-name normalizer (multi-language).

    Pipeline: NFKC + casefold → Han simplified fold → (the caller's existing
    honorific / whitespace / punctuation steps still apply on top in
    ``canonicalize_entity_name`` once Phase 2 wires this in). On its own this
    function returns the script-folded, case-folded, NFKC form — the equivalence
    key two variants of the same name share.
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be str, got {type(name).__name__}")
    return fold_han_simplified(nfkc_casefold(name))
