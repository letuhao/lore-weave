"""W3a — MEASURE `select_known_entities` at book scale before optimizing it.

The production docstring says "fine for the low thousands; a book in the tens
of thousands wants a trie / Aho-Corasick pass". That was reasoning, not a
measurement. This module turns it into a number, and pins the behaviour a
faster implementation would have to reproduce exactly.

Corpus: 20,000 real entities / ~34,900 real surface forms (see corpus.py).
"""

from __future__ import annotations

import time

import pytest

from app.runner import CanonIndex, _mentions, select_known_entities
from tests.corpus import canon, load_corpus, surface_forms, synth_chapter


def reference_select(
    pinned: list[str],
    canon_rows: list[tuple[str, list[str]]],
    chunk_text: str,
    *,
    cap: int,
) -> tuple[list[str], int]:
    """The PRE-W3b implementation, verbatim, kept here as the differential oracle.

    It lives in the test rather than in production because production must carry one
    matcher, not two — but "the fast one behaves like the slow one" is only a claim
    until something actually runs both. This is that something.
    """
    if cap <= 0:
        return [], len(pinned) + len(canon_rows)
    out = list(pinned[:cap])
    seen = {n.casefold() for n in out}
    dropped = max(0, len(pinned) - cap)
    for name, aliases in canon_rows:
        if name.casefold() in seen:
            continue
        if not any(_mentions(chunk_text, s) for s in (name, *aliases)):
            continue
        if len(out) >= cap:
            dropped += 1
            continue
        seen.add(name.casefold())
        out.append(name)
    return out, dropped


def test_corpus_has_the_properties_the_matcher_is_judged_on():
    """Guard the FIXTURE. A corpus silently regenerated into something tame
    would make every test below pass while proving nothing."""
    rows = load_corpus()
    assert len(rows) == 20_000, len(rows)

    forms = set(surface_forms())
    assert len(forms) > 30_000, len(forms)

    cjk = [n for n, _ in rows if any("一" <= c <= "鿿" for c in n)]
    assert len(cjk) > 4_000, f"CJK names: {len(cjk)}"

    # Nesting is the property a naive matcher gets wrong. Substring containment
    # over 35k forms is O(n^2); sample enough to prove presence, not count all.
    sample = sorted(forms)[:4_000]
    nested = sum(1 for s in sample if any(s != t and s in t for t in sample))
    assert nested > 50, f"nested forms in sample: {nested}"


def test_selection_finds_planted_mentions_including_via_alias():
    """Recall floor: every planted entity is selected, and via its ALIAS —
    the path a real chapter takes ('Thiếu chủ', not 'Lâm Uyên')."""
    corpus = canon()
    text, expected = synth_chapter(corpus, mentions=60)

    names, dropped = select_known_entities([], CanonIndex.build(corpus), text, cap=500)

    missing = expected - set(names)
    assert not missing, f"{len(missing)} planted entities not selected: {sorted(missing)[:10]}"
    assert dropped == 0


def test_pinned_names_survive_and_lead():
    corpus = canon()
    text, _ = synth_chapter(corpus, mentions=20)
    names, _ = select_known_entities(
        ["Lâm Uyên", "Tô gia"], CanonIndex.build(corpus), text, cap=500)
    assert names[:2] == ["Lâm Uyên", "Tô gia"]


def test_cap_truncates_and_reports_the_drop():
    corpus = canon()
    text, expected = synth_chapter(corpus, mentions=60)
    names, dropped = select_known_entities([], CanonIndex.build(corpus), text, cap=10)
    assert len(names) == 10
    assert dropped == len(expected) - 10


def test_new_matcher_matches_the_regex_over_the_whole_corpus():
    """THE differential proof. Same 20k corpus, same prose, both implementations —
    identical output, order included. Without this, "behaviour is unchanged" is a
    comment, and a matcher that quietly drops or invents a match would ship green.

    Split deliberately: the ORACLE costs ~10s per call at 20k entities, so the full
    corpus runs once (breadth of surface forms) and the cap/pin matrix runs over a
    slice (breadth of control flow). Running the whole matrix at 20k would take four
    minutes, and a four-minute test is a test that gets marked slow and then skipped."""
    full = canon()
    text, _ = synth_chapter(full, mentions=60, seed=1060)
    assert select_known_entities([], CanonIndex.build(full), text, cap=150) == \
        reference_select([], full, text, cap=150), "divergence on the full 20k corpus"

    slice_ = canon(limit=3_000)
    index = CanonIndex.build(slice_)
    for mentions in (5, 60, 200):
        text, _ = synth_chapter(slice_, mentions=mentions, seed=1000 + mentions)
        for cap in (0, 10, 150, 5_000):
            for pinned in ([], ["Lâm Uyên", "Tô gia"]):
                assert select_known_entities(pinned, index, text, cap=cap) == \
                    reference_select(pinned, slice_, text, cap=cap), (
                        f"divergence at mentions={mentions} cap={cap} "
                        f"pinned={len(pinned)}"
                    )


def test_matching_cost_is_bounded_by_the_PROSE_not_the_glossary(capsys):
    """W3a/W3b. The old matcher ran one regex per surface form per chunk, so its cost
    scaled with the GLOSSARY: 10.2s for a single 8k-char chunk at 20k entities — and
    synchronously, on the async worker's event loop.

    This asserts the SHAPE, not a wall-clock target (a CI box is not a benchmark rig):
    quadrupling the glossary while holding the prose fixed must not come close to
    quadrupling the per-chunk cost. A regression to per-form scanning fails here."""
    corpus = canon()
    text, _ = synth_chapter(corpus, mentions=60)

    def per_chunk(rows):
        index = CanonIndex.build(rows)  # once per JOB — excluded from the measurement
        t0 = time.perf_counter()
        for _ in range(5):
            select_known_entities([], index, text, cap=150)
        return (time.perf_counter() - t0) / 5

    small = per_chunk(corpus[:5_000])
    full = per_chunk(corpus)

    forms = sum(1 + len(a) for _, a in corpus)
    with capsys.disabled():
        print(
            f"\n  [W3b] {len(corpus):,} entities / {forms:,} surface forms "
            f"vs {len(text):,} chars -> {full * 1000:.1f} ms per chunk "
            f"(5k entities: {small * 1000:.1f} ms) — regex baseline was 10,158 ms"
        )
    assert full < 1.0, f"per-chunk cost regressed to {full:.3f}s"
    # 4x the glossary for well under 2x the cost: the corpus is no longer the driver.
    assert full < small * 2, f"cost tracks glossary size: {small:.4f}s -> {full:.4f}s"


class TestCjkBoundary:
    """The prediction I recorded before looking: `_BOUNDARY_L/R` are ASCII-only,
    so for CJK they assert nothing and a short name matches INSIDE a longer word.
    These tests state the real behaviour either way — they are not written to pass."""

    def test_cjk_name_matches_inside_a_longer_word(self):
        # 林 (a surname) inside 森林 ("forest") — unrelated word, same characters.
        assert _mentions("他走进森林深处。", "林") is True

    def test_latin_name_does_not_match_inside_a_longer_word(self):
        assert _mentions("She joined the Landing party.", "Lan") is False

    def test_cjk_false_positive_reaches_selection(self):
        index = CanonIndex.build([("林", []), ("云龙山", [])])
        names, _ = select_known_entities([], index, "他走进森林深处。", cap=50)
        assert names == ["林"], (
            "documents the CJK substring false-positive: 林 is selected from 森林"
        )
