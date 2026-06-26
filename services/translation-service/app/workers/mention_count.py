"""Per-chapter mention frequency counting (M7 / D-T5.2-WINDOWED-MENTIONS).

Counts how many times an entity is *mentioned* in a chunk of prose, by its canonical
name and its alias surface forms, with a **CJK-aware longest-match + span-dedup** scan
(NOT a space tokenizer — CJK prose has no word spaces, so `/\\s+|\\S+/`-style tokenizing
degrades badly; see lesson `feedback_space_tokenizer_degrades_on_cjk`).

Design:
  * **Surface forms** = the canonical display name + every alias. Per CLARIFY the
    per-chapter *breakdown* (which alias appeared) is OUT of scope — we sum all forms
    into ONE count for the entity.
  * **Longest-match** — forms are tried longest-first at each position so "Harker"
    inside "Jonathan Harker" is counted ONCE (the long form), not twice. After a match
    the cursor jumps past the whole matched span (**span-dedup**), so overlapping forms
    can't double-count the same characters.
  * **Fold-insensitive** — both the text and the forms are normalized with the shared
    `loreweave_extraction` fold (NFKC + Unicode casefold + Han simplified→traditional
    equivalence) so 張若塵/张若尘, full-width Ｋａｉ/Kai and casing all match. This is the
    SAME fold the resolver/dedup key uses, so a name that dedups to one entity also
    counts as one surface form.
  * **Presence-gating is the caller's job** — this function counts within whatever text
    it is given. The producer only calls it for chapters the entity is LINKED to, so a
    raw match in an unlinked chapter (possibly a homonym) is never counted.

Counting happens in the *folded* string space. The fold is (near) length-stable for the
CJK + Latin entity names this targets (Han chars are single code points; casefold/NFKC
only rarely change length, e.g. ﬁ→fi), and we only need COUNTS here — not offsets back
into the original text — so folded-space scanning is sound.
"""
from __future__ import annotations

from collections.abc import Iterable

from loreweave_extraction.name_normalize import fold_han_simplified, nfkc_casefold


def _fold(s: str) -> str:
    """The shared equivalence fold: NFKC + casefold + Han simplified."""
    return fold_han_simplified(nfkc_casefold(s))


def build_surface_forms(name: str, aliases: Iterable[str] | None) -> list[str]:
    """Return the deduped, folded, longest-first surface forms for an entity.

    Empty / whitespace-only forms are dropped. Duplicates that collapse under the fold
    (e.g. an alias equal to the casefolded name) are removed so they count as one form.
    Sorted longest-first so the scanner prefers the longest match at each position.
    """
    forms: list[str] = []
    seen: set[str] = set()
    for raw in (name, *(aliases or [])):
        if not raw or not isinstance(raw, str):
            continue
        folded = _fold(raw).strip()
        if not folded or folded in seen:
            continue
        seen.add(folded)
        forms.append(folded)
    forms.sort(key=len, reverse=True)
    return forms


def count_surface_form_mentions(text: str, forms: list[str]) -> int:
    """Count non-overlapping longest-match occurrences of any of `forms` in `text`.

    `forms` MUST already be folded + longest-first (use `build_surface_forms`). `text`
    is folded here. A single linear scan with a cursor that jumps past each matched span
    gives longest-match + span-dedup in one pass.
    """
    if not text or not forms:
        return 0
    folded_text = _fold(text)
    n = len(folded_text)
    count = 0
    i = 0
    while i < n:
        matched_len = 0
        for form in forms:  # longest-first → first match at i is the longest
            fl = len(form)
            if fl == 0 or i + fl > n:
                continue
            if folded_text[i : i + fl] == form:
                matched_len = fl
                break
        if matched_len:
            count += 1
            i += matched_len  # span-dedup: skip the whole matched span
        else:
            i += 1
    return count


def count_entity_mentions(text: str, name: str, aliases: Iterable[str] | None) -> int:
    """Convenience: build surface forms for an entity and count its mentions in `text`.

    The single entry point the producer uses per (entity, window/chapter)."""
    forms = build_surface_forms(name, aliases)
    return count_surface_form_mentions(text, forms)
